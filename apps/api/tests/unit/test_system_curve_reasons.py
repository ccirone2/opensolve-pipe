"""System-curve points without a head carry their reason as data (``SystemCurvePoint.reason``
and the fields after it): a code for each case the message describes, the ids of the elements
it names in its order, the assigned-flow nodes it counts and the numbers it quotes (flows in
m³/s, heads in m), so that the web can say the same with element names and display units. The
message stays as it was, word for word.

Each test builds a network whose case is derived here by hand from its topology and inputs,
then checks the code, the fields and the whole message (written out here, not read from the
code). Flows quoted from a cut are sums of test inputs (setpoints and assigned flows); the open
head at a valve's switch is the Darcy–Weisbach loss of the pipes (f from
``fluids.friction.Colebrook``) plus the reservoir levels, the valve ideal (no resistance given)
and no entrance or exit loss at a reservoir without those fittings (CLAUDE.md D10).
"""

import importlib
import itertools
import math
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fluids.friction import Colebrook
from scipy import constants

from opensolve_pipe.main import app
from opensolve_pipe.models.api import SolveOptions
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.budget import Budget, use_budget
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.status import run_outer_loop

from .helpers import assigned_flow, connection, make_project, reservoir, tee

# The package exports a function named system_curve, so the module is fetched by name.
sc = importlib.import_module("opensolve_pipe.services.solver.system_curve")

CURVE = [(0.0, 45.0), (0.01, 44.0), (0.02, 41.0), (0.03, 35.5), (0.04, 27.0)]
"""A centrifugal curve, 45 m shutoff (test input)."""
DENSITY, VISCOSITY = 998.0, 1.0e-3
"""The helpers' custom fluid, kg/m³ and Pa·s."""
D, ROUGHNESS = 0.1, 4.5e-5
"""The helpers' pipe, m."""
G = constants.g
"""Standard gravity, m/s² (scipy.constants)."""
P_SET = 50_000.0
"""A PRV's static setpoint, Pa (test input): 5.1 m of head at z = 0."""

NO_WAY = (
    "the flow has no way through: a side of the pump reaches no reservoir or reference node, "
    "nor the pump's other side, through elements that can open (every element but those closed "
    "by a status the user set)"
)
FCV_RULE = "an FCV passes neither reverse flow nor more than its setpoint"
CHECK_RULE = "a check valve passes no reverse flow"
PRV_RULE = (
    "a PRV passes no reverse flow, and no flow while the pressure its outlet side needs is above "
    "its setting"
)
ASSIGNED = "which take or supply their flows whatever the pressure"
NO_STEADY_STATE_PRV = (
    "no steady state found that carries this flow: the status rules close PRV 'V', which leaves "
    f"a side of the pump with no way to a reservoir or reference node ({PRV_RULE}); none is "
    "found from "
)


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


def valve(cid: str, vtype: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kw,
    }


def project(comps: list[dict[str, Any]], conns: list[dict[str, Any]]) -> Project:
    library = [{"id": "C1", "name": "C1", "points": [{"flow": q, "head": h} for q, h in CURVE]}]
    return make_project(comps, conns, pump_library=library)


def line(h1: float, h2: float, middle: dict[str, Any], *, flip: bool = False) -> Project:
    """R1 (level h1) -> L1 (10 m) -> PU -> L2 (10 m) -> the valve V -> L3 (200 m) -> R2
    (level h2), all at z = 0; ``flip``: V's outlet faces the pump."""
    inlet, outlet = ("outlet", "inlet") if flip else ("inlet", "outlet")
    comps = [reservoir("R1", level=h1), pump(), middle, reservoir("R2", level=h2)]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("V", inlet), length=10.0),
        connection("L3", ("V", outlet), ("R2", "port_1"), length=200.0),
    ]
    return project(comps, conns)


def points(net: Project, flows: list[float], *, warm: bool = False) -> list[Any]:
    """The system curve of PU at ``flows``: cold (as ``POST /system-curve``) or warm (as a
    solve's curves: the first point from that solve)."""
    built = build_network(net, fluid_properties(net.fluid))
    start = run_outer_loop(built, tolerance=1e-9, max_iterations=100) if warm else None
    if start is not None:
        assert start.converged, start.message
    out = sc.system_curve_points(built, "PU", flows, tolerance=1e-9, max_iterations=100, warm=start)
    assert [p.flow for p in out] == flows
    return out


