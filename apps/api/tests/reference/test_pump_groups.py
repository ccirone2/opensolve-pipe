"""Pump group curves against closed forms, through the public API (docs/proposals/pump-groups.md
§3, §5 and §9.1, cases PG1-PG11; CLAUDE.md D6, D11, D13).

Written from the proposal, the models (``models/pump_groups.py``) and the contract as built by a
tester who did not read ``services/``. Every case posts ``POST /api/v1/pump-group-curve`` (and,
where the duty is compared with the case's own solve, ``POST /api/v1/solve``) through FastAPI's
TestClient, and checks the response against values derived in ``derivations_pump_groups`` from
first principles (PCHIP pump curves with the affinity laws, Darcy–Weisbach with Colebrook and
the fluids fitting K, Crane TP-410 tees from ``fluids.fittings``, the status rules written out),
solved with SciPy, never with solver code:

- **The station** (§3.1): its inlet S and outlet D (a port, or a reservoir taken whole), its
  arrangement, members in component order, and its interior components and connections, by
  hand from the topology.
- **The duty** (§3.2): Q_st, ΔH_st = EGL(D) − EGL(S) and EGL(S) against the derivation's own
  solve of the case (D6) and against ``/solve``'s reported values (identities, 10⁻⁹); shares
  Q_i/Q_st (parallel) or H_i/ΣH (series); in parallel each route loss H_i − ΔH_st equals the
  sum of the losses ``/solve`` reports along the member's way (its pipes, valves and tee paths),
  and in series the interstage loss ΣH − ΔH_st the piping between the pumps.
- **The group curve** (§3.3): at each rise held, the station's flow and each member's flow,
  status and head against the derivation of the station alone (D6: 0.5 % or 0.01 m of head;
  flows 0.5 % with a floor of Qtol, 10⁻⁸ m³/s, for zero flows); the rises at which members stop;
  a flow-controlled member's control state and speed (D6's speed rule); the default head range
  and grid (§5.3); the duty check (§5.4).
- **Refusals** (§5.6): one project per ``NOT_A_STATION`` reason, the order of the errors, and
  that no 400 quotes a submitted value.

Rises within ``STOP_CLEARANCE`` of a member's stopping band are left out of the grid checks and
tested on their own (``check_stop``): with Crane tees the head at a dead leg's tee port is any
value between two readings (``element_laws.zero_flow_limits``), so a pump at zero flow there may
be reported running or stopped (CLAUDE.md D13: the same answer). Splits within
``CRANE_CLEARANCE`` of a Crane step are left out too.

PG11 is adapted: no case was found whose duty check disagrees. The duty's rise is solved first
from the case's own solve, and wherever v1's rules leave a drooping member without a state the
case's own solve does not converge either (measured: ``drooping_project`` with R2's level from
18 to 21 m). The test checks instead that the group curve reports those rises as not converged,
naming the member, and agrees with the closed form on either side.

**Slice 4b, the group system curve** (curve 'system'; §3.4, §7, §9.2; cases PGS1–PGS12, by the
same rules): with every link inside the station closed and the station's flow Q forced from S
to D, H_sys(Q) = EGL(D) − EGL(S). Every fixture's outside is a chain of lines from R1 to S and
from D to R2, so H_sys(Q) = H_R2 − H_R1 + Σ h_line(Q) (``group_system_rise``) at every flow of
the grid (D6), whatever the station holds: ideal or Crane tees, a member off, at another speed
or on a flow setpoint, a check valve or an active PRV in a leg (each against the base case's
points to 10⁻⁹ m). Other routes to the same rise: ``/solve`` with the members holding flow
setpoints that sum to Q (the forced-split construction, 10⁻⁹ m), ``/system-curve`` for a
station of one pump (bit for bit, with the messages in the station's words), the group curve
crossing it at the duty, and EPANET 2.2 on the outside alone. An FCV outside: the open-valve
closed form below its setpoint, ``beyond_limit`` above it, its switch at the duty. The grid and
default range, scenarios, the methods' count, the errors in order and no 400 quoting a value.
"""

import copy
import itertools
import re
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import derivations_pump_groups as dg
from tests.reference import derivations_pumps as dp
from tests.reference import element_laws as el
from tests.reference.case_format import builtin_glycol, custom_fluid, flow_control

GROUP = "/api/v1/pump-group-curve"
SOLVE = "/api/v1/solve"
RELATIVE = 0.005
HEAD_FLOOR = 0.01  # m
FLOW_FLOOR = el.QTOL  # m³/s: a zero flow
IDENTITY = 1.0e-9
"""Relative (and absolute in m or m³/s below 1): the duty's identities with /solve's values."""
STATE_MARGIN = el.STATE_MARGIN
"""m: a status is checked only this far from the rise at which it changes."""
NU = dg.NU

# --------------------------------------------------------------------------- the API

_addresses = itertools.count(1)


class Api:
    """POST through the app from a client address of its own, changed every 40 requests: the
    rate limit (60 a minute per client) is never reached, and no bucket is shared with the rest
    of the suite."""

    def __init__(self) -> None:
        self._client = self._new()
        self._sent = 0

    @staticmethod
    def _new() -> TestClient:
        n = next(_addresses)
        return TestClient(app, client=(f"10.75.{n // 256 % 256}.{n % 256}", 50000))

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self._sent == 40:
            self._client, self._sent = self._new(), 0
        self._sent += 1
        response: httpx.Response = self._client.post(path, json=body)
        return response

    def group(
        self, project: Project | dict[str, Any], pump_ids: Sequence[str], **options: Any
    ) -> dict[str, Any]:
        response = self.post(GROUP, group_body(project, pump_ids, **options))
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        return data

    def solve(self, project: Project | dict[str, Any]) -> dict[str, Any]:
        body = {"project": as_json(project), "options": {"includeSystemCurve": False}}
        response = self.post(SOLVE, body)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        state: dict[str, Any] = response.json()["solvedState"]
        assert state["converged"], state["convergence"]["message"]
        return state


@pytest.fixture(scope="module")
def api() -> Api:
    return Api()


def as_json(project: Project | dict[str, Any]) -> dict[str, Any]:
    if isinstance(project, Project):
        data: dict[str, Any] = project.model_dump(mode="json", by_alias=True, exclude_none=True)
        return data
    return project


def group_body(
    project: Project | dict[str, Any], pump_ids: Sequence[str], **options: Any
) -> dict[str, Any]:
    return {"project": as_json(project), "pumpIds": list(pump_ids), **options}


# --------------------------------------------------------------------------- comparisons


def flow_ok(got: float | None, want: float) -> bool:
    return got is not None and abs(got - want) <= max(RELATIVE * abs(want), FLOW_FLOOR)


def head_ok(got: float | None, want: float) -> bool:
    return got is not None and abs(got - want) <= max(RELATIVE * abs(want), HEAD_FLOOR)


def same(got: float | None, want: float) -> bool:
    return got is not None and abs(got - want) <= IDENTITY * max(1.0, abs(want))


def speed_ok(got: float, want: float, curve: Any, q: float) -> bool:
    """D6's speed rule: within 0.5 % (relative), and the head it implies, s²H₀(Q/s), within
    0.01 m of the reference's."""
    implied = el.pump_head(curve, got, q)
    reference = el.pump_head(curve, want, q)
    return abs(got - want) <= RELATIVE * want and abs(implied - reference) <= HEAD_FLOOR


