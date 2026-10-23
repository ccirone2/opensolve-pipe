"""System curves through a control valve in series with the pump (owner's decision of
2026-10-23, TSD §12): every point whose forced flow can pass with a determined head reports that
head; a point with no steady state, or whose head is undetermined, reports none, and its message
says which and why, never that the flow has no way through when it has one.

Expected values are derived here, not taken from the solver: at zero flow every pipe and valve
loss is zero and the reservoirs are quiescent, so H_sys(0) is the difference of the reservoir
levels (test inputs). Whether a series PRV can pass a flow follows from its outlet side: the
outlet's EGL must be H_R2 + h_f(Q) (no exit loss at a boundary without an exit fitting, CLAUDE.md
D10), with h_f the Darcy–Weisbach loss of the 200 m outlet pipe, f from
``fluids.friction.Colebrook``, and the PRV passes Q only while that is at most its setpoint head
p_set/(ρg) + v²/(2g) (port at z = 0); a PSV before the pump passes Q only while the inlet
pipe leaves an EGL of at least its setpoint head at its inlet. The closed-form heads of these
curves are in the reference suite (tests/reference); here the points are checked for a head, or
for the reason they have none.
"""

import importlib
import math
from typing import Any

import pytest
from fluids.friction import Colebrook
from scipy import constants

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from opensolve_pipe.services.solver.status import run_outer_loop

from .helpers import connection, make_project, plug, reservoir, tee

# The package exports a function named system_curve, so the module is fetched by name.
sc = importlib.import_module("opensolve_pipe.services.solver.system_curve")

CURVE = [(0.0, 45.0), (0.01, 44.0), (0.02, 41.0), (0.03, 35.5), (0.04, 27.0)]
"""A centrifugal curve (test input)."""
DENSITY, VISCOSITY = 998.0, 1.0e-3
"""The helpers' custom fluid, kg/m³ and Pa·s."""
D, ROUGHNESS, L_OUT = 0.1, 4.5e-5, 200.0
"""The helpers' pipe (m) and the outlet pipe's length (m)."""
G = constants.g
"""Standard gravity, m/s² (scipy.constants)."""
NO_WAY = "no way through"


def pump(cid: str = "PU") -> dict[str, Any]:
    return {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "curveId": "C1",
        "speed": 1.0,
        "status": "on",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }


def valve(vtype: str, setpoint: float) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": "V",
        "name": "V",
        "elevation": 0.0,
        "setpoint": setpoint,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }


def series(vtype: str, setpoint: float, h1: float, h2: float, *, valve_first: bool) -> Project:
    """R1 (level h1) -> L1 (10 m) -> PU -> L2 (10 m) -> V -> L3 (200 m) -> R2 (level h2), or
    the valve before the pump (valve_first); 0.1 m pipes, all at z = 0."""
    first, second = (("V", "inlet", "outlet"), ("PU", "suction", "discharge"))
    if not valve_first:
        first, second = second, first
    comps = [reservoir("R1", level=h1), pump(), valve(vtype, setpoint), reservoir("R2", level=h2)]
    conns = [
        connection("L1", ("R1", "port_1"), (first[0], first[1]), length=10.0),
        connection("L2", (first[0], first[2]), (second[0], second[1]), length=10.0),
        connection("L3", (second[0], second[2]), ("R2", "port_1"), length=L_OUT),
    ]
    library = [
        {"id": "C1", "name": "curve C1", "points": [{"flow": q, "head": h} for q, h in CURVE]}
    ]
    return make_project(comps, conns, pump_library=library)


def build(project: Project) -> BuiltNetwork:
    return build_network(project, fluid_properties(project.fluid))


def curve(project: Project, flows: list[float], start: str) -> list[Any]:
    """The system curve of PU at ``flows``, cold (``POST /system-curve``: the first point from
    the initial state) or warm (with a solve, the first point from that solve)."""
    built = build(project)
    warm = run_outer_loop(built, tolerance=1e-9, max_iterations=100) if start == "warm" else None
    points = sc.system_curve_points(
        built, "PU", flows, tolerance=1e-9, max_iterations=100, warm=warm
    )
    assert [p.flow for p in points] == flows
    return points