def pipe_loss(q: float, length: float) -> float:
    """Darcy–Weisbach loss of a helpers' pipe at flow q, f (L/D) v²/(2g), m."""
    v = q / (math.pi * D * D / 4.0)
    f = Colebrook(DENSITY * v * D / VISCOSITY, ROUGHNESS / D)
    return f * length / D * v * v / (2.0 * G)


def assert_no_head(p: Any, code: str, ids: tuple[str, ...] = (), **fields: Any) -> None:
    """A point without a head whose reason has this code and ids, and these other fields; every
    field not given is empty."""
    assert p.head is None
    assert not p.converged
    r = p.reason
    assert r is not None, p.message
    assert (r.code, r.component_ids) == (code, ids), p.message
    expected = {
        "assigned_flow_node_ids": (),
        "limit_flow": None,
        "passed_flow": None,
        "open_head": None,
        "open_head_bound": None,
        "starts_tried": (),
    }
    for name, value in (expected | fields).items():
        got = getattr(r, name)
        if isinstance(value, float):
            assert got == pytest.approx(value, rel=1e-12), name
        else:
            assert got == value, name


# --------------------------------------------------------------------------- no way through


def test_no_way_through() -> None:
    """The only way from the pump's discharge to a reservoir passes a gate valve the user
    isolated: no other start can open it, so the reason names no element; at zero flow the
    head is undetermined, at any other flow no steady state carries it."""
    net = line(2.0, 10.0, valve("V", "gate", status="isolated"))
    zero, flowing = points(net, [0.0, 0.01])
    assert_no_head(zero, "no_way_through")
    assert zero.message == NO_WAY + "; at zero flow the head across the pump is undetermined"
    assert_no_head(flowing, "no_way_through")
    assert flowing.message == NO_WAY + ", so no steady state carries it"


# --------------------------------------------------------------------------- beyond the limit


def test_beyond_the_limit_of_a_check_valve_facing_the_pump() -> None:
    """Every way from the discharge back to the suction (through R2, R1 and the network) passes
    the check valve backwards: it passes no flow that way, so the limit and what it passes are
    both 0."""
    net = line(2.0, 10.0, valve("V", "check"), flip=True)
    [p] = points(net, [0.01])
    assert_no_head(p, "beyond_limit", ("V",), limit_flow=0.0, passed_flow=0.0)
    assert p.message == (
        "no steady state carries this flow: every way from the pump's discharge back to its "
        "suction, through the network or a reservoir or reference node, passes check valve 'V', "
        f"which passes no flow that way ({CHECK_RULE})"
    )


def test_beyond_the_limit_of_a_series_fcv() -> None:
    """The FCV, the only way, passes at most its setpoint, 0.02 m³/s: a forced 0.03 m³/s is
    beyond it. With no assigned flow the limit is what the FCV passes."""
    net = line(2.0, 10.0, valve("V", "fcv", setpoint=0.02))
    for warm in (False, True):
        [p] = points(net, [0.03], warm=warm)
        assert_no_head(p, "beyond_limit", ("V",), limit_flow=0.02, passed_flow=0.02)
        assert p.message == (
            "no steady state carries this flow: every way from the pump's discharge back to its "
            "suction, through the network or a reservoir or reference node, passes FCV 'V', "
            f"which passes at most 0.02 m³/s that way ({FCV_RULE})"
        )


