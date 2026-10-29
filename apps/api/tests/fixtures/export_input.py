"""The shared export fixture of the web app (docs/proposals/export.md §7.2).

    cd apps/api && uv run python -m tests.fixtures.export_input \
        > ../web/src/lib/utils/__fixtures__/export-input.json

``apps/web/scripts/gen-api-types.sh`` (``pnpm gen:types``) writes it with ``openapi.json``; it is
generated, never edited by hand. Every response in it is the real API's, through the real app
(``POST /api/v1/solve``, ``/system-curve`` and ``/goal-seek``, ``GET /api/v1/library``), so the
web's export model (``utils/export/``) is checked against what the server returns, and its
committed workbook (``export-results.xlsx``, written by ``utils/export/fixture.test.ts``) is read
back by openpyxl.

Each case is an ``ExportInput`` of the web (``utils/export/model.ts``) in JSON, with ``now`` as
an ISO 8601 string, and every value the page would add fixed: the export's time and a nonzero UTC
offset (+120 min), the build commit, the server's source link and the origin; each solve's
timestamp and compute time, and the goal seek's run time and seconds, are replaced by constants
so the fixture does not change from one run to the next.

- ``pump-transfer``: the "Pump transfer between two tanks" example, its pump's system curve and
  a finished goal seek (the pump's speed for a flow), exported as the case shown, display units.
- ``scenarios``: a project with two scenarios, a Crane tee, a PRV, a reservoir with two ports, a
  reference node, an assigned-flow node, two equipment items, a strainer rated by a pressure
  drop at a flow and a cooler rated by a Kv (proposal equipment-pressure-drop.md §7.6), an
  orifice flow meter with flange taps on ISO 5167-2's C whose outlet pipe is a size up
  (proposal orifice-plate.md §7.6), and, on a pressure tank of its own, a relief valve on an API
  526 letter discharging to atmosphere, its outlet pipe a size up, closed in the base case
  (proposal pressure-relief-valve.md §7.6); one scenario changes the PRV's resistance to a Cv, a
  reservoir's level, the strainer's rated pressure drop (a dirty strainer), the meter's bore (a
  second plate) and the relief valve's set and letter (a lower set on a larger valve, so that it
  relieves at partial lift), the other sets a negative assigned flow (a supply), a pipe's length
  and the meter's discharge coefficient (a calibration at its taps, moved to D and D/2 tappings
  for the loss); names hold ``_x0041_x0042_`` (two escapes that share an underscore) and a CR, a
  formula (``=HYPERLINK(...)``) and a leading ``-``. Its Compare rows include the four orifice
  quantities on the meter (proposal orifice-plate.md §5.3) and the relief valve's five
  (pressure-relief-valve.md decision 20). Exported as All cases, SI base units: the committed
  workbook.
- ``tee-fallback``: ``tests/reference/cases/tee_crane_bullhead_fallback.json``, a tee on the Darby
  3-K fallback (TEE_PATTERN_FALLBACK), in US display units: its K values are on the combined-flow
  velocity (export.md decision 29).
- ``design-checks``: ``pump_system.json`` with every design check on (CLAUDE.md D19): the pump at
  90 % speed with an efficiency curve and the manufacturer data, but no NPSHr curve, so the
  results are not met, met and not evaluated; API 610's preferred region, HI 9.6.1-2012's NPSH
  margin and a 3 m/s maximum velocity; US display units.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.scenarios import apply_scenario

GENERATED_BY = "apps/api/tests/fixtures/export_input.py"

TESTS = Path(__file__).parents[1]
NOW = "2026-10-25T12:32:05.000Z"
UTC_OFFSET_MINUTES = 120
APP_VERSION = "0123456789abcdef0123456789abcdef01234567"
SERVER_SOURCE = "https://api.opensolve-pipe.app/source"
ORIGIN = "https://opensolve-pipe.app"
SOLVED_AT = "2026-10-25T12:30:00Z"
COMPUTE_TIME = 0.125
GOAL_SEEK_STARTED_AT = int(datetime(2026, 10, 25, 12, 31, 0, tzinfo=UTC).timestamp() * 1000)
GOAL_SEEK_SECONDS = 0.05
GOAL_SEEK_COMPUTE_TIME = 1.5

SI_UNITS = {
    "length": "m",
    "diameter": "mm",
    "pressure": "kPa",
    "head": "m",
    "flow": "L/s",
    "velocity": "m/s",
    "temperature": "C",
    "density": "kg/m3",
    "viscosity": "mPa.s",
}
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
    return TestClient(app, client=("192.0.2.251", 50000))


def _post(client: TestClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=body)
    assert response.status_code == 200, (path, response.text)
    result: dict[str, Any] = response.json()
    return result


def _fixed_solve(response: dict[str, Any]) -> dict[str, Any]:
    """A solve response with its timestamp and compute time replaced by constants."""
    fixed = copy.deepcopy(response)
    fixed["computeTime"] = COMPUTE_TIME
    fixed["solvedState"]["timestamp"] = SOLVED_AT
    return fixed


def _solve(client: TestClient, project: dict[str, Any], scenario: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {"project": project, "options": {"includeSystemCurve": False}}
    if scenario is not None:
        body["scenarioId"] = scenario
    response = _post(client, "/api/v1/solve", body)
    assert response["success"], scenario
    assert response["solvedState"]["converged"], scenario
    return _fixed_solve(response)


def _library(client: TestClient) -> dict[str, Any]:
    """The library's names as the page holds them (LibraryStore: materials, fittings, sizes)."""
    response = client.get("/api/v1/library")
    assert response.status_code == 200, response.text
    library = response.json()
    sizes: dict[float, str] = {}
    for material in library["materials"]:
        for schedule in material["schedules"]:
            for size in schedule["sizes"]:
                if not any(abs(s - size["nominalSize"]) <= 1e-9 * s for s in sizes):
                    sizes[size["nominalSize"]] = size["nps"]
    return {
        "materials": {m["id"]: m["name"] for m in library["materials"]},
        "fittings": {f["type"]: f["name"] for f in library["fittings"]},
        "nominalSizes": [{"nominalSize": s, "nps": sizes[s]} for s in sorted(sizes)],
    }


