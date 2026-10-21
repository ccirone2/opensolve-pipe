"""Flags audit (GOALS §4.6): every condition that makes a result physically invalid or unreliable
is flagged by default, with the severity of its code and the element it concerns.

GOALS §4.6 conditions and their flags:

- cavitation (NPSHa < NPSHr): CAVITATION, invalid, on the pump (port 'suction');
- flow reversal through a pump: PUMP_FLOW_REVERSAL, invalid, on the pump;
- outside a correlation's validated range: CORRELATION_OUT_OF_RANGE (warning) on the connection
  (friction ranges, Crane fittings in laminar flow), the valve (a Crane default in laminar flow)
  or the branch (tee / wye ranges); PUMP_OUTSIDE_CURVE (warning) for extrapolated head,
  efficiency or NPSHr curves; TRANSITIONAL_FLOW (warning) on the connection; TEE_PATTERN_FALLBACK
  (warning) on the tee; a fluid outside its property source's range is rejected (FLUID_ERROR),
  and one that would flash anywhere is BELOW_VAPOR_PRESSURE (invalid) on the component / port;
- non-convergence: NOT_CONVERGED, invalid, network-wide, naming the elements involved;
- a section whose flow is determined but whose pressure level nothing fixes (a pump loop behind
  a closed valve): UNDETERMINED_PRESSURE, warning, on the pump or FCV driving the flow, naming
  the section's components (its pressures and NPSH are not computed).
"""

import math
from pathlib import Path
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, FlagCode, SolvedState
from opensolve_pipe.services.solver import solve_project, status
from opensolve_pipe.services.solver.flags import FLAG_SEVERITY, make_flag
from opensolve_pipe.services.solver.status import Status
from tests.reference.case_format import case_files, read_case

from .helpers import connection, custom_fluid, make_project, plug, reservoir, tee

NETWORK_FLAGS = {"NOT_CONVERGED", "NO_VAPOR_PRESSURE"}
"""Codes about the whole solve, which name no single element."""


def _flags(result: SolvedState, code: str) -> list[Flag]:
    return [f for f in result.flags if f.code == code]


def test_every_flag_code_has_one_severity() -> None:
    assert set(FLAG_SEVERITY) == set(FlagCode.__args__)
    invalid = {c for c, s in FLAG_SEVERITY.items() if s == "invalid"}
    warning = {c for c, s in FLAG_SEVERITY.items() if s == "warning"}
    assert invalid == {
        "NOT_CONVERGED",
        "CAVITATION",
        "BELOW_VAPOR_PRESSURE",
        "PUMP_FLOW_REVERSAL",
        "UNSUPPORTED_FLOW_PATTERN",
        "PORT_ABOVE_LIQUID_LEVEL",
    }
    assert warning == {
        "PUMP_OUTSIDE_CURVE",
        "TRANSITIONAL_FLOW",
        "CORRELATION_OUT_OF_RANGE",
        "TEE_PATTERN_FALLBACK",
        "UNDETERMINED_PRESSURE",
        "NPSH_NOT_CHECKED",
    }


def test_a_flag_cannot_be_raised_with_another_severity() -> None:
    with pytest.raises(ValueError, match="CAVITATION"):
        make_flag("CAVITATION", "warning", "x")
    assert make_flag("CAVITATION", "invalid", "x").severity == "invalid"


@pytest.mark.parametrize("path", case_files(), ids=lambda p: p.stem)
def test_reference_case_flags_name_existing_elements(path: Path) -> None:
    project = Project.model_validate(read_case(path)["project"])
    result = solve_project(project)
    components = {c.id: {p.id for p in c.ports} for c in project.components}
    connections = {c.id for c in project.connections}
    for flag in result.flags:
        assert flag.severity == FLAG_SEVERITY[flag.code]
        if flag.code in NETWORK_FLAGS:
            assert flag.component_id is None
            assert flag.connection_id is None
            continue
        assert (flag.component_id in components) != (flag.connection_id in connections), flag
        if flag.port_id is not None:
            assert flag.component_id is not None
            assert flag.port_id in components[flag.component_id]


# --------------------------------------------------------------------------- scenarios


def _valve(cid: str, vtype: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kw,
    }


