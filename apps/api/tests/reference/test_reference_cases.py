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
the rating it echoes equal to the project's (no scenario here). An orifice plate
(docs/proposals/orifice-plate.md §2.2) has its ``orificeResults`` entry, every field expected:
flows within D6 (the flow floor), head loss within D6 (0.01 m), pressures within D6 (ρ·g·0.01 m),
the dimensionless and diameter fields within 0.5 % (D6's relative part), the null fields null and
the text fields equal. A flag may name the ``limit`` (or a ``detail`` key) its details must hold,
as an orifice's CORRELATION_OUT_OF_RANGE (one per inequality broken) and its vena-contracta
BELOW_VAPOR_PRESSURE do (§3.5, decision 15).

Independent checks that D6 cannot replace (orifice-plate.md §7.4), at the solver's own reported
state: the reported Reynolds number is 4ρ|Q|/(πDμ) at the reported flow, C_L is
``element_laws``' own transcription of ISO 5167-2 eq. (4) at max(Re_D, Re_lo) (times the move's
ratio for an entered C at corner or flange taps, or the entered C), the meter's C likewise, all to
1e-12 relative; K is K(C_L); the head loss is K v|v|/2g within the energy stop tolerance (10⁻⁷ m +
4ε·max(|H_in|, |H_out|, |h|), CLAUDE.md D7); the reading is ISO eq. (1) at the reported flow and
the vena contracta pressure decision 15's, at the reported port pressures. On a line where the
plate dominates, a C(Re) with the wrong dependence moves the flow by less than D6 at high Re but
not at the low Re of orifice_reynolds_dependence (test_derivation_checks), and these checks catch
it at any Re.

A pressure relief valve (docs/proposals/pressure-relief-valve.md §2.2) has its
``reliefValveResults`` entry, every field expected: flows within D6 (the flow floor), the head
loss within D6 (0.01 m), pressures and differences within D6 (ρ·g·0.01 m), the lift and the two
ratios within D6's 0.5 % (the flow floor below), the values the inputs fix (set, overpressure,
full-lift difference and flow, the capacity's numbers) to 10⁻¹² relative, the texts equal, the
null fields null; a valve expected without a result (null: a closed-off or floating side,
decision 16) has none. At the solver's own reported state (decisions 5, 13): the head loss is
EGL_in − EGL_out; Δp_t = ρg(h − (z_in − z_out)); a relieving valve's head loss is the suite's
law h(Q) within the energy stop tolerance; the lift is Q/(C√(2Δp_t/ρ)); the state follows Q
against Q_f; setRatio, flowRatio and Re follow their definitions; the static drop is the ports'
pressure difference and Δp_t − ρ(v_in² − v_out²)/2; and the inlet and back pressures are the
ports' node pressures.
"""

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from opensolve_pipe.models.components import AssignedFlow, Equipment, Orifice, Pump, ReliefValve
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from tests.reference import derivations as dv
from tests.reference import element_laws as el
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


def _details_match(flag: Any, want: dict[str, str]) -> bool:
    """An expected ``limit`` must be the flag's details.limit, an expected ``detail`` a key of
    its details (orifice-plate.md §3.5, decision 15)."""
    details = flag.details or {}
    return ("limit" not in want or details.get("limit") == want["limit"]) and (
        "detail" not in want or want["detail"] in details
    )


def _check_flags(result: SolvedState, expected: list[dict[str, str]]) -> list[str]:
    """Every expected flag must be present (design §12), matched on code and on componentId /
    connectionId when given (and on its ``limit`` or ``detail`` when given). Warning and invalid
    flags are exhaustive: each one the solver raises must be expected with exactly its code,
    componentId and connectionId (absent = the flag names none), and the limit or detail of such
    an entry when it names one. Info flags (states worth knowing) may appear unlisted."""
    problems = []
    for want in expected:
        if not any(
            flag.code == want["code"]
            and want.get("componentId") in (None, flag.component_id)
            and want.get("connectionId") in (None, flag.connection_id)
            and _details_match(flag, want)
            for flag in result.flags
        ):
            problems.append(f"missing flag {want}")
    for flag in result.flags:
        if flag.severity == "info":
            continue
        if not any(
            (flag.code, flag.component_id, flag.connection_id)
            == (w["code"], w.get("componentId"), w.get("connectionId"))
            and _details_match(flag, w)
            for w in expected
        ):
            problems.append(
                f"unexpected {flag.severity} flag {flag.code} {flag.details}: {flag.message}"
            )
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


ORIFICE_FIELDS = {
    "flow": ("flow", "flow"),
    "headLoss": ("head_loss", "head"),
    "pressureLoss": ("pressure_loss", "pressure"),
    "pressureDrop": ("pressure_drop", "pressure"),
    "differentialPressure": ("differential_pressure", "pressure"),
    "venaContractaPressure": ("vena_contracta_pressure", "pressure"),
    "beta": ("beta", "relative"),
    "pipeDiameter": ("pipe_diameter", "relative"),
    "boreDiameter": ("bore_diameter", "relative"),
    "reynoldsNumber": ("reynolds_number", "relative"),
    "dischargeCoefficient": ("discharge_coefficient", "relative"),
    "coefficientSource": ("coefficient_source", "text"),
    "coefficientReynoldsNumber": ("coefficient_reynolds_number", "relative"),
    "tapCoefficientRatio": ("tap_coefficient_ratio", "relative"),
    "lossCoefficient": ("loss_coefficient", "relative"),
    "taps": ("taps", "text"),
    "meterDischargeCoefficient": ("meter_discharge_coefficient", "relative"),
}
"""Expected key -> (OrificeResult attribute, how it is compared): D6's floors for flows, heads
and pressures, D6's 0.5 % alone for the dimensionless and diameter fields, text exactly."""
COEFFICIENT_RELATIVE = 1.0e-12
"""The independent checks at the solver's own state (module docstring): far above round-off
(~1e-15), far below any difference a wrong correlation makes."""
ENERGY_STOP_ABSOLUTE = 1.0e-7
"""m: the energy stop test's absolute part (CLAUDE.md D7, METHOD_VERSION 1.2.0)."""
ENERGY_STOP_ROUND_OFF = 4.0 * 2.0**-52
"""4ε, the energy stop test's round-off allowance (CLAUDE.md D7)."""


