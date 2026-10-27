"""Run every reference case through the solver (CLAUDE.md D6, design §9).

Pass criteria (D6): flows, heads and pressures within 0.5 % of the reference, or the absolute
floor, whichever is looser: 1e-9 m³/s for flows (the solver's flow tolerance scale), 0.01 m for
EGL, ρ·g·0.01 m for pressures. Mass balance must close at every non-boundary component, checked
here from the link results alone, independently of the solver's own residual report: its net
inflow is zero, or an assigned-flow node's flow (SDD §4.11).

An EGL tolerance of 0.5 % of the head itself depends on the datum and can exceed a connection's
loss, so the head loss of every connection whose two ports have expected EGLs is also checked,
EGL(from) − EGL(to) within 0.5 % of the expected difference or 0.01 m (still D6, datum-free).

Cases may also expect (design §12): flags (each must be present, matched on code and on
componentId / connectionId when given; warning and invalid flags are exhaustive, info flags
may appear unlisted), the state of every valve and
status of every pump, pump operating flow and head and NPSH available / required / margin (heads:
0.5 % or 0.01 m; flows: 0.5 % or the flow floor), the vapor pressure (a property lookup, or
null when the source has none) and the atmospheric pressure used. A speed-controlled pump
(CLAUDE.md D11) also has its control state, matched exactly, and its speed: within 0.5 % of
the reference, and the head that speed implies at the reference flow, F(s, Q_ref) =
s² H₀(Q_ref/s) with H₀ the case curve's PCHIP (``element_laws.pump_head``), within 0.01 m of
the reference head (owner's answer Q6, proposal vfd-pump-modes.md §7). A case that expects a Crane
K held across a correlation step (``stepHolds``) also checks the two splits the solver reports
holding between (its flag's details) against the derived pair, to SPLIT_TOLERANCE. An equipment
item (docs/proposals/equipment-pressure-drop.md §2.2) has its ``equipmentResults`` entry: flow
and flow ratio (0.5 % or the flow floor; the ratio null exactly when the rating is a Cv or Kv),
head loss (0.5 % or 0.01 m), pressure loss and static pressure drop (0.5 % or ρ·g·0.01 m), and
the rating it echoes equal to the project's (no scenario here).
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from opensolve_pipe.models.components import AssignedFlow, Equipment, Pump
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from tests.reference.case_format import case_files, read_case
from tests.reference.derivations import G
from tests.reference.element_laws import pump_head

RELATIVE = 0.005
FLOW_FLOOR = 1.0e-9  # m³/s
HEAD_FLOOR = 0.01  # m
PROPERTY_RELATIVE = 1.0e-6  # fluid properties are inputs or CoolProp lookups, not iterated
MASS_BALANCE_RELATIVE = 1.0e-9  # of the largest flow
SPLIT_TOLERANCE = 1.0e-6
"""Absolute, in the flow split q, for the splits of a step hold: the derived pair is the settled
2-cycle of the outer update (``derivations_branches.derive_step_hold``), which the solver
reaches to about 1e-8 before it holds; a hold taken at another pair (an earlier alternation)
would differ by orders of magnitude more."""
BOUNDARY_TYPES = ("reservoir", "reference_node")

CASES = case_files()


def _within(actual: float, expected: float, floor: float) -> bool:
    return abs(actual - expected) <= max(RELATIVE * abs(expected), floor)


def _failures(
    label: str, actual: dict[str, float], expected: dict[str, float], floor: float
) -> list[str]:
    return [
        f"{label} {key}: got {actual[key]!r}, expected {value!r}"
        for key, value in expected.items()
        if not _within(actual[key], value, floor)
    ]


def _head_loss_failures(
    project: Project, actual: dict[str, float], expected: dict[str, float]
) -> list[str]:
    failures = []
    for c in project.connections:
        a, b = f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"
        if a in expected and b in expected:
            got, want = actual[a] - actual[b], expected[a] - expected[b]
            if not _within(got, want, HEAD_FLOOR):
                failures.append(f"head loss {c.id}: got {got!r}, expected {want!r}")
    return failures


def _check_flags(result: SolvedState, expected: list[dict[str, str]]) -> list[str]:
    """Every expected flag must be present (design §12), matched on code and on componentId /
    connectionId when given. Warning and invalid flags are exhaustive: each one the solver
    raises must be expected with exactly its code, componentId and connectionId (absent = the
    flag names none). Info flags (states worth knowing) may appear unlisted."""
    problems = []
    for want in expected:
        if not any(
            flag.code == want["code"]
            and want.get("componentId") in (None, flag.component_id)
            and want.get("connectionId") in (None, flag.connection_id)
            for flag in result.flags
        ):
            problems.append(f"missing flag {want}")
    listed = {(w["code"], w.get("componentId"), w.get("connectionId")) for w in expected}
    for flag in result.flags:
        if flag.severity == "info":
            continue
        if (flag.code, flag.component_id, flag.connection_id) not in listed:
            problems.append(f"unexpected {flag.severity} flag {flag.code}: {flag.message}")
    return problems


PUMP_FLOW_FIELDS = {"operatingFlow": "operating_flow"}
PUMP_HEAD_FIELDS = {
    "operatingHead": "operating_head",
    "npshAvailable": "npsh_available",
    "npshRequired": "npsh_required",
    "npshMargin": "npsh_margin",
}


def _speed_failures(
    project: Project, pump_id: str, speed: float, want: dict[str, Any]
) -> list[str]:
    """A controlled pump's speed (D6 for speed, owner's answer Q6): within 0.5 % of the
    reference, and, for a running pump, the head it implies at the reference flow within
    0.01 m of the reference head."""
    failures = []
    if abs(speed - want["speed"]) > RELATIVE * abs(want["speed"]):
        failures.append(f"pump {pump_id} speed: got {speed!r}, expected {want['speed']!r}")
    if want["status"] == "running" and "operatingHead" in want:
        component = next(c for c in project.components if c.id == pump_id)
        assert isinstance(component, Pump)
        curve = next(c for c in project.pump_library if c.id == component.curve_id)
        implied = pump_head(curve, speed, want["operatingFlow"])
        if abs(implied - want["operatingHead"]) > HEAD_FLOOR:
            failures.append(
                f"pump {pump_id}: speed {speed!r} implies {implied!r} m at the reference flow, "
                f"expected {want['operatingHead']!r} m"
            )
    return failures


def _component_failures(
    project: Project, result: SolvedState, expected: dict[str, Any]
) -> list[str]:
    """Pump statuses, operating values, speeds and control states, valve states (design §12,
    CLAUDE.md D11)."""
    failures = []
    for pump_id, want in expected.get("pumps", {}).items():
        got = result.pump_results.get(pump_id)
        if got is None:
            failures.append(f"no pump result for {pump_id}")
            continue
        if got.status != want["status"]:
            failures.append(f"pump {pump_id}: status {got.status!r}, expected {want['status']!r}")
        for fields, floor in ((PUMP_FLOW_FIELDS, FLOW_FLOOR), (PUMP_HEAD_FIELDS, HEAD_FLOOR)):
            for key, attr in fields.items():
                if key in want:
                    value = getattr(got, attr)
                    if value is None or not _within(value, want[key], floor):
                        failures.append(
                            f"pump {pump_id} {key}: got {value!r}, expected {want[key]!r}"
                        )
        if "controlState" in want:
            state = None if got.control is None else got.control.state
            if state != want["controlState"]:
                failures.append(
                    f"pump {pump_id}: control state {state!r}, expected {want['controlState']!r}"
                )
        if "speed" in want:
            failures += _speed_failures(project, pump_id, got.speed, want)
    isolated = {
        cid
        for flag in result.flags
        if flag.code == "ISOLATED_SECTION"
        for cid in str(flag.details.get("componentIds", "")).split(", ")
    }
    for valve_id, want in expected.get("valves", {}).items():
        got_valve = result.valve_results.get(valve_id)
        # A valve with a port in an isolated section (no expected EGL there, design §4) has
        # no defined head loss or pressure drop, which ValveResult requires: its result is
        # optional, but then an ISOLATED_SECTION flag must name it, and its state must match
        # when it is reported.
        bounded = all(f"{valve_id}:{port}" in expected["egl"] for port in ("inlet", "outlet"))
        if got_valve is None:
            if bounded:
                failures.append(f"no valve result for {valve_id}")
            elif valve_id not in isolated:
                failures.append(f"{valve_id} has no result and no ISOLATED_SECTION flag")
        elif got_valve.state != want["state"]:
            failures.append(
                f"valve {valve_id}: state {got_valve.state!r}, expected {want['state']!r}"
            )
    return failures


EQUIPMENT_FIELDS = {
    "flow": ("flow", "flow"),
    "flowRatio": ("flow_ratio", "ratio"),
    "headLoss": ("head_loss", "head"),
    "pressureLoss": ("pressure_loss", "pressure"),
    "pressureDrop": ("pressure_drop", "pressure"),
}
"""Expected key -> (EquipmentResult attribute, D6 floor kind)."""


def _equipment_failures(
    project: Project, result: SolvedState, expected: dict[str, Any], density: float
) -> list[str]:
    """Every expected equipment result (proposal §2.2) within D6, and every equipment item of
    the project expected, so none goes unchecked."""
    floors = {
        "flow": FLOW_FLOOR,
        "ratio": FLOW_FLOOR,
        "head": HEAD_FLOOR,
        "pressure": density * G * HEAD_FLOOR,
    }
    wanted = expected.get("equipment", {})
    failures = [
        f"equipment {c.id} has no expected result"
        for c in project.components
        if isinstance(c, Equipment) and c.id not in wanted
    ]
    for eid, want in wanted.items():
        got = result.equipment_results.get(eid)
        if got is None:
            failures.append(f"no equipment result for {eid}")
            continue
        component = next(c for c in project.components if c.id == eid)
        assert isinstance(component, Equipment)
        if got.rating != component.rating:
            failures.append(f"equipment {eid}: rating {got.rating!r}, not {component.rating!r}")
        for key, (attr, kind) in EQUIPMENT_FIELDS.items():
            value = getattr(got, attr)
            if want[key] is None or value is None:
                if want[key] is not value:
                    failures.append(f"equipment {eid} {key}: got {value!r}, expected {want[key]!r}")
            elif not _within(value, want[key], floors[kind]):
                failures.append(f"equipment {eid} {key}: got {value!r}, expected {want[key]!r}")
    return failures


def _step_hold_failures(result: SolvedState, expected: dict[str, Any]) -> list[str]:
    """The step and the two splits of every expected step hold, from the solver's
    CORRELATION_OUT_OF_RANGE flag on that branch (details step, splitA, splitB)."""
    failures = []
    for cid, want in expected.get("stepHolds", {}).items():
        reported = [
            flag.details
            for flag in result.flags
            if flag.code == "CORRELATION_OUT_OF_RANGE"
            and flag.component_id == cid
            and "splitA" in flag.details
        ]
        if len(reported) != 1:
            failures.append(f"{cid}: {len(reported)} step-hold flags, expected 1")
            continue
        got = reported[0]
        if got["step"] != want["step"]:
            failures.append(f"{cid}: held at the step {got['step']}, expected {want['step']}")
        pairs = (
            sorted([float(got["splitA"]), float(got["splitB"])]),
            sorted([want["splitA"], want["splitB"]]),
        )
        for g, w in zip(*pairs, strict=True):
            if abs(g - w) > SPLIT_TOLERANCE:
                failures.append(f"{cid}: held between splits {pairs[0]}, expected {pairs[1]}")
                break
    return failures


def test_cases_exist() -> None:
    assert CASES, "no reference cases found in tests/reference/cases"


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_reference_case(case_path: Path) -> None:
    # Imported here so that a missing or broken solver fails these cases, not test collection.
    from opensolve_pipe.services.solver import solve_project

    case: dict[str, Any] = read_case(case_path)
    project = Project.model_validate(case["project"])
    expected = case["expected"]

    result = solve_project(project)

    assert result.converged, result.convergence.message

    fluid = expected["fluid"]
    assert result.fluid.density == pytest.approx(fluid["density"], rel=PROPERTY_RELATIVE)
    assert result.fluid.dynamic_viscosity == pytest.approx(
        fluid["dynamicViscosity"], rel=PROPERTY_RELATIVE
    )
    if "vaporPressure" in fluid:
        if fluid["vaporPressure"] is None:
            assert result.fluid.vapor_pressure is None
        else:
            assert result.fluid.vapor_pressure == pytest.approx(
                fluid["vaporPressure"], rel=PROPERTY_RELATIVE
            )
    if "atmosphericPressure" in expected:
        assert result.atmospheric_pressure == pytest.approx(
            expected["atmosphericPressure"], rel=PROPERTY_RELATIVE
        )

    flows = {cid: link.flow for cid, link in result.link_results.items()}
    assert set(flows) == {c.id for c in project.connections}
    egl = {key: node.egl for key, node in result.node_results.items()}
    pressures = {key: node.pressure for key, node in result.node_results.items()}
    # Every port with an expected EGL has a head, and no other port does: ports in an isolated
    # section (the only ones without an expected EGL) have none (design §4).
    assert set(egl) == set(expected["egl"])
    assert set(expected.get("pressures", {})) <= set(pressures)

    failures = (
        _failures("flow", flows, expected["flows"], FLOW_FLOOR)
        + _failures("egl", egl, expected["egl"], HEAD_FLOOR)
        + _failures(
            "pressure",
            pressures,
            expected.get("pressures", {}),
            fluid["density"] * G * HEAD_FLOOR,
        )
        + _head_loss_failures(project, egl, expected["egl"])
        + _check_flags(result, expected.get("flags", []))
        + _component_failures(project, result, expected)
        + _step_hold_failures(result, expected)
        + _equipment_failures(project, result, expected, fluid["density"])
    )
    assert not failures, "\n".join(failures)

    # Mass balance from the link results only: net flow into every non-boundary component,
    # which an assigned-flow node withdraws (its flow; TSD §4.8) and every other one passes on.
    net: dict[str, float] = defaultdict(float)
    for c in project.connections:
        net[c.to_component_id] += flows[c.id]
        net[c.from_component_id] -= flows[c.id]
    q_max = max(abs(q) for q in flows.values())
    for component in project.components:
        if component.type not in BOUNDARY_TYPES:
            withdrawn = component.flow if isinstance(component, AssignedFlow) else 0.0
            assert abs(net[component.id] - withdrawn) <= MASS_BALANCE_RELATIVE * q_max, component.id

    # The solver's own continuity report must agree (design §4 convergence criterion).
    residual = result.convergence.max_continuity_residual.value
    assert abs(residual) <= MASS_BALANCE_RELATIVE * q_max + 1.0e-14