def by_id(members: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {m["pumpId"]: m for m in members}


def duty_point(response: dict[str, Any]) -> dict[str, Any]:
    points: list[dict[str, Any]] = [p for p in response["points"] if p["isDuty"]]
    [point] = points
    return point


def station_of(
    response: dict[str, Any],
    inlet: tuple[str, str | None],
    outlet: tuple[str, str | None],
    arrangement: str,
    members: list[str],
    components: list[str],
    connections: list[str],
) -> None:
    station = response["station"]
    assert station["inlet"] == {"componentId": inlet[0], "portId": inlet[1]}
    assert station["outlet"] == {"componentId": outlet[0], "portId": outlet[1]}
    assert station["arrangement"] == arrangement
    assert station["memberIds"] == members
    assert station["interiorComponentIds"] == components
    assert station["interiorConnectionIds"] == connections


def check_response(
    response: dict[str, Any],
    project: Project,
    num_points: int,
    *,
    head_min: float | None = None,
    head_max: float | None = None,
    allow_unconverged: bool = False,
) -> None:
    """The response's own rules (§5.1, §5.3, §5.4): the grid (numPoints evenly spaced rises over
    the head range, plus the duty's rise when it lies inside and is not one of them), points in
    rise order, members in member order, continuity at S, beyondData, the duty check."""
    assert response["converged"] is True
    assert response["message"] == ""
    duty = response["duty"]
    low, high = response["headRange"]["min"], response["headRange"]["max"]
    assert response["headRange"]["unit"] == "m"
    if head_min is not None:
        assert low == head_min
    if head_max is not None:
        assert high == head_max
    points = response["points"]
    rises = [p["head"] for p in points]
    assert rises == sorted(rises)
    assert len(set(rises)) == len(rises)
    grid = np.linspace(low, high, num_points)
    duty_inside = low <= duty["head"] <= high
    duty_on_grid = any(abs(g - duty["head"]) <= IDENTITY * max(1.0, abs(g)) for g in grid)
    assert len(points) == num_points + (1 if duty_inside and not duty_on_grid else 0)
    flagged = [p for p in points if p["isDuty"]]
    if duty_inside:
        assert len(flagged) == 1
        assert flagged[0]["head"] == duty["head"]
    else:
        assert flagged == []
    others = [p["head"] for p in points if not (p["isDuty"] and not duty_on_grid)]
    assert len(others) == num_points
    for got, want in zip(others, grid, strict=True):
        assert abs(got - want) <= IDENTITY * max(1.0, abs(want)), (got, want)
    member_ids = response["station"]["memberIds"]
    arrangement = response["station"]["arrangement"]
    curves = curves_of(project)
    for point in points:
        if not point["converged"]:
            assert allow_unconverged, point
            assert point["flow"] is None
            assert point["members"] == []
            assert point["reason"] == "not_converged"
            assert point["message"]
            continue
        assert point["flow"] is not None
        assert point["reason"] is None
        assert point["message"] == ""
        assert point["componentIds"] == []
        members = point["members"]
        assert [m["pumpId"] for m in members] == member_ids
        flows = [m["flow"] for m in members]
        scale = max(abs(point["flow"]), *(abs(f) for f in flows), 1.0e-3)
        if arrangement == "parallel":
            assert abs(point["flow"] - sum(flows)) <= IDENTITY * scale, point
        elif arrangement == "series":
            for f in flows:
                assert abs(point["flow"] - f) <= IDENTITY * scale, point
        for m in members:
            if m["status"] == "off":
                assert m["flow"] == 0.0
            if m["status"] != "running" or abs(m["flow"]) <= FLOW_FLOOR:
                continue
            curve = curves[m["pumpId"]]
            x = m["flow"] / m["speed"]
            x_min, x_max = curve.points[0].flow, curve.points[-1].flow
            if min(abs(x - x_min), abs(x - x_max)) > 1.0e-9:
                assert m["beyondData"] is (not x_min <= x <= x_max), (point["head"], m)
    check = response["dutyCheck"]
    if duty_inside:
        at_duty = flagged[0]
        assert check["agrees"] is True, check["message"]
        assert check["message"]
        assert check["flow"] == at_duty["flow"]
        assert [(m["pumpId"], m["flow"]) for m in check["members"]] == [
            (m["pumpId"], m["flow"]) for m in at_duty["members"]
        ]


def curves_of(project: Project) -> dict[str, PumpCurve]:
    """Each pump's rated curve, by pump id."""
    library = {c.id: c for c in project.pump_library}
    return {c.id: library[c.curve_id] for c in project.components if c.type == "pump"}


def check_duty_against_solve(
    response: dict[str, Any], state: dict[str, Any], inlet_key: str, outlet_key: str, q_st: float
) -> list[str]:
    """The duty's identities with the case's own solve (§3.2, §5.4): Q_st, ΔH_st, EGL(S) and each
    member's status, speed, flow and head as ``/solve`` reports them."""
    duty = response["duty"]
    nodes = state["nodeResults"]
    problems = []
    if not same(duty["flow"], q_st):
        problems.append(f"duty flow {duty['flow']!r} vs the solve's {q_st!r}")
    rise = nodes[outlet_key]["egl"] - nodes[inlet_key]["egl"]
    if not same(duty["head"], rise):
        problems.append(f"duty rise {duty['head']!r} vs the solve's {rise!r}")
    if not same(duty["inletEgl"], nodes[inlet_key]["egl"]):
        problems.append(f"inlet EGL {duty['inletEgl']!r} vs {nodes[inlet_key]['egl']!r}")
    for m in duty["members"]:
        pr = state["pumpResults"][m["pumpId"]]
        if m["status"] != pr["status"] or m["speed"] != pr["speed"]:
            problems.append(f"{m['pumpId']}: {m['status']} {m['speed']} vs {pr}")
        if not same(m["flow"], pr["operatingFlow"]):
            problems.append(f"{m['pumpId']} flow {m['flow']!r} vs {pr['operatingFlow']!r}")
        if m["head"] is not None and not same(m["head"], pr["operatingHead"]):
            problems.append(f"{m['pumpId']} head {m['head']!r} vs {pr['operatingHead']!r}")
    return problems


def tee_path_loss(state: dict[str, Any], tee_id: str, port_in: str, port_out: str) -> float:
    """The EGL loss along a tee's path port_in → port_out, as ``/solve`` reports it
    (``pathHeadLosses`` is keyed by the path's port that is not the combined port)."""
    branch = state["branchResults"][tee_id]
    combined = branch["combinedPortId"]
    assert combined in (port_in, port_out), (tee_id, combined, port_in, port_out)
    loss: float = branch["pathHeadLosses"][port_out if combined == port_in else port_in]
    return loss


Way = Sequence[tuple[str, ...]]
"""A member's way from S to D: ("link", id), ("valve", id) and ("tee", id, port_in, port_out)."""


def way_loss(state: dict[str, Any], way: Way) -> float:
    total = 0.0
    for step in way:
        if step[0] == "link":
            total += state["linkResults"][step[1]]["headLoss"]
        elif step[0] == "valve":
            total += state["valveResults"][step[1]]["headLoss"]
        else:
            total += tee_path_loss(state, step[1], step[2], step[3])
    return total


def check_route_losses(
    response: dict[str, Any], state: dict[str, Any], ways: dict[str, Way]
) -> list[str]:
    """§2.4's identities: each running member's route loss is the sum of the losses /solve
    reports along its way (10⁻⁹ m), and H_i − route loss = ΔH_st; shares Q_i/Q_st."""
    duty = response["duty"]
    problems = []
    for m in duty["members"]:
        want = way_loss(state, ways[m["pumpId"]])
        if abs(m["routeHeadLoss"] - want) > 1.0e-9:
            problems.append(f"{m['pumpId']} route loss {m['routeHeadLoss']!r} vs {want!r}")
        if abs(m["head"] - m["routeHeadLoss"] - duty["head"]) > 1.0e-9:
            problems.append(f"{m['pumpId']}: H − route loss is not the rise")
        if not same(m["share"], m["flow"] / duty["flow"]):
            problems.append(f"{m['pumpId']} share {m['share']!r}")
    if abs(sum(m["share"] for m in duty["members"]) - 1.0) > 1.0e-9:
        problems.append("the shares do not sum to 1")
    return problems


def check_ladder_points(
    response: dict[str, Any],
    ladder: dg.Ladder,
    skip: Sequence[tuple[float, float]] = (),
) -> int:
    """Every point of the group curve against ``ladder_state`` (D6): the station's flow, each
    member's flow, its status where its flow is not zero or its stop is clear, and a running
    member's head s²H₀(Q/s) (§3.3). Rises within STOP_CLEARANCE of a band in ``skip`` and
    splits near a Crane step are left out (module docstring). Returns the points checked."""
    failures: list[str] = []
    checked = 0
    top = response["headRange"]["max"]
    for point in response["points"]:
        rise = point["head"]
        if any(lo - dg.STOP_CLEARANCE <= rise <= hi + dg.STOP_CLEARANCE for lo, hi in skip):
            continue
        want = dg.ladder_state(ladder, rise)
        if not dg.clear_of_crane_steps(ladder, want):
            continue
        checked += 1
        assert point["converged"], point["message"]
        if not flow_ok(point["flow"], want.total):
            failures.append(f"rise {rise:.6g}: station flow {point['flow']!r} vs {want.total!r}")
        members = by_id(point["members"])
        for k, leg in enumerate(ladder.legs):
            m = members[leg.pump_id]
            q = want.flows[k]
            if not flow_ok(m["flow"], q):
                failures.append(f"rise {rise:.6g}: {leg.pump_id} flow {m['flow']!r} vs {q!r}")
            if leg.status == "off":
                status = "off"
            elif k in want.running and q > FLOW_FLOOR:
                status = "running"
            elif abs(rise - top) <= STATE_MARGIN:
                continue  # at the top of the range a member at zero flow: a label (D13)
            else:
                status = "running" if k in want.running else "no_flow"
            if m["status"] != status:
                failures.append(f"rise {rise:.6g}: {leg.pump_id} {m['status']} vs {status}")
            if status == "running":
                head = want.member_head(ladder, k)
                if not head_ok(m["head"], head):
                    failures.append(f"rise {rise:.6g}: {leg.pump_id} head {m['head']!r}")
    assert not failures, "\n".join(failures)
    return checked


def check_stop(
    api: Api,
    project: Project,
    pump_ids: list[str],
    ladder: dg.Ladder,
    k: int,
    running: list[int],
    guess: float,
) -> tuple[float, float]:
    """Where member k stops (§2.5): r_run, the rise at which its running flow reaches 0 with the
    legs ``running`` on (``stop_rise`` from the running side), and r_dead, the rise from which
    the zero-flow reading of ``branch_losses`` puts the head across it at its shutoff head (the
    same rise with ideal tees). Below min(r_run, r_dead) − STATE_MARGIN it runs, with the flows
    of ``ladder_point``; above r_run + STATE_MARGIN it has no running state, so it carries no
    flow and the others carry ``ladder_point``'s flows without it; above max(r_run, r_dead) +
    STATE_MARGIN its status is no_flow (the rule closes a pump whose head would exceed its
    shutoff head). Between, a zero-flow member may be labelled either way (D13). Returns
    (r_run, r_dead)."""
    r_run = dg.stop_rise(ladder, k, running, guess)
    r_dead = dg.stop_rise(ladder, k, running, guess, q_k=0.0)
    # 9 rises from r_run − 0.43 m to max(r_run, r_dead) + 0.37 m: none at r_run itself, where
    # the member's flow is exactly zero and its status flips (a knife edge, left out).
    response = api.group(
        project,
        pump_ids,
        headMin=r_run - 0.43,
        headMax=max(r_run, r_dead) + 0.37,
        numPoints=9,
    )
    others = [j for j in running if j != k]
    failures = []
    for point in response["points"]:
        rise = point["head"]
        assert point["converged"], point["message"]
        members = by_id(point["members"])
        member = members[ladder.legs[k].pump_id]
        if rise < min(r_run, r_dead) - STATE_MARGIN:
            want = dg.ladder_point(ladder, [*others, k], rise)
            if member["status"] != "running":
                failures.append(f"rise {rise:.6g}: {member['pumpId']} is {member['status']}")
        elif rise > r_run + STATE_MARGIN:
            want = dg.ladder_point(ladder, others, rise)
            if rise > max(r_run, r_dead) + STATE_MARGIN and member["status"] != "no_flow":
                failures.append(f"rise {rise:.6g}: {member['pumpId']} is {member['status']}")
        else:
            continue
        for j, leg in enumerate(ladder.legs):
            if not flow_ok(members[leg.pump_id]["flow"], want.flows[j]):
                failures.append(
                    f"rise {rise:.6g}: {leg.pump_id} flow {members[leg.pump_id]['flow']!r} "
                    f"vs {want.flows[j]!r}"
                )
    assert not failures, "\n".join(failures)
    return r_run, r_dead


# --------------------------------------------------------------------------- PG1


def test_pg1_identical_pumps_on_symmetric_legs(api: Api) -> None:
    """Q(ΔH) = 2q with H(q) − h_LA1(q) − h_LA2(q) = ΔH (ideal tees); each share 0.5."""
    project = dg.symmetric_project()
    response = api.group(project, ["PA", "PB"], numPoints=9)
    station_of(
        response,
        ("T1", "run_inlet"),
        ("T2", "run_outlet"),
        "parallel",
        ["PA", "PB"],
        ["T1", "PA", "PB", "T2"],
        ["LA1", "LA2", "LB1", "LB2"],
    )
    check_response(response, project, 9, head_min=0.0, head_max=45.0)
    curve = dp.curve_a()
    leg = dg.Leg("PA", curve, 1.0, (dg.SYMMETRIC_SUCTION,), (dg.SYMMETRIC_DISCHARGE,))
    failures = []
    for point in response["points"]:
        q = dg.leg_flow_alone(leg, point["head"])
        if not flow_ok(point["flow"], 2.0 * q):
            failures.append(f"rise {point['head']:.6g}: {point['flow']!r} vs {2.0 * q!r}")
        for m in point["members"]:
            if not flow_ok(m["flow"], q):
                failures.append(f"rise {point['head']:.6g}: {m['pumpId']} {m['flow']!r}")
            if q > FLOW_FLOOR and not head_ok(m["head"], el.pump_head(curve, 1.0, q)):
                failures.append(f"rise {point['head']:.6g}: {m['pumpId']} head {m['head']!r}")
    assert not failures, "\n".join(failures)
    ladder = dg.Ladder((leg, leg), "ideal", dg.SYMMETRIC_INLET.d, dg.SYMMETRIC_OUTLET.d)
    outside = dg.Outside(3.0, 22.0, dg.SYMMETRIC_INLET, dg.SYMMETRIC_OUTLET)
    want = dg.ladder_duty(ladder, outside, [0.02, 0.02])
    duty = response["duty"]
    assert flow_ok(duty["flow"], want.total)
    assert head_ok(duty["head"], want.rise)
    assert head_ok(duty["inletEgl"], want.inlet_egl)
    for m in duty["members"]:
        assert m["status"] == "running"
        assert flow_ok(m["flow"], want.flows[0])
        assert abs(m["share"] - 0.5) <= 1.0e-9
        # route loss = H(q) − ΔH = the leg's own losses at q
        assert head_ok(m["routeHeadLoss"], leg.losses(m["flow"]))
    a, b = duty["members"]
    assert abs(a["routeHeadLoss"] - b["routeHeadLoss"]) <= 1.0e-9
    assert duty["interstageHeadLoss"] is None


# --------------------------------------------------------------------------- PG2


def test_pg2_dissimilar_speeds_with_ideal_tees(api: Api) -> None:
    """``pumps_in_parallel``: each leg's equation at each rise (ideal tees: the legs meet at one
    head on each side); PB stops at its shutoff head s²H₀(0) = 0.85² × 45 m = 32.5125 m."""
    case = dp.pumps_in_parallel()
    project = case.project
    response = api.group(project, ["PB", "PA"], numPoints=13)
    station_of(
        response,
        ("T1", "run_inlet"),
        ("T2", "run_outlet"),
        "parallel",
        ["PA", "PB"],
        ["T1", "PA", "PB", "T2"],
        ["LA1", "LA2", "LB1", "LB2"],
    )
    check_response(response, project, 13, head_min=0.0, head_max=45.0)
    ladder, _ = dg.parallel_ladder(project)
    shutoff_b = el.shutoff_head(dp.curve_a(), 0.85)
    assert shutoff_b == pytest.approx(32.5125, abs=1.0e-12)  # the proposal's number, verified
    assert check_ladder_points(response, ladder, skip=[(shutoff_b, shutoff_b)]) >= 12
    # The duty against the derivation of the case (derivations_pumps.pumps_in_parallel)
    exp = case.expected
    duty = response["duty"]
    assert flow_ok(duty["flow"], exp.flows["L1"])
    assert head_ok(duty["head"], exp.egl["T2:run_outlet"] - exp.egl["T1:run_inlet"])
    assert head_ok(duty["inletEgl"], exp.egl["T1:run_inlet"])
    members = by_id(duty["members"])
    for pid, conn in (("PA", "LA1"), ("PB", "LB1")):
        assert flow_ok(members[pid]["flow"], exp.flows[conn])
        assert head_ok(members[pid]["head"], float(exp.pumps[pid]["operatingHead"]))
    # Around PB's stop: running below, no flow at and above, the rule's no_flow above.
    near = api.group(
        project, ["PA", "PB"], headMin=shutoff_b - 0.5, headMax=shutoff_b + 0.5, numPoints=5
    )
    failures = []
    for point in near["points"]:
        rise = point["head"]
        pb = by_id(point["members"])["PB"]
        if rise < shutoff_b - STATE_MARGIN:
            want = dg.ladder_state(ladder, rise)
            if pb["status"] != "running" or not flow_ok(pb["flow"], want.flows[0]):
                failures.append(f"rise {rise:.6g}: PB {pb}")
        elif rise >= shutoff_b - 1.0e-12:
            if abs(pb["flow"]) > FLOW_FLOOR:
                failures.append(f"rise {rise:.6g}: PB flow {pb['flow']!r}")
            if rise > shutoff_b + el.HTOL and pb["status"] != "no_flow":
                failures.append(f"rise {rise:.6g}: PB is {pb['status']}")
            if not same(pb["head"], rise):  # no flow on its leg: its head is the rise
                failures.append(f"rise {rise:.6g}: PB head {pb['head']!r}")
    assert any(p["head"] == pytest.approx(shutoff_b, abs=1e-12) for p in near["points"])
    assert not failures, "\n".join(failures)


# --------------------------------------------------------------------------- PG3

PARALLEL_WAYS: dict[str, Way] = {
    "PA": [
        ("tee", "T1", "run_inlet", "run_outlet"),
        ("link", "LA1"),
        ("link", "LA2"),
        ("tee", "T2", "run_inlet", "run_outlet"),
    ],
    "PB": [
        ("tee", "T1", "run_inlet", "branch"),
        ("link", "LB1"),
        ("link", "LB2"),
        ("tee", "T2", "branch", "run_outlet"),
    ],
}


def test_pg3_crane_tees_duty_route_losses_and_curve(api: Api) -> None:
    """PG2 with Crane tees: the duty equals /solve's (identities) and the derivation's (D6);
    each route loss is the sum of /solve's losses along the member's way (10⁻⁹ m); the group
    curve at the duty's rise gives /solve's member flows; the curve against the closed form;
    PB's stop."""
    project = dg.with_crane_tees(dp.pumps_in_parallel().project)
    state = api.solve(project)
    response = api.group(project, ["PA", "PB"], numPoints=13)
    check_response(response, project, 13, head_min=0.0, head_max=45.0)
    assert response["methodVersion"] == state["methodVersion"]
    problems = check_duty_against_solve(
        response, state, "T1:run_inlet", "T2:run_outlet", state["linkResults"]["L1"]["flow"]
    )
    problems += check_route_losses(response, state, PARALLEL_WAYS)
    assert not problems, "\n".join(problems)
    at_duty = by_id(duty_point(response)["members"])
    for pid in ("PA", "PB"):
        assert flow_ok(at_duty[pid]["flow"], state["pumpResults"][pid]["operatingFlow"])
    ladder, outside = dg.parallel_ladder(project)
    want = dg.ladder_duty(ladder, outside, [0.015, 0.035])
    duty = response["duty"]
    assert flow_ok(duty["flow"], want.total)
    assert head_ok(duty["head"], want.rise)
    assert head_ok(duty["inletEgl"], want.inlet_egl)
    members = by_id(duty["members"])
    assert flow_ok(members["PB"]["flow"], want.flows[0])
    assert flow_ok(members["PA"]["flow"], want.flows[1])
    r_run, r_dead = check_stop(api, project, ["PA", "PB"], ladder, 0, [0, 1], 32.0)
    band = (min(r_run, r_dead), max(r_run, r_dead))
    assert check_ladder_points(response, ladder, skip=[band]) >= 10


# --------------------------------------------------------------------------- PG4


def test_pg4_series(api: Api) -> None:
    """``pumps_in_series``: Q from H_A(Q) + H_B(Q) − h_L2(Q) = ΔH; the interstage loss at the
    duty is h_L2(Q) ≈ 5.0737 m; shares H_i/ΣH."""
    case = dp.pumps_in_series()
    project = case.project
    state = api.solve(project)
    response = api.group(project, ["PB", "PA"], numPoints=9)
    station_of(
        response,
        ("PA", "suction"),
        ("PB", "discharge"),
        "series",
        ["PA", "PB"],
        ["PA", "PB"],
        ["L2"],
    )
    check_response(response, project, 9, head_min=0.0)
    ca, sa, _, _ = dg.pump_of(project, "PA")
    cb, sb, _, _ = dg.pump_of(project, "PB")
    assert same(response["headRange"]["max"], 45.0 + 0.81 * 30.0)
    l2 = dg.line_of(project, "L2")

    def h_a(q: float) -> float:
        return el.pump_head(ca, sa, q)

    def h_b(q: float) -> float:
        return el.pump_head(cb, sb, q)

    failures = []
    for point in response["points"]:
        q = dg.series_flow([h_a, h_b], l2, point["head"])
        if not flow_ok(point["flow"], q):
            failures.append(f"rise {point['head']:.6g}: {point['flow']!r} vs {q!r}")
        if q <= FLOW_FLOOR:
            continue
        members = by_id(point["members"])
        for pid, law in (("PA", h_a), ("PB", h_b)):
            if members[pid]["status"] != "running" or not head_ok(members[pid]["head"], law(q)):
                failures.append(f"rise {point['head']:.6g}: {pid} {members[pid]}")
    assert not failures, "\n".join(failures)
    duty = response["duty"]
    exp = case.expected
    q = exp.flows["L1"]
    assert flow_ok(duty["flow"], q)
    assert head_ok(duty["head"], exp.egl["PB:discharge"] - exp.egl["PA:suction"])
    assert head_ok(duty["inletEgl"], exp.egl["PA:suction"])
    interstage = duty["interstageHeadLoss"]
    assert head_ok(interstage, l2.head_loss(q, NU))
    assert abs(interstage - 5.0737) < 1.0e-4  # the proposal's number (§2.4), verified
    heads = [m["head"] for m in duty["members"]]
    assert abs(sum(heads) - duty["head"] - interstage) <= 1.0e-9
    assert abs(interstage - state["linkResults"]["L2"]["headLoss"]) <= 1.0e-9
    for m in duty["members"]:
        assert same(m["share"], m["head"] / sum(heads))
        assert m["routeHeadLoss"] is None
    problems = check_duty_against_solve(
        response, state, "PA:suction", "PB:discharge", state["linkResults"]["L1"]["flow"]
    )
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- PG5


def test_pg5_series_with_a_flow_controlled_member(api: Api) -> None:
    """PG4 with PB holding 0.024 m³/s (CLAUDE.md D11): the group curve holds Q_set while
    F(s_lo, Q_set) ≤ H_B ≤ F(s_max, Q_set), H_B = ΔH − H_A(Q_set) + h_L2(Q_set); above the band
    PB is the fixed pump at s_max, below it at s_min; PB's control state and speed."""
    base = dp.pumps_in_series().project
    project = dg.series_controlled_project(base)
    ca, sa, _, _ = dg.pump_of(project, "PA")
    cb, s_max, _, control = dg.pump_of(project, "PB")
    assert control is not None
    l2 = dg.line_of(project, "L2")
    band_lo, band_hi = dg.control_band(ca, sa, cb, control, s_max, l2)
    q_set = control.setpoint
    default = api.group(project, ["PA", "PB"], numPoints=11)
    check_response(default, project, 11, head_min=0.0)
    assert same(default["headRange"]["max"], 45.0 + s_max**2 * 30.0)  # PB at its maximum speed
    near = api.group(
        project, ["PA", "PB"], headMin=band_lo - 2.0, headMax=band_hi + 2.0, numPoints=9
    )
    check_response(near, project, 9, head_min=band_lo - 2.0, head_max=band_hi + 2.0)
    failures = []
    states = set()
    for point in [*default["points"], *near["points"]]:
        rise = point["head"]
        want = dg.controlled_series_point(ca, sa, cb, control, s_max, l2, rise)
        if not flow_ok(point["flow"], want.flow):
            failures.append(f"rise {rise:.6g}: {point['flow']!r} vs {want.flow!r}")
        members = by_id(point["members"])
        pa, pb = members["PA"], members["PB"]
        if pa["controlState"] is not None:
            failures.append(f"rise {rise:.6g}: PA control state {pa['controlState']}")
        if want.flow <= FLOW_FLOOR or min(abs(rise - band_lo), abs(rise - band_hi)) < STATE_MARGIN:
            continue
        states.add(want.state)
        if pb["controlState"] != want.state or pb["status"] != "running":
            failures.append(f"rise {rise:.6g}: PB {pb['status']} {pb['controlState']}")
        if not speed_ok(pb["speed"], want.speed, cb, want.flow):
            failures.append(f"rise {rise:.6g}: PB speed {pb['speed']!r} vs {want.speed!r}")
        if want.state == "active" and abs(point["flow"] - q_set) > IDENTITY * q_set:
            failures.append(f"rise {rise:.6g}: {point['flow']!r} is not the setpoint")
        if not head_ok(pb["head"], want.head_b):
            failures.append(f"rise {rise:.6g}: PB head {pb['head']!r} vs {want.head_b!r}")
    assert not failures, "\n".join(failures)
    assert states == {"active", "max_speed", "min_speed"}
    # The duty: Q_set, with ΔH_st = H_R2 − H_R1 + h_L1(Q_set) + h_L3(Q_set) inside the band.
    l1, l3 = dg.line_of(project, "L1"), dg.line_of(project, "L3")
    h1, h2 = dg.reservoir_head(project, "R1"), dg.reservoir_head(project, "R2")
    rise = h2 - h1 + l1.head_loss(q_set, NU) + l3.head_loss(q_set, NU)
    assert band_lo + STATE_MARGIN < rise < band_hi - STATE_MARGIN
    want = dg.controlled_series_point(ca, sa, cb, control, s_max, l2, rise)
    duty = default["duty"]
    assert flow_ok(duty["flow"], q_set)
    assert head_ok(duty["head"], rise)
    assert head_ok(duty["inletEgl"], h1 - l1.head_loss(q_set, NU))
    pb = by_id(duty["members"])["PB"]
    assert speed_ok(pb["speed"], want.speed, cb, q_set)
    assert by_id(duty_point(default)["members"])["PB"]["controlState"] == "active"


# --------------------------------------------------------------------------- PG6

LADDER_WAYS: dict[str, Way] = {
    "P1": [
        ("tee", "TS1", "run_inlet", "branch"),
        ("link", "S1"),
        ("link", "D1a"),
        ("valve", "CV1"),
        ("link", "D1b"),
        ("tee", "TD1", "branch", "run_outlet"),
    ],
    "P2": [
        ("tee", "TS1", "run_inlet", "run_outlet"),
        ("link", "H1"),
        ("tee", "TS2", "run_inlet", "branch"),
        ("link", "S2"),
        ("link", "D2a"),
        ("valve", "CV2"),
        ("link", "D2b"),
        ("tee", "TD2", "branch", "run_outlet"),
        ("link", "H2"),
        ("tee", "TD1", "run_inlet", "run_outlet"),
    ],
    "P3": [
        ("tee", "TS1", "run_inlet", "run_outlet"),
        ("link", "H1"),
        ("tee", "TS2", "run_inlet", "run_outlet"),
        ("link", "S3"),
        ("link", "D3a"),
        ("valve", "CV3"),
        ("link", "D3b"),
        ("tee", "TD2", "run_inlet", "run_outlet"),
        ("link", "H2"),
        ("tee", "TD1", "run_inlet", "run_outlet"),
    ],
}


def test_pg6_three_pump_crane_ladder_with_check_valves(api: Api) -> None:
    """The 3-pump ladder (``ladder_project``): the duty and each member's flow from the
    derivation's own solve; route losses along shared headers from /solve; the group curve; P3
    stops first, then P2, each at the rise its zero-flow equation gives."""
    project = dg.ladder_project()
    state = api.solve(project)
    response = api.group(project, ["P3", "P1", "P2"], numPoints=11)
    station_of(
        response,
        ("TS1", "run_inlet"),
        ("TD1", "run_outlet"),
        "parallel",
        ["P1", "P2", "P3"],
        ["TS1", "TS2", "P1", "CV1", "P2", "CV2", "P3", "CV3", "TD2", "TD1"],
        ["S1", "D1a", "D1b", "S2", "D2a", "D2b", "S3", "D3a", "D3b", "H1", "H2"],
    )
    check_response(response, project, 11, head_min=0.0, head_max=45.0)
    ladder, outside = dg.ladder(), dg.ladder_outside()
    want = dg.ladder_duty(ladder, outside, [0.05, 0.03, 0.015])
    duty = response["duty"]
    assert flow_ok(duty["flow"], want.total)
    assert head_ok(duty["head"], want.rise)
    assert head_ok(duty["inletEgl"], want.inlet_egl)
    members = by_id(duty["members"])
    for k, leg in enumerate(ladder.legs):
        assert flow_ok(members[leg.pump_id]["flow"], want.flows[k]), leg.pump_id
    problems = check_duty_against_solve(
        response, state, "TS1:run_inlet", "TD1:run_outlet", state["linkResults"]["L0"]["flow"]
    )
    problems += check_route_losses(response, state, LADDER_WAYS)
    assert not problems, "\n".join(problems)
    r3 = check_stop(api, project, ["P1", "P2", "P3"], ladder, 2, [0, 1, 2], 28.0)
    r2 = check_stop(api, project, ["P1", "P2", "P3"], ladder, 1, [0, 1], 38.0)
    assert max(r3) < min(r2)  # P3 stops first
    assert max(r2) < el.shutoff_head(ladder.legs[1].curve, ladder.legs[1].speed)
    bands = [(min(r3), max(r3)), (min(r2), max(r2))]
    assert check_ladder_points(response, ladder, skip=bands) >= 6


# --------------------------------------------------------------------------- PG7


@pytest.mark.parametrize(
    ("case", "pump_id"),
    [(dp.pump_single_pipe_reduced_speed, "PU1"), (dp.pumps_in_parallel, "PB")],
)
def test_pg7_a_station_of_one_pump(api: Api, case: Callable[[], Any], pump_id: str) -> None:
    """One member: S and D are its own suction and discharge ports, and the group curve is the
    inverse of s²H₀(Q/s) (brentq on the PCHIP and its end tangent); its share is 1 and its route
    loss 0; the default range is [0, s²H₀(0)]."""
    reference = case()
    project = reference.project
    response = api.group(project, [pump_id], numPoints=9)
    station_of(
        response,
        (pump_id, "suction"),
        (pump_id, "discharge"),
        "parallel",
        [pump_id],
        [pump_id],
        [],
    )
    curve, speed, _, _ = dg.pump_of(project, pump_id)
    check_response(response, project, 9, head_min=0.0)
    assert same(response["headRange"]["max"], el.shutoff_head(curve, speed))
    failures = []
    for point in response["points"]:
        q = dg.pump_flow_at_head(curve, speed, point["head"])
        [m] = point["members"]
        if not flow_ok(point["flow"], q) or not flow_ok(m["flow"], q):
            failures.append(f"rise {point['head']:.6g}: {point['flow']!r} vs {q!r}")
        if not same(m["head"], point["head"]):
            failures.append(f"rise {point['head']:.6g}: head {m['head']!r}")
    assert not failures, "\n".join(failures)
    beyond = [p for p in response["points"] if p["members"][0]["beyondData"]]
    assert beyond, "the range reaches flows beyond the curve's points"
    duty = response["duty"]
    [m] = duty["members"]
    assert m["share"] == 1.0
    assert abs(m["routeHeadLoss"]) <= 1.0e-9
    assert same(duty["head"], m["head"])
    exp = reference.expected
    assert head_ok(duty["head"], exp.egl[f"{pump_id}:discharge"] - exp.egl[f"{pump_id}:suction"])
    assert flow_ok(duty["flow"], float(exp.pumps[pump_id]["operatingFlow"]))


def test_pg7_a_pump_on_a_loop_is_a_station_of_one_pump(api: Api) -> None:
    """A pump circulating round a loop whose only way to the reservoir is a tee's branch: the
    loop is the pump's outside, joining its two ports through the tee, so the pump between its
    own ports is a station, and its group curve is the inverse of s²H₀(Q/s) at every rise."""
    project = dg.pump_on_a_loop_project()
    response = api.group(project, ["PA"], numPoints=9)
    station_of(response, ("PA", "suction"), ("PA", "discharge"), "parallel", ["PA"], ["PA"], [])
    curve, speed, _, _ = dg.pump_of(project, "PA")
    failures = []
    for point in response["points"]:
        q = dg.pump_flow_at_head(curve, speed, point["head"])
        if not flow_ok(point["flow"], q):
            failures.append(f"rise {point['head']:.6g}: {point['flow']!r} vs {q!r}")
    assert not failures, "\n".join(failures)
    assert response["dutyCheck"]["agrees"]


# --------------------------------------------------------------------------- PG8


def test_pg8_a_reservoir_as_the_inlet(api: Api) -> None:
    """Two pumps drawing from one reservoir through its two ports: S is the reservoir taken
    whole (portId null), EGL(S) is its head, and the curve is the ladder's from S."""
    project = dg.reservoir_inlet_project()
    state = api.solve(project)
    response = api.group(project, ["PA", "PB"], numPoints=9)
    station_of(
        response,
        ("R1", None),
        ("T2", "run_outlet"),
        "parallel",
        ["PA", "PB"],
        ["PA", "PB", "T2"],
        ["LA1", "LA2", "LB1", "LB2"],
    )
    check_response(response, project, 9, head_min=0.0, head_max=45.0)
    ladder, outside = dg.reservoir_inlet_ladder()
    want = dg.ladder_duty(ladder, outside, [0.02, 0.03])
    duty = response["duty"]
    assert duty["inletEgl"] == 3.0  # the reservoir's head: elevation 0 + level 3 m
    assert flow_ok(duty["flow"], want.total)
    assert head_ok(duty["head"], want.rise)
    assert same(duty["flow"], state["boundaryResults"]["R1"]["outflow"])
    members = by_id(duty["members"])
    assert flow_ok(members["PB"]["flow"], want.flows[0])
    assert flow_ok(members["PA"]["flow"], want.flows[1])
    shutoff_b = ladder.legs[0].shutoff
    assert check_ladder_points(response, ladder, skip=[(shutoff_b, shutoff_b)]) >= 8


# --------------------------------------------------------------------------- PG9

_PARALLEL = dp.pumps_in_parallel().project

NOT_A_STATION: list[tuple[str, Callable[[], Project], list[str], str, set[str] | None]] = [
    (
        "assigned_flow_between_member_tees",
        lambda: dg.header_tap_project("assigned_flow"),
        ["PA", "PB"],
        "ASSIGNED_FLOW_INSIDE",
        {"AF"},
    ),
    (
        "other_pump_between_members",
        lambda: dg.series_chain_project(middle_pump=True),
        ["PA", "PB"],
        "OTHER_PUMP_INSIDE",
        {"PX"},
    ),
    (
        "members_on_two_suction_reservoirs",
        dg.two_reservoir_project,
        ["PA", "PB"],
        "DIFFERENT_BOUNDARIES",
        {"R1", "R3"},
    ),
    (
        "members_delivering_to_two_reservoirs",
        dg.two_outlet_project,
        ["PA", "PB"],
        "DIFFERENT_BOUNDARIES",
        {"R2", "R3"},
    ),
    (
        "reservoir_tapped_off_the_header",
        lambda: dg.header_tap_project("reservoir"),
        ["PA", "PB"],
        "FIXED_HEAD_INSIDE",
        {"R2", "RX"},
    ),
    (
        "reservoir_on_the_header",
        lambda: dg.header_tap_project("reservoir_inline"),
        ["PA", "PB"],
        "FIXED_HEAD_INSIDE",
        {"R2", "RX"},
    ),
    (
        "member_reversed",
        lambda: dg.series_chain_project(reverse_b=True),
        ["PA", "PB"],
        "MEMBERS_OPPOSED",
        None,
    ),
    (
        "active_prv_in_a_leg",
        lambda: dg.pressure_control_leg_project(_PARALLEL, "prv"),
        ["PA", "PB"],
        "PRESSURE_CONTROL_INSIDE",
        {"V1"},
    ),
    (
        "active_psv_in_a_leg",
        lambda: dg.pressure_control_leg_project(_PARALLEL, "psv"),
        ["PA", "PB"],
        "PRESSURE_CONTROL_INSIDE",
        {"V1"},
    ),
    (
        "one_place",
        dg.dead_end_project,
        ["PA"],
        "NO_SEPARATING_PORTS",
        {"PA"},
    ),
    (
        "three_places",
        dg.three_place_project,
        ["PA", "PB"],
        "NO_SEPARATING_PORTS",
        None,
    ),
]


@pytest.mark.parametrize(
    ("build", "pump_ids", "code", "component_ids"),
    [pytest.param(*case[1:], id=case[0]) for case in NOT_A_STATION],
)
def test_pg9_not_a_station(
    api: Api,
    build: Callable[[], Project],
    pump_ids: list[str],
    code: str,
    component_ids: set[str] | None,
) -> None:
    """One project per reason (§5.6): 422 NOT_A_STATION with that reason alone, naming the
    elements at fault (by hand from the topology). A reversed member is named relative to the
    other, so either or both may be listed; the three places of ``three_place_project`` are
    the suction header's way in and each discharge's way out."""
    project = build()
    response = api.post(GROUP, group_body(project, pump_ids))
    assert response.status_code == 422, response.text
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "NOT_A_STATION"
    [issue] = data["issues"]
    assert issue["code"] == code
    assert issue["message"]
    ids = set(issue["componentIds"])
    if component_ids is not None:
        assert ids == component_ids
    elif code == "MEMBERS_OPPOSED":
        assert ids
        assert ids <= {"PA", "PB"}
    else:
        assert len(ids) == 3
        assert "T1" in ids or "R1" in ids
        assert ids <= {"R1", "T1", "PA", "PB", "TA", "TB", "TC", "TD"}
    for cid in ids:
        assert cid in issue["message"]


@pytest.mark.parametrize("status", ["failed_open", "failed_closed"])
def test_pg9_a_prv_that_is_not_active_is_allowed(api: Api, status: str) -> None:
    """Only an active PRV or PSV is refused (§5.6): one failed open or closed has no setpoint
    to hold, and the station holds it."""
    project = dg.pressure_control_leg_project(_PARALLEL, "prv", status)  # type: ignore[arg-type]
    response = api.group(project, ["PA", "PB"], numPoints=5)
    assert "V1" in response["station"]["interiorComponentIds"]
    check_response(response, project, 5)


def _bad_material(project: Project) -> dict[str, Any]:
    """The project with L1's pipe of an unknown material: a topology issue (CLAUDE.md D7)."""
    data = copy.deepcopy(as_json(project))
    conn = next(c for c in data["connections"] if c["id"] == "L1")
    conn["piping"]["pipes"][0] = {
        "materialId": "unobtainium",
        "schedule": "40",
        "nominalSize": 0.1016,
        "length": 5.0,
    }
    return data


def test_pg9_errors_come_in_order(api: Api) -> None:
    """§5.6 and the contract: the request (400) before the scenario (404) before the fluid
    (400) before unknown pumps (404, one UNKNOWN_PUMP per id) before the topology (422) before
    NOT_A_STATION (422) before an empty head range (400 EMPTY_HEAD_RANGE)."""
    tapped = dg.header_tap_project("assigned_flow")  # not a station
    broken = _bad_material(tapped)  # ... with a topology issue too

    def post(project: Any, ids: list[str], **options: Any) -> tuple[int, dict[str, Any]]:
        r = api.post(GROUP, group_body(project, ids, **options))
        return r.status_code, r.json()

    status, data = post(broken, ["PA", "PA", "NOPE"])
    assert (status, data["error"]) == (400, "VALIDATION_ERROR"), data
    cold = tapped.model_copy(
        update={"fluid": builtin_glycol("propylene_glycol", 240.0, 0.3)}
    )  # below its property source's range (as test_scenarios' FLUID_ERROR case)
    with_scenarios = {**as_json(cold), "scenarios": []}
    status, data = post(with_scenarios, ["NOPE"], scenarioId="S9")
    assert (status, data["error"]) == (404, "NOT_FOUND"), data
    assert "UNKNOWN_PUMP" not in {i["code"] for i in data["issues"]}
    status, data = post(cold, ["NOPE"])
    assert (status, data["error"]) == (400, "FLUID_ERROR"), data
    status, data = post(broken, ["PA", "NOPE", "TB"])
    assert (status, data["error"]) == (404, "NOT_FOUND"), data
    assert [i["code"] for i in data["issues"]] == ["UNKNOWN_PUMP", "UNKNOWN_PUMP"]
    assert "NOPE" in data["issues"][0]["message"]
    assert "TB" in data["issues"][1]["message"]
    status, data = post(broken, ["PA", "PB"], headMin=100.0)
    assert (status, data["error"]) == (422, "TOPOLOGY_ERROR"), data
    status, data = post(tapped, ["PA", "PB"], headMin=100.0)
    assert (status, data["error"]) == (422, "NOT_A_STATION"), data
    status, data = post(_PARALLEL, ["PA", "PB"], headMin=100.0)
    assert status == 400, data
    assert [i["code"] for i in data["issues"]] == ["EMPTY_HEAD_RANGE"]


def test_pg9_no_400_quotes_a_submitted_value(api: Api) -> None:
    """SDD §5.1.2: a request error never echoes what was submitted."""
    project = as_json(_PARALLEL)
    bodies: list[tuple[dict[str, Any], list[str]]] = [
        ({"pumpIds": ["QX7Z9", "QX7Z9"]}, ["QX7Z9"]),
        ({"pumpIds": ["PA"], "headMin": 77.7777, "headMax": 66.6666}, ["77.7777", "66.6666"]),
        ({"pumpIds": ["PA"], "numPoints": 1234}, ["1234"]),
        ({"pumpIds": [f"ZQ{i}W" for i in range(7)]}, [f"ZQ{i}W" for i in range(7)]),
        ({"pumpIds": ["PA"], "curve": "sysXYZ"}, ["sysXYZ"]),
        ({"pumpIds": ["PA"], "headMin": -23456.5}, ["23456"]),
        ({"pumpIds": ["PA", "PB"], "headMin": 98.7654}, ["98.7654"]),
    ]
    for options, secrets in bodies:
        response = api.post(GROUP, {"project": project, **options})
        assert response.status_code == 400, (options, response.text)
        for secret in secrets:
            assert secret not in response.text, (options, response.text)


# --------------------------------------------------------------------------- PG10


def test_pg10_an_off_member(api: Api) -> None:
    """PB off: it is left out of the shares (share 0, no route loss), it is off at every point,
    and the group curve is PA's leg alone; with PA off instead, the default range ends at PB's
    shutoff head (an off member adds nothing) and the curve is PB's leg alone."""
    base = dp.pumps_in_parallel().project
    for off, on in (("PB", "PA"), ("PA", "PB")):
        project = dg.with_component(base, off, status="off")
        state = api.solve(project)
        response = api.group(project, ["PA", "PB"], numPoints=9)
        ladder, outside = dg.parallel_ladder(project)
        k_on = next(k for k, leg in enumerate(ladder.legs) if leg.pump_id == on)
        shutoff_on = ladder.legs[k_on].shutoff
        check_response(response, project, 9, head_min=0.0)
        assert same(response["headRange"]["max"], shutoff_on)
        duty = response["duty"]
        members = by_id(duty["members"])
        assert members[off]["status"] == "off"
        assert members[off]["flow"] == 0.0
        assert members[off]["share"] == 0.0
        assert members[off]["routeHeadLoss"] is None
        assert same(members[on]["share"], 1.0)
        want = dg.ladder_duty(ladder, outside, [0.03], running=[k_on])
        assert flow_ok(duty["flow"], want.total)
        assert head_ok(duty["head"], want.rise)
        problems = check_duty_against_solve(
            response, state, "T1:run_inlet", "T2:run_outlet", state["linkResults"]["L1"]["flow"]
        )
        assert not problems, "\n".join(problems)
        for point in response["points"]:
            m = by_id(point["members"])[off]
            assert (m["status"], m["flow"], m["controlState"]) == ("off", 0.0, None)
            q = dg.leg_flow_alone(ladder.legs[k_on], point["head"])
            assert flow_ok(point["flow"], q), (off, point["head"], point["flow"], q)


# --------------------------------------------------------------------------- PG11


def test_pg11_a_drooping_member(api: Api) -> None:
    """A drooping member PD (``curve_droop``: 40 m at shutoff, 43 m at its hump) beside a larger
    pump, between ideal tees. Below r_lo it runs on the falling side of its hump; from r_lo to
    its shutoff head 40 m no state satisfies v1's rules (``no_state_band``): those points are
    not converged and name PD (CLAUDE.md D13); above 40 m it is closed (no_flow) and the curve
    is PA's leg alone. The duty check agrees for a duty below the band, and a case whose duty
    lies in the band does not converge at all (so no duty check can disagree, module
    docstring)."""
    project = dg.drooping_project(2.0)
    ladder = dg.drooping_ladder()
    leg_d = ladder.legs[0]
    r_lo, shutoff = dg.no_state_band(leg_d)
    peak = dg.drooping_peak(leg_d.curve, leg_d.speed)[1]
    assert shutoff < peak  # a falling-side running state exists in the band physically
    low, high = r_lo - 1.0, shutoff + 1.0
    response = api.group(project, ["PA", "PD"], headMin=low, headMax=high, numPoints=9)
    check_response(response, project, 9, head_min=low, head_max=high, allow_unconverged=True)
    band = [p for p in response["points"] if r_lo + STATE_MARGIN < p["head"] < shutoff]
    assert band
    for point in band:
        assert point["converged"] is False
        assert point["reason"] == "not_converged"
        assert "PD" in point["componentIds"]
        assert "PD" in point["message"]
    clear = [
        p for p in response["points"] if p["head"] < r_lo - STATE_MARGIN or p["head"] > shutoff
    ]
    assert len(clear) >= 3
    for point in clear:
        assert point["converged"], point["message"]
        want = dg.ladder_state(ladder, point["head"])
        members = by_id(point["members"])
        assert flow_ok(point["flow"], want.total)
        assert flow_ok(members["PD"]["flow"], want.flows[0])
        assert members["PD"]["status"] == ("running" if 0 in want.running else "no_flow")
    duty = api.group(project, ["PA", "PD"], numPoints=5)
    check_response(duty, project, 5)
    assert duty["duty"]["head"] < r_lo
    in_band = api.group(dg.drooping_project(19.0), ["PA", "PD"], numPoints=5)
    assert in_band["converged"] is False
    assert (in_band["duty"], in_band["dutyCheck"], in_band["points"]) == (None, None, [])
    assert "PD" in in_band["message"]


# --------------------------------------------------------------------------- other stations


def test_a_mixed_station(api: Api) -> None:
    """Two legs of two pumps in series (2 × 2): arrangement mixed, no shares or route losses;
    the curve from each leg's Σ s²H₀(q/s) − losses = ΔH; the default range ends at the larger
    leg's sum of shutoff heads."""
    project = dg.mixed_project()
    ids = ["PA", "PA2", "PB", "PB2"]
    response = api.group(project, ids, numPoints=9)
    station_of(
        response,
        ("T1", "run_inlet"),
        ("T2", "run_outlet"),
        "mixed",
        ids,
        ["T1", *ids, "T2"],
        ["LA1", "LA2", "LA3", "LB1", "LB2", "LB3"],
    )
    check_response(response, project, 9, head_min=0.0)
    ladder, outside = dg.mixed_ladder()
    assert same(response["headRange"]["max"], max(leg.shutoff for leg in ladder.legs))
    duty = response["duty"]
    assert duty["interstageHeadLoss"] is None
    for m in duty["members"]:
        assert (m["share"], m["routeHeadLoss"]) == (None, None)
    want = dg.ladder_duty(ladder, outside, [0.02, 0.03])
    assert flow_ok(duty["flow"], want.total)
    assert head_ok(duty["head"], want.rise)
    legs = {"PB": 0, "PB2": 0, "PA": 1, "PA2": 1}
    failures = []
    for point in response["points"]:
        want_point = dg.ladder_state(ladder, point["head"])
        if not flow_ok(point["flow"], want_point.total):
            failures.append(f"rise {point['head']:.6g}: {point['flow']!r}")
        for m in point["members"]:
            q = want_point.flows[legs[m["pumpId"]]]
            if not flow_ok(m["flow"], q):
                failures.append(f"rise {point['head']:.6g}: {m['pumpId']} {m['flow']!r}")
            if q > FLOW_FLOOR:
                curve, speed, _, _ = dg.pump_of(project, m["pumpId"])
                if not head_ok(m["head"], el.pump_head(curve, speed, q)):
                    failures.append(f"rise {point['head']:.6g}: {m['pumpId']} {m['head']!r}")
    assert not failures, "\n".join(failures)


def test_a_case_that_does_not_converge_has_no_duty_and_no_points(api: Api) -> None:
    """Two FCVs in series outside the station, set alike (over-controlled, CLAUDE.md D11): the
    case's solve does not converge, so 200 with converged false, the station, no duty, no duty
    check, no points and no head range, and a message naming the controls."""
    project = dg.over_controlled_project(_PARALLEL)
    body = {"project": as_json(project), "options": {"includeSystemCurve": False}}
    response = api.post(SOLVE, body)
    assert response.json()["solvedState"]["converged"] is False
    data = api.group(project, ["PA", "PB"])
    assert data["converged"] is False
    assert data["station"]["inlet"] == {"componentId": "T1", "portId": "run_inlet"}
    assert data["station"]["outlet"] == {"componentId": "T2", "portId": "run_outlet"}
    assert (data["duty"], data["dutyCheck"], data["points"], data["headRange"]) == (
        None,
        None,
        [],
        None,
    )
    assert "FCV1" in data["message"]
    assert "FCV2" in data["message"]


# --------------------------------------------------------------------------- scenarios


def test_a_scenario_gives_the_hand_edited_projects_result(api: Api) -> None:
    """``scenarioId`` (D15): the response equals the hand-edited project's in every field but
    ``scenario``, which records the override applied."""
    base = dp.pumps_in_parallel().project
    scenarios = [
        ("S1", "speed", 0.95, 0.85, "PB", dg.with_component(base, "PB", speed=0.95)),
        ("S2", "status", "off", "on", "PA", dg.with_component(base, "PA", status="off")),
    ]
    project = {
        **as_json(base),
        "scenarios": [
            {
                "id": sid,
                "name": f"Scenario {sid}",
                "overrides": [
                    {"kind": "component", "componentId": cid, "field": field, "value": value}
                ],
            }
            for sid, field, value, _, cid, _ in scenarios
        ],
    }
    for sid, field, value, base_value, cid, hand in scenarios:
        got = api.group(project, ["PA", "PB"], numPoints=7, scenarioId=sid)
        want = api.group(hand, ["PA", "PB"], numPoints=7)
        record = got.pop("scenario")
        assert want.pop("scenario") is None
        assert got == want, sid
        assert record["id"] == sid
        [override] = record["overrides"]
        assert override["state"] == "applied"
        assert (override["value"], override["baseValue"]) == (value, base_value)
        assert override["override"]["componentId"] == cid
        assert override["override"]["field"] == field


# --------------------------------------------------------------------------- methods


def test_the_methods_section_names_the_station(api: Api) -> None:
    """The methods section (§5.5): titled "Pump group", naming S, D and the members, with the
    method version of /solve."""
    project = dp.pumps_in_parallel().project
    state = api.solve(project)
    response = api.group(project, ["PA", "PB"], numPoints=5)
    methods = response["methods"]
    assert methods["title"] == "Pump group"
    text = " ".join(methods["items"])
    for name in ("T1", "T2", "PA", "PB"):
        assert name in text
    assert response["methodVersion"] == state["methodVersion"]
    assert state["methodVersion"] in text


def test_the_methods_section_counts_the_rises(api: Api) -> None:
    """The "Points:" item states how many rises were solved: numPoints evenly spaced, "plus the
    duty's rise" when the duty's is added (the grid of §5.3, as the response's own points), so
    the number stated plus one for an added duty's rise is the number of points returned."""
    base = dp.pumps_in_parallel().project
    all_off = dg.with_component(dg.with_component(base, "PA", status="off"), "PB", status="off")
    problems = []
    for project, options in (
        (base, {"numPoints": 5}),  # the duty's rise added: 6 points
        (base, {"numPoints": 7, "headMin": 0.0, "headMax": 30.0}),  # added: 8 points
        (base, {"numPoints": 5, "headMin": 0.0, "headMax": 20.0}),  # outside: 5 points
        (all_off, {"numPoints": 5}),  # the duty's rise (19 m) is the top of the grid: 5 points
    ):
        response = api.group(project, ["PA", "PB"], **options)
        [item] = [i for i in response["methods"]["items"] if i.startswith("Points:")]
        found = re.match(r"Points: (\d+) rises", item)
        assert found, item
        count = int(found.group(1))
        stated = count + (1 if "plus the duty's rise" in item else 0)
        if stated != len(response["points"]):
            problems.append(f"{options}: '{item[:60]}' for {len(response['points'])} points")
    assert not problems, "\n".join(problems)


# =========================================================================== slice 4b
# The group system curve (curve 'system'; proposal §3.4, §7 and §9.2; CLAUDE.md D21, D10, D6):
# H_sys(Q) = EGL(D) − EGL(S) with every link inside the station held closed and the station's
# flow Q forced from S to D, the outside on its own laws and rules. Cases PGS1–PGS12, written
# from the proposal, the models (``models/pump_groups.py``, ``models/api.py``) and the brief's
# contract, without reading ``services/``; the closed forms are ``derivations_pump_groups``'
# ``group_system_rise`` (every fixture's outside is a chain of lines from R1 to S and from D to
# R2), and the other routes to the same rise are ``/solve`` with the members forced to a split
# (``forced_split_project``), ``/system-curve`` for a station of one pump, and EPANET's outside.

SYSTEM = "/api/v1/system-curve"

NO_HEAD_FIELDS: dict[str, Any] = {
    "componentIds": [],
    "assignedFlowNodeIds": [],
    "limitFlow": None,
    "passedFlow": None,
    "openHead": None,
    "openHeadBound": None,
    "startsTried": [],
}
"""A point with a rise carries none of the fields that say why a point has none."""

POINT_FIELDS = (
    "flow",
    "head",
    "converged",
    "reason",
    "componentIds",
    "assignedFlowNodeIds",
    "limitFlow",
    "passedFlow",
    "openHead",
    "openHeadBound",
    "startsTried",
)
"""The fields a group system curve point shares with /system-curve's (all but the message, in
the station's words, and npshAvailable, which a group point has not)."""


def system_curve(
    api: Api, project: Project | dict[str, Any], pump_ids: Sequence[str], **options: Any
) -> dict[str, Any]:
    return api.group(project, pump_ids, curve="system", **options)


def check_system_response(
    response: dict[str, Any],
    num_points: int,
    *,
    flow_min: float = 0.0,
    flow_max: float | None = None,
) -> list[dict[str, Any]]:
    """The response's own rules for curve 'system' (the contract): no group-curve fields; the
    flow range (flowMin, default 0, to flowMax); numPoints evenly spaced flows in flow order,
    plus the duty's flow Q_st (isDuty) when it lies in the range and is not one of them (a grid
    flow equal to it is the duty's point); each point with a rise has none of the why-fields,
    each without one says why; no NPSHa; the system duty check reads the duty's point. Returns
    the grid's points (the added duty point left out)."""
    assert response["converged"] is True
    assert response["message"] == ""
    assert (response["dutyCheck"], response["points"], response["headRange"]) == (None, [], None)
    flow_range = response["flowRange"]
    assert flow_range["unit"] == "m³/s"
    low, high = flow_range["min"], flow_range["max"]
    assert low == flow_min
    if flow_max is not None:
        assert high == flow_max
    points = response["systemPoints"]
    flows = [p["flow"] for p in points]
    assert flows == sorted(flows)
    assert len(set(flows)) == len(flows)
    grid = np.linspace(low, high, num_points)
    q_st = response["duty"]["flow"]
    inside = low <= q_st <= high
    added = inside and not any(g == q_st for g in grid)
    assert len(points) == num_points + (1 if added else 0)
    flagged = [p for p in points if p["isDuty"]]
    if inside:
        assert len(flagged) == 1
        assert flagged[0]["flow"] == q_st
    else:
        assert flagged == []
    on_grid = [p for p in points if not (added and p["isDuty"])]
    for point, want in zip(on_grid, grid, strict=True):
        assert abs(point["flow"] - want) <= IDENTITY * max(1.0, abs(want)), (point["flow"], want)
    for point in points:
        assert "npshAvailable" not in point
        if point["head"] is None:
            assert point["converged"] is False, point
            assert point["reason"] is not None, point
            assert point["message"], point
            continue
        assert point["converged"] is True, point
        assert point["reason"] is None, point
        assert point["message"] == "", point
        assert {k: point[k] for k in NO_HEAD_FIELDS} == NO_HEAD_FIELDS, point
    check = response["systemDutyCheck"]
    assert check["message"]
    if inside:
        assert check["head"] == flagged[0]["head"]
    return on_grid


def closed_form_failures(
    points: Iterable[dict[str, Any]], h1: float, h2: float, lines: Sequence[Any]
) -> list[str]:
    """Each point against H_sys(Q) = H_R2 − H_R1 + Σ h_line(Q) (D6): every point must have a
    rise; at Q = 0 it is exactly the static rise (identity)."""
    failures = []
    for point in points:
        want = dg.group_system_rise(h1, h2, lines, point["flow"])
        if not head_ok(point["head"], want):
            failures.append(f"Q {point['flow']!r}: rise {point['head']!r} vs {want!r}")
        elif point["flow"] == 0.0 and not same(point["head"], h2 - h1):
            failures.append(f"Q 0: rise {point['head']!r} vs the static rise {h2 - h1!r}")
    return failures


def in_station_words(message: str) -> list[str]:
    """What a point's message must not say (the contract): the pump's sides and head, which
    the station's inlet, outlet and rise replace. Another pump may be named as an element."""
    text = message.lower()
    return [w for w in ("pump's", "suction", "discharge", "across the pump") if w in text]


def reservoir_inlet_outside(project: Project) -> tuple[float, float, tuple[Any, ...]]:
    _, outside = dg.reservoir_inlet_ladder()
    assert outside.inlet is None  # S is R1 taken whole: no line from R1 to S
    return outside.h1, outside.h2, dg.outside_lines(outside)


def ladder_outside_lines(project: Project) -> tuple[float, float, tuple[Any, ...]]:
    outside = dg.ladder_outside()
    return outside.h1, outside.h2, dg.outside_lines(outside)


# --------------------------------------------------------------------------- PGS1


def test_pgs1_parallel_with_ideal_tees(api: Api) -> None:
    """``pumps_in_parallel``: the station is T1:run_inlet → T2:run_outlet, so the outside is L1
    (R1 → T1) and L2 (T2 → R2): H_sys(Q) = H_R2 − H_R1 + h_L1(Q) + h_L2(Q) at every flow of the
    default grid (41 flows from 0), H_sys(0) = 22 − 3 = 19 m; the duty's flow is the case's."""
    case = dp.pumps_in_parallel()
    project = case.project
    response = system_curve(api, project, ["PB", "PA"])
    station_of(
        response,
        ("T1", "run_inlet"),
        ("T2", "run_outlet"),
        "parallel",
        ["PA", "PB"],
        ["T1", "PA", "PB", "T2"],
        ["LA1", "LA2", "LB1", "LB2"],
    )
    check_system_response(response, 41)
    h1, h2, lines = dg.parallel_outside(project)
    assert (h1, h2) == (3.0, 22.0)
    points = response["systemPoints"]
    assert points[0]["flow"] == 0.0
    failures = closed_form_failures(points, h1, h2, lines)
    assert not failures, "\n".join(failures)
    assert flow_ok(response["duty"]["flow"], case.expected.flows["L1"])
    assert response["systemDutyCheck"]["agrees"] is True
    titles = [i for i in response["methods"]["items"] if i.startswith("Group system curve")]
    assert len(titles) == 1


# --------------------------------------------------------------------------- PGS2


def test_pgs2_crane_tees_change_nothing_outside(api: Api) -> None:
    """PGS1 with Crane tees: the tees are inside, so the same closed form, and the same rises
    as with ideal tees to 10⁻⁹ m at the same flows; the duty moves (Crane tees lose more), the
    curve does not."""
    base = dp.pumps_in_parallel().project
    crane = dg.with_crane_tees(base)
    grid = {"flowMin": 0.0, "flowMax": 0.12, "numPoints": 9}
    ideal = system_curve(api, base, ["PA", "PB"], **grid)
    tees = system_curve(api, crane, ["PA", "PB"], **grid)
    ideal_points = check_system_response(ideal, 9, flow_max=0.12)
    crane_points = check_system_response(tees, 9, flow_max=0.12)
    for a, b in zip(ideal_points, crane_points, strict=True):
        assert a["flow"] == b["flow"]
        assert abs(a["head"] - b["head"]) <= IDENTITY, (a, b)
    h1, h2, lines = dg.parallel_outside(crane)
    failures = closed_form_failures(tees["systemPoints"], h1, h2, lines)
    assert not failures, "\n".join(failures)
    assert not flow_ok(tees["duty"]["flow"], ideal["duty"]["flow"])  # the duty moved
    assert tees["systemDutyCheck"]["agrees"] is True


FORCED_SPLITS = (0.02, 0.028, 0.012)
"""PA's share of the forced 0.04 m³/s (PB the rest), m³/s (test inputs)."""


def test_pgs2_forced_splits_read_at_s_and_d(api: Api) -> None:
    """Proposal §9.2's forced-split construction with Crane tees: the members at speed 1 hold
    flow setpoints (CLAUDE.md D11) summing to Q = 0.04 m³/s in three splits; each /solve, both
    members regulating, passes Q through the station, its tee paths differ by the split, and its
    EGL(D) − EGL(S) is the group system curve's rise at Q to 10⁻⁹ m (and the closed form, D6)."""
    crane = dg.with_crane_tees(dp.pumps_in_parallel().project)
    q = 0.04
    response = system_curve(api, crane, ["PA", "PB"], flowMin=q, flowMax=2.0 * q, numPoints=5)
    check_system_response(response, 5, flow_min=q, flow_max=2.0 * q)
    [at_q] = [p for p in response["systemPoints"] if p["flow"] == q]
    h1, h2, lines = dg.parallel_outside(crane)
    assert head_ok(at_q["head"], dg.group_system_rise(h1, h2, lines, q))
    failures = []
    branch_losses = []
    for q_a in FORCED_SPLITS:
        setpoints = {"PA": q_a, "PB": q - q_a}
        state = api.solve(dg.forced_split_project(crane, q_a, q - q_a, 0.5))
        for pid, setpoint in setpoints.items():
            pr = state["pumpResults"][pid]
            assert pr["control"]["state"] == "active", (q_a, pid, pr["control"])
            assert same(pr["operatingFlow"], setpoint)
        assert same(state["linkResults"]["L1"]["flow"], q)
        nodes = state["nodeResults"]
        rise = nodes["T2:run_outlet"]["egl"] - nodes["T1:run_inlet"]["egl"]
        if abs(rise - at_q["head"]) > IDENTITY:
            failures.append(f"PA {q_a}: the solve's rise {rise!r} vs {at_q['head']!r}")
        branch_losses.append(tee_path_loss(state, "T1", "run_inlet", "branch"))
    assert not failures, "\n".join(failures)
    assert max(branch_losses) - min(branch_losses) > 0.5  # the insides differ


# --------------------------------------------------------------------------- PGS3


def test_pgs3_series(api: Api) -> None:
    """``pumps_in_series``: the station is PA:suction → PB:discharge (L2 inside), so the outside
    is L1 and L3: H_sys(Q) = H_R2 − H_R1 + h_L1(Q) + h_L3(Q), H_R2 − H_R1 = 43 − 2 = 41 m."""
    project = dp.pumps_in_series().project
    response = system_curve(api, project, ["PB", "PA"], numPoints=9)
    station_of(
        response,
        ("PA", "suction"),
        ("PB", "discharge"),
        "series",
        ["PA", "PB"],
        ["PA", "PB"],
        ["L2"],
    )
    check_system_response(response, 9)
    h1, h2, lines = dg.series_outside(project)
    assert (h1, h2) == (2.0, 43.0)
    failures = closed_form_failures(response["systemPoints"], h1, h2, lines)
    assert not failures, "\n".join(failures)
    assert response["systemDutyCheck"]["agrees"] is True


# --------------------------------------------------------------------------- PGS4

PARALLEL_GRID = {"flowMin": 0.0, "flowMax": 0.12, "numPoints": 9}
SERIES_GRID = {"flowMin": 0.0, "flowMax": 0.06, "numPoints": 7}

Outsider = Callable[[Project], tuple[float, float, tuple[Any, ...]]]


def _parallel() -> Project:
    return dp.pumps_in_parallel().project


def _series() -> Project:
    return dp.pumps_in_series().project


INVARIANCE: list[
    tuple[str, Callable[[], Project], Callable[[Project], Project], dict[str, Any], Outsider, bool]
] = [
    (
        "parallel, PB off",
        _parallel,
        lambda p: dg.with_component(p, "PB", status="off"),
        PARALLEL_GRID,
        dg.parallel_outside,
        True,
    ),
    (
        "parallel, PA at speed 0.9",
        _parallel,
        lambda p: dg.with_component(p, "PA", speed=0.9),
        PARALLEL_GRID,
        dg.parallel_outside,
        True,
    ),
    (
        "parallel, a check valve in PB's leg",
        _parallel,
        dg.leg_check_valve_project,
        PARALLEL_GRID,
        dg.parallel_outside,
        False,
    ),
    (
        "parallel with Crane tees, the members on flow setpoints",
        lambda: dg.with_crane_tees(_parallel()),
        lambda p: dg.forced_split_project(p, 0.02, 0.015, 0.5),
        PARALLEL_GRID,
        dg.parallel_outside,
        True,
    ),
    (
        "series, PB off",
        _series,
        lambda p: dg.with_component(p, "PB", status="off"),
        SERIES_GRID,
        dg.series_outside,
        True,
    ),
    (
        "series, PA at speed 0.8",
        _series,
        lambda p: dg.with_component(p, "PA", speed=0.8),
        SERIES_GRID,
        dg.series_outside,
        True,
    ),
]


@pytest.mark.parametrize(
    ("build", "change", "grid", "outside", "moves"),
    [pytest.param(*case[1:], id=case[0]) for case in INVARIANCE],
)
def test_pgs4_the_curve_does_not_depend_on_the_members(
    api: Api,
    build: Callable[[], Project],
    change: Callable[[Project], Project],
    grid: dict[str, Any],
    outside: Outsider,
    moves: bool,
) -> None:
    """A member off, at another speed, on a flow setpoint, or a check valve in a member's leg:
    the station's ports are the same, and its system points equal the base case's at the same
    flows to 10⁻⁹ m with the same reasons (the interior is held closed); the duty moves (but
    for the check valve, which only adds a little loss), and its point lies on the same closed
    form wherever it moved to."""
    base = build()
    project = change(base)
    want = system_curve(api, base, ["PA", "PB"], **grid)
    got = system_curve(api, project, ["PA", "PB"], **grid)
    n = grid["numPoints"]
    want_points = check_system_response(want, n, flow_max=grid["flowMax"])
    got_points = check_system_response(got, n, flow_max=grid["flowMax"])
    for key in ("inlet", "outlet", "arrangement", "memberIds"):
        assert got["station"][key] == want["station"][key]
    failures = []
    for a, b in zip(want_points, got_points, strict=True):
        assert a["flow"] == b["flow"]
        if a["reason"] != b["reason"] or abs(a["head"] - b["head"]) > IDENTITY:
            failures.append(f"Q {a['flow']!r}: {b['head']!r} ({b['reason']}) vs {a['head']!r}")
    assert not failures, "\n".join(failures)
    if moves:
        assert not flow_ok(got["duty"]["flow"], want["duty"]["flow"]), got["duty"]
    h1, h2, lines = outside(project)
    failures = closed_form_failures(got_points, h1, h2, lines)
    assert not failures, "\n".join(failures)
    # The duty's point (when Q_st lies in the range: with PB off in series Q_st is −6.4e-34
    # m³/s, round-off below the range's 0, so no point is added) and the system duty check.
    check = got["systemDutyCheck"]
    assert check["agrees"] is True, check["message"]
    q_st = got["duty"]["flow"]
    assert abs(q_st) > FLOW_FLOOR or abs(q_st) <= 1.0e-15
    rise = dg.group_system_rise(h1, h2, lines, max(q_st, 0.0))
    assert head_ok(check["head"], rise), (check, rise)


# --------------------------------------------------------------------------- PGS5

ONE_PUMP_GRID = {"flowMin": 0.0, "flowMax": 0.06, "numPoints": 7}

ONE_PUMP: list[tuple[str, Callable[[], Project], str]] = [
    ("parallel PA", _parallel, "PA"),
    ("parallel PB", _parallel, "PB"),
    ("series PA", _series, "PA"),
    ("series PB", _series, "PB"),
    (
        "a flow-controlled PB",
        lambda: dg.with_component(_parallel(), "PB", control=flow_control(0.015, 0.5)),
        "PB",
    ),
    (
        "PA beside a flow-controlled PB",
        lambda: dg.with_component(_parallel(), "PB", control=flow_control(0.015, 0.5)),
        "PA",
    ),
    ("a flow-controlled PB in series", lambda: dg.series_controlled_project(_series()), "PB"),
    ("PA under an outlet FCV", lambda: dg.outlet_fcv_project(_parallel(), 0.037), "PA"),
]


@pytest.mark.parametrize(
    ("build", "pump_id"), [pytest.param(*case[1:], id=case[0]) for case in ONE_PUMP]
)
def test_pgs5_a_station_of_one_pump_is_its_system_curve(
    api: Api, build: Callable[[], Project], pump_id: str
) -> None:
    """A station of one pump lies between its own suction and discharge, and its group system
    curve is /system-curve's on the same grid (flowMin, flowMax and numPoints equal): the same
    flows, and bit for bit the same rises, reasons and the data the reasons quote, with the
    messages in the station's words; a flow-controlled member's control is replaced by the
    forced flow, another controlled pump keeps regulating. The duty's own point, solved warm
    from the case's solve, agrees with /system-curve at that flow to 10⁻⁹ m."""
    project = build()
    response = system_curve(api, project, [pump_id], **ONE_PUMP_GRID)
    station_of(
        response,
        (pump_id, "suction"),
        (pump_id, "discharge"),
        "parallel",
        [pump_id],
        [pump_id],
        [],
    )
    points = check_system_response(response, 7, flow_max=0.06)
    body = {"project": as_json(project), "pumpId": pump_id, **ONE_PUMP_GRID}
    reply = api.post(SYSTEM, body)
    assert reply.status_code == 200, reply.text
    pump_points = reply.json()["points"]
    failures = []
    for g, s in zip(points, pump_points, strict=True):
        assert g["flow"] == s["flow"]
        if g["isDuty"]:  # the grid's flow is the duty's: solved from the case's solve
            g_head, s_head = g["head"], s["head"]
            if g_head is None or s_head is None or abs(g_head - s_head) > IDENTITY:
                failures.append(f"Q {g['flow']!r} (duty): {g_head!r} vs {s_head!r}")
            continue
        differ = [k for k in POINT_FIELDS if g[k] != s[k]]
        if differ:
            failures.append(f"Q {g['flow']!r}: {differ}: {[(g[k], s[k]) for k in differ]}")
        if bool(g["message"]) != bool(s["message"]):
            failures.append(f"Q {g['flow']!r}: message {g['message']!r} vs {s['message']!r}")
        if in_station_words(g["message"]):
            failures.append(f"Q {g['flow']!r}: pump's words in {g['message']!r}")
    assert not failures, "\n".join(failures)
    q_st = response["duty"]["flow"]
    [duty_point] = [p for p in response["systemPoints"] if p["isDuty"]]
    assert duty_point["converged"], duty_point["message"]
    reply = api.post(SYSTEM, {**body, "flowMin": q_st, "flowMax": 2.0 * q_st, "numPoints": 5})
    assert reply.status_code == 200, reply.text
    first = reply.json()["points"][0]
    assert first["flow"] == q_st
    assert abs(duty_point["head"] - first["head"]) <= IDENTITY, (duty_point, first)


# --------------------------------------------------------------------------- PGS6


def test_pgs6_a_reservoir_as_the_inlet(api: Api) -> None:
    """Two pumps drawing from R1 through its two ports (PG8): S is R1 taken whole, so the
    outside is the delivery side only, L2 from T2 to R2: H_sys(Q) = H_R2 − H_R1 + h_L2(Q)
    (24 − 3 = 21 m at Q = 0), EGL(S) the reservoir's head."""
    project = dg.reservoir_inlet_project()
    response = system_curve(api, project, ["PA", "PB"], numPoints=9)
    station_of(
        response,
        ("R1", None),
        ("T2", "run_outlet"),
        "parallel",
        ["PA", "PB"],
        ["PA", "PB", "T2"],
        ["LA1", "LA2", "LB1", "LB2"],
    )
    check_system_response(response, 9)
    assert response["duty"]["inletEgl"] == 3.0
    h1, h2, lines = reservoir_inlet_outside(project)
    assert (h1, h2, len(lines)) == (3.0, 24.0, 1)
    failures = closed_form_failures(response["systemPoints"], h1, h2, lines)
    assert not failures, "\n".join(failures)
    assert response["systemDutyCheck"]["agrees"] is True


# --------------------------------------------------------------------------- PGS7

CROSSINGS: list[tuple[str, Callable[[], Project], list[str], Outsider]] = [
    ("parallel", _parallel, ["PA", "PB"], dg.parallel_outside),
    (
        "parallel_crane",
        lambda: dg.with_crane_tees(_parallel()),
        ["PA", "PB"],
        dg.parallel_outside,
    ),
    ("series", _series, ["PA", "PB"], dg.series_outside),
    ("reservoir_inlet", dg.reservoir_inlet_project, ["PA", "PB"], reservoir_inlet_outside),
    ("crane_ladder", dg.ladder_project, ["P1", "P2", "P3"], ladder_outside_lines),
]


@pytest.mark.parametrize(
    ("build", "pump_ids", "outside"), [pytest.param(*case[1:], id=case[0]) for case in CROSSINGS]
)
def test_pgs7_the_two_curves_cross_at_the_duty(
    api: Api, build: Callable[[], Project], pump_ids: list[str], outside: Outsider
) -> None:
    """The group system curve's point at Q_st has the duty's rise ΔH_st (10⁻⁹ m) and
    systemDutyCheck agrees; the group curve's point at ΔH_st has Q_st (D6) and dutyCheck agrees:
    both curves pass through the duty. Here H_sys rises with Q and the group curve's flow falls
    with the rise, so they cross once: along the group curve's points in rise order, H_sys(Q) −
    ΔH (the closed form at each point's flow) is positive below the duty's rise and negative
    above it."""
    project = build()
    system = system_curve(api, project, pump_ids, numPoints=9)
    check_system_response(system, 9)
    group = api.group(project, pump_ids, numPoints=9)
    check_response(group, project, 9)
    duty = system["duty"]
    assert group["duty"] == duty  # the case's own solve, read the same way
    [at] = [p for p in system["systemPoints"] if p["isDuty"]]
    assert at["flow"] == duty["flow"]
    assert abs(at["head"] - duty["head"]) <= IDENTITY, (at, duty)
    check = system["systemDutyCheck"]
    assert check["agrees"] is True, check["message"]
    assert check["head"] == at["head"]
    h1, h2, lines = outside(project)
    assert head_ok(at["head"], dg.group_system_rise(h1, h2, lines, at["flow"]))
    g_at = duty_point(group)
    assert g_at["head"] == duty["head"]
    assert flow_ok(g_at["flow"], duty["flow"])
    assert group["dutyCheck"]["agrees"] is True
    heads = [p["head"] for p in system["systemPoints"]]
    assert all(b > a for a, b in itertools.pairwise(heads)), heads
    flows = [p["flow"] for p in group["points"]]
    assert all(b <= a + FLOW_FLOOR for a, b in itertools.pairwise(flows)), flows
    above = [
        dg.group_system_rise(h1, h2, lines, p["flow"]) - p["head"] > 0.0
        for p in group["points"]
        if not p["isDuty"]
    ]
    assert above == sorted(above, reverse=True), above  # one sign change...
    assert above[0]
    assert not above[-1]
    rises = [p["head"] for p in group["points"] if not p["isDuty"]]
    k = above.index(False)
    assert rises[k - 1] < duty["head"] < rises[k]  # ...at the duty's rise


# --------------------------------------------------------------------------- PGS8

OUTLET_FCV_SETPOINT = 0.037
"""m³/s: the delivery FCV's setpoint (a test input), below the duty's unthrottled 0.0551."""


def test_pgs8_an_fcv_outside_the_station(api: Api) -> None:
    """An ideal FCV on the delivery line, outside the station, set below the duty's unthrottled
    flow. Below the setpoint it is wide open (no loss, CLAUDE.md D9) and H_sys is the closed
    form of L1, L2a and L2; above it every way from D back to S passes the FCV, which passes at
    most its setpoint that way: no steady state (beyond_limit, the FCV and the setpoint as
    limitFlow and passedFlow), in the station's words. The case's solve holds the setpoint, so
    Q_st is the setpoint and ΔH_st the group curve's rise at it; the duty's point is the FCV's
    switch, where the rise is undetermined from the open-valve rise up (valve_at_switch,
    openHeadBound 'lower'), and ΔH_st lies on that vertical stretch. The system duty check
    then has no rise to compare (head null, agrees false) and names the FCV."""
    base = dp.pumps_in_parallel().project
    q_f = OUTLET_FCV_SETPOINT
    assert q_f < 0.9 * dp.pumps_in_parallel().expected.flows["L1"]
    project = dg.outlet_fcv_project(base, q_f)
    response = system_curve(api, project, ["PA", "PB"], flowMin=0.0, flowMax=0.08, numPoints=9)
    station_of(
        response,
        ("T1", "run_inlet"),
        ("T2", "run_outlet"),
        "parallel",
        ["PA", "PB"],
        ["T1", "PA", "PB", "T2"],
        ["LA1", "LA2", "LB1", "LB2"],
    )
    points = check_system_response(response, 9, flow_max=0.08)
    h1, h2, lines = dg.outlet_fcv_outside(project)
    failures = []
    regimes = {"open": 0, "beyond": 0}
    for point in points:
        q = point["flow"]
        assert abs(q - q_f) >= 0.01 * q_f, q
        if q < q_f:
            regimes["open"] += 1
            failures += closed_form_failures([point], h1, h2, lines)
            continue
        regimes["beyond"] += 1
        got = {k: point[k] for k in ("head", "converged", "reason", "componentIds")}
        if got != {
            "head": None,
            "converged": False,
            "reason": "beyond_limit",
            "componentIds": ["FC"],
        }:
            failures.append(f"Q {q!r}: {got}")
        if not (same(point["limitFlow"], q_f) and same(point["passedFlow"], q_f)):
            failures.append(
                f"Q {q!r}: limit {point['limitFlow']!r}, passed {point['passedFlow']!r}"
            )
        if point["assignedFlowNodeIds"] or point["openHead"] is not None:
            failures.append(f"Q {q!r}: {point}")
        text = point["message"]
        if (
            "the station's outlet back to its inlet" not in text
            or "'FC'" not in text
            or "no steady state" not in text.lower()
            or "no way through" in text.lower()
            or "pump" in text.lower()
        ):
            failures.append(f"Q {q!r}: message {text!r}")
    assert not failures, "\n".join(failures)
    assert regimes["open"] >= 3, regimes
    assert regimes["beyond"] >= 3, regimes
    duty = response["duty"]
    assert same(duty["flow"], q_f)
    ladder, _ = dg.parallel_ladder(base)
    assert head_ok(duty["head"], dg.rise_at_station_flow(ladder, q_f, 20.0, 40.0))
    [at] = [p for p in response["systemPoints"] if p["isDuty"]]
    assert (at["head"], at["converged"], at["reason"]) == (None, False, "valve_at_switch")
    assert at["componentIds"] == ["FC"]
    assert at["openHeadBound"] == "lower"
    open_rise = dg.group_system_rise(h1, h2, lines, q_f)
    assert head_ok(at["openHead"], open_rise)
    assert duty["head"] > at["openHead"] + 1.0  # the throttled FCV takes the rest
    assert "undetermined" in at["message"]
    assert "'FC'" in at["message"]
    assert "pump" not in at["message"].lower()
    check = response["systemDutyCheck"]
    assert (check["head"], check["agrees"]) == (None, False)
    assert "'FC'" in check["message"]


# --------------------------------------------------------------------------- PGS9


def test_pgs9_an_active_prv_inside_refuses_only_the_group_curve(api: Api) -> None:
    """An active PRV in PA's discharge leg: curve 'group' is refused (422 NOT_A_STATION,
    PRESSURE_CONTROL_INSIDE naming it), curve 'system' is not: the PRV is inside, held closed,
    so the curve is PGS1's closed form; with no group curve the default flowMax is 1.2 × Q_st,
    Q_st the solve's flow in L1."""
    project = dg.pressure_control_leg_project(_PARALLEL, "prv")
    refused = api.post(GROUP, group_body(project, ["PA", "PB"]))
    assert refused.status_code == 422, refused.text
    data = refused.json()
    assert data["error"] == "NOT_A_STATION"
    assert [(i["code"], i["componentIds"]) for i in data["issues"]] == [
        ("PRESSURE_CONTROL_INSIDE", ["V1"])
    ]
    response = system_curve(api, project, ["PA", "PB"], numPoints=7)
    assert "V1" in response["station"]["interiorComponentIds"]
    assert response["station"]["inlet"] == {"componentId": "T1", "portId": "run_inlet"}
    assert response["station"]["outlet"] == {"componentId": "T2", "portId": "run_outlet"}
    check_system_response(response, 7)
    state = api.solve(project)
    q_st = state["linkResults"]["L1"]["flow"]
    assert same(response["duty"]["flow"], q_st)
    assert abs(response["flowRange"]["max"] - 1.2 * q_st) <= 1.0e-12 * q_st
    h1, h2, lines = dg.parallel_outside(project)
    failures = closed_form_failures(response["systemPoints"], h1, h2, lines)
    assert not failures, "\n".join(failures)
    assert response["systemDutyCheck"]["agrees"] is True


# --------------------------------------------------------------------------- PGS10

DEFAULT_RANGES: list[tuple[str, Callable[[], Project], dict[str, Any]]] = [
    ("parallel, default rises", _parallel, {"numPoints": 9}),
    ("parallel, rises 5-40 m", _parallel, {"numPoints": 7, "headMin": 5.0, "headMax": 40.0}),
    ("parallel, rises above the duty", _parallel, {"numPoints": 5, "headMin": 30.0}),
    (
        "Crane tees, rises 10-30 m",
        lambda: dg.with_crane_tees(_parallel()),
        {"numPoints": 6, "headMin": 10.0, "headMax": 30.0},
    ),
    ("series, default rises", _series, {"numPoints": 9}),
]


@pytest.mark.parametrize(
    ("build", "options"), [pytest.param(*case[1:], id=case[0]) for case in DEFAULT_RANGES]
)
def test_pgs10_the_default_flow_range(
    api: Api, build: Callable[[], Project], options: dict[str, Any]
) -> None:
    """Without flowMax the range is 0 to 1.2 × the largest of Q_st and the flows of the group
    curve that curve 'group' returns on the same headMin, headMax and numPoints (rises above
    the duty's: Q_st itself is the largest)."""
    project = build()
    system = system_curve(api, project, ["PA", "PB"], **options)
    group = api.group(project, ["PA", "PB"], **options)
    flows = [p["flow"] for p in group["points"] if p["flow"] is not None]
    largest = max(group["duty"]["flow"], *flows)
    if options.get("headMin", 0.0) > group["duty"]["head"]:
        assert largest == group["duty"]["flow"]
    assert abs(system["flowRange"]["max"] - 1.2 * largest) <= 1.0e-12 * largest
    check_system_response(system, options["numPoints"])


def test_pgs10_every_member_off_takes_the_fallback(api: Api) -> None:
    """Every member off: Q_st and every group-curve flow are 0 (within 10⁻⁶ m³/s), so flowMax
    is 1.2 × Σ (the curve's largest data flow × the member's speed) = 1.2 × 0.04 × (1 + 0.85);
    the curve is PGS1's all the same."""
    project = dg.with_component(
        dg.with_component(_PARALLEL, "PA", status="off"), "PB", status="off"
    )
    system = system_curve(api, project, ["PA", "PB"], numPoints=5)
    group = api.group(project, ["PA", "PB"], numPoints=5)
    assert abs(group["duty"]["flow"]) <= 1.0e-6
    assert all(p["flow"] is not None and abs(p["flow"]) <= 1.0e-6 for p in group["points"])
    curves = curves_of(project)
    want = 1.2 * sum(curves[pid].points[-1].flow * dg.pump_of(project, pid)[1] for pid in curves)
    assert want == pytest.approx(1.2 * 0.04 * 1.85, rel=1.0e-15)
    assert abs(system["flowRange"]["max"] - want) <= 1.0e-12 * want
    check_system_response(system, 5)
    h1, h2, lines = dg.parallel_outside(project)
    failures = closed_form_failures(system["systemPoints"], h1, h2, lines)
    assert not failures, "\n".join(failures)


# --------------------------------------------------------------------------- PGS11


def test_pgs11_a_scenario_gives_the_hand_edited_projects_curve(api: Api) -> None:
    """``scenarioId`` (D15) with curve 'system': R2's level raised to 5 m, or PB off; the
    response equals the hand-edited project's in every field but ``scenario``; R2 at 5 m moves
    the curve by 3 m (the closed form with H_R2 = 25 m), PB off leaves it as the base's."""
    base = _parallel()
    scenarios = [
        ("S1", "R2", "liquidLevel", 5.0, 2.0, dg.with_component(base, "R2", liquid_level=5.0)),
        ("S2", "PB", "status", "off", "on", dg.with_component(base, "PB", status="off")),
    ]
    project = {
        **as_json(base),
        "scenarios": [
            {
                "id": sid,
                "name": f"Scenario {sid}",
                "overrides": [
                    {"kind": "component", "componentId": cid, "field": field, "value": value}
                ],
            }
            for sid, cid, field, value, _, _ in scenarios
        ],
    }
    grid = {"flowMin": 0.0, "flowMax": 0.1, "numPoints": 6}
    got_by_id = {}
    for sid, cid, field, value, base_value, hand in scenarios:
        got = system_curve(api, project, ["PA", "PB"], scenarioId=sid, **grid)
        want = system_curve(api, hand, ["PA", "PB"], **grid)
        record = got.pop("scenario")
        assert want.pop("scenario") is None
        assert got == want, sid
        assert record["id"] == sid
        [override] = record["overrides"]
        assert override["state"] == "applied"
        assert (override["value"], override["baseValue"]) == (value, base_value)
        assert (override["override"]["componentId"], override["override"]["field"]) == (cid, field)
        got_by_id[sid] = got
    raised = got_by_id["S1"]
    h1, h2, lines = dg.parallel_outside(scenarios[0][5])
    assert h2 == 25.0
    failures = closed_form_failures(raised["systemPoints"], h1, h2, lines)
    assert not failures, "\n".join(failures)
    plain = system_curve(api, base, ["PA", "PB"], **grid)
    off = check_system_response(got_by_id["S2"], 6, flow_max=0.1)
    for a, b in zip(check_system_response(plain, 6, flow_max=0.1), off, strict=True):
        assert abs(a["head"] - b["head"]) <= IDENTITY


# --------------------------------------------------------------------------- PGS12


EPANET_LOSSES = 1.5e-3
"""The largest difference from EPANET's rise, relative to the outside's losses (docstring)."""


@pytest.mark.parametrize("branched", [False, True], ids=["one_line_out", "branched_outside"])
def test_pgs12_epanet_solves_the_outside(api: Api, branched: bool) -> None:
    """EPANET 2.2 (WNTR) on the outside alone: S a junction with demand Q, D one with demand −Q
    (``epanet_outside_project``), its head difference D − S against the group system curve of
    the whole station (D6), our solver in 'swamee_jain' mode with EPANET's viscosity
    (``generate_epanet_cases``' conversion). With ``branched`` the delivery splits through an
    ideal tee to two reservoirs, an outside EPANET solves as a network (the grid's flows keep
    both delivery lines carrying flow one way, clear of laminar flow). Beyond D6, the rises
    agree within 1.5 × 10⁻³ of the outside's losses H_sys − (H_R2 − H_R1): EPANET's losses run
    about 8 × 10⁻⁴ low (measured 8.2–8.4 × 10⁻⁴), its g being 32.2 ft/s² (9.80665 m/s² is
    32.174) and its minor-loss constant 0.02517 (8/(gπ²) = 0.025194 ft·s²)."""
    gen = pytest.importorskip("tests.reference.generate_epanet_cases")
    rho = gen.EPANET_FLUID_DENSITY
    fluid_ = custom_fluid("Water at EPANET's default viscosity", rho, gen.NU_EPANET * rho)
    station = dg.epanet_station_project(fluid_, branched)
    response = system_curve(api, station, ["PA", "PB"], flowMin=0.02, flowMax=0.09, numPoints=5)
    points = check_system_response(response, 5, flow_min=0.02, flow_max=0.09)
    duty = [p for p in response["systemPoints"] if p["isDuty"]]
    failures = []
    for point in [*points, *duty]:
        outside = dg.epanet_outside_project(station, point["flow"])
        flows, heads, _ = gen.run_epanet(outside)
        want = heads["DX:port_1"] - heads["SX:port_1"]
        losses = point["head"] - (
            dg.reservoir_head(station, "R2") - dg.reservoir_head(station, "R1")
        )
        if not head_ok(point["head"], want) or abs(point["head"] - want) > EPANET_LOSSES * losses:
            failures.append(f"Q {point['flow']!r}: {point['head']!r} vs EPANET's {want!r}")
        if branched:
            assert flows["L3"] > 0.0, flows
            assert flows["L4"] > 0.0, flows
    assert not failures, "\n".join(failures)


# --------------------------------------------------------------------------- errors, no duty


def test_pgs_errors_come_in_order(api: Api) -> None:
    """flowMin and flowMax belong to curve 'system' (400 with curve 'group', said or by
    default), flowMin < flowMax (400), the request's 400 before NOT_A_STATION, NOT_A_STATION
    (but an active PRV or PSV) refusing curve 'system' too, before EMPTY_HEAD_RANGE (the group
    curve the default flowMax comes from) before EMPTY_FLOW_RANGE (flowMin above the default
    flowMax); a flowMax given needs no group curve, so no head range is checked."""
    project = as_json(_PARALLEL)
    tapped = dg.header_tap_project("assigned_flow")

    def post(body_project: Any, **options: Any) -> tuple[int, dict[str, Any]]:
        r = api.post(GROUP, group_body(body_project, ["PA", "PB"], **options))
        return r.status_code, r.json()

    for options in (
        {"flowMin": 0.01},
        {"curve": "group", "flowMax": 0.05},
        {"curve": "group", "flowMin": 0.01, "flowMax": 0.05},
        {"curve": "system", "flowMin": 0.05, "flowMax": 0.02},
        {"curve": "system", "flowMin": 0.05, "flowMax": 0.05},
    ):
        status, data = post(project, **options)
        assert (status, data["error"]) == (400, "VALIDATION_ERROR"), (options, data)
        assert data["issues"], options
    status, data = post(tapped, curve="group", flowMin=0.01)
    assert (status, data["error"]) == (400, "VALIDATION_ERROR"), data
    status, data = post(tapped, curve="system", flowMin=50.0)
    assert (status, data["error"]) == (422, "NOT_A_STATION"), data
    assert [i["code"] for i in data["issues"]] == ["ASSIGNED_FLOW_INSIDE"]
    status, data = post(project, curve="system", headMin=100.0, flowMin=50.0)
    assert status == 400, data
    assert [i["code"] for i in data["issues"]] == ["EMPTY_HEAD_RANGE"]
    status, data = post(project, curve="system", flowMin=50.0)
    assert status == 400, data
    assert [i["code"] for i in data["issues"]] == ["EMPTY_FLOW_RANGE"]
    status, data = post(project, curve="system", headMin=100.0, flowMax=0.1, numPoints=5)
    assert status == 200, data
    assert data["flowRange"]["max"] == 0.1


def test_pgs_no_400_quotes_a_submitted_value(api: Api) -> None:
    """SDD §5.1.2: no error of the flow range echoes what was submitted."""
    project = as_json(_PARALLEL)
    bodies: list[tuple[dict[str, Any], list[str]]] = [
        ({"pumpIds": ["PA"], "flowMin": 0.0777777}, ["0.0777777"]),
        ({"pumpIds": ["PA"], "curve": "group", "flowMax": 0.0444444}, ["0.0444444"]),
        (
            {"pumpIds": ["PA"], "curve": "system", "flowMin": 0.0654321, "flowMax": 0.0123456},
            ["0.0654321", "0.0123456"],
        ),
        ({"pumpIds": ["PA", "PB"], "curve": "system", "flowMin": 55.5555}, ["55.5555"]),
        ({"pumpIds": ["PA"], "curve": "system", "flowMax": 123.456}, ["123.456"]),
        ({"pumpIds": ["PA"], "curve": "system", "flowMin": -0.98765}, ["0.98765"]),
        ({"pumpIds": ["PA", "PB"], "curve": "system", "headMin": 98.7654}, ["98.7654"]),
        ({"pumpIds": ["PA"], "curve": "system", "numPoints": 2345}, ["2345"]),
    ]
    for options, secrets in bodies:
        response = api.post(GROUP, {"project": project, **options})
        assert response.status_code == 400, (options, response.text)
        for secret in secrets:
            assert secret not in response.text, (options, response.text)


def test_pgs_a_case_that_does_not_converge_has_no_system_curve(api: Api) -> None:
    """Two FCVs in series outside the station, set alike (over-controlled): the case's solve
    does not converge, so curve 'system' returns the station, converged false, no duty, no
    points, no duty check and no flow range, with a message naming the controls."""
    project = dg.over_controlled_project(_PARALLEL)
    data = system_curve(api, project, ["PA", "PB"])
    assert data["converged"] is False
    assert data["station"]["inlet"] == {"componentId": "T1", "portId": "run_inlet"}
    assert (data["duty"], data["systemDutyCheck"], data["systemPoints"], data["flowRange"]) == (
        None,
        None,
        [],
        None,
    )
    assert (data["dutyCheck"], data["points"], data["headRange"]) == (None, [], None)
    assert "FCV1" in data["message"]
    assert "FCV2" in data["message"]


def test_pgs_the_methods_describe_the_group_system_curve(api: Api) -> None:
    """The "Pump group" methods section of curve 'system' defines the curve, counts its flows
    ("Points: n flows ...", "plus the duty's flow" when it is added: the stated count is the
    number of points returned) and states the system duty check; the method version is
    /solve's."""
    base = _PARALLEL
    all_off = dg.with_component(dg.with_component(base, "PA", status="off"), "PB", status="off")
    problems = []
    for project, options in (
        (base, {"numPoints": 5}),  # the duty's flow added: 6 points
        (base, {"numPoints": 5, "flowMin": 0.0, "flowMax": 0.03}),  # outside: 5 points
        (base, {"numPoints": 7, "flowMin": 0.01, "flowMax": 0.1}),  # added: 8 points
        (all_off, {"numPoints": 5}),  # Q_st ≈ 0 (round-off) added beside the flow 0
    ):
        response = system_curve(api, project, ["PA", "PB"], **options)
        methods = response["methods"]
        assert methods["title"] == "Pump group"
        items = methods["items"]
        [points_item] = [i for i in items if i.startswith("Points:")]
        found = re.match(r"Points: (\d+) flows", points_item)
        assert found, points_item
        stated = int(found.group(1)) + (1 if "plus the duty's flow" in points_item else 0)
        if stated != len(response["systemPoints"]):
            problems.append(f"{options}: '{points_item[:60]}' for {len(response['systemPoints'])}")
        assert len([i for i in items if i.startswith("Group system curve")]) == 1
        [check_item] = [i for i in items if i.startswith("System duty check:")]
        assert response["systemDutyCheck"]["message"] in check_item
    assert not problems, "\n".join(problems)
    state = api.solve(base)
    response = system_curve(api, base, ["PA", "PB"], numPoints=5)
    assert response["methodVersion"] == state["methodVersion"]
    assert state["methodVersion"] in " ".join(response["methods"]["items"])
