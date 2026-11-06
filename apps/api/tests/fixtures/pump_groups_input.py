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
it of. A case whose project has scenarios (slice 4d) also has ``scenarioCases``: for each
scenario id, ``{solve, groupCurve, systemCurve}``, the same three requests with that
``scenarioId``.

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
- ``one-off``: ``one_off_project()`` (``parallel-ideal`` on water at 20 °C, with efficiency data,
  a 15 kW motor and two design checks) with four scenarios: S1 "Pump PA off" and S2 "Pump PB off"
  exactly as the card's "Add cases with one pump off" makes them (slice 4d), S3 "Delivery tank
  5 m higher" (R2's level 7 m, an outside change) and S4 "Both pumps off" (a duty at zero
  station flow); with PB off, PA runs beyond its curve data.
- ``one-off-dead-headed``: ``dead-headed`` with S1 "Pump PA off" as the card makes it: PB, held
  at zero flow in the base case, runs with PA off.
- ``lineups`` (pump lineups, D24; docs/proposals/pump-lineups.md §10.1): ``lineups_project()``,
  four ``curve_a`` pumps P1 to P4 on Crane-tee headers, each leg with a swing check valve, on
  CoolProp water at 20 °C, every pump carrying flow in the base case; its scenarios exactly as
  the card's "Add cases" writes them, By number running in the default stop order (S1 to S3: P4,
  then P3 and P4, then P2 to P4 off), then Each pump off (S4 to S6: P1, P2, P3 off; P4's case is
  S1 already), and two for slice L3: S7 "Pump P1 at 90 % speed" (the station differs inside
  other than in which pumps are on) and S8 "Delivery tank 5 m higher" (the same inside).
- ``lineups-closed-leg``: ``closed_leg_project()``, PA and PB between two ideal tees with a gate
  valve VB on PB's discharge isolated in the base case, so PB is on and carries no flow
  (``running`` at exactly zero flow); S1 "Pump PB off", where PB's leg is closed off on both
  sides and PB has no result.