def _viscous_line(resistance: dict[str, Any] | None = None, h2: float = 10.0) -> SolvedState:
    """R1 (20 m) -> L1 [elbow] -> gate valve V -> L2 -> R2, with a liquid of 1 Pa·s (a test
    input): laminar flow everywhere."""
    valve = _valve("V", "gate", **({"resistance": resistance} if resistance else {}))
    comps = [reservoir("R1", level=20.0), valve, reservoir("R2", level=h2)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet"), fittings=[{"type": "elbow_90_lr"}]),
        connection("L2", ("V", "outlet"), ("R2", "port_1")),
    ]
    return solve_project(make_project(comps, conns, fluid=custom_fluid(1200.0, 1.0)))


def test_crane_fitting_and_valve_defaults_in_laminar_flow_are_flagged() -> None:
    result = _viscous_line()
    assert result.converged
    assert result.link_results["L1"].flow_regime == "laminar"
    out_of_range = _flags(result, "CORRELATION_OUT_OF_RANGE")
    assert {(f.connection_id, f.component_id) for f in out_of_range} == {("L1", None), (None, "V")}
    assert all(f.severity == "warning" for f in out_of_range)
    valve_flag = next(f for f in out_of_range if f.component_id == "V")
    assert "laminar" in valve_flag.message
    assert 0.0 < float(valve_flag.details["reynoldsNumber"]) < 2000.0


def test_user_valve_resistance_and_zero_flow_are_not_flagged() -> None:
    """A user K carries no Crane validity range; with no flow there is no regime to flag."""
    user = _viscous_line({"kind": "K", "value": 0.2})
    assert {f.component_id for f in _flags(user, "CORRELATION_OUT_OF_RANGE")} == {None}
    still = _viscous_line(h2=20.0)  # equal levels: no flow
    assert still.valve_results["V"].flow == 0.0
    assert not _flags(still, "CORRELATION_OUT_OF_RANGE")


@pytest.mark.parametrize("method", ["colebrook", "swamee_jain"])
def test_friction_outside_its_cited_range_is_flagged_on_the_connection(method: str) -> None:
    comps, conns = (
        [reservoir("R1", level=20.0), reservoir("R2", level=10.0)],
        [connection("P1", ("R1", "port_1"), ("R2", "port_1"), roughness=0.006)],  # ε/D = 0.06
    )
    result = solve_project(make_project(comps, conns, method=method))
    [flag] = _flags(result, "CORRELATION_OUT_OF_RANGE")
    assert (flag.connection_id, flag.component_id, flag.severity) == ("P1", None, "warning")
    assert "ε/D" in flag.message


def test_tee_outside_the_crane_range_is_flagged_on_the_tee() -> None:
    comps = [
        reservoir("R1", level=20.0),
        tee("T", loss_model="crane"),
        reservoir("R2", level=10.0),
        reservoir("R3", level=12.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet"), length=50.0),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1"), length=30.0),
        connection("L3", ("T", "branch"), ("R3", "port_1"), length=20.0, diameter=0.12),
    ]
    result = solve_project(make_project(comps, conns))
    flags = _flags(result, "CORRELATION_OUT_OF_RANGE")
    assert flags
    assert all(f.component_id == "T" and f.severity == "warning" for f in flags)
    assert any("β > 1" in f.message for f in flags)


def test_crane_tee_in_laminar_flow_is_flagged_on_the_tee() -> None:
    """The Crane TP-410 tee K values come from the same fully turbulent data as the bends and
    valves already flagged in laminar flow (M4 review: a tee at Re ~ 200 was reported in
    range)."""
    comps = [
        reservoir("R1", level=20.0),
        tee("T1", loss_model="crane"),
        reservoir("R2", level=10.0),
        reservoir("R3", level=12.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T1", "run_inlet"), diameter=0.05),
        connection("L2", ("T1", "run_outlet"), ("R2", "port_1"), diameter=0.05),
        connection("L3", ("T1", "branch"), ("R3", "port_1"), diameter=0.05),
    ]
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(1000.0, 0.2)))
    assert result.converged
    branch = result.branch_results["T1"]
    q_c = abs(branch.port_flows["run_inlet"])
    re = q_c * 0.05 / (math.pi * 0.05**2 / 4 * 0.2 / 1000.0)
    assert 0.0 < re < 2000.0
    assert not branch.in_correlation_range
    [flag] = [f for f in _flags(result, "CORRELATION_OUT_OF_RANGE") if f.component_id == "T1"]
    assert flag.severity == "warning"
    assert "laminar" in flag.message
    assert f"Re = {re:.0f}" in flag.message
    trace = result.trace.elements["T1"]
    assert any("laminar" in n for n in trace.notes)


