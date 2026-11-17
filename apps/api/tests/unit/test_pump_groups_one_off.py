"""Pump groups, one pump off (CLAUDE.md D21 slice 4d; docs/proposals/pump-groups.md §8 and §17):
the facts the web's "Pumps together" card relies on when it makes cases with one pump off and
draws their station duties beside the case shown, proven against the real API through its
TestClient (``POST /api/v1/solve`` and ``/api/v1/pump-group-curve``, curves 'group' and
'system', with and without ``scenarioId``).

Written by a tester who read neither ``services/`` nor the web source: from D6, D13, D15 and D21
(``docs/decisions``), SDD §4.17, and the slice's design as the proposal's §17 records it ("the
design" below: its API test, §6.2; its duty claim, §2.6; its other cases, §2.3). The networks
are the shared fixture's (``tests/fixtures/pump_groups_input.py``, cases ``parallel-ideal``,
``parallel-crane``, ``ladder``, ``dead-headed``, ``one-off`` and ``prv-inside``), built by its
own recipes from the reference derivations (``derivations_pumps.pumps_in_parallel``,
``derivations_pump_groups.ladder_project``). A case with one pump off is made as the card's
"Add cases with one pump off" makes it: a D15 scenario of the base whose only override is that
pump's ``status`` set to 'off', one per pump running in the base case's solve.

The tests are metamorphic, like ``pump_group_check``'s (t2): both sides of each comparison are
the API's own answers, and no expected number is typed except two closed forms (the 5 m a
delivery tank is raised by, and the static rise between the reservoirs at zero flow).

- **A case's duty lies on another case's group system curve where the rest of the network is
  the same** (D21: the curve "depends on nothing inside" but its duty's own point). For each
  one-pump-off case of five networks, the base's group system curve, requested on a grid that
  holds that case's station flow Q (``flowMin`` 0, ``flowMax`` 4Q, ``numPoints`` 5), gives the
  case's rise ΔH_st at Q within D6; so does every one-pump-off case's own curve for the base's
  duty and the other one-pump-off duties ("it holds for whichever case is shown", proposal §17,
  departure 3). On the curve the card draws (the API's default flows), each such duty lies inside
  the range with a rise on both sides, and the polyline's chord at Q is within D6 of ΔH_st.
- **An outside change moves the duty off it:** raising the delivery tank 5 m puts the duty
  5 m above the base's curve (closed form: the rest needs 5 m more at every flow), beyond D6.
- **The station is the same in every case** (D21: its extent is topology only), whatever the
  scenario changes, in the 'group' and the 'system' answers: the six fields the web compares.
- **Every member off gives a duty at zero station flow** (below the duty check's floor,
  10⁻⁶ m³/s, the web's ``zero_flow`` branch), shares not given, and the static rise.
- **An idle member's off case repeats the base** (D13's same answer): a pump on but held at zero
  flow (``no_flow``) switched off gives the base case's flows, heads, pressures and duty within
  D6, which is why the card makes no case for it.
- **The cases solve as hand edits** (D15): a one-pump-off scenario's ``/solve`` and both
  ``/pump-group-curve`` answers equal the hand-edited project's bit for bit, apart from the
  ``scenario`` field and D15's own trace additions (the "Scenario" methods section and the
  changed pump's note), the timestamp and the compute time.
- **With an active PRV inside** the group curve of each case is refused for that reason alone,
  and the case's duty, which the card then takes from its group system curve (design §2.3), lies
  on the base's group system curve as above.

Tolerances: D6 for heads (0.5 % or 0.01 m, whichever is looser) and pressures (0.5 % or 0.01 m
× ρg); flows 0.5 % with D21's duty-check floor of 10⁻⁶ m³/s for the station's duty and the
reference suite's Qtol of 10⁻⁸ m³/s for every other flow (a zero flow); a grid flow equal to Q
within 10⁻¹² Q (design §6.2).
"""

import copy
import itertools
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from tests.fixtures import pump_groups_input as pgi
from tests.reference import derivations_pump_groups as dpg
from tests.reference import element_laws as el
from tests.reference.case_format import control_valve

