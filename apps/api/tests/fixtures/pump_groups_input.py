"""The shared pump-group fixture of the web app (docs/proposals/pump-groups.md §9.1, Web).

    cd apps/api && uv run python -m tests.fixtures.pump_groups_input \
        > ../web/src/lib/utils/__fixtures__/pump-groups-input.json

``apps/web/scripts/gen-api-types.sh`` (``pnpm gen:types``) writes it with ``openapi.json``; it is
generated, never edited by hand. Every response in it is the real API's, through the real app
(``POST /api/v1/solve`` and ``/api/v1/pump-group-curve``, curves ``group`` and ``system``), so
the web's "Pumps together" card (``utils/pump-groups.ts``, ``utils/pump-group-chart.ts``,
``components/results/PumpGroupChart.svelte``) is checked against what the server returns. Each
solve's timestamp and compute time are replaced by constants so the fixture does not change from
one run to the next, and its trace keeps only the members' element traces (the card links to
them) and the methods summary, so the fixture stays small.

Each case is ``{name, description, project, memberIds, solve, groupCurve: {status, body},
systemCurve}``: ``project`` as API JSON (the web's ``Project``), ``solve`` the ``SolveResponse``
of the base case, ``groupCurve`` the status and JSON body of the group-curve request for
``memberIds`` (200: a ``PumpGroupCurveResponse``; 422: the error envelope with its issues), and
``systemCurve`` the same for its group system curve (``curve: 'system'``, slice 4b: the request
the card sends after the group curve's answer), or null for a case the card's tests do not ask
it of.

- ``parallel-ideal``: ``pumps_in_parallel`` (tests/reference/derivations_pumps.py), PA at full
  speed and PB at 85 % between two ideal tees; PB stops above its shutoff head on the curve.
  With its group system curve, which crosses the group curve at the duty.
- ``parallel-crane``: the same with Crane tees (the members' heads at the duty differ more), with
  its group system curve.
- ``ladder``: three pumps on Crane-tee headers with a check valve per leg
  (tests/reference/derivations_pump_groups.py ``ladder_project``).
- ``series``: ``pumps_in_series``, PA then PB (US display units), with its group system curve.
- ``dead-headed``: ``parallel-ideal`` with PB at 70 % speed: its shutoff head is below the
  station's rise, so the solve holds it at zero flow.
- ``off``: ``parallel-ideal`` with PB off.
- ``controlled``: ``series`` with PB on a flow setpoint of 24 L/s (minimum speed 50 %).
- ``refused``: ``parallel-ideal`` with a tank on the discharge header (a third tee piped to a
  reservoir): not a station (422 NOT_A_STATION, FIXED_HEAD_INSIDE).
- ``refused-reversed``: ``parallel-ideal`` with PB turned round: its members face opposite ways
  (422 NOT_A_STATION, MEMBERS_OPPOSED).
- ``refused-opposed-three``: PA from T1 to T2, PB turned round between them, and PC in a loop of
  its own beside PA's suction pipe, on no way between T1 and T2 (MEMBERS_OPPOSED, naming PA and
  PB only).
- ``refused-own-loops``: each pump circulating around a tee of its own, TA and TB, off every way
  between the two places where they meet the rest of the network (NO_WAY_THROUGH).
- ``no-duty``: the corpus project ``fuzz_2168``, pumps PU1 and PU2: the station's outlet lies in
  a section no reservoir or reference node reaches, so the case converges with no duty and no
  curve (200, ``duty`` null, the reason in ``message``).
- ``fcv-outside``: ``parallel-ideal`` with an FCV FC (setpoint 60 L/s) on the delivery pipe, outside
  the station, wide open at the duty: the group system curve's flows above 60 L/s have no rise
  (``beyond_limit``, a gap and its reason).
- ``prv-inside``: ``parallel-ideal`` with an active PRV V1 (250 kPa) in PA's discharge leg, inside
  the station: no group curve (422 NOT_A_STATION, PRESSURE_CONTROL_INSIDE only), but a group
  system curve (200).
"""