def test_valve_cv_or_kv_in_laminar_flow_is_flagged() -> None:
    """A Cv or Kv is converted to K with the turbulent ISA-75.01.01 equation, without the
    Reynolds number factor F_R: flagged in laminar flow, as a Crane default is. A K entered
    directly carries no validity range (test above)."""
    for kind, value in (("Cv", 50.0), ("Kv", 43.0)):
        result = _viscous_line({"kind": kind, "value": value})
        assert result.converged
        [flag] = [f for f in _flags(result, "CORRELATION_OUT_OF_RANGE") if f.component_id == "V"]
        assert flag.severity == "warning"
        assert "laminar" in flag.message
        assert "F_R" in flag.message
        assert 0.0 < float(flag.details["reynoldsNumber"]) < 2000.0


def _pump_project(
    efficiency: list[tuple[float, float]],
    npshr: list[tuple[float, float]],
    h2: float = 20.0,
) -> SolvedState:
    """R1 (level 2 m) -> L1 -> PU -> L2 -> R2 (level h2); every curve point is a test input."""
    comps = [
        reservoir("R1", level=2.0),
        {
            "type": "pump",
            "id": "PU",
            "name": "PU",
            "elevation": 0.0,
            "curveId": "C1",
            "ports": [
                {"id": "suction", "nominalSize": 0.1},
                {"id": "discharge", "nominalSize": 0.1},
            ],
        },
        reservoir("R2", level=h2),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    curve = {
        "id": "C1",
        "name": "test pump",
        "points": [
            {"flow": q, "head": h}
            for q, h in ((0.0, 32.0), (0.01, 30.0), (0.02, 25.0), (0.03, 16.0))
        ],
        "efficiencyCurve": [{"flow": q, "efficiency": e} for q, e in efficiency],
        "npshrCurve": [{"flow": q, "npshr": n} for q, n in npshr],
    }
    fluid = custom_fluid(998.0, 1.0e-3, vapor_pressure=2339.0)
    return solve_project(make_project(comps, conns, pump_library=[curve], fluid=fluid))


def test_a_pump_whose_cavitation_cannot_be_checked_is_flagged() -> None:
    """Without a vapor pressure (a glycol, or a custom fluid without one) NPSHa is not computed,
    so CAVITATION can never be raised: a running pump with an NPSHr curve carries a warning
    naming it (M4 review: only the fluid-wide NO_VAPOR_PRESSURE info said so)."""
    curve = [(0.0, 1.0), (0.03, 3.0)]
    result = _pump_project([(0.0, 0.5), (0.03, 0.7)], curve)
    assert result.pump_results["PU"].npsh_available is not None
    assert not _flags(result, "NPSH_NOT_CHECKED")

    comps = [
        reservoir("R1", level=2.0),
        {
            "type": "pump",
            "id": "PU",
            "name": "PU",
            "elevation": 0.0,
            "curveId": "C1",
            "ports": [
                {"id": "suction", "nominalSize": 0.1},
                {"id": "discharge", "nominalSize": 0.1},
            ],
        },
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=200.0),
    ]
    pump_curve = {
        "id": "C1",
        "name": "test pump",
        "points": [
            {"flow": q, "head": h}
            for q, h in ((0.0, 32.0), (0.01, 30.0), (0.02, 25.0), (0.03, 16.0))
        ],
        "npshrCurve": [{"flow": q, "npshr": n} for q, n in curve],
    }
    glycol = {
        "kind": "builtin",
        "fluidId": "ethylene_glycol",
        "temperature": 293.15,
        "concentration": 0.3,
    }
    result = solve_project(make_project(comps, conns, pump_library=[pump_curve], fluid=glycol))
    pump = result.pump_results["PU"]
    assert pump.status == "running"
    assert pump.npsh_available is None
    assert pump.npsh_required is not None
    [flag] = _flags(result, "NPSH_NOT_CHECKED")
    assert (flag.component_id, flag.port_id, flag.severity) == ("PU", "suction", "warning")
    assert "cavitation is not checked" in flag.message
    assert _flags(result, "NO_VAPOR_PRESSURE")  # the fluid-wide info stays

    glycol["overrides"] = {"vaporPressure": 2000.0}
    result = solve_project(make_project(comps, conns, pump_library=[pump_curve], fluid=glycol))
    assert result.pump_results["PU"].npsh_available is not None
    assert not _flags(result, "NPSH_NOT_CHECKED")