SOLVE = "/api/v1/solve"
GROUP = "/api/v1/pump-group-curve"

RELATIVE = 0.005
"""D6: 0.5 % of the reference."""
HEAD_FLOOR = 0.01
"""m: D6's 0.01 m of head."""
DUTY_FLOW_FLOOR = 1.0e-6
"""m³/s: D21's duty check floor; the web reads a station flow below it as zero (design §2.6)."""
FLOW_FLOOR = el.QTOL
"""m³/s: the reference suite's zero flow (the status logic's flow tolerance)."""
GRID = 1.0e-12
"""Relative: a grid flow is the station flow Q when within 10⁻¹² Q of it (design §6.2)."""
G = 9.80665
"""m/s²: standard gravity, for D6's 0.01 m of head as a pressure."""


# --------------------------------------------------------------------------- the API

_addresses = itertools.count(1)


class Api:
    """POST through the app from a client address of its own, changed every 40 requests, so the
    rate limit (60 a minute per client) is never reached. The addresses are in 10.76.0.0/16,
    which no other module sends from (``test_client_addresses.py``), so no bucket is shared
    with the rest of the suite."""

    def __init__(self) -> None:
        self._client = self._new()
        self._sent = 0

    @staticmethod
    def _new() -> TestClient:
        n = next(_addresses)
        return TestClient(app, client=(f"10.76.{n // 256 % 256}.{n % 256}", 50000))

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self._sent == 40:
            self._client, self._sent = self._new(), 0
        self._sent += 1
        response: httpx.Response = self._client.post(path, json=body)
        return response

    def solve(self, project: dict[str, Any], scenario: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"project": project, "options": {"includeSystemCurve": False}}
        if scenario is not None:
            body["scenarioId"] = scenario
        response = self.post(SOLVE, body)
        assert response.status_code == 200, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        assert data["success"], data.get("message")
        assert data["solvedState"]["converged"], data["solvedState"]["convergence"]
        return data

    def group(
        self,
        project: dict[str, Any],
        members: Sequence[str],
        scenario: str | None = None,
        status: int = 200,
        **options: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"project": project, "pumpIds": list(members), **options}
        if scenario is not None:
            body["scenarioId"] = scenario
        response = self.post(GROUP, body)
        assert response.status_code == status, f"{response.status_code} {response.text[:2000]}"
        data: dict[str, Any] = response.json()
        return data

    def system(
        self,
        project: dict[str, Any],
        members: Sequence[str],
        scenario: str | None = None,
        flow: float | None = None,
    ) -> dict[str, Any]:
        """The group system curve: on the API's default flows, or with ``flow`` on a grid that
        holds it (``flowMin`` 0, ``flowMax`` 4 × flow, 5 points: 0, Q, 2Q, 3Q, 4Q)."""
        grid: dict[str, Any] = {}
        if flow is not None:
            grid = {"flowMin": 0.0, "flowMax": 4.0 * flow, "numPoints": 5}
        return self.group(project, members, scenario, curve="system", **grid)


@pytest.fixture(scope="module")
def api() -> Api:
    return Api()


# --------------------------------------------------------------------------- the networks


def _dead_headed() -> dict[str, Any]:
    """``dead-headed``: parallel-ideal with PB at 70 % speed, its shutoff head below the
    station's rise, so the base case holds it at zero flow (``no_flow``)."""
    data = pgi._parallel()
    pgi._component(data, "PB")["speed"] = 0.7
    return data


def _prv_inside() -> dict[str, Any]:
    """``prv-inside``: parallel-ideal with an active PRV V1 (250 kPa) in PA's discharge leg."""
    data = pgi._parallel()
    valve = pgi._dump(control_valve("V1", 0.5, "prv", 250000.0))
    pgi._split(data, "LA2", valve, "inlet", "outlet")
    return data


NETWORKS: dict[str, tuple[Callable[[], dict[str, Any]], tuple[str, ...]]] = {
    "parallel-ideal": (pgi._parallel, ("PA", "PB")),
    "parallel-crane": (lambda: pgi._parallel("crane"), ("PA", "PB")),
    "ladder": (lambda: pgi._dump(dpg.ladder_project()), ("P1", "P2", "P3")),
    "dead-headed": (_dead_headed, ("PA", "PB")),
    "one-off": (pgi.one_off_project, ("PA", "PB")),
}
"""The design's five networks (§6.2), each with the members the card ticks."""