def _orifice_failures(
    project: Project, result: SolvedState, expected: dict[str, Any], density: float
) -> list[str]:
    """Every expected orifice result (orifice-plate.md §2.2) within D6, every plate of the
    project expected, and the independent checks of the module docstring."""
    floors = {
        "flow": FLOW_FLOOR,
        "head": HEAD_FLOOR,
        "pressure": density * G * HEAD_FLOOR,
        "relative": 0.0,
    }
    wanted = expected.get("orifices", {})
    failures = [
        f"orifice {c.id} has no expected result"
        for c in project.components
        if isinstance(c, Orifice) and c.id not in wanted
    ]
    for oid, want in wanted.items():
        got = result.orifice_results.get(oid)
        if got is None:
            failures.append(f"no orifice result for {oid}")
            continue
        for key, (attr, kind) in ORIFICE_FIELDS.items():
            value = getattr(got, attr)
            if kind == "text" or want[key] is None or value is None:
                if value != want[key]:
                    failures.append(f"orifice {oid} {key}: got {value!r}, expected {want[key]!r}")
            elif not _within(value, want[key], floors[kind]):
                failures.append(f"orifice {oid} {key}: got {value!r}, expected {want[key]!r}")
        component = next(c for c in project.components if c.id == oid)
        assert isinstance(component, Orifice)
        failures += _orifice_own_state(project, result, component)
    return failures


def _end_bore(project: Project, key: str) -> float:
    """The inner diameter of the end segment of the pipe on a port (the reference cases' pipes
    are custom pipes)."""
    for c in project.connections:
        if f"{c.to_component_id}:{c.to_port_id}" == key:
            end = c.piping.pipes[-1]
        elif f"{c.from_component_id}:{c.from_port_id}" == key:
            end = c.piping.pipes[0]
        else:
            continue
        assert end.inner_diameter is not None, "the orifice cases use custom pipes"
        return end.inner_diameter
    raise KeyError(key)


def _relative_miss(
    got: float | None, want: float | None, rel: float = COEFFICIENT_RELATIVE
) -> bool:
    if got is None or want is None:
        return got is not want
    return abs(got - want) > rel * abs(want)