def pipe_loss(q: float, length: float) -> float:
    """Darcy–Weisbach loss of a helpers' pipe of this length at flow Q, f (L/D) v²/(2g), m
    (module docstring)."""
    v = q / (math.pi * D * D / 4.0)
    if v == 0.0:
        return 0.0
    f = Colebrook(DENSITY * v * D / VISCOSITY, ROUGHNESS / D)
    return f * length / D * v * v / (2.0 * G)


def setpoint_head(q: float, p_set: float) -> float:
    """A PRV's (PSV's) setpoint as an EGL at its outlet (inlet) port, at z = 0:
    p_set/(ρg) + v²/(2g), m."""
    v = q / (math.pi * D * D / 4.0)
    return p_set / (DENSITY * G) + v * v / (2.0 * G)


# --------------------------------------------------------------------------- series FCV

Q_FCV = 0.02
"""The FCV's setpoint, m³/s (test input)."""
FCV_FLOWS = [0.0, 0.004, 0.008, 0.012, 0.016, 0.019, 0.021, 0.025, 0.03, 0.04]


@pytest.mark.parametrize("valve_first", [False, True])
@pytest.mark.parametrize("start", ["cold", "warm"])
def test_series_fcv_curve_has_a_head_at_every_flow_below_its_setpoint(
    valve_first: bool, start: str
) -> None:
    """Below its setpoint an FCV in series is fully open: the forced flow passes with a
    determined head, H_sys(0) = H_R2 − H_R1. Above it the FCV, the only way, passes no more than
    its setpoint: no steady state carries the flow, and the message names the FCV and that bound
    (``flow_limit``). Before,
    the zero-flow point starved and closed the FCV, and every later point inherited the closed
    valve and was reported as having no way through."""
    h1, h2 = 2.0, 10.0
    points = curve(series("fcv", Q_FCV, h1, h2, valve_first=valve_first), FCV_FLOWS, start)
    for p in points:
        if p.flow < Q_FCV:
            assert p.converged, (p.flow, p.message)
            assert p.head is not None
            assert p.message == ""
        else:
            assert not p.converged
            assert p.head is None
            assert p.message.startswith("no steady state carries this flow"), p.message
            assert "FCV 'V', which passes at most 0.02 m³/s that way" in p.message
            assert "an FCV passes neither reverse flow nor more than its setpoint" in p.message
            assert NO_WAY not in p.message
    assert points[0].head == pytest.approx(h2 - h1, abs=1e-9)
    heads = [p.head for p in points if p.head is not None]
    assert heads == sorted(heads)  # friction grows with the flow


UNDETERMINED_AT_FCV = (
    "the head across the pump is undetermined: at this flow FCV 'V' passes exactly its setpoint "
    "flow, so the valve could also hold it throttled, with any head across the pump at or above "
)


def open_head(q: float, h1: float, h2: float) -> float:
    """H_sys(q) with the valve fully open: H_R2 − H_R1 plus the three pipes' losses (the valve
    is ideal, no resistance given; no entrance or exit loss at a reservoir without those
    fittings, CLAUDE.md D10), m."""
    return h2 - h1 + 2.0 * pipe_loss(q, 10.0) + pipe_loss(q, L_OUT)