def off_override(pump_id: str) -> dict[str, Any]:
    """The one override of a case with one pump off (D21's web defaults: that pump's ``status`` off
    and nothing else)."""
    return {"kind": "component", "componentId": pump_id, "field": "status", "value": "off"}


def with_one_pump_off(
    project: dict[str, Any], pumps: Iterable[str]
) -> tuple[dict[str, Any], dict[str, str]]:
    """The project with one scenario per pump as the card's add makes it: "{name} off", the
    base with that pump's status off and nothing else, ids S1, S2, … (the first free ones),
    appended after any scenario the project has; and the scenario id of each pump."""
    data = copy.deepcopy(project)
    scenarios: list[dict[str, Any]] = data.setdefault("scenarios", [])
    names = {c["id"]: c["name"] for c in data["components"]}
    taken = {s["id"] for s in scenarios}
    free = (f"S{n}" for n in itertools.count(1) if f"S{n}" not in taken)
    ids: dict[str, str] = {}
    for pump in pumps:
        sid = next(free)
        scenarios.append(
            {"id": sid, "name": f"{names[pump]} off", "overrides": [off_override(pump)]}
        )
        ids[pump] = sid
    return data, ids


@dataclass(frozen=True)
class OneOff:
    """A network with its one-pump-off cases: the project (holding the scenarios), the members,
    the pumps running in the base case's solve, each running pump's scenario id, and the base's
    group-curve answer."""

    project: dict[str, Any]
    members: tuple[str, ...]
    running: tuple[str, ...]
    scenario: dict[str, str]
    base: dict[str, Any]


def one_off(api: Api, network: str) -> OneOff:
    build, members = NETWORKS[network]
    project = build()
    solve = api.solve(project)
    pumps = solve["solvedState"]["pumpResults"]
    running = tuple(m for m in members if pumps[m]["status"] == "running")
    project, scenario = with_one_pump_off(project, running)
    base = api.group(project, members)
    return OneOff(project, members, running, scenario, base)


# --------------------------------------------------------------------------- comparisons


def head_ok(got: float | None, want: float) -> bool:
    """D6 for heads: 0.5 % or 0.01 m, whichever is looser."""
    return got is not None and abs(got - want) <= max(RELATIVE * abs(want), HEAD_FLOOR)


def pressure_ok(got: float | None, want: float | None, rho: float) -> bool:
    """D6 for pressures: 0.5 % or 0.01 m of head (× ρg), whichever is looser."""
    if got is None or want is None:
        return got is want
    return abs(got - want) <= max(RELATIVE * abs(want), HEAD_FLOOR * rho * G)


def flow_ok(got: float | None, want: float | None, floor: float = FLOW_FLOOR) -> bool:
    """D6 for flows: 0.5 %, with a floor for zero flows."""
    if got is None or want is None:
        return got is want
    return abs(got - want) <= max(RELATIVE * abs(want), floor)


def points_at(curve: dict[str, Any], flow: float) -> list[dict[str, Any]]:
    """The group system curve's points at ``flow`` (within ``GRID`` of it)."""
    return [p for p in curve["systemPoints"] if abs(p["flow"] - flow) <= GRID * abs(flow)]


def rise_at(curve: dict[str, Any], flow: float) -> list[str]:
    """Problems with the rise the curve (requested on a grid holding ``flow``) gives there:
    none when a converged point stands at that flow with a rise."""
    points = points_at(curve, flow)
    if not points:
        flows = [p["flow"] for p in curve["systemPoints"]]
        return [f"no point at the flow {flow!r} among {flows!r}"]
    return [
        f"the point at {p['flow']!r} has no rise ({p['reason']}: {p['message']})"
        for p in points
        if p["head"] is None or not p["converged"]
    ]