def _orifice_own_state(project: Project, result: SolvedState, component: Orifice) -> list[str]:
    """The checks at the solver's own reported state (module docstring)."""
    oid = component.id
    got = result.orifice_results[oid]
    d_pipe = _end_bore(project, f"{oid}:inlet")
    rho, mu = result.fluid.density, result.fluid.dynamic_viscosity
    law = el.orifice_law(component, d_pipe, rho, mu)
    q = got.flow
    failures = []

    def check(label: str, value: float | None, want: float | None) -> None:
        if _relative_miss(value, want):
            failures.append(f"orifice {oid} at its own flow: {label} {value!r}, expected {want!r}")

    check("pipeDiameter", got.pipe_diameter, d_pipe)
    check("reynoldsNumber", got.reynolds_number, law.reynolds(q))
    check("dischargeCoefficient (C_L)", got.discharge_coefficient, law.c_loss(q))
    check("meterDischargeCoefficient (C_M)", got.meter_discharge_coefficient, law.c_meter(q))
    check("tapCoefficientRatio", got.tap_coefficient_ratio, law.ratio(q))
    check("coefficientReynoldsNumber", got.coefficient_reynolds_number, law.coefficient_reynolds(q))
    check(
        "lossCoefficient K(C_L)",
        got.loss_coefficient,
        el.orifice_k(d_pipe, component.bore_diameter, got.discharge_coefficient),
    )
    check("differentialPressure (eq. 1)", got.differential_pressure, law.differential(q))
    nodes = result.node_results
    h_in, h_out = nodes[f"{oid}:inlet"].egl, nodes[f"{oid}:outlet"].egl
    v = law.velocity(q)
    h_law = got.loss_coefficient * v * abs(v) / (2.0 * G)
    stop = ENERGY_STOP_ABSOLUTE + ENERGY_STOP_ROUND_OFF * max(abs(h_in), abs(h_out), abs(h_law))
    if abs(got.head_loss - h_law) > stop:
        failures.append(
            f"orifice {oid}: head loss {got.head_loss!r} is not K v|v|/2g = {h_law!r} within "
            f"the energy stop tolerance {stop:.3g} m"
        )
    if abs(got.head_loss - (h_in - h_out)) > ENERGY_STOP_ROUND_OFF * max(abs(h_in), abs(h_out)):
        failures.append(f"orifice {oid}: head loss {got.head_loss!r} is not EGL_in - EGL_out")
    if q != 0.0 and got.vena_contracta_pressure is not None:
        up, down = ("inlet", "outlet") if q > 0.0 else ("outlet", "inlet")
        p_up = nodes[f"{oid}:{up}"].pressure
        z = {
            p.id: component.elevation if p.elevation is None else p.elevation
            for p in component.ports
        }
        want_vc = p_up + rho * G * (z[up] - z[down]) - law.vena_contracta_drop(q)
        scale = max(abs(p_up), law.vena_contracta_drop(q), 1.0)
        if abs(got.vena_contracta_pressure - want_vc) > 1.0e-12 * scale:
            failures.append(
                f"orifice {oid}: vena contracta {got.vena_contracta_pressure!r}, decision 15 at "
                f"its own state gives {want_vc!r}"
            )
    return failures


RELIEF_FIELDS = {
    "state": ("state", "text"),
    "flow": ("flow", "flow"),
    "lift": ("lift", "ratio"),
    "headLoss": ("head_loss", "head"),
    "totalPressureDifference": ("total_pressure_difference", "pressure"),
    "pressureDrop": ("pressure_drop", "pressure"),
    "inletPressure": ("inlet_pressure", "pressure"),
    "backPressure": ("back_pressure", "pressure"),
    "setPressure": ("set_pressure", "input"),
    "setRatio": ("set_ratio", "ratio"),
    "overpressure": ("overpressure", "input"),
    "overpressureSource": ("overpressure_source", "text"),
    "fullLiftPressureDifference": ("full_lift_pressure_difference", "input"),
    "fullLiftFlow": ("full_lift_flow", "input"),
    "flowRatio": ("flow_ratio", "ratio"),
    "reynoldsNumber": ("reynolds_number", "relative"),
}
"""Expected key -> (ReliefValveResult attribute, how it is compared): D6's floors for flows,
heads and pressures; D6's 0.5 % with the flow floor for the lift and the ratios; 0.5 % for Re;
INPUT_RELATIVE for values the inputs and the fluid fix; text exactly. ``capacity`` is compared
on its own (``_capacity_failures``)."""
INPUT_RELATIVE = 1.0e-12
"""Values the inputs and the case fluid's density fix (no solve between): far above round-off."""