import copy
import json
from typing import Any

from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from tests.differential.corpus import items, load
from tests.reference import derivations_pump_groups as dpg
from tests.reference import derivations_pumps as dp
from tests.reference.case_format import control_valve

GENERATED_BY = "apps/api/tests/fixtures/pump_groups_input.py"

SOLVED_AT = "2026-10-28T09:30:00Z"
COMPUTE_TIME = 0.125

US_UNITS = {
    "length": "ft",
    "diameter": "in",
    "pressure": "psi",
    "head": "ft",
    "flow": "gpm",
    "velocity": "ft/s",
    "temperature": "F",
    "density": "lb/ft3",
    "viscosity": "cP",
}


def _client() -> TestClient:
    return TestClient(app, client=("192.0.2.252", 50000))


def _dump(project: Any) -> dict[str, Any]:
    data: dict[str, Any] = project.model_dump(mode="json", by_alias=True)
    return data


def _component(data: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in data["components"] if c["id"] == cid)


def _connection(data: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in data["connections"] if c["id"] == cid)


def _parallel(model: str = "ideal") -> dict[str, Any]:
    data = _dump(dp.pumps_in_parallel().project)
    for comp in data["components"]:
        if comp["type"] == "branch":
            comp["lossModel"] = model
    return data


def _series() -> dict[str, Any]:
    data = _dump(dp.pumps_in_series().project)
    data["settings"]["units"] = dict(US_UNITS)
    return data