def on_curve(curve: dict[str, Any], duty: dict[str, Any], what: str) -> list[str]:
    """``duty`` (a station flow and rise) is a point of ``curve``, requested on a grid holding
    its flow: the rise there within D6 of the duty's."""
    flow, rise = duty["flow"], duty["head"]
    problems = rise_at(curve, flow)
    if problems:
        return [f"{what}: {p}" for p in problems]
    return [
        f"{what}: at {flow!r} m³/s the curve's rise is {p['head']!r} m, the duty's {rise!r} m "
        f"(difference {p['head'] - rise:.6g} m, {abs(p['head'] - rise) / abs(rise):.3g} relative)"
        for p in points_at(curve, flow)
        if not head_ok(p["head"], rise)
    ]


def chord(points: Sequence[dict[str, Any]], flow: float) -> tuple[float | None, str | None]:
    """The rise the drawn curve (straight lines between its points, in flow order) gives at
    ``flow``, or None and why not: as the web's claim reads it (design §2.6), the flow lies
    beyond the curve's flows when no point stands at or below it, or none at or above it, and
    the curve has a gap there when the nearest point either side has no rise."""
    below = [p for p in points if p["flow"] <= flow]
    above = [p for p in points if p["flow"] >= flow]
    if not below or not above:
        return None, "beyond_range"
    a = max(below, key=lambda p: p["flow"])
    b = min(above, key=lambda p: p["flow"])
    if a["head"] is None or b["head"] is None:
        return None, "gap"
    if b["flow"] == a["flow"]:
        return float(a["head"]), None
    t = (flow - a["flow"]) / (b["flow"] - a["flow"])
    return float(a["head"] + t * (b["head"] - a["head"])), None


