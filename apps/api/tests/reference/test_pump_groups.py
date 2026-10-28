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
from tests.reference.case_format import builtin_glycol

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