- ``two-systems`` (the pump lineups table, slice L2; docs/proposals/pump-lineups.md §10.2):
  ``two_systems_project()``, PA and PB between two Crane tees with PB off in the base case (a
  standby), the P1–P3 tee ladder of ``ladder`` and a lone pump P9 on a line of its own, on
  CoolProp water at 20 °C; S1 "PB in service, PA off" (a name the user typed), S2 "2 of 2
  running; 2 of 3 running (Pump P3 off)" (a lineup crossed over both stations, its name as the
  app makes it) and S3 "Aged pipe" (the ladder's delivery pipe ten times as rough, and P2 off).
  Its group curves are PA's and PB's.

The lineup cases are asked from a client address of their own (``_lineups_client``): with them
the fixture sends more requests than the rate limit lets one address send in a minute (the
first address sends 53, the lineup cases 45).
"""

import copy
import json
from typing import Any

from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.fluids import BuiltinFluid
from tests.differential.corpus import items, load
from tests.reference import derivations_pump_groups as dpg
from tests.reference import derivations_pumps as dp
from tests.reference.case_format import (
    check_valve,
    control_valve,
    crane_tee,
    ideal_tee,
    isolation_valve,
    make_project,
    pump,
    reservoir,
)
from tests.reference.line import Line

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


def _lineups_client() -> TestClient:
    """The lineup cases' client: the rate limit (60 requests a minute) counts by address."""
    return TestClient(app, client=("192.0.2.249", 50000))


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


def _scenario_case(
    client: TestClient, project: dict[str, Any], scenario_id: str, members: list[str]
) -> dict[str, Any]:
    """A scenario's solve, group curve and group system curve (each with its ``scenarioId``),
    trimmed and fixed as the base case's are."""
    response = client.post(
        "/api/v1/solve",
        json={
            "project": project,
            "scenarioId": scenario_id,
            "options": {"includeSystemCurve": False},
        },
    )
    assert response.status_code == 200, response.text
    solve: dict[str, Any] = response.json()
    assert solve["success"], solve.get("message")
    assert solve["solvedState"]["converged"], solve.get("message")
    solve["computeTime"] = COMPUTE_TIME
    solve["solvedState"]["timestamp"] = SOLVED_AT
    trace = solve["solvedState"]["trace"]
    trace["elements"] = {k: v for k, v in trace["elements"].items() if k in members}
    curves: dict[str, dict[str, Any]] = {}
    for kind in ("group", "system"):
        answer = client.post(
            "/api/v1/pump-group-curve",
            json={
                "project": project,
                "pumpIds": members,
                "scenarioId": scenario_id,
                **({"curve": "system"} if kind == "system" else {}),
            },
        )
        curves[kind] = {"status": answer.status_code, "body": answer.json()}
    return {"solve": solve, "groupCurve": curves["group"], "systemCurve": curves["system"]}


def _case(
    client: TestClient,
    name: str,
    description: str,
    project: dict[str, Any],
    members: list[str],
    status: int = 200,
    system: int | None = None,
    scenarios: list[str] | None = None,
) -> dict[str, Any]:
    """The case's solve, its group curve (answered with ``status``) and, when ``system`` is
    given, its group system curve (answered with that status); with ``scenarios``, the same for
    each of those scenario ids (``scenarioCases``)."""
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
    case: dict[str, Any] = {
        "name": name,
        "description": description,
        "project": project,
        "memberIds": members,
        "solve": solve,
        "groupCurve": {"status": response.status_code, "body": response.json()},
        "systemCurve": system_curve,
    }
    if scenarios is not None:
        case["scenarioCases"] = {
            sid: _scenario_case(client, project, sid, members) for sid in scenarios
        }
    return case


def _off(pump_id: str) -> dict[str, Any]:
    """The override the card's "Add cases with one pump off" makes (slice 4d)."""
    return {"kind": "component", "componentId": pump_id, "field": "status", "value": "off"}


def one_off_project() -> dict[str, Any]:
    """``parallel-ideal`` (``_parallel()``) on CoolProp water at 20 °C, which has a vapor
    pressure, so NPSH margins exist; its pump curve PC-A with an efficiency curve and a 15 kW
    motor, and two design checks (an NPSH margin of 1 m; a preferred operating region of 0.7 to
    1.2 × the BEP flow), so shaft powers and the checks have values (slice 4d). The efficiency
    points and the motor rating are illustrative manufacturer data, not from a cited datasheet,
    as the condenser water example labels its own (D22)."""
    data = _parallel()
    data["fluid"] = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    curve = data["pumpLibrary"][0]
    curve["efficiencyCurve"] = [
        {"flow": flow, "efficiency": efficiency}
        for flow, efficiency in ((0.01, 0.50), (0.02, 0.68), (0.03, 0.74), (0.04, 0.70))
    ]
    curve["motorRatedPower"] = 15000.0
    data["settings"]["designChecks"] = {
        "npshMargin": {"minimumMargin": 1.0, "source": {"kind": "user"}},
        "operatingRegion": {
            "preferredMin": 0.7,
            "preferredMax": 1.2,
            "source": {"kind": "user"},
        },
    }
    return data


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


def fcv_outside_project() -> dict[str, Any]:
    """``parallel-ideal`` with an FCV FC (setpoint 60 L/s) on the delivery pipe, outside the
    station (this fixture's ``fcv-outside``, and the export fixture's ``pump-groups``)."""
    fcv = _parallel()
    _split(fcv, "L2", _dump(control_valve("FC", 1.0, "fcv", 0.06)), "inlet", "outlet")
    return fcv


WATER_20C = BuiltinFluid(kind="builtin", fluid_id="water", temperature=293.15)
"""CoolProp water at 20 °C (it has a vapor pressure, so NPSH margins exist)."""

LINEUP_HEADER = Line(0.2027, 1.5)
"""The headers between neighbouring tees of ``lineups`` (test input)."""
LINEUP_OUTLET = Line(0.1541, 150.0, (("elbow_90_lr", 2), ("exit", 1)))
"""``lineups``' delivery line to the upper tank (test input)."""
CLOSED_LEG_PIPE = Line(0.1023, 5.0)
"""Every pipe of ``lineups-closed-leg`` (test input)."""


def lineups_project() -> dict[str, Any]:
    """Four ``curve_a`` pumps on a Crane-tee ladder (the pump lineups proposal's measurement
    station, §3.3 and §10.1; the derivations' ``Ladder`` layout): R1 → L0 → TS1:run_inlet; leg k
    leaves TSk:branch (k < 4) and TS3:run_outlet feeds leg 4; TSk:run_outlet → HSk →
    TS(k+1):run_inlet. Leg k: a suction pipe, Pk, a pipe, a swing check valve CVk and a pipe to
    TDk:branch (k < 4), leg 4 to TD3:run_inlet; TD(k+1):run_outlet → HDk → TDk:run_inlet;
    TD1:run_outlet → Lout → R2, whose level is 20 m above R1's, the pumps 3 m above R1's level.
    Every dimension is a test input; the efficiency points are ``one_off_project``'s,
    illustrative."""
    n = 4
    curve = dp.curve_a()
    components: list[Any] = [reservoir("R1", 0.0, 1.0)]
    components += [crane_tee(f"TS{k + 1}", 0.5) for k in range(n - 1)]
    connections = [dpg.LADDER_INLET.connect("L0", "R1:port_1", "TS1:run_inlet")]
    starts = [f"TS{k + 1}:branch" for k in range(n - 1)] + [f"TS{n - 1}:run_outlet"]
    ends = [f"TD{k + 1}:branch" for k in range(n - 1)] + [f"TD{n - 1}:run_inlet"]
    for k in range(n - 2):
        connections += [
            LINEUP_HEADER.connect(f"HS{k + 1}", f"TS{k + 1}:run_outlet", f"TS{k + 2}:run_inlet"),
            LINEUP_HEADER.connect(f"HD{k + 1}", f"TD{k + 2}:run_outlet", f"TD{k + 1}:run_inlet"),
        ]
    for k in range(n):
        pid, cv = f"P{k + 1}", f"CV{k + 1}"
        components += [pump(pid, 4.0, curve.id), check_valve(cv, 4.0, "check")]
        connections += [
            dpg.SUCTION_LEG.connect(f"S{k + 1}", starts[k], f"{pid}:suction"),
            dpg.DISCHARGE_TO_CV.connect(f"D{k + 1}a", f"{pid}:discharge", f"{cv}:inlet"),
            dpg.DISCHARGE_FROM_CV.connect(f"D{k + 1}b", f"{cv}:outlet", ends[k]),
        ]
    components += [crane_tee(f"TD{k + 1}", 1.0) for k in range(n - 1)]
    components.append(reservoir("R2", 19.0, 2.0))
    connections.append(LINEUP_OUTLET.connect("Lout", "TD1:run_outlet", "R2:port_1"))
    project = make_project(
        "lineups",
        "Four pumps on Crane tees",
        WATER_20C,
        components,
        connections,
        pump_library=[curve],
    )
    data = _dump(project)
    data["pumpLibrary"][0]["efficiencyCurve"] = copy.deepcopy(
        one_off_project()["pumpLibrary"][0]["efficiencyCurve"]
    )
    return data


def closed_leg_project() -> dict[str, Any]:
    """PA and PB between two ideal tees (the pump lineups review's probe, §3.5): R1 → L1 → T1;
    T1:run_outlet → a1 → PA → a2 → T2:run_inlet; T1:branch → b1 → PB → b2 → VB (a gate valve,
    isolated in the base case) → b3 → T2:branch; T2:run_outlet → L2 → R2. PB is on and carries
    no flow. Every dimension is a test input."""
    curve = dp.curve_a()
    pipe = CLOSED_LEG_PIPE
    components: list[Any] = [
        reservoir("R1", 0.0, 1.0),
        ideal_tee("T1", 0.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id),
        isolation_valve("VB", 0.0, "gate", status="isolated"),
        ideal_tee("T2", 0.0),
        reservoir("R2", 25.0, 2.0),
    ]
    connections = [
        pipe.connect("L1", "R1:port_1", "T1:run_inlet"),
        pipe.connect("a1", "T1:run_outlet", "PA:suction"),
        pipe.connect("a2", "PA:discharge", "T2:run_inlet"),
        pipe.connect("b1", "T1:branch", "PB:suction"),
        pipe.connect("b2", "PB:discharge", "VB:inlet"),
        pipe.connect("b3", "VB:outlet", "T2:branch"),
        pipe.connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    project = make_project(
        "lineups-closed-leg",
        "PB behind a closed valve",
        WATER_20C,
        components,
        connections,
        pump_library=[curve],
    )
    return _dump(project)


TWO_SYSTEMS_AGED_ROUGHNESS = 4.5e-4
"""m; the absolute roughness of the ladder's delivery line in ``two-systems``' "Aged pipe" (a test
input: ten times the line's own, ``tests/reference/line.py`` ROUGHNESS)."""


def two_systems_project() -> dict[str, Any]:
    """Three pumped lines in one project, each between reservoirs of its own (the pump lineups
    table, docs/proposals/pump-lineups.md §10.2), in this component order:

    - PA and PB between two Crane tees, ``closed_leg_project``'s layout without its valve: R1 →
      L1 → T1:run_inlet; T1:run_outlet → a1 → PA → a2 → T2:run_inlet; T1:branch → b1 → PB → b2
      → T2:branch; T2:run_outlet → L2 → R2. PB is off in the base case (a standby);
    - the P1–P3 tee ladder of ``ladder`` (``derivations_pump_groups.ladder_project``), its
      reservoirs renamed R3 and R4;
    - a lone pump P9 on a line of its own: R5 → L9a → P9 → L9b → R6.

    Every dimension is a test input."""
    curve = dp.curve_a()
    pipe = CLOSED_LEG_PIPE
    station: list[Any] = [
        reservoir("R1", 0.0, 1.0),
        crane_tee("T1", 0.0),
        pump("PA", 0.0, curve.id),
        pump("PB", 0.0, curve.id, status="off"),
        crane_tee("T2", 0.0),
        reservoir("R2", 25.0, 2.0),
    ]
    station_links = [
        pipe.connect("L1", "R1:port_1", "T1:run_inlet"),
        pipe.connect("a1", "T1:run_outlet", "PA:suction"),
        pipe.connect("a2", "PA:discharge", "T2:run_inlet"),
        pipe.connect("b1", "T1:branch", "PB:suction"),
        pipe.connect("b2", "PB:discharge", "T2:branch"),
        pipe.connect("L2", "T2:run_outlet", "R2:port_1"),
    ]
    ladder = dpg.ladder_project()
    renamed = {"R1": "R3", "R2": "R4"}
    ladder_parts = [
        c.model_copy(update={"id": renamed[c.id], "name": f"Reservoir {renamed[c.id]}"})
        if c.id in renamed
        else c
        for c in ladder.components
    ]
    ladder_links = [
        c.model_copy(
            update={
                "from_component_id": renamed.get(c.from_component_id, c.from_component_id),
                "to_component_id": renamed.get(c.to_component_id, c.to_component_id),
            }
        )
        for c in ladder.connections
    ]
    lone: list[Any] = [
        reservoir("R5", 0.0, 1.0),
        pump("P9", 0.0, curve.id),
        reservoir("R6", 25.0, 2.0),
    ]
    lone_links = [
        pipe.connect("L9a", "R5:port_1", "P9:suction"),
        pipe.connect("L9b", "P9:discharge", "R6:port_1"),
    ]
    project = make_project(
        "two-systems",
        "Two stations and a lone pump",
        WATER_20C,
        [*station, *ladder_parts, *lone],
        [*station_links, *ladder_links, *lone_links],
        pump_library=list(ladder.pump_library),
    )
    assert curve.id in {c.id for c in ladder.pump_library}
    return _dump(project)


def _status(pump_id: str, value: str) -> dict[str, Any]:
    """A pump's status change, as Build's Status segment and the lineups table write it."""
    return {"kind": "component", "componentId": pump_id, "field": "status", "value": value}


def _carries_flow(result: dict[str, Any]) -> bool:
    """On, with its flow above the duty check's floor (10⁻⁶ m³/s; pump-lineups.md §3.5)."""
    return bool(result["status"] != "off" and abs(result["operatingFlow"]) > 1.0e-6)


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

    case = _case(
        client,
        "fcv-outside",
        "An FCV (60 L/s) on the delivery pipe, outside the station",
        fcv_outside_project(),
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

    one_off = one_off_project()
    assert _component(one_off, "R2")["liquidLevel"] == 2.0
    one_off["scenarios"] = [
        {"id": "S1", "name": "Pump PA off", "overrides": [_off("PA")]},
        {"id": "S2", "name": "Pump PB off", "overrides": [_off("PB")]},
        {
            "id": "S3",
            "name": "Delivery tank 5 m higher",
            "overrides": [
                {"kind": "component", "componentId": "R2", "field": "liquidLevel", "value": 7.0}
            ],
        },
        {"id": "S4", "name": "Both pumps off", "overrides": [_off("PA"), _off("PB")]},
    ]
    case = _case(
        client,
        "one-off",
        "parallel-ideal on water with manufacturer data and design checks; each pump off, the "
        "delivery tank 5 m higher, both pumps off",
        one_off,
        ["PA", "PB"],
        system=200,
        scenarios=["S1", "S2", "S3", "S4"],
    )
    base_station = case["groupCurve"]["body"]["station"]
    for sid, scenario_case in case["scenarioCases"].items():
        assert scenario_case["groupCurve"]["status"] == 200, (sid, scenario_case["groupCurve"])
        assert scenario_case["groupCurve"]["body"]["station"] == base_station, sid
    s2 = case["scenarioCases"]["S2"]["solve"]["solvedState"]
    assert s2["pumpResults"]["PA"]["inCurveRange"] is False, s2["pumpResults"]["PA"]
    assert any(
        f["code"] == "PUMP_OUTSIDE_CURVE" and f.get("componentId") == "PA" for f in s2["flags"]
    ), s2["flags"]
    s4_duty = case["scenarioCases"]["S4"]["groupCurve"]["body"]["duty"]
    assert abs(s4_duty["flow"]) < 1e-6, s4_duty
    assert case["solve"]["solvedState"]["designChecks"], case["solve"]["solvedState"]
    cases.append(case)

    dead_off = _parallel()
    _component(dead_off, "PB")["speed"] = 0.7
    dead_off["scenarios"] = [{"id": "S1", "name": "Pump PA off", "overrides": [_off("PA")]}]
    case = _case(
        client,
        "one-off-dead-headed",
        "dead-headed with PA off: PB, held at zero flow in the base case, runs",
        dead_off,
        ["PA", "PB"],
        scenarios=["S1"],
    )
    assert case["solve"]["solvedState"]["pumpResults"]["PB"]["status"] == "no_flow"
    s1 = case["scenarioCases"]["S1"]["solve"]["solvedState"]
    assert s1["pumpResults"]["PB"]["status"] == "running", s1["pumpResults"]["PB"]
    cases.append(case)

    client = _lineups_client()
    lineups = lineups_project()
    members = ["P1", "P2", "P3", "P4"]

    def lineup(sid: str, name: str, stopped: list[str]) -> dict[str, Any]:
        return {"id": sid, "name": name, "overrides": [_off(p) for p in stopped]}

    lineups["scenarios"] = [
        lineup("S1", "3 of 4 running (Pump P4 off)", ["P4"]),
        lineup("S2", "2 of 4 running (Pump P3, Pump P4 off)", ["P3", "P4"]),
        lineup("S3", "1 of 4 running (Pump P2, Pump P3, Pump P4 off)", ["P2", "P3", "P4"]),
        lineup("S4", "Pump P1 off", ["P1"]),
        lineup("S5", "Pump P2 off", ["P2"]),
        lineup("S6", "Pump P3 off", ["P3"]),
        {
            "id": "S7",
            "name": "Pump P1 at 90 % speed",
            "overrides": [
                {"kind": "component", "componentId": "P1", "field": "speed", "value": 0.9}
            ],
        },
        {
            "id": "S8",
            "name": "Delivery tank 5 m higher",
            "overrides": [
                {"kind": "component", "componentId": "R2", "field": "liquidLevel", "value": 7.0}
            ],
        },
    ]
    case = _case(
        client,
        "lineups",
        "Four pumps on Crane tees; by number running, each pump off, one pump's speed and the "
        "delivery tank 5 m higher",
        lineups,
        members,
        system=200,
        scenarios=[s["id"] for s in lineups["scenarios"]],
    )
    results = case["solve"]["solvedState"]["pumpResults"]
    assert all(_carries_flow(results[m]) for m in members), results
    base_station = case["groupCurve"]["body"]["station"]
    for sid, scenario_case in case["scenarioCases"].items():
        assert scenario_case["groupCurve"]["status"] == 200, (sid, scenario_case["groupCurve"])
        assert scenario_case["groupCurve"]["body"]["station"] == base_station, sid
        assert scenario_case["systemCurve"]["status"] == 200, (sid, scenario_case["systemCurve"])
    cases.append(case)

    closed = closed_leg_project()
    closed["scenarios"] = [lineup("S1", "Pump PB off", ["PB"])]
    case = _case(
        client,
        "lineups-closed-leg",
        "PA and PB between ideal tees, PB's discharge valve isolated: PB on at zero flow; PB off",
        closed,
        ["PA", "PB"],
        system=200,
        scenarios=["S1"],
    )
    pb = case["solve"]["solvedState"]["pumpResults"]["PB"]
    assert pb["status"] == "running", pb
    assert pb["operatingFlow"] == 0.0, pb
    assert _carries_flow(case["solve"]["solvedState"]["pumpResults"]["PA"])
    # With PB off too, its leg is closed off on both sides: no result for PB (ISOLATED_SECTION).
    s1 = case["scenarioCases"]["S1"]["solve"]["solvedState"]["pumpResults"]
    assert "PB" not in s1, s1
    assert _carries_flow(s1["PA"]), s1["PA"]
    cases.append(case)

    two = two_systems_project()
    lout = _connection(two, "Lout")["piping"]["pipes"][0]
    aged = {
        "kind": "pipe",
        "connectionId": "Lout",
        "pipeIndex": 0,
        "field": "spec",
        "value": {
            "materialId": lout["materialId"],
            "innerDiameter": lout["innerDiameter"],
            "roughness": TWO_SYSTEMS_AGED_ROUGHNESS,
        },
    }
    assert lout["roughness"] != TWO_SYSTEMS_AGED_ROUGHNESS, lout
    two["scenarios"] = [
        {
            "id": "S1",
            "name": "PB in service, PA off",
            "overrides": [_status("PB", "on"), _off("PA")],
        },
        {
            "id": "S2",
            "name": "2 of 2 running; 2 of 3 running (Pump P3 off)",
            "overrides": [_status("PB", "on"), _off("P3")],
        },
        {"id": "S3", "name": "Aged pipe", "overrides": [aged, _off("P2")]},
    ]
    case = _case(
        client,
        "two-systems",
        "PA and PB between two tees (PB a standby, off in the base case), the P1–P3 tee ladder "
        "and a lone pump P9; PB in service with PA off, a lineup crossed over both stations, and "
        "an aged delivery pipe with P2 off",
        two,
        ["PA", "PB"],
        system=200,
        scenarios=["S1", "S2", "S3"],
    )
    base = case["solve"]["solvedState"]["pumpResults"]
    assert base["PB"]["status"] == "off", base["PB"]
    assert all(_carries_flow(base[p]) for p in ("PA", "P1", "P9")), base
    # Every change of each scenario applied, as the server records it (D15).
    applied = {
        sid: {
            (o.get("componentId") or o.get("connectionId"), o["field"])
            for r in sc["solve"]["scenario"]["overrides"]
            if r["state"] == "applied"
            for o in [r["override"]]
        }
        for sid, sc in case["scenarioCases"].items()
    }
    assert applied == {
        "S1": {("PB", "status"), ("PA", "status")},
        "S2": {("PB", "status"), ("P3", "status")},
        "S3": {("Lout", "spec"), ("P2", "status")},
    }, applied
    s1 = case["scenarioCases"]["S1"]["solve"]["solvedState"]["pumpResults"]
    assert s1["PA"]["status"] == "off", s1["PA"]
    assert _carries_flow(s1["PB"]), s1["PB"]
    s2 = case["scenarioCases"]["S2"]["solve"]["solvedState"]["pumpResults"]
    assert all(_carries_flow(s2[p]) for p in ("PA", "PB")), s2
    assert s2["P3"]["status"] == "off", s2["P3"]
    s3 = case["scenarioCases"]["S3"]["solve"]["solvedState"]["pumpResults"]
    assert s3["P2"]["status"] == "off", s3["P2"]
    assert s3["PB"]["status"] == "off", s3["PB"]
    cases.append(case)

    return {"generatedBy": GENERATED_BY, "cases": cases}


def main() -> None:
    print(json.dumps(generate(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