@pytest.mark.parametrize("valve_first", [False, True])
@pytest.mark.parametrize(
    "q",
    [Q_FCV, math.nextafter(Q_FCV, 1.0), Q_FCV + 5.0e-9, Q_FCV - 5.0e-9],
    ids=["exact", "one-ulp-above", "half-qtol-above", "half-qtol-below"],
)
@pytest.mark.parametrize("before", [[], [0.01]], ids=["alone", "after-0.01"])
def test_series_fcv_at_its_setpoint_flow_has_an_undetermined_head(
    valve_first: bool, q: float, before: list[float]
) -> None:
    """At a forced flow equal to the FCV's setpoint (exactly, one ulp above as numpy.linspace
    can give, or within the status rules' Qtol, 1e-8 m³/s, either side) the FCV, the only way,
    passes it: open at its switch, or active, throttled, with any higher head across the pump.
    The head is undetermined, with the open-valve head as its floor, and the message says so,
    not that no steady state carries the flow, whether the point is solved on its own or after
    a point below the setpoint. Before, an open FCV whose solved flow rounded to its setpoint or
    above turned active, was starved beside the forced flow and closed, from every start; and a
    retry that found the switch was dropped."""
    h1, h2 = 2.0, 10.0
    project = series("fcv", Q_FCV, h1, h2, valve_first=valve_first)
    *below, point = curve(project, [*before, q], "cold")
    assert all(p.head is not None for p in below)
    assert point.head is None
    assert not point.converged
    assert point.message.startswith(UNDETERMINED_AT_FCV), point.message
    floor = point.message.removeprefix(UNDETERMINED_AT_FCV).split(" m ")[0]
    assert float(floor) == pytest.approx(open_head(q, h1, h2), rel=1e-5)


def fcv_before_a_closing_prv() -> Project:
    """R1 (2 m) -> L1 -> PU -> L2 -> FCV 'F' (0.02 m³/s) -> L3 -> PRV 'V' (50 kPa, 5.1 m) ->
    L4 (200 m) -> R2 (10 m, above the PRV's setting, so that it passes no flow)."""
    fcv = valve("fcv", Q_FCV) | {"id": "F", "name": "F"}
    comps = [reservoir("R1", level=2.0), pump(), fcv, valve("prv", P_SET)]
    comps.append(reservoir("R2", level=10.0))
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("F", "inlet"), length=10.0),
        connection("L3", ("F", "outlet"), ("V", "inlet"), length=10.0),
        connection("L4", ("V", "outlet"), ("R2", "port_1"), length=L_OUT),
    ]
    library = [
        {"id": "C1", "name": "curve C1", "points": [{"flow": q, "head": h} for q, h in CURVE]}
    ]
    return make_project(comps, conns, pump_library=library)


def test_fcv_at_its_setpoint_ahead_of_a_closing_prv_has_no_steady_state() -> None:
    """The FCV's setpoint is the most any steady state carries (``flow_limit``), but the PRV
    beyond it passes no flow at all: at the setpoint flow there is no steady state, held open
    or not, so the point must not be reported as the FCV's undetermined switch."""
    project = fcv_before_a_closing_prv()
    assert sc.flow_limit(build(project), "PU").flow == Q_FCV
    for start in ("cold", "warm"):
        flowing, at, above = curve(project, [0.01, Q_FCV, 0.03], start)
        for p in (flowing, at):
            assert p.head is None
            assert p.message.startswith("no steady state found that carries this flow"), p
            assert "undetermined" not in p.message
        assert above.message.startswith("no steady state carries this flow"), above.message
        assert "FCV 'F', which passes at most 0.02 m³/s that way" in above.message


# --------------------------------------------------------------------------- series PRV

P_SET = 50_000.0
"""The PRV's static setpoint at its outlet, Pa (test input): 5.1 m of head."""
PRV_FLOWS = [0.0, 0.002, 0.004, 0.006, 0.008, 0.01, 0.014, 0.02, 0.03, 0.04]