def _case(
    project: dict[str, Any],
    response: dict[str, Any],
    case_id: str | None,
    name: str,
    system_curves: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = (
        project
        if case_id is None
        else apply_scenario(Project.model_validate(project), case_id).project.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
    )
    return {
        "id": case_id,
        "name": name,
        "status": "solved",
        "response": response,
        "stale": False,
        "error": None,
        "keptResponse": False,
        "sent": project,
        "inputs": inputs,
        "systemCurves": system_curves or {},
    }


def _input(
    project: dict[str, Any],
    cases: list[dict[str, Any]],
    library: dict[str, Any],
    *,
    options: dict[str, Any],
    compare_rows: list[dict[str, Any]] | None = None,
    goal_seek: dict[str, Any] | None = None,
    loaded_method_version: str = "",
) -> dict[str, Any]:
    return {
        "options": options,
        "now": NOW,
        "utcOffsetMinutes": UTC_OFFSET_MINUTES,
        "appVersion": APP_VERSION,
        "serverSource": SERVER_SOURCE,
        "origin": ORIGIN,
        "project": project,
        "prefs": project["settings"]["units"],
        "library": library,
        "shownCase": None,
        "cases": cases,
        "compareRows": compare_rows or [{"quantity": "status"}],
        "goalSeek": goal_seek,
        "loadedMethodVersion": loaded_method_version,
    }


def pump_transfer(client: TestClient, library: dict[str, Any]) -> dict[str, Any]:
    project = json.loads((TESTS / "fixtures" / "pump_system.json").read_text())
    project["settings"]["units"] = dict(SI_UNITS)
    response = _solve(client, project, None)
    curve = _post(client, "/api/v1/system-curve", {"project": project, "pumpId": "P1"})
    flow = response["solvedState"]["linkResults"]["L2"]["flow"]
    request = {
        "project": project,
        "variables": [
            {"kind": "component", "componentId": "P1", "field": "speed", "lower": 0.5, "upper": 1.0}
        ],
        "goals": [{"quantity": "link_flow", "elementId": "L2", "target": round(0.8 * flow, 4)}],
    }
    goal = _post(client, "/api/v1/goal-seek", request)
    goal["computeTime"] = GOAL_SEEK_COMPUTE_TIME
    for evaluation in goal["result"]["evaluations"]:
        evaluation["seconds"] = GOAL_SEEK_SECONDS
    if goal["solvedState"] is not None:
        goal["solvedState"]["timestamp"] = SOLVED_AT
    goal_seek = {
        "status": "done",
        "run": {
            "caseId": None,
            "request": request,
            "project": project,
            "key": "fixture",
            "startedAt": GOAL_SEEK_STARTED_AT,
        },
        "response": goal,
        "error": None,
        "stale": False,
        "applied": None,
        "appliedCurrent": False,
    }
    return _input(
        project,
        [
            _case(
                project,
                response,
                None,
                "Base case",
                {"P1": {"status": "ready", "curve": curve}},
            )
        ],
        library,
        options={"cases": "shown", "format": "xlsx", "units": "display", "link": True},
        goal_seek=goal_seek,
    )


def _ports(*ids: str, size: float = 0.0762) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": size} for p in ids]


def _steel(length: float, size: float = 0.0762) -> dict[str, Any]:
    return {"materialId": "carbon_steel", "schedule": "40", "nominalSize": size, "length": length}


def _custom(length: float, diameter: float) -> dict[str, Any]:
    return {
        "materialId": "custom",
        "length": length,
        "innerDiameter": diameter,
        "roughness": 4.5e-5,
    }


def _link(
    cid: str,
    a: tuple[str, str],
    b: tuple[str, str],
    pipes: list[dict[str, Any]],
    fittings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": cid,
        "fromComponentId": a[0],
        "fromPortId": a[1],
        "toComponentId": b[0],
        "toPortId": b[1],
        "piping": {"pipes": pipes, "fittings": fittings or []},
    }


STRAINER_RATING = {"kind": "point", "pressureLoss": 20000.0, "flow": 0.01, "density": 999.102621}
"""The strainer E1's rating (test input): 20 kPa at 10 L/s on water at 15 °C."""
COOLER_RATING = {"kind": "Kv", "value": 60.0}
"""The cooler E2's rating (test input): Kv 60."""
ORIFICE_BORE = 0.025
"""m: the flow meter O1's bore (test input), β 0.5 in its 50 mm inlet pipe."""
RELIEF_SET, RELIEF_LETTER = 350000.0, "J"
"""Pa (a difference) and an API 526 letter: the relief valve RV1's set and orifice (test inputs),
above the pressure tank R4's 280 kPa(g) and 2 m of water (about 300 kPa), so that it is closed
in the base case."""


def scenario_project() -> dict[str, Any]:
    """R1 (two ports) feeds a Crane tee T1, whose run goes through the strainer E1 and PRV1 to
    R2 and whose branch ends at the demand AF1; R1's second port feeds the reference node R3
    through the orifice flow meter O1 and the cooler E2. Apart, the pressure tank R4 (a part of
    the network with fixed heads of its own) feeds the relief valve RV1, which discharges to
    atmosphere (the web's open discharge: 1 m of pipe with an exit to the reference node N1 at
    0 kPa(g), at the valve's elevation). E1's, O1's and RV1's outlet pipes
    are a size up and E2's outlet port 0.5 m up, so each element's static pressure drop differs
    from its pressure loss (proposal equipment-pressure-drop.md §3.3, orifice-plate.md §3.7) or
    total-pressure difference (pressure-relief-valve.md §2.2), and a column that swapped them
    would fail."""
    components = [
        {
            "type": "reservoir",
            "id": "R1",
            "name": "Supply tank",
            "elevation": 0.0,
            "liquidLevel": 30.0,
            "surfacePressure": 0.0,
            "ports": _ports("port_1", "port_2"),
        },
        {
            "type": "branch",
            "branchType": "tee",
            "id": "T1",
            "name": "Header tee",
            "elevation": 0.0,
            "lossModel": "crane",
            "ports": _ports("run_inlet", "run_outlet", "branch"),
        },
        {
            "type": "valve",
            "valveType": "prv",
            "id": "PRV1",
            "name": "Pressure-reducing valve",
            "elevation": 0.0,
            "setpoint": 120000.0,
            "ports": _ports("inlet", "outlet"),
        },
        {
            "type": "equipment",
            "id": "E1",
            "name": "Y-strainer",
            "elevation": 0.0,
            "rating": STRAINER_RATING,
            "ports": _ports("inlet", "outlet"),
        },
        {
            "type": "equipment",
            "id": "E2",
            "name": "Cooler (hot side)",
            "elevation": 0.0,
            "rating": COOLER_RATING,
            "ports": [
                {"id": "inlet", "nominalSize": 0.0508},
                {"id": "outlet", "nominalSize": 0.0508, "elevation": 0.5},
            ],
        },
        {
            "type": "orifice",
            "id": "O1",
            "name": "Cooler flow meter",
            "elevation": 0.0,
            "boreDiameter": ORIFICE_BORE,
            "taps": "flange",
            "ports": _ports("inlet", "outlet", size=0.0508),
        },
        {
            "type": "reservoir",
            "id": "R4",
            "name": "Pressure tank",
            "elevation": 0.0,
            "liquidLevel": 2.0,
            "surfacePressure": 280000.0,
            "ports": _ports("port_1"),
        },
        {
            "type": "relief_valve",
            "id": "RV1",
            "name": "Header relief valve",
            "elevation": 0.0,
            "setPressure": RELIEF_SET,
            "capacity": {"kind": "api526", "letter": RELIEF_LETTER},
            "ports": [
                {"id": "inlet", "nominalSize": 0.0762},
                {"id": "outlet", "nominalSize": 0.1016},
            ],
        },
        {
            "type": "reference_node",
            "referenceType": "ideal",
            "id": "N1",
            "name": "Relief discharge",
            "elevation": 0.0,
            "pressure": 0.0,
            "ports": _ports("port_1", size=0.1016),
        },
        {
            "type": "reservoir",
            "id": "R2",
            "name": "Low tank_x0041_x0042_\r(B)",
            "elevation": 0.0,
            "liquidLevel": 5.0,
            "surfacePressure": 0.0,
            "ports": _ports("port_1"),
        },
        {
            "type": "assigned_flow",
            "id": "AF1",
            "name": '=HYPERLINK("https://example.com","Demand")',
            "elevation": 1.0,
            "flow": 0.003,
            "ports": _ports("port_1", size=0.0508),
        },
        {
            "type": "reference_node",
            "referenceType": "ideal",
            "id": "R3",
            "name": "-North main",
            "elevation": 0.0,
            "pressure": 200000.0,
            "ports": _ports("port_1"),
        },
    ]
    connections = [
        _link(
            "L1",
            ("R1", "port_1"),
            ("T1", "run_inlet"),
            [_steel(20.0)],
            [{"type": "entrance_sharp", "quantity": 1, "pipeIndex": 0}],
        ),
        _link("L2", ("T1", "run_outlet"), ("E1", "inlet"), [_steel(10.0)]),
        _link("L6", ("E1", "outlet"), ("PRV1", "inlet"), [_steel(2.0, size=0.1016)]),
        _link(
            "L3",
            ("PRV1", "outlet"),
            ("R2", "port_1"),
            [_steel(200.0), _steel(100.0, size=0.1016)],
            [
                {"type": "elbow_90_lr", "quantity": 2, "pipeIndex": 0},
                {"type": "reducer_sudden", "quantity": 1, "pipeIndex": 0},
                {"type": "exit", "quantity": 1, "pipeIndex": 1},
            ],
        ),
        _link("L4", ("T1", "branch"), ("AF1", "port_1"), [_custom(15.0, 0.05)]),
        _link("L5", ("R1", "port_2"), ("O1", "inlet"), [_custom(50.0, 0.05)]),
        _link("L8", ("O1", "outlet"), ("E2", "inlet"), [_custom(3.0, 0.0627)]),
        _link("L7", ("E2", "outlet"), ("R3", "port_1"), [_custom(5.0, 0.05)]),
        _link(
            "L9",
            ("R4", "port_1"),
            ("RV1", "inlet"),
            [_steel(3.0)],
            [{"type": "entrance_sharp", "quantity": 1, "pipeIndex": 0}],
        ),
        _link(
            "L10",
            ("RV1", "outlet"),
            ("N1", "port_1"),
            [_steel(1.0, size=0.1016)],
            [{"type": "exit", "quantity": 1, "pipeIndex": 0}],
        ),
    ]
    return {
        "schemaVersion": 1,
        "methodVersion": "",
        "id": "fixture-export-scenarios",
        "metadata": {
            "name": "Plant water header",
            "description": (
                "Export fixture: a tee, a PRV, a demand, a strainer, a flow meter, a cooler and "
                "a relief valve, with two scenarios."
            ),
            "created": "2026-10-25T00:00:00Z",
            "modified": "2026-10-25T00:00:00Z",
        },
        "settings": {
            "units": dict(SI_UNITS),
            "siteElevation": 120.0,
            "solverOptions": {
                "frictionMethod": "colebrook",
                "maxIterations": 100,
                "tolerance": 1e-9,
            },
        },
        "fluid": {"kind": "builtin", "fluidId": "water", "temperature": 293.15},
        "components": components,
        "connections": connections,
        "pumpLibrary": [],
        "scenarios": [
            {
                "id": "S1",
                "name": "Cv valve",
                "description": (
                    "The PRV with a Cv 120 trim, a higher low tank, a dirty strainer, a larger "
                    "meter bore and a lower relief set on a K orifice."
                ),
                "overrides": [
                    {
                        "kind": "component",
                        "componentId": "PRV1",
                        "field": "resistance",
                        "value": {"kind": "Cv", "value": 120},
                    },
                    {
                        "kind": "component",
                        "componentId": "R2",
                        "field": "liquidLevel",
                        "value": 6.0,
                    },
                    {
                        "kind": "component",
                        "componentId": "E1",
                        "field": "rating.pressureLoss",
                        "value": 40000.0,
                    },
                    {
                        "kind": "component",
                        "componentId": "O1",
                        "field": "boreDiameter",
                        "value": 0.03,
                    },
                    {
                        "kind": "component",
                        "componentId": "RV1",
                        "field": "setPressure",
                        "value": 270000.0,
                    },
                    {
                        "kind": "component",
                        "componentId": "RV1",
                        "field": "capacity.letter",
                        "value": "K",
                    },
                ],
            },
            {
                "id": "S2",
                "name": "Supply at AF1",
                "overrides": [
                    {"kind": "component", "componentId": "AF1", "field": "flow", "value": -0.002},
                    {
                        "kind": "pipe",
                        "connectionId": "L4",
                        "pipeIndex": 0,
                        "field": "length",
                        "value": 25.0,
                    },
                    {
                        "kind": "component",
                        "componentId": "O1",
                        "field": "dischargeCoefficient",
                        "value": 0.62,
                    },
                ],
            },
        ],
    }


def scenarios(client: TestClient, library: dict[str, Any]) -> dict[str, Any]:
    project = scenario_project()
    cases = [
        _case(project, _solve(client, project, case_id), case_id, name)
        for case_id, name in ((None, "Base case"), ("S1", "Cv valve"), ("S2", "Supply at AF1"))
    ]
    rows = [
        {"quantity": "status"},
        {"quantity": "valveFlow", "elementId": "PRV1"},
        {"quantity": "valveState", "elementId": "PRV1"},
        {"quantity": "linkFlow", "elementId": "L4"},
        {"quantity": "portPressure", "elementId": "T1", "portId": "branch"},
        {"quantity": "boundaryOutflow", "elementId": "R1"},
        {"quantity": "assignedPressure", "elementId": "AF1"},
        {"quantity": "equipmentFlow", "elementId": "E1"},
        {"quantity": "equipmentPressureLoss", "elementId": "E1"},
        {"quantity": "equipmentPressureDrop", "elementId": "E2"},
        # proposal orifice-plate.md §5.3: Compare's four orifice quantities, on the flow meter
        {"quantity": "orificeFlow", "elementId": "O1"},
        {"quantity": "orificePressureLoss", "elementId": "O1"},
        {"quantity": "orificeDifferentialPressure", "elementId": "O1"},
        {"quantity": "orificePressureDrop", "elementId": "O1"},
        # proposal pressure-relief-valve.md decision 20: the relief valve's five quantities
        {"quantity": "reliefFlow", "elementId": "RV1"},
        {"quantity": "reliefState", "elementId": "RV1"},
        {"quantity": "reliefInletPressure", "elementId": "RV1"},
        {"quantity": "reliefSetRatio", "elementId": "RV1"},
        {"quantity": "reliefPressureDrop", "elementId": "RV1"},
        {"quantity": "lowestPressure"},
        {"quantity": "highestVelocity"},
    ]
    return _input(
        project,
        cases,
        library,
        options={"cases": "all", "format": "xlsx", "units": "si", "link": True},
        compare_rows=rows,
        loaded_method_version="1.1.0",
    )


def tee_fallback(client: TestClient, library: dict[str, Any]) -> dict[str, Any]:
    case = json.loads(
        (TESTS / "reference" / "cases" / "tee_crane_bullhead_fallback.json").read_text()
    )
    project = case["project"]
    project["settings"]["units"] = dict(US_UNITS)
    response = _solve(client, project, None)
    codes = {f["code"] for f in response["solvedState"]["flags"]}
    assert "TEE_PATTERN_FALLBACK" in codes, codes
    return _input(
        project,
        [_case(project, response, None, "Base case")],
        library,
        options={"cases": "shown", "format": "xlsx", "units": "display", "link": True},
    )


def design_checks(client: TestClient, library: dict[str, Any]) -> dict[str, Any]:
    project = json.loads((TESTS / "fixtures" / "pump_system.json").read_text())
    project["settings"]["units"] = dict(US_UNITS)
    project["settings"]["designChecks"] = {
        "npshMargin": {
            "minimumRatio": 1.1,
            "minimumMargin": 1.0,
            "source": {"kind": "preset", "preset": "hi961_2012_general"},
        },
        "operatingRegion": {
            "preferredMin": 0.7,
            "preferredMax": 1.2,
            "source": {"kind": "preset", "preset": "api610_por"},
        },
        "pipeVelocity": {"maximum": 3.0, "source": {"kind": "user"}},
    }
    [pump] = [c for c in project["components"] if c["type"] == "pump"]
    pump["speed"] = 0.9
    project["pumpLibrary"][0].update(
        {
            "efficiencyCurve": [
                {"flow": 0.005, "efficiency": 0.45},
                {"flow": 0.015, "efficiency": 0.7},
                {"flow": 0.025, "efficiency": 0.6},
            ],
            "allowableOperatingRegion": {"flowMin": 0.006, "flowMax": 0.026},
            "minimumContinuousStableFlow": 0.004,
            "minimumThermalFlow": 0.005,
            "motorRatedPower": 4000.0,
        }
    )
    response = _solve(client, project, None)
    outcomes = {r["outcome"] for r in response["solvedState"]["designChecks"]}
    assert outcomes == {"pass", "fail", "not_evaluated"}, outcomes
    return _input(
        project,
        [_case(project, response, None, "Base case")],
        library,
        options={"cases": "shown", "format": "xlsx", "units": "display", "link": True},
    )


def generate() -> dict[str, Any]:
    client = _client()
    library = _library(client)
    return {
        "generatedBy": GENERATED_BY,
        "cases": [
            {"name": "pump-transfer", "input": pump_transfer(client, library)},
            {"name": "scenarios", "input": scenarios(client, library)},
            {"name": "tee-fallback", "input": tee_fallback(client, library)},
            {"name": "design-checks", "input": design_checks(client, library)},
        ],
    }


def main() -> None:
    print(json.dumps(generate(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