def _solve(client: TestClient, project: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/solve", json={"project": project, "options": {"includeSystemCurve": False}}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["success"], body.get("message")
    assert body["solvedState"]["converged"], body.get("message")
    body["computeTime"] = COMPUTE_TIME
    body["solvedState"]["timestamp"] = SOLVED_AT
    return body


def _case(
    client: TestClient,
    name: str,
    description: str,
    project: dict[str, Any],
    members: list[str],
    status: int = 200,
    system: int | None = None,
) -> dict[str, Any]:
    """The case's solve, its group curve (answered with ``status``) and, when ``system`` is
    given, its group system curve (answered with that status)."""
    solve = _solve(client, project)
    trace = solve["solvedState"]["trace"]
    trace["elements"] = {k: v for k, v in trace["elements"].items() if k in members}
    response = client.post(
        "/api/v1/pump-group-curve", json={"project": project, "pumpIds": members}
    )
    assert response.status_code == status, (name, response.text)
    system_curve = None
    if system is not None:
        answer = client.post(
            "/api/v1/pump-group-curve",
            json={"project": project, "pumpIds": members, "curve": "system"},
        )
        assert answer.status_code == system, (name, answer.text)
        system_curve = {"status": answer.status_code, "body": answer.json()}
    return {
        "name": name,
        "description": description,
        "project": project,
        "memberIds": members,
        "solve": solve,
        "groupCurve": {"status": response.status_code, "body": response.json()},
        "systemCurve": system_curve,
    }


def _network(ids: list[str], links: list[tuple[str, str, str]]) -> dict[str, Any]:
    """A project of ``parallel-ideal``'s parts: reservoirs (R…, one port per connection; R2
    as its delivery tank), ideal tees (T…) and PA's pump at full speed (P…), joined by LA1's
    piping."""
    data = _parallel()
    proto = {c["id"]: c for c in data["components"]}
    pipe = _connection(data, "LA1")
    ends = [end.split(":")[0] for _, a, b in links for end in (a, b)]
    components = []
    for cid in ids:
        kind = cid[0]
        comp = copy.deepcopy(
            proto["R2" if cid == "R2" else {"R": "R1", "T": "T1", "P": "PA"}[kind]]
        )
        comp.update(id=cid, name=f"{comp['name'].split()[0]} {cid}")
        if kind == "R":
            comp["ports"] = [
                {**comp["ports"][0], "id": f"port_{i + 1}"} for i in range(ends.count(cid))
            ]
        components.append(comp)
    connections = []
    for cid, a, b in links:
        conn = copy.deepcopy(pipe)
        (fa, fp), (ta, tp) = a.split(":"), b.split(":")
        conn.update(id=cid, fromComponentId=fa, fromPortId=fp, toComponentId=ta, toPortId=tp)
        connections.append(conn)
    data["components"], data["connections"] = components, connections
    return data


def _tee(data: dict[str, Any], cid: str) -> dict[str, Any]:
    tee = copy.deepcopy(_component(data, "T1"))
    tee.update(id=cid, name=f"Tee {cid}")
    return tee


def _split(data: dict[str, Any], conn_id: str, comp: dict[str, Any], a: str, b: str) -> None:
    """Insert ``comp`` into connection ``conn_id``: from -> comp:a, comp:b -> to."""
    data["components"].append(comp)
    conn = _connection(data, conn_id)
    tail = copy.deepcopy(conn)
    conn.update(toComponentId=comp["id"], toPortId=a)
    tail.update(id=f"{conn_id}x", fromComponentId=comp["id"], fromPortId=b)
    data["connections"].append(tail)


def generate() -> dict[str, Any]:
    client = _client()
    cases: list[dict[str, Any]] = []

    cases.append(
        _case(
            client,
            "parallel-ideal",
            "Two pumps in parallel between ideal tees (PA at 100 %, PB at 85 %)",
            _parallel(),
            ["PA", "PB"],
            system=200,
        )
    )
    cases.append(
        _case(
            client,
            "parallel-crane",
            "The same pumps between Crane tees",
            _parallel("crane"),
            ["PA", "PB"],
            system=200,
        )
    )
    ladder = _dump(dpg.ladder_project())
    cases.append(
        _case(
            client,
            "ladder",
            "Three pumps on Crane-tee headers, a check valve in each leg",
            ladder,
            ["P1", "P2", "P3"],
        )
    )
    cases.append(
        _case(client, "series", "Two pumps in series", _series(), ["PA", "PB"], system=200)
    )

    dead = _parallel()
    _component(dead, "PB")["speed"] = 0.7
    case = _case(
        client, "dead-headed", "PB at 70 % speed, below the station's rise", dead, ["PA", "PB"]
    )
    assert case["solve"]["solvedState"]["pumpResults"]["PB"]["status"] == "no_flow"
    cases.append(case)

    off = _parallel()
    _component(off, "PB")["status"] = "off"
    case = _case(client, "off", "PB off", off, ["PA", "PB"])
    assert case["solve"]["solvedState"]["pumpResults"]["PB"]["status"] == "off"
    cases.append(case)

    controlled = _series()
    _component(controlled, "PB")["control"] = {
        "mode": "flow",
        "setpoint": 0.024,
        "minSpeed": 0.5,
    }
    case = _case(client, "controlled", "PB on a flow setpoint of 24 L/s", controlled, ["PA", "PB"])
    control = case["solve"]["solvedState"]["pumpResults"]["PB"]["control"]
    assert control, control
    assert control["state"] == "active", control
    cases.append(case)

    tank = _parallel()
    _split(tank, "LA2", _tee(tank, "T3"), "run_inlet", "run_outlet")
    reservoir = copy.deepcopy(_component(tank, "R1"))
    reservoir.update(id="R4", name="Tank R4", liquidLevel=30.0)
    tank["components"].append(reservoir)
    leg = copy.deepcopy(_connection(tank, "LA1"))
    leg.update(
        id="LT", fromComponentId="T3", fromPortId="branch", toComponentId="R4", toPortId="port_1"
    )
    tank["connections"].append(leg)
    case = _case(
        client, "refused", "A tank on the discharge header", tank, ["PA", "PB"], status=422
    )
    assert case["groupCurve"]["body"]["error"] == "NOT_A_STATION", case["groupCurve"]
    cases.append(case)

    reversed_ = _parallel()
    _connection(reversed_, "LB1").update(toPortId="discharge")
    _connection(reversed_, "LB2").update(fromPortId="suction")
    case = _case(client, "refused-reversed", "PB turned round", reversed_, ["PA", "PB"], status=422)
    assert case["groupCurve"]["body"]["error"] == "NOT_A_STATION", case["groupCurve"]
    cases.append(case)

    opposed = _network(
        ["R1", "T1", "T3", "T4", "PA", "PB", "PC", "T2", "R2"],
        [
            ("L1", "R1:port_1", "T1:run_inlet"),
            ("LA0", "T1:run_outlet", "T3:run_inlet"),
            ("LA0b", "T3:run_outlet", "T4:run_inlet"),
            ("LC1", "T3:branch", "PC:suction"),
            ("LC2", "PC:discharge", "T4:branch"),
            ("LA1", "T4:run_outlet", "PA:suction"),
            ("LA2", "PA:discharge", "T2:run_inlet"),
            ("LB1", "T1:branch", "PB:discharge"),
            ("LB2", "PB:suction", "T2:branch"),
            ("L2", "T2:run_outlet", "R2:port_1"),
        ],
    )
    case = _case(
        client,
        "refused-opposed-three",
        "PB turned round, PC in a loop of its own",
        opposed,
        ["PA", "PB", "PC"],
        status=422,
    )
    assert [i["code"] for i in case["groupCurve"]["body"]["issues"]] == ["MEMBERS_OPPOSED"]
    cases.append(case)

    loops = _network(
        ["R1", "T0", "TA", "TB", "PA", "PB"],
        [
            ("C0", "R1:port_1", "T0:branch"),
            ("C1", "T0:run_outlet", "TA:run_inlet"),
            ("C2", "TA:run_outlet", "PA:suction"),
            ("C3", "PA:discharge", "TA:branch"),
            ("C4", "TB:run_inlet", "T0:run_inlet"),
            ("C5", "TB:run_outlet", "PB:suction"),
            ("C6", "PB:discharge", "TB:branch"),
        ],
    )
    case = _case(
        client, "refused-own-loops", "Each pump in a loop of its own", loops, ["PA", "PB"], 422
    )
    assert [i["code"] for i in case["groupCurve"]["body"]["issues"]] == ["NO_WAY_THROUGH"]
    cases.append(case)

    floating = _dump(load(dict(items())["fuzz_2168"]))
    case = _case(
        client,
        "no-duty",
        "The station's outlet in a floating section",
        floating,
        [
            "PU1",
            "PU2",
        ],
    )
    body = case["groupCurve"]["body"]
    assert body["converged"], body
    assert body["duty"] is None, body
    cases.append(case)

    fcv = _parallel()
    _split(fcv, "L2", _dump(control_valve("FC", 1.0, "fcv", 0.06)), "inlet", "outlet")
    case = _case(
        client,
        "fcv-outside",
        "An FCV (60 L/s) on the delivery pipe, outside the station",
        fcv,
        ["PA", "PB"],
        system=200,
    )
    body = case["systemCurve"]["body"]
    assert body["systemDutyCheck"]["agrees"], body["systemDutyCheck"]
    reasons = {p["reason"] for p in body["systemPoints"] if p["head"] is None}
    assert reasons == {"beyond_limit"}, reasons
    cases.append(case)

    prv = _parallel()
    _split(prv, "LA2", _dump(control_valve("V1", 0.5, "prv", 250000.0)), "inlet", "outlet")
    case = _case(
        client,
        "prv-inside",
        "An active PRV (250 kPa) in PA's discharge leg, inside the station",
        prv,
        ["PA", "PB"],
        status=422,
        system=200,
    )
    issues = case["groupCurve"]["body"]["issues"]
    assert [i["code"] for i in issues] == ["PRESSURE_CONTROL_INSIDE"], issues
    assert case["systemCurve"]["body"]["systemDutyCheck"]["agrees"], case["systemCurve"]
    cases.append(case)

    return {"generatedBy": GENERATED_BY, "cases": cases}


def main() -> None:
    print(json.dumps(generate(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