@pytest.mark.parametrize("start", ["cold", "warm"])
def test_series_prv_curve_has_a_head_while_its_outlet_side_needs_less_than_its_setting(
    start: str,
) -> None:
    """A PRV between the pump and R2 (level 1 m, below its 5.1 m setting): while the outlet pipe
    needs an EGL below the setpoint head to pass the forced flow into R2, the PRV is fully open
    and the head is determined (H_sys(0) = H_R2 − H_R1). Once it needs more, the PRV, which
    cannot raise the pressure at its outlet, closes: no steady state carries the flow. Flows
    within 1 cm of head of the switch are not on the list."""
    h1, h2 = 2.0, 1.0
    points = curve(series("prv", P_SET, h1, h2, valve_first=False), PRV_FLOWS, start)
    for p in points:
        margin = h2 + pipe_loss(p.flow, L_OUT) - setpoint_head(p.flow, P_SET)
        assert abs(margin) > 0.01  # the list keeps clear of the switch
        if margin < 0.0:
            assert p.converged, (p.flow, p.message)
            assert p.head is not None
        else:
            assert p.head is None
            assert p.message.startswith("no steady state found that carries this flow"), p.message
            assert "PRV 'V'" in p.message
            assert NO_WAY not in p.message
    assert {p.head is None for p in points} == {True, False}  # both kinds are on the list
    assert points[0].head == pytest.approx(h2 - h1, abs=1e-9)


@pytest.mark.parametrize("start", ["cold", "warm"])
def test_series_prv_whose_outlet_side_is_above_its_setting(start: str) -> None:
    """R2 at 10 m, above the PRV's 5.1 m setting: the PRV passes no flow, so no forced flow
    finds a steady state; at zero flow the PRV is closed and nothing fixes the pressure between
    it and the pump, so the head across the pump is undetermined."""
    points = curve(series("prv", P_SET, 2.0, 10.0, valve_first=False), PRV_FLOWS, start)
    assert all(p.head is None and not p.converged for p in points)
    assert all(NO_WAY not in p.message for p in points)
    zero, *rest = points
    assert zero.message.startswith("the head across the pump is undetermined at zero flow")
    assert "PRV 'V'" in zero.message
    assert all(p.message.startswith("no steady state found that carries this flow") for p in rest)


PSV_FLOWS = [0.0, 0.004, 0.008, 0.016, 0.024, 0.032, 0.05, 0.06]


@pytest.mark.parametrize("start", ["cold", "warm"])
def test_series_psv_before_the_pump(start: str) -> None:
    """A PSV between R1 (6 m) and the pump, set to 20 kPa at its inlet: while the inlet pipe
    (10 m) leaves an EGL above the setpoint head at the PSV's inlet, the PSV is fully open and
    the head is determined (H_sys(0) = H_R2 − H_R1); at a flow that would draw the inlet below
    its setting the PSV closes, and no steady state carries the flow."""
    h1, h2, p_set = 6.0, 10.0, 20_000.0
    points = curve(series("psv", p_set, h1, h2, valve_first=True), PSV_FLOWS, start)
    for p in points:
        margin = h1 - pipe_loss(p.flow, 10.0) - setpoint_head(p.flow, p_set)
        assert abs(margin) > 0.01  # the list keeps clear of the switch
        if margin > 0.0:
            assert p.converged, (p.flow, p.message)
            assert p.head is not None
        else:
            assert p.head is None
            assert p.message.startswith("no steady state found that carries this flow"), p.message
            assert "PSV 'V'" in p.message
            assert NO_WAY not in p.message
    assert {p.head is None for p in points} == {True, False}
    assert points[0].head == pytest.approx(h2 - h1, abs=1e-9)


# --------------------------------------------------------------------------- other no-head points


def floating_discharge(prv: bool = False) -> Project:
    """R1 -> PU -> tee T1; T1 -> P2 -> tee T2 -> T1, a loop with a running pump; T2 -> plug, so
    that the discharge side reaches a reservoir only through PU; or (prv) T2 -> a PRV set to
    50 kPa -> R2 at 10 m, above its setting, so that the PRV closes."""
    comps = [reservoir("R1", level=2.0), pump(), tee("T1"), tee("T2"), pump("P2")]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "branch"), length=10.0),
        connection("L3", ("T1", "run_outlet"), ("P2", "suction"), length=10.0),
        connection("L4", ("P2", "discharge"), ("T2", "run_inlet"), length=10.0),
        connection("L5", ("T2", "run_outlet"), ("T1", "run_inlet"), length=50.0),
    ]
    if prv:
        comps += [valve("prv", P_SET), reservoir("R2", level=10.0)]
        conns += [
            connection("L6", ("T2", "branch"), ("V", "inlet"), length=10.0),
            connection("L7", ("V", "outlet"), ("R2", "port_1"), length=10.0),
        ]
    else:
        comps.append(plug("X"))
        conns.append(connection("L6", ("T2", "branch"), ("X", "port_1"), length=10.0))
    library = [
        {"id": "C1", "name": "curve C1", "points": [{"flow": q, "head": h} for q, h in CURVE]}
    ]
    return make_project(comps, conns, pump_library=library)