def _capacity_failures(rid: str, got: Any, want: dict[str, Any]) -> list[str]:
    """The capacity a relief result echoes (proposal §2.2): its kind, letter and covering
    letter equal, its numbers to INPUT_RELATIVE, null where expected null."""
    dumped = got.model_dump(mode="json", by_alias=True)
    failures = []
    for key, value in want.items():
        found = dumped.get(key)
        if isinstance(value, float) and isinstance(found, int | float):
            if abs(found - value) > INPUT_RELATIVE * abs(value):
                failures.append(f"relief valve {rid} capacity.{key}: {found!r}, not {value!r}")
        elif found != value:
            failures.append(f"relief valve {rid} capacity.{key}: {found!r}, not {value!r}")
    extra = set(dumped) - set(want)
    if extra:
        failures.append(f"relief valve {rid} capacity has unexpected fields {sorted(extra)}")
    return failures


def _relief_failures(
    project: Project, result: SolvedState, expected: dict[str, Any], density: float
) -> list[str]:
    """Every expected relief result (pressure-relief-valve.md §2.2) within D6, every relief
    valve of the project expected, and the checks at the solver's own state (module
    docstring)."""
    floors = {
        "flow": FLOW_FLOOR,
        "ratio": FLOW_FLOOR,
        "head": HEAD_FLOOR,
        "pressure": density * G * HEAD_FLOOR,
        "relative": 0.0,
    }
    wanted = expected.get("reliefValves", {})
    failures = [
        f"relief valve {c.id} has no expected result"
        for c in project.components
        if isinstance(c, ReliefValve) and c.id not in wanted
    ]
    for rid, want in wanted.items():
        got = result.relief_valve_results.get(rid)
        if want is None:
            if got is not None:
                failures.append(f"relief valve {rid}: a result, expected none")
            continue
        if got is None:
            failures.append(f"no relief valve result for {rid}")
            continue
        for key, (attr, kind) in RELIEF_FIELDS.items():
            value = getattr(got, attr)
            if kind == "text" or want[key] is None or value is None:
                if value != want[key]:
                    failures.append(
                        f"relief valve {rid} {key}: got {value!r}, expected {want[key]!r}"
                    )
            elif kind == "input":
                if abs(value - want[key]) > INPUT_RELATIVE * abs(want[key]):
                    failures.append(
                        f"relief valve {rid} {key}: got {value!r}, expected {want[key]!r}"
                    )
            elif not _within(value, want[key], floors[kind]):
                failures.append(f"relief valve {rid} {key}: got {value!r}, expected {want[key]!r}")
        failures += _capacity_failures(rid, got.capacity, want["capacity"])
        component = next(c for c in project.components if c.id == rid)
        assert isinstance(component, ReliefValve)
        failures += _relief_own_state(project, result, component)
    return failures