def differences(a: Any, b: Any, path: str = "") -> list[str]:
    """Every leaf at which ``a`` and ``b`` differ, compared as JSON text (bit for bit: distinct
    doubles have distinct shortest representations, and -0.0 is not 0.0)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}/{key}: only in {'the first' if key in a else 'the second'}")
            else:
                out.extend(differences(a[key], b[key], f"{path}/{key}"))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: {len(a)} items, {len(b)}"]
        return [
            d
            for i, (x, y) in enumerate(zip(a, b, strict=True))
            for d in differences(x, y, f"{path}[{i}]")
        ]
    sa, sb = json.dumps(a), json.dumps(b)
    return [] if sa == sb else [f"{path}: {sa[:120]} against {sb[:120]}"]


def by_pump(members: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {m["pumpId"]: m for m in members}


# --------------------------------------------------------------------------- the duty on the curve


@pytest.mark.parametrize("network", list(NETWORKS))
def test_a_one_pump_off_duty_lies_on_the_base_group_system_curve(api: Api, network: str) -> None:
    """For each pump running in the base case, the case with it off has the base's station and
    a duty above zero station flow, and that duty lies on the base's group system curve: the
    curve requested on a grid holding the case's station flow Q gives its rise at Q within D6.
    On the curve the card draws (the default flows) the duty lies inside the range with a rise
    on both sides, and the drawn chord at Q is within D6 of the duty's rise. The base's own
    system duty check agrees (the web says "on the curve" only then, proposal §17, departure 3)."""
    case = one_off(api, network)
    assert case.running, f"{network}: no pump runs in the base case"
    drawn = api.system(case.project, case.members)
    assert drawn["station"] == case.base["station"], network
    problems: list[str] = []
    if not drawn["systemDutyCheck"]["agrees"]:
        problems.append(f"the base's system duty check: {drawn['systemDutyCheck']['message']}")
    ordered = sorted(drawn["systemPoints"], key=lambda p: p["flow"])
    for pump in case.running:
        sid = case.scenario[pump]
        what = f"{network}, {pump} off ({sid})"
        answer = api.group(case.project, case.members, sid)
        if answer["station"] != case.base["station"]:
            problems.append(
                f"{what}: station {answer['station']}, the base's {case.base['station']}"
            )
        duty = answer["duty"]
        if duty is None or not duty["flow"] > DUTY_FLOW_FLOOR:
            problems.append(f"{what}: no duty with flow ({duty}; {answer['message']})")
            continue
        off = by_pump(duty["members"])[pump]
        if off["status"] != "off" or off["flow"] != 0.0:
            problems.append(f"{what}: the pump off reads {off}")
        curve = api.system(case.project, case.members, flow=duty["flow"])
        if curve["station"] != case.base["station"]:
            problems.append(f"{what}: the base's curve has station {curve['station']}")
        problems.extend(on_curve(curve, duty, f"{what} on the base's curve"))
        rise, why = chord(ordered, duty["flow"])
        if rise is None:
            problems.append(f"{what}: on the base's default flows the duty's flow is {why}")
        elif not head_ok(rise, duty["head"]):
            problems.append(
                f"{what}: the drawn chord at {duty['flow']!r} m³/s is {rise!r} m, the duty's "
                f"{duty['head']!r} m"
            )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("network", list(NETWORKS))
def test_every_other_duty_lies_on_a_one_pump_off_cases_curve(api: Api, network: str) -> None:
    """The same with a one-pump-off case shown (proposal §17, departure 3: the claim holds for
    whichever case is shown): that case's group system curve (with its ``scenarioId``),
    requested on a grid holding another case's station flow, gives the other case's rise there
    within D6, for the base's duty and every other one-pump-off duty; and its own system duty
    check agrees."""
    case = one_off(api, network)
    duties: dict[str, dict[str, Any]] = {"the base": case.base["duty"]}
    for pump in case.running:
        sid = case.scenario[pump]
        duties[sid] = api.group(case.project, case.members, sid)["duty"]
    problems: list[str] = []
    for pump in case.running:
        shown = case.scenario[pump]
        for other, duty in duties.items():
            if other == shown:
                continue
            what = f"{network}: {other}'s duty on {shown}'s curve ({pump} off)"
            if duty is None or not duty["flow"] > DUTY_FLOW_FLOOR:
                problems.append(f"{what}: no duty with flow ({duty})")
                continue
            curve = api.system(case.project, case.members, shown, flow=duty["flow"])
            if curve["station"] != case.base["station"]:
                problems.append(f"{what}: station {curve['station']}")
            if not curve["systemDutyCheck"]["agrees"]:
                problems.append(
                    f"{what}: {shown}'s own system duty check: {curve['systemDutyCheck']}"
                )
            problems.extend(on_curve(curve, duty, what))
    assert not problems, "\n".join(problems)


def test_with_a_pressure_control_inside_the_duty_comes_from_the_system_answer(api: Api) -> None:
    """``prv-inside``: each case's group curve is refused for the active PRV inside alone, so
    the card takes the case's duty from its group system curve (design §2.3); that answer has
    the base's station and a duty with flow, and the duty lies on the base's group system
    curve within D6."""
    members = ("PA", "PB")
    project = _prv_inside()
    solve = api.solve(project)
    running = [m for m in members if solve["solvedState"]["pumpResults"][m]["status"] == "running"]
    assert running == ["PA", "PB"], running
    project, scenario = with_one_pump_off(project, running)
    base = api.group(project, members, status=422)
    assert [i["code"] for i in base["issues"]] == ["PRESSURE_CONTROL_INSIDE"], base
    station = api.system(project, members)["station"]
    problems: list[str] = []
    for pump in running:
        sid = scenario[pump]
        what = f"prv-inside, {pump} off ({sid})"
        refused = api.group(project, members, sid, status=422)
        codes = [i["code"] for i in refused["issues"]]
        if codes != ["PRESSURE_CONTROL_INSIDE"]:
            problems.append(f"{what}: refused for {codes}")
        answer = api.system(project, members, sid)
        if answer["station"] != station:
            problems.append(f"{what}: station {answer['station']}, the base's {station}")
        duty = answer["duty"]
        if duty is None or not duty["flow"] > DUTY_FLOW_FLOOR:
            problems.append(f"{what}: no duty with flow ({duty}; {answer['message']})")
            continue
        curve = api.system(project, members, flow=duty["flow"])
        problems.extend(on_curve(curve, duty, f"{what} on the base's curve"))
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- the one-off project


def _one_off_scenarios() -> dict[str, Any]:
    """``one-off``'s project with the fixture's four scenarios: S1 and S2 as the card makes
    them, S3 the delivery tank R2 5 m higher (an outside change), S4 both pumps off."""
    project = pgi.one_off_project()
    assert pgi._component(project, "R2")["liquidLevel"] == 2.0
    project, _ = with_one_pump_off(project, ["PA", "PB"])
    level = {"kind": "component", "componentId": "R2", "field": "liquidLevel", "value": 7.0}
    project["scenarios"] += [
        {"id": "S3", "name": "Delivery tank 5 m higher", "overrides": [level]},
        {
            "id": "S4",
            "name": "Both pumps off",
            "overrides": [off_override("PA"), off_override("PB")],
        },
    ]
    assert [s["id"] for s in project["scenarios"]] == ["S1", "S2", "S3", "S4"]
    return project


MEMBERS = ("PA", "PB")


def test_the_station_is_the_same_in_every_case(api: Api) -> None:
    """D21: the station's extent is topology only, the same in every case. Every scenario of
    ``one-off`` (each pump off, the delivery tank higher, both off) gives the base's station in
    its group and its group system answers: inlet, outlet, arrangement, members and interior,
    the six fields the web's ``sameStation`` compares."""
    project = _one_off_scenarios()
    base = api.group(project, MEMBERS)["station"]
    assert set(base) == {
        "inlet",
        "outlet",
        "arrangement",
        "memberIds",
        "interiorComponentIds",
        "interiorConnectionIds",
    }, base
    assert base["arrangement"] == "parallel", base
    problems = [
        f"{sid} ({kind}): {answer['station']}"
        for sid in ("S1", "S2", "S3", "S4")
        for kind, answer in (
            ("group", api.group(project, MEMBERS, sid)),
            ("system", api.system(project, MEMBERS, sid)),
        )
        if answer["station"] != base
    ]
    assert not problems, f"the base's station {base}; " + "; ".join(problems)