@pytest.mark.parametrize("start", ["cold", "warm"])
def test_a_side_whose_pressure_level_is_free_has_no_head(start: str) -> None:
    """With PU replaced by a fixed flow, its discharge side is a loop that P2 keeps circulating
    and that reaches no reservoir: its heads are on an arbitrary level, so the head across PU is
    undetermined at zero flow. Before, the zero-flow point reported the difference between R1's
    head and that arbitrary level (−2 m). A forced flow has no way out of that side."""
    zero, flowing = curve(floating_discharge(), [0.0, 0.01], start)
    assert zero.head is None
    assert not zero.converged
    assert zero.message.startswith("the flow has no way through"), zero.message
    assert "at zero flow the head across the pump is undetermined" in zero.message
    assert flowing.head is None
    assert flowing.message.startswith("the flow has no way through")
    assert "so no steady state carries it" in flowing.message
    # The same loop behind a PRV whose outlet side (R2) is above its setting: there is a way
    # through, but the PRV closes, and the loop P2 circulates is on a free level at zero flow.
    zero, flowing = curve(floating_discharge(prv=True), [0.0, 0.01], start)
    assert zero.head is None
    assert zero.message == (
        "the head across the pump is undetermined: a side of the pump, closed off by PRV 'V', "
        "is in a part of the network that carries flow but reaches no reservoir or reference "
        "node, so nothing fixes its pressure level"
    )
    assert flowing.head is None
    assert flowing.message.startswith("no steady state found that carries this flow")
    assert "PRV 'V'" in flowing.message


def isolated_discharge() -> Project:
    """R1 -> PU -> an isolated gate valve -> R2: a status the user set closes the only way."""
    project = series("fcv", Q_FCV, 2.0, 10.0, valve_first=False)
    data = project.model_dump(mode="json", by_alias=True, exclude_none=True)
    [v] = [c for c in data["components"] if c["id"] == "V"]
    v.pop("setpoint")
    v.update(valveType="gate", status="isolated")
    return Project.model_validate(data)