def _relief_own_state(project: Project, result: SolvedState, component: ReliefValve) -> list[str]:
    """The checks at the solver's own reported state (module docstring)."""
    rid = component.id
    got = result.relief_valve_results[rid]
    rho, mu = result.fluid.density, result.fluid.dynamic_viscosity
    law = el.relief_law(component, rho)
    nodes = result.node_results
    key_in, key_out = f"{rid}:inlet", f"{rid}:outlet"
    q = got.flow
    failures = []

    def check(label: str, value: float | None, want: float | None, scale: float = 0.0) -> None:
        if value is None or want is None:
            if value is not want:
                failures.append(
                    f"relief valve {rid} at its own state: {label} {value!r}, expected {want!r}"
                )
        elif abs(value - want) > COEFFICIENT_RELATIVE * max(abs(want), scale):
            failures.append(
                f"relief valve {rid} at its own state: {label} {value!r}, expected {want!r}"
            )

    dp_t = got.total_pressure_difference
    check(
        "totalPressureDifference", dp_t, rho * G * (got.head_loss - law.dz), rho * G * abs(law.dz)
    )
    check("setRatio", got.set_ratio, dp_t / component.set_pressure)
    check("flowRatio", got.flow_ratio, q / law.q_full)
    check("fullLiftFlow", got.full_lift_flow, law.q_full)
    check("reynoldsNumber", got.reynolds_number, law.reynolds(q, mu))
    if q > 0.0:
        check("lift", got.lift, q / (law.c * math.sqrt(2.0 * dp_t / rho)))
        state = "full_lift" if q >= law.q_full else "partial_lift"
    else:
        state = "closed"
        if q != 0.0:
            failures.append(f"relief valve {rid}: reverse flow {q!r}")
        check("lift", got.lift, 0.0)
    if got.state != state:
        failures.append(f"relief valve {rid}: state {got.state!r} at Q/Q_f {q / law.q_full!r}")
    if key_in in nodes and key_out in nodes:
        h_in, h_out = nodes[key_in].egl, nodes[key_out].egl
        if abs(got.head_loss - (h_in - h_out)) > ENERGY_STOP_ROUND_OFF * max(abs(h_in), abs(h_out)):
            failures.append(
                f"relief valve {rid}: head loss {got.head_loss!r} is not EGL_in - EGL_out"
            )
        if q > 0.0:
            h_law = law.head(q)
            stop = ENERGY_STOP_ABSOLUTE + ENERGY_STOP_ROUND_OFF * max(
                abs(h_in), abs(h_out), abs(h_law)
            )
            if abs(got.head_loss - h_law) > stop:
                failures.append(
                    f"relief valve {rid}: head loss {got.head_loss!r} is not the law's h(Q) = "
                    f"{h_law!r} within the energy stop tolerance {stop:.3g} m"
                )
        check("inletPressure", got.inlet_pressure, nodes[key_in].pressure)
        check("backPressure", got.back_pressure, nodes[key_out].pressure)
        if got.inlet_pressure is not None and got.back_pressure is not None:
            scale = max(abs(got.inlet_pressure), abs(got.back_pressure))
            check("pressureDrop", got.pressure_drop, got.inlet_pressure - got.back_pressure, scale)
    v_in = dv.velocity(q, _end_bore(project, key_in))
    v_out = dv.velocity(q, _end_bore(project, key_out))
    identity = dp_t - rho * (v_in**2 - v_out**2) / 2.0
    check("pressureDrop (Δp_t identity)", got.pressure_drop, identity, abs(dp_t))
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
        + _orifice_failures(project, result, expected, fluid["density"])
        + _relief_failures(project, result, expected, fluid["density"])
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


CALIBRATION_RELATIVE = 1.0e-10
"""The calibration identity's agreement (orifice-plate.md §7.4): two solves of one network
whose plates have the same law, so their states agree to the solver's convergence, far below
the 2.5 % the identity tells apart."""


def test_a_calibration_equal_to_iso_c_at_the_taps_gives_iso_answer() -> None:
    """The calibration identity (decision 13): C12's network on ISO's C, then with an entered C
    equal to the reported meterDischargeCoefficient (ISO's C at the corner taps, the full
    double). The move to D and D/2 tappings makes the two plates one law, so the flow, K and
    reading agree to CALIBRATION_RELATIVE; an entered C used for the loss as entered would move
    the flow by −2.5 % (test_derivation_checks), and a wrong move by more than this allows."""
    from opensolve_pipe.services.solver import solve_project
    from tests.reference import derivations_orifice as do

    iso = do.corner_series(entered=None).project(
        "ref-calibration", "ISO", do.liquid_a(), "colebrook"
    )
    first = solve_project(iso)
    assert first.converged, first.convergence.message
    plate = first.orifice_results["OR1"]
    assert plate.coefficient_source == "iso_5167_2"
    assert plate.meter_discharge_coefficient is not None
    entered = do.corner_series(entered=plate.meter_discharge_coefficient).project(
        "ref-calibration", "Calibrated", do.liquid_a(), "colebrook"
    )
    second = solve_project(entered)
    assert second.converged, second.convergence.message
    moved = second.orifice_results["OR1"]
    assert moved.coefficient_source == "entered"
    assert moved.tap_coefficient_ratio is not None
    for label, a, b in (
        ("flow", moved.flow, plate.flow),
        ("lossCoefficient", moved.loss_coefficient, plate.loss_coefficient),
        ("dischargeCoefficient", moved.discharge_coefficient, plate.discharge_coefficient),
        ("differentialPressure", moved.differential_pressure, plate.differential_pressure),
    ):
        assert a is not None
        assert b is not None
        assert abs(a - b) <= CALIBRATION_RELATIVE * abs(b), (label, a, b)