def test_an_outside_change_is_off_the_base_curve(api: Api) -> None:
    """S3 raises the delivery tank R2 by 5 m, outside the station: at the case's station flow
    the base's group system curve lies 5 m below the case's rise (the rest of the network needs
    5 m more at every flow: R2's head enters EGL(D) directly), so the duty is off the base's
    curve by more than D6, while the case's own curve passes through it."""
    project = _one_off_scenarios()
    answer = api.group(project, MEMBERS, "S3")
    duty = answer["duty"]
    assert duty is not None, answer["message"]
    assert duty["flow"] > DUTY_FLOW_FLOOR, duty
    curve = api.system(project, MEMBERS, flow=duty["flow"])
    assert not rise_at(curve, duty["flow"]), rise_at(curve, duty["flow"])
    [point] = points_at(curve, duty["flow"])
    assert not head_ok(point["head"], duty["head"]), (point["head"], duty["head"])
    assert head_ok(point["head"] + 5.0, duty["head"]), (point["head"], duty["head"])
    own = api.system(project, MEMBERS, "S3", flow=duty["flow"])
    assert own["systemDutyCheck"]["agrees"], own["systemDutyCheck"]
    assert not on_curve(own, duty, "S3 on its own curve"), on_curve(own, duty, "S3")


def test_both_off_is_at_zero_station_flow(api: Api) -> None:
    """S4, every member off: the duty's station flow is below the duty check's floor of
    10⁻⁶ m³/s (the web's ``zero_flow`` branch: no claim about the curve), each member off with
    no flow and no share (D21: none in parallel at a duty without flow), and the rise is the
    static one between the reservoirs, H_R2 − H_R1 (closed form: no loss at zero flow), within
    D6."""
    project = _one_off_scenarios()
    answer = api.group(project, MEMBERS, "S4")
    duty = answer["duty"]
    assert duty is not None, answer["message"]
    assert abs(duty["flow"]) < DUTY_FLOW_FLOOR, duty
    for member in duty["members"]:
        assert member["status"] == "off", member
        assert member["flow"] == 0.0, member
        assert member["share"] is None, member
    model = Project.model_validate(project)
    static = dpg.reservoir_head(model, "R2") - dpg.reservoir_head(model, "R1")
    assert head_ok(duty["head"], static), (duty["head"], static)