def test_points_with_a_head_and_points_with_no_way_through_solve_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A curve whose every point has a head is solved as before, one outer loop per point (so it
    does not change); so is one with no way through, which no other starting state can open,
    and a point above a series FCV's setpoint, which no state carries (the FCV, the only way,
    passes at most its setpoint: ``flow_limit``). A point above a series PRV's switch, where
    the pressure its outlet side needs closes it (which no cut shows), is solved again: from
    the initial state and from it with the control valves open."""
    calls = {"n": 0}
    forced: list[float] = []
    real = sc.run_outer_loop

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        forced.append(kwargs["forced_flows"]["PU"])
        return real(*args, **kwargs)

    monkeypatch.setattr(sc, "run_outer_loop", counting)
    flows = [0.002, 0.008, 0.016]  # all below the FCV's setpoint: every point has a head
    for project, expected in (
        (series("fcv", Q_FCV, 2.0, 10.0, valve_first=False), True),
        (isolated_discharge(), False),
    ):
        calls["n"] = 0
        points = curve(project, flows, "cold")
        assert [p.head is not None for p in points] == [expected] * len(flows)
        assert calls["n"] == len(flows)
        if not expected:
            assert all(p.message.startswith("the flow has no way through") for p in points)
    forced.clear()
    points = curve(series("fcv", Q_FCV, 2.0, 10.0, valve_first=False), [0.01, 0.03], "cold")
    assert points[0].head is not None
    assert points[1].head is None
    assert points[1].message.startswith("no steady state carries this flow"), points[1].message
    assert forced == [0.01, 0.03]  # the second point from the first only
    forced.clear()
    prv = series("prv", P_SET, 2.0, 1.0, valve_first=False)
    q_high = 0.04
    assert 1.0 + pipe_loss(q_high, L_OUT) - setpoint_head(q_high, P_SET) > 0.01  # above it
    points = curve(prv, [0.002, q_high], "cold")
    assert points[0].head is not None
    assert points[1].head is None
    assert points[1].message.startswith("no steady state found that carries this flow")
    assert forced.count(q_high) == 3  # from the first point, the initial state, then open


# --------------------------------------------------------------------------- flow limit (cut)


def reversed_check(h1: float, h2: float) -> Project:
    """R1 (h1) -> L1 -> PU -> L2 -> a check valve facing the pump (its outlet on L2) -> L3 ->
    R2 (h2): the pump's forced flow would pass the check valve backwards."""
    check = {
        "type": "valve",
        "valveType": "check",
        "id": "V",
        "name": "V",
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }
    comps = [reservoir("R1", level=h1), pump(), check, reservoir("R2", level=h2)]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("V", "outlet"), length=10.0),
        connection("L3", ("V", "inlet"), ("R2", "port_1"), length=L_OUT),
    ]
    library = [
        {"id": "C1", "name": "curve C1", "points": [{"flow": q, "head": h} for q, h in CURVE]}
    ]
    return make_project(comps, conns, pump_library=library)


@pytest.mark.parametrize("valve_first", [False, True])
def test_flow_limit_of_a_series_fcv_is_its_setpoint(valve_first: bool) -> None:
    """Every way from the pump's discharge back to its suction passes the FCV forwards, so no
    steady state carries more than its setpoint (max-flow min-cut); failed open, it passes any
    flow either way, and nothing bounds the flow."""
    project = series("fcv", Q_FCV, 2.0, 10.0, valve_first=valve_first)
    limit = sc.flow_limit(build(project), "PU")
    assert limit.flow == Q_FCV
    assert [(c.component_id, cap) for c, cap in limit.elements] == [("V", Q_FCV)]
    data = project.model_dump(mode="json", by_alias=True, exclude_none=True)
    [v] = [c for c in data["components"] if c["id"] == "V"]
    v["status"] = "failed_open"
    assert sc.flow_limit(build(Project.model_validate(data)), "PU").flow == math.inf


def test_flow_limit_of_a_check_valve_facing_the_pump_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The forced flow would pass the check valve backwards, which the rules never allow: no
    steady state carries any flow, so a flowing point is solved once (no other start can help)
    and says so, naming the check valve and its rule; the zero-flow point is solved as any
    other and has the static head."""
    project = reversed_check(2.0, 10.0)
    limit = sc.flow_limit(build(project), "PU")
    assert limit.flow == 0.0
    assert [(c.component_id, c.kind, cap) for c, cap in limit.elements] == [("V", "check", 0.0)]
    forced: list[float] = []
    real = sc.run_outer_loop

    def counting(*args: Any, **kwargs: Any) -> Any:
        forced.append(kwargs["forced_flows"]["PU"])
        return real(*args, **kwargs)

    monkeypatch.setattr(sc, "run_outer_loop", counting)
    zero, *flowing = curve(project, [0.0, 0.01, 0.02], "cold")
    for p in flowing:
        assert p.head is None
        assert p.message == (
            "no steady state carries this flow: every way from the pump's discharge back to its "
            "suction, through the network or a reservoir or reference node, passes check valve "
            "'V', which passes no flow that way (a check valve passes no reverse flow)"
        )
        assert forced.count(p.flow) == 1
    # At zero flow the check valve may be open with no head across it (its forward head, 0, is
    # not above its cracking pressure, 0, and nothing flows back): H_sys(0) = H_R2 − H_R1.
    assert zero.head == pytest.approx(10.0 - 2.0, abs=1e-9), zero.message