def demand_on_the_discharge_side(q_set: float, d: float) -> Project:
    """R1 (20 m) -> PU -> tee T1; T1's branch -> D1 (assigned flow d); T1's run outlet -> FCV V1
    (setpoint q_set) -> R2 (5 m); 10 m pipes."""
    comps = [
        reservoir("R1", level=20.0),
        pump(),
        tee("T1"),
        assigned_flow("D1", d),
        valve("V1", "fcv", setpoint=q_set),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L3", ("T1", "branch"), ("D1", "port_1"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("V1", "inlet"), length=10.0),
        connection("L5", ("V1", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    return project(comps, conns)


def demand_on_the_suction_side(q_set: float, d: float) -> Project:
    """R0 (20 m) -> FCV V1 (setpoint q_set) -> tee T1; T1's branch -> D1 (assigned flow d); T1's
    run outlet -> PU -> R2 (30 m); 10 m pipes."""
    comps = [
        reservoir("R0", level=20.0),
        valve("V1", "fcv", setpoint=q_set),
        tee("T1"),
        assigned_flow("D1", d),
        pump(),
        reservoir("R2", level=30.0),
    ]
    conns = [
        connection("L0", ("R0", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L1", ("V1", "outlet"), ("T1", "run_inlet"), length=10.0),
        connection("L2", ("T1", "branch"), ("D1", "port_1"), length=10.0),
        connection("L3", ("T1", "run_outlet"), ("PU", "suction"), length=10.0),
        connection("L4", ("PU", "discharge"), ("R2", "port_1"), length=10.0),
    ]
    return project(comps, conns)


def test_beyond_a_limit_that_counts_an_assigned_flow() -> None:
    """D1 takes 0.004 m³/s between the pump and the FCV (0.01 m³/s): the pump can pass at most
    0.01 + 0.004 = 0.014 m³/s, while the FCV across the cut passes 0.01 m³/s; both numbers are
    quoted, and D1 is named."""
    [p] = points(demand_on_the_discharge_side(0.01, 0.004), [0.016])
    assert_no_head(
        p,
        "beyond_limit",
        ("V1",),
        assigned_flow_node_ids=("D1",),
        limit_flow=0.014,
        passed_flow=0.01,
    )
    assert p.message == (
        "no steady state carries this flow: every way from the pump's discharge back to its "
        "suction, through the network or a reservoir or reference node, passes FCV 'V1', which "
        f"passes at most 0.01 m³/s that way ({FCV_RULE}), and with the flows of assigned-flow "
        f"node(s) 'D1', {ASSIGNED}, the pump can pass at most 0.014 m³/s"
    )


def test_beyond_a_negative_limit() -> None:
    """D1 takes 0.015 m³/s before the pump's suction, where the FCV passes at most 0.01 m³/s:
    the limit is 0.01 − 0.015 = −0.005 m³/s, a reverse flow, so no forced flow from 0 up has a
    steady state; the reason holds the negative limit."""
    for p in points(demand_on_the_suction_side(0.01, 0.015), [0.0, 0.005]):
        assert_no_head(
            p,
            "beyond_limit",
            ("V1",),
            assigned_flow_node_ids=("D1",),
            limit_flow=-0.005,
            passed_flow=0.01,
        )
        assert p.message == (
            "no steady state carries this flow: every way from the pump's discharge back to its "
            "suction, through the network or a reservoir or reference node, passes FCV 'V1', "
            f"which passes at most 0.01 m³/s that way ({FCV_RULE}), and with the flows of "
            f"assigned-flow node(s) 'D1', {ASSIGNED}, the pump would have to pass 0.005 m³/s in "
            "reverse: no forced flow from its suction to its discharge, zero included, has a "
            "steady state"
        )


# --------------------------------------------------------------------------- below the floor


def test_below_the_floor_of_an_assigned_flow_only_the_pump_can_feed() -> None:
    """D1 takes 0.0125 m³/s on the discharge side, where a check valve keeps R2 from feeding it:
    only the pump can, so it must pass at least 0.0125 m³/s; the check valve passes no flow from
    the suction's side to the discharge's."""
    comps = [
        reservoir("R1", level=20.0),
        pump(),
        tee("T1"),
        assigned_flow("D1", 0.0125),
        valve("CV", "check"),
        reservoir("R2", level=30.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L3", ("T1", "branch"), ("D1", "port_1"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("CV", "inlet"), length=10.0),
        connection("L5", ("CV", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    [p] = points(project(comps, conns), [0.006])
    assert_no_head(
        p,
        "below_floor",
        ("CV",),
        assigned_flow_node_ids=("D1",),
        limit_flow=0.0125,
        passed_flow=0.0,
    )
    assert p.message == (
        "no steady state carries this flow: every way from the pump's suction to its discharge, "
        "through the network or a reservoir or reference node, passes check valve 'CV', which "
        f"passes no flow that way ({CHECK_RULE}), and with the flows of assigned-flow node(s) "
        f"'D1', {ASSIGNED}, the pump must pass at least 0.0125 m³/s"
    )


# --------------------------------------------------------------------------- no steady state found


def test_no_steady_state_found_lists_the_starts_tried() -> None:
    """A PRV set to 5.1 m between the pump and R2 at 10 m: its outlet side needs more than its
    setting at any forward flow, so it closes and the pump's discharge side reaches no
    reservoir. No start helps: the reason names the PRV and the starts the message lists, the
    point's own first start (none for the first point of a cold curve, the solve for a warm
    one, the previous point after it), then the initial state and, the PRV being active, that
    state with the control valves open."""
    net = line(2.0, 10.0, valve("V", "prv", setpoint=P_SET))
    initial = "the network's initial state or that state with its control valves open"
    cases = [
        (False, ("initial", "initial_open"), initial),
        (True, ("solve", "initial", "initial_open"), f"the network's own solve, {initial}"),
    ]
    for warm, starts, words in cases:
        first, second = points(net, [0.01, 0.02], warm=warm)
        assert_no_head(first, "no_steady_state_found", ("V",), starts_tried=starts)
        assert first.message == NO_STEADY_STATE_PRV + words
        assert_no_head(
            second,
            "no_steady_state_found",
            ("V",),
            starts_tried=("previous_point", "initial", "initial_open"),
        )
        assert (
            second.message
            == NO_STEADY_STATE_PRV + f"the last converged point's solution, {initial}"
        )


# --------------------------------------------------------------------------- undetermined heads


def test_closed_off_at_zero_flow() -> None:
    """The same PRV closed at zero flow: nothing fixes the pressure between it and the pump."""
    [p] = points(line(2.0, 10.0, valve("V", "prv", setpoint=P_SET)), [0.0])
    assert_no_head(p, "closed_off", ("V",))
    assert p.message == (
        "the head across the pump is undetermined at zero flow: PRV 'V' closes off a side of the "
        "pump, and no reservoir or reference node fixes the pressure in the part closed off"
    )


def test_free_level() -> None:
    """R1 -> PU -> tee T1; T1 -> P2 -> tee T2 -> T1, a loop P2 keeps circulating, joined to R2
    (10 m) only through a PRV set to 5.1 m, which closes: with PU replaced by zero flow its
    discharge side carries flow on a free level."""
    comps = [
        reservoir("R1", level=2.0),
        pump(),
        tee("T1"),
        tee("T2"),
        pump("P2"),
        valve("V", "prv", setpoint=P_SET),
        reservoir("R2", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "branch"), length=10.0),
        connection("L3", ("T1", "run_outlet"), ("P2", "suction"), length=10.0),
        connection("L4", ("P2", "discharge"), ("T2", "run_inlet"), length=10.0),
        connection("L5", ("T2", "run_outlet"), ("T1", "run_inlet"), length=50.0),
        connection("L6", ("T2", "branch"), ("V", "inlet"), length=10.0),
        connection("L7", ("V", "outlet"), ("R2", "port_1"), length=10.0),
    ]
    [p] = points(project(comps, conns), [0.0])
    assert_no_head(p, "free_level", ("V",))
    assert p.message == (
        "the head across the pump is undetermined: a side of the pump, closed off by PRV 'V', "
        "is in a part of the network that carries flow but reaches no reservoir or reference "
        "node, so nothing fixes its pressure level"
    )


SWITCH = (
    "the head across the pump is undetermined: at this flow FCV '{v}' passes exactly its "
    "setpoint flow, so the valve could also hold it throttled, with any head across the pump at "
    "or {side} {head:.6g} m (with the valve fully open), and no reservoir or reference node "
    "fixes the pressure between the valve and the pump"
)


def test_valve_at_its_switch_with_heads_above_the_open_one() -> None:
    """An FCV in series set to 0.02 m³/s, at a forced 0.02 m³/s: fully open it passes the flow
    with H = H_R2 − H_R1 + the three pipes' losses; throttled it passes the same flow with more
    loss, a higher head across the pump, which nothing between them fixes. The open head is a
    lower bound."""
    q = 0.02
    [p] = points(line(2.0, 10.0, valve("V", "fcv", setpoint=q)), [q])
    open_head = 10.0 - 2.0 + 2.0 * pipe_loss(q, 10.0) + pipe_loss(q, 200.0)
    assert p.reason is not None
    assert p.reason.open_head == pytest.approx(open_head, rel=1e-5)
    assert_no_head(
        p, "valve_at_switch", ("V",), open_head=p.reason.open_head, open_head_bound="lower"
    )
    assert p.message == SWITCH.format(v="V", side="above", head=p.reason.open_head)


def test_valve_at_its_switch_with_heads_below_the_open_one() -> None:
    """D1 takes 0.02 m³/s at the tee the pump discharges into, fed by the pump and by an FCV
    set to 0.005 m³/s from R0: the pump must pass at least 0.015 m³/s. There the FCV passes
    exactly its setpoint; throttled, it loses more head on its way into the tee, which lowers
    the tee's head and so the head across the pump: the open head is an upper bound. With the
    ideal tee (one head at its ports) and both reservoirs at 20 m, the open head is the loss of
    the pump's two 10 m pipes at 0.015 m³/s less that of the FCV's two at 0.005 m³/s."""
    comps = [
        reservoir("R1", level=20.0),
        pump(),
        tee("T1"),
        reservoir("R0", level=20.0),
        valve("V1", "fcv", setpoint=0.005),
        assigned_flow("D1", 0.02),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L0", ("R0", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L3", ("V1", "outlet"), ("T1", "branch"), length=10.0),
        connection("L4", ("T1", "run_outlet"), ("D1", "port_1"), length=10.0),
    ]
    [p] = points(project(comps, conns), [0.015])
    open_head = 2.0 * pipe_loss(0.015, 10.0) - 2.0 * pipe_loss(0.005, 10.0)
    assert p.reason is not None
    assert p.reason.open_head == pytest.approx(open_head, rel=1e-5)
    assert_no_head(
        p, "valve_at_switch", ("V1",), open_head=p.reason.open_head, open_head_bound="upper"
    )
    assert p.message == SWITCH.format(v="V1", side="below", head=p.reason.open_head)


# --------------------------------------------------------------- not converged, not computed


def test_not_converged_names_what_the_outer_loop_names() -> None:
    """Beside R1 -> PU -> R2, a part where D1 takes 0.01 m³/s that only an FCV set to
    0.005 m³/s can bring from R3: no steady state carries D1's flow at any forced flow, so every
    point is not converged, and the reason names the FCV, as the outer loop does for /solve."""
    comps = [
        reservoir("R1", level=20.0),
        pump(),
        reservoir("R2", level=10.0),
        reservoir("R3", level=20.0),
        valve("V1", "fcv", setpoint=0.005),
        assigned_flow("D1", 0.01),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=10.0),
        connection("L3", ("R3", "port_1"), ("V1", "inlet"), length=10.0),
        connection("L4", ("V1", "outlet"), ("D1", "port_1"), length=10.0),
    ]
    net = project(comps, conns)
    solved = solve_project(net, SolveOptions(include_system_curve=False))
    assert not solved.converged
    assert solved.convergence.oscillating_components == ["V1"]
    for p in points(net, [0.0, 0.01]):
        assert_no_head(p, "not_converged", ("V1",))
        assert p.message.startswith(
            "not converged: in these statuses only FCV 'V1' can connect assigned-flow node(s) "
            "'D1' to a reservoir or reference node, and they take 0.01 m³/s through it, more than "
            f"its setpoint (0.005 m³/s) ({FCV_RULE}), so no steady state carries their flows; "
        ), p.message


def test_not_computed_past_the_time_budget() -> None:
    """With the request's time budget spent before the first solve, no point is computed."""
    net = line(2.0, 10.0, valve("V", "fcv", setpoint=0.02))
    with use_budget(Budget(deadline=time.monotonic() - 1.0, seconds=45.0)):
        out = points(net, [0.0, 0.01])
    for p in out:
        assert_no_head(p, "not_computed")
        assert p.message == "not computed: the request's time budget of 45 s ran out"


# --------------------------------------------------------------------------- the API


_addresses = itertools.count(1)


def test_the_api_sends_the_reason_and_empty_fields_on_points_with_a_head() -> None:
    """POST /system-curve: below the FCV's 0.02 m³/s plus D1's 0.004 m³/s the points have a
    head and every reason field empty; beyond it the reason, D1 and both flows (camelCase)."""
    client = TestClient(app, client=(f"198.51.100.{next(_addresses) + 200}", 50000))
    net = demand_on_the_discharge_side(0.01, 0.004)
    body = {
        "project": net.model_dump(mode="json", by_alias=True, exclude_none=True),
        "pumpId": "PU",
        "flowMin": 0.004,
        "flowMax": 0.016,
        "numPoints": 5,
    }
    response = client.post("/api/v1/system-curve", json=body)
    assert response.status_code == 200
    with_head, *_, beyond = response.json()["points"]
    assert with_head["head"] is not None
    assert {k: with_head[k] for k in REASON_KEYS} == {
        "reason": None,
        "componentIds": [],
        "assignedFlowNodeIds": [],
        "limitFlow": None,
        "passedFlow": None,
        "openHead": None,
        "openHeadBound": None,
        "startsTried": [],
    }
    assert beyond["flow"] == pytest.approx(0.016)
    assert beyond["head"] is None
    assert beyond["message"].endswith("the pump can pass at most 0.014 m³/s")
    assert {k: beyond[k] for k in REASON_KEYS} == {
        "reason": "beyond_limit",
        "componentIds": ["V1"],
        "assignedFlowNodeIds": ["D1"],
        "limitFlow": pytest.approx(0.014, rel=1e-12),
        "passedFlow": 0.01,
        "openHead": None,
        "openHeadBound": None,
        "startsTried": [],
    }


def post_curve(net: Project, **request: Any) -> list[dict[str, Any]]:
    """The points POST /system-curve returns for PU with these request fields (camelCase)."""
    client = TestClient(app, client=(f"198.51.100.{next(_addresses) + 200}", 50000))
    body = {
        "project": net.model_dump(mode="json", by_alias=True, exclude_none=True),
        "pumpId": "PU",
        **request,
    }
    response = client.post("/api/v1/system-curve", json=body)
    assert response.status_code == 200, response.text
    points: list[dict[str, Any]] = response.json()["points"]
    return points


def test_the_api_sends_the_open_head_its_bound_and_the_starts_tried() -> None:
    """POST /system-curve, the fields only these reasons fill. An FCV in series set to
    0.02 m³/s, over 0 to 0.02 m³/s: the last point is at its switch, the valve named, with the
    open head of ``test_valve_at_its_switch_with_heads_above_the_open_one`` (H_R2 − H_R1 + the
    three pipes' losses) as the lower bound. The PRV of
    ``test_no_steady_state_found_lists_the_starts_tried`` over 0.01 to 0.02 m³/s: the first
    point cold from the initial state and from it with the control valves open, every later one
    first from the point before."""
    *below, switch = post_curve(
        line(2.0, 10.0, valve("V", "fcv", setpoint=0.02)), flowMin=0.0, flowMax=0.02, numPoints=5
    )
    assert all(p["head"] is not None and p["reason"] is None for p in below)
    assert switch["flow"] == pytest.approx(0.02)
    assert switch["head"] is None
    open_head = 10.0 - 2.0 + 2.0 * pipe_loss(0.02, 10.0) + pipe_loss(0.02, 200.0)
    assert {k: switch[k] for k in REASON_KEYS} == {
        "reason": "valve_at_switch",
        "componentIds": ["V"],
        "assignedFlowNodeIds": [],
        "limitFlow": None,
        "passedFlow": None,
        "openHead": pytest.approx(open_head, rel=1e-5),
        "openHeadBound": "lower",
        "startsTried": [],
    }

    first, *later = post_curve(
        line(2.0, 10.0, valve("V", "prv", setpoint=P_SET)),
        flowMin=0.01,
        flowMax=0.02,
        numPoints=5,
    )
    starts = [["initial", "initial_open"]] + [["previous_point", "initial", "initial_open"]] * 4
    for p, tried in zip([first, *later], starts, strict=True):
        assert {k: p[k] for k in REASON_KEYS} == {
            "reason": "no_steady_state_found",
            "componentIds": ["V"],
            "assignedFlowNodeIds": [],
            "limitFlow": None,
            "passedFlow": None,
            "openHead": None,
            "openHeadBound": None,
            "startsTried": tried,
        }


def test_the_api_sends_several_elements_in_the_messages_order() -> None:
    """R1 (2 m) -> PU -> tee T1, whose run outlet feeds FCV VB (0.01 m³/s) to R2 and whose
    branch feeds FCV VA (0.005 m³/s) to R3 (both 10 m): every way from the discharge back to the
    suction passes both FCVs, which together pass 0.015 m³/s, so no forced flow from 0.02 m³/s
    has a steady state. The message names them in id order (``FlowLimit.elements``), VA first
    although VB comes first in the project, and componentIds is in the same order."""
    comps = [
        reservoir("R1", level=2.0),
        pump(),
        tee("T1"),
        valve("VB", "fcv", setpoint=0.01),
        valve("VA", "fcv", setpoint=0.005),
        reservoir("R2", level=10.0),
        reservoir("R3", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("T1", "run_inlet"), length=10.0),
        connection("L3", ("T1", "run_outlet"), ("VB", "inlet"), length=10.0),
        connection("L4", ("VB", "outlet"), ("R2", "port_1"), length=10.0),
        connection("L5", ("T1", "branch"), ("VA", "inlet"), length=10.0),
        connection("L6", ("VA", "outlet"), ("R3", "port_1"), length=10.0),
    ]
    out = post_curve(project(comps, conns), flowMin=0.02, flowMax=0.03, numPoints=5)
    for p in out:
        assert p["head"] is None
        assert p["message"] == (
            "no steady state carries this flow: every way from the pump's discharge back to its "
            "suction, through the network or a reservoir or reference node, passes FCV 'VA' and "
            f"FCV 'VB', which together pass at most 0.015 m³/s that way ({FCV_RULE})"
        )
        assert {k: p[k] for k in REASON_KEYS} == {
            "reason": "beyond_limit",
            "componentIds": ["VA", "VB"],
            "assignedFlowNodeIds": [],
            "limitFlow": pytest.approx(0.015, rel=1e-12),
            "passedFlow": pytest.approx(0.015, rel=1e-12),
            "openHead": None,
            "openHeadBound": None,
            "startsTried": [],
        }


def test_not_converged_ids_are_what_solve_reports_and_the_message_may_name_more() -> None:
    """Beside R1 (20 m) -> PU -> R2 (10 m), D1 takes 0.01 m³/s from a part joined to R3 only by
    a check valve facing away from it (its inlet at D1), which its rule closes: no steady state
    carries D1's flow, and the outer loop names no oscillating or over-controlled element. So
    every point is not converged with componentIds empty, as /solve's oscillatingComponents is,
    while the message names D1 and the check valve closed around it. The published contract
    says so: for not_converged the message may name elements that componentIds does not hold."""
    comps = [
        reservoir("R1", level=20.0),
        pump(),
        reservoir("R2", level=10.0),
        assigned_flow("D1", 0.01),
        valve("CV", "check"),
        reservoir("R3", level=20.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction"), length=10.0),
        connection("L2", ("PU", "discharge"), ("R2", "port_1"), length=10.0),
        connection("L3", ("D1", "port_1"), ("CV", "inlet"), length=10.0),
        connection("L4", ("CV", "outlet"), ("R3", "port_1"), length=10.0),
    ]
    net = project(comps, conns)
    solved = solve_project(net, SolveOptions(include_system_curve=False))
    assert not solved.converged
    assert solved.convergence.oscillating_components == []
    out = post_curve(net, numPoints=5)
    assert len(out) == 5
    for p in out:
        assert p["head"] is None
        assert p["message"] == (
            "not converged: no reservoir or reference node reaches assigned-flow node 'D1' "
            "(takes 0.01 m³/s out of the network) through open elements, so no steady state "
            "carries that flow (an assigned-flow node fixes a flow, not a pressure; EPANET "
            "reports such a part as disconnected); closed around it: check valve 'CV' (closed by "
            f"its status rule: {CHECK_RULE})"
        )
        assert {k: p[k] for k in REASON_KEYS} == {
            "reason": "not_converged",
            "componentIds": [],
            "assignedFlowNodeIds": [],
            "limitFlow": None,
            "passedFlow": None,
            "openHead": None,
            "openHeadBound": None,
            "startsTried": [],
        }
    fields = app.openapi()["components"]["schemas"]["SystemCurvePoint"]["properties"]
    assert (
        "not_converged: /solve's convergence.oscillatingComponents for that solve (see reason), "
        "maybe none, and the message may name other elements, in its words only"
    ) in fields["componentIds"]["description"]
    assert (
        "Other elements and nodes its words name (the assigned-flow nodes of a part no reservoir "
        "or reference node reaches and the elements closed around it, a wye in a flow pattern "
        "with no cited correlation) are in message only."
    ) in fields["reason"]["description"]


REASON_KEYS = (
    "reason",
    "componentIds",
    "assignedFlowNodeIds",
    "limitFlow",
    "passedFlow",
    "openHead",
    "openHeadBound",
    "startsTried",
)