# --------------------------------------------------------------------------- an idle member


def _state_problems(base: dict[str, Any], case: dict[str, Any], what: str) -> list[str]:
    """Where ``case`` is not the same answer as ``base`` (D13): every node's heads and pressures,
    every link's flow and head loss, every pump's flow, head and suction pressure, every
    boundary's outflow and every branch's port flows within D6. State labels at zero flow are
    not compared (D13)."""
    rho = float(base["fluid"]["density"])
    problems: list[str] = []
    for table in ("nodeResults", "linkResults", "pumpResults", "boundaryResults", "branchResults"):
        if set(base[table]) != set(case[table]):
            problems.append(
                f"{what}: {table} {sorted(case[table])}, the base's {sorted(base[table])}"
            )
    for key in set(base["nodeResults"]) & set(case["nodeResults"]):
        a, b = base["nodeResults"][key], case["nodeResults"][key]
        for field in ("egl", "hgl"):
            if not head_ok(b[field], a[field]):
                problems.append(f"{what}: node {key} {field} {b[field]!r}, the base's {a[field]!r}")
        for field in ("pressure", "absolutePressure", "dynamicPressure", "totalPressure"):
            if not pressure_ok(b[field], a[field], rho):
                problems.append(f"{what}: node {key} {field} {b[field]!r}, the base's {a[field]!r}")
    for key in set(base["linkResults"]) & set(case["linkResults"]):
        a, b = base["linkResults"][key], case["linkResults"][key]
        if not flow_ok(b["flow"], a["flow"]):
            problems.append(f"{what}: link {key} flow {b['flow']!r}, the base's {a['flow']!r}")
        if not head_ok(b["headLoss"], a["headLoss"]):
            problems.append(
                f"{what}: link {key} head loss {b['headLoss']!r}, the base's {a['headLoss']!r}"
            )
    for key in set(base["pumpResults"]) & set(case["pumpResults"]):
        a, b = base["pumpResults"][key], case["pumpResults"][key]
        if not flow_ok(b["operatingFlow"], a["operatingFlow"]):
            problems.append(
                f"{what}: pump {key} flow {b['operatingFlow']!r}, the base's {a['operatingFlow']!r}"
            )
        if not head_ok(b["operatingHead"], a["operatingHead"]):
            problems.append(
                f"{what}: pump {key} head {b['operatingHead']!r}, the base's {a['operatingHead']!r}"
            )
        if not pressure_ok(b["suctionAbsolutePressure"], a["suctionAbsolutePressure"], rho):
            problems.append(f"{what}: pump {key} suction pressure {b['suctionAbsolutePressure']!r}")
    for key in set(base["boundaryResults"]) & set(case["boundaryResults"]):
        a, b = base["boundaryResults"][key], case["boundaryResults"][key]
        if not flow_ok(b["outflow"], a["outflow"]):
            problems.append(
                f"{what}: boundary {key} outflow {b['outflow']!r}, the base's {a['outflow']!r}"
            )
    for key in set(base["branchResults"]) & set(case["branchResults"]):
        a, b = base["branchResults"][key]["portFlows"], case["branchResults"][key]["portFlows"]
        if set(a) != set(b) or not all(flow_ok(b[p], a[p]) for p in a):
            problems.append(f"{what}: branch {key} port flows {b}, the base's {a}")
    return problems