def test_extrapolated_efficiency_and_npshr_curves_are_flagged_on_the_pump() -> None:
    result = _pump_project(
        efficiency=[(0.0, 0.1), (0.005, 0.4)], npshr=[(0.001, 1.0), (0.004, 1.5)]
    )
    pump = result.pump_results["PU"]
    assert pump.status == "running"
    assert pump.in_curve_range  # the head curve is not extrapolated
    assert pump.operating_flow > 0.005  # beyond both short curves (a guard on the inputs)
    flags = _flags(result, "PUMP_OUTSIDE_CURVE")
    assert {str(f.details["curve"]) for f in flags} == {"efficiency", "npshr"}
    assert all(f.component_id == "PU" and f.severity == "warning" for f in flags)
    assert pump.efficiency == 0.4  # held at the curve's end value


def test_cavitation_and_flow_reversal_are_invalid_on_the_pump() -> None:
    cavitating = _pump_project(
        efficiency=[(0.0, 0.1), (0.03, 0.7)], npshr=[(0.0, 20.0), (0.03, 25.0)]
    )
    [cav] = _flags(cavitating, "CAVITATION")
    assert (cav.component_id, cav.port_id, cav.severity) == ("PU", "suction", "invalid")
    reversed_ = _pump_project(
        efficiency=[(0.0, 0.1), (0.03, 0.7)], npshr=[(0.0, 1.0), (0.03, 2.0)], h2=40.0
    )
    [rev] = _flags(reversed_, "PUMP_FLOW_REVERSAL")
    assert (rev.component_id, rev.severity) == ("PU", "invalid")
    assert not _flags(reversed_, "CAVITATION")  # no flow: nothing to cavitate


def test_non_convergence_is_invalid_and_names_the_oscillating_elements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def flip(old: Status, dh: float, q: float, h_c: float) -> Status:
        return Status.CLOSED if old is Status.OPEN else Status.OPEN

    monkeypatch.setattr(status, "check_valve_status", flip)
    comps = [reservoir("R1", level=20.0), _valve("V", "check"), reservoir("R2", level=10.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("R2", "port_1")),
    ]
    result = solve_project(make_project(comps, conns))
    assert not result.converged
    [flag] = _flags(result, "NOT_CONVERGED")
    assert flag.severity == "invalid"
    assert flag.component_id is None
    assert flag.connection_id is None
    assert flag.details["componentIds"] == "V"


def test_a_flowing_section_without_a_pressure_level_is_flagged_on_its_pump() -> None:
    """R1 -> L1 -> isolated gate valve V -> L2 -> tee T1; loop T1 -> L3 -> PU -> L4 -> T2 -> L6
    -> T1 with a plugged stub T2 -> L5 -> P. The loop circulates (a pump adds its shutoff head
    around a loop of open pipes at zero flow), but nothing fixes its pressure."""
    pump_component = {
        "type": "pump",
        "id": "PU",
        "name": "PU",
        "elevation": 0.0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    comps = [
        reservoir("R1", level=10.0),
        _valve("V", "gate", status="isolated"),
        tee("T1"),
        pump_component,
        tee("T2"),
        plug("P"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("T1", "run_inlet")),
        connection("L3", ("T1", "run_outlet"), ("PU", "suction"), length=50.0),
        connection("L4", ("PU", "discharge"), ("T2", "run_inlet"), length=50.0),
        connection("L5", ("T2", "run_outlet"), ("P", "port_1")),
        connection("L6", ("T2", "branch"), ("T1", "branch"), length=400.0),
    ]
    curve = {
        "id": "C1",
        "name": "test pump",
        "points": [{"flow": q, "head": h} for q, h in ((0.0, 30.0), (0.01, 25.0), (0.02, 20.0))],
    }
    result = solve_project(make_project(comps, conns, pump_library=[curve]))
    assert result.converged
    assert result.link_results["L6"].flow > 0.0
    [flag] = _flags(result, "UNDETERMINED_PRESSURE")
    assert (flag.component_id, flag.severity) == ("PU", "warning")
    assert flag.details["componentIds"] == "P, PU, T1, T2, V"
    assert result.pump_results["PU"].npsh_available is None