def test_an_idle_members_off_case_repeats_the_base(api: Api) -> None:
    """``dead-headed``: PB is on but held at zero flow (``no_flow``) in the base case. With it
    off the solve is the base's state (D13: every flow, head and pressure within D6; only PB's
    label at zero flow differs), and so is the station's duty (its flow, rise and inlet EGL, and
    each member's flow and head), with the same station: so the card makes no case for an idle
    member (proposal §17, departure 2). The comparison is not vacuous: the running member off
    (PA) fails it."""
    project = _dead_headed()
    base = api.solve(project)
    assert base["solvedState"]["pumpResults"]["PB"]["status"] == "no_flow", base["solvedState"]
    assert base["solvedState"]["pumpResults"]["PA"]["status"] == "running"
    project, scenario = with_one_pump_off(project, ["PB", "PA"])
    running_off = api.solve(project, scenario["PA"])["solvedState"]
    assert _state_problems(base["solvedState"], running_off, "PA off"), "PA off reads as the base"
    sid = scenario["PB"]
    case = api.solve(project, sid)
    state = case["solvedState"]
    assert state["pumpResults"]["PB"]["status"] == "off", state["pumpResults"]["PB"]
    problems = _state_problems(base["solvedState"], state, f"dead-headed, PB off ({sid})")
    group_base = api.group(project, MEMBERS)
    group_case = api.group(project, MEMBERS, sid)
    if group_case["station"] != group_base["station"]:
        problems.append(f"station {group_case['station']}, the base's {group_base['station']}")
    a, b = group_base["duty"], group_case["duty"]
    assert a is not None, group_base["message"]
    assert b is not None, group_case["message"]
    if not flow_ok(b["flow"], a["flow"], DUTY_FLOW_FLOOR):
        problems.append(f"duty flow {b['flow']!r}, the base's {a['flow']!r}")
    for field in ("head", "inletEgl"):
        if not head_ok(b[field], a[field]):
            problems.append(f"duty {field} {b[field]!r}, the base's {a[field]!r}")
    ma, mb = by_pump(a["members"]), by_pump(b["members"])
    for pump in MEMBERS:
        if not flow_ok(mb[pump]["flow"], ma[pump]["flow"], DUTY_FLOW_FLOOR):
            problems.append(
                f"duty {pump} flow {mb[pump]['flow']!r}, the base's {ma[pump]['flow']!r}"
            )
        if not head_ok(mb[pump]["head"], ma[pump]["head"]):
            problems.append(
                f"duty {pump} head {mb[pump]['head']!r}, the base's {ma[pump]['head']!r}"
            )
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------------------- scenarios as hand edits


@pytest.mark.parametrize("pump", MEMBERS)
def test_scenarios_as_the_action_makes_them_solve_as_hand_edits(api: Api, pump: str) -> None:
    """D15: a case the card's add makes (the base with one pump's status off) solves as the
    project with that status set off by hand, bit for bit. ``/solve``: equal but for
    ``computeTime``, the timestamp, ``scenario`` (the override applied, 'off' over the base's
    'on') and D15's trace additions (a "Scenario" methods section first, and a note first on the
    pump it changes); ``/pump-group-curve``, curves 'group' and 'system': equal but for
    ``scenario``."""
    project, scenario = with_one_pump_off(pgi.one_off_project(), [pump])
    sid = scenario[pump]
    by_hand = pgi.one_off_project()
    pgi._component(by_hand, pump)["status"] = "off"

    made = api.solve(project, sid)
    hand = api.solve(by_hand)
    assert hand["scenario"] is None, hand["scenario"]
    [override] = made["scenario"]["overrides"]
    assert override["override"] == off_override(pump), override
    assert (override["state"], override["value"], override["baseValue"]) == ("applied", "off", "on")

    made_state, hand_state = copy.deepcopy(made["solvedState"]), copy.deepcopy(hand["solvedState"])
    for state in (made_state, hand_state):
        del state["timestamp"]
    made_methods = made_state["trace"]["methods"]["sections"]
    assert made_methods[0]["title"] == "Scenario", made_methods[0]
    del made_methods[0]
    notes = made_state["trace"]["elements"][pump]["notes"]
    assert notes[0].startswith(f"Scenario '{project['scenarios'][0]['name']}' (id {sid})"), notes
    del notes[0]
    assert differences(made_state, hand_state) == []

    for options in ({}, {"curve": "system"}):
        made_curve = api.group(project, MEMBERS, sid, **options)
        hand_curve = api.group(by_hand, MEMBERS, **options)
        assert made_curve["scenario"]["id"] == sid
        assert hand_curve["scenario"] is None
        del made_curve["scenario"], hand_curve["scenario"]
        assert differences(made_curve, hand_curve) == [], options
