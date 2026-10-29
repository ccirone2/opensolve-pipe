"""The shared scenario fixture of the web app's client mirror (proposal scenario-manager.md §6.16).

    cd apps/api && uv run python -m tests.fixtures.scenario_cases \
        > ../web/src/lib/utils/__fixtures__/scenario-cases.json

``apps/web/scripts/gen-api-types.sh`` (``pnpm gen:types``) writes it with ``openapi.json``; it is
generated, never edited by hand, and ``tests/unit/test_scenario_cases.py`` fails while it is
stale. Every case is computed here with the real ``apply_scenario`` and the real request
validation, so the web's ``utils/scenarios.ts`` (``applyScenario``) is checked against the API
on every case by Vitest:

- ``applied``: an input project (API JSON, its set fields only), a scenario id, the expected
  effective project (the same form) and each override's ``index``, ``state``, ``message``,
  ``value``, ``baseValue`` and ``unit``;
- ``invalid``: a scenario whose values its targets reject: the 400 issues (``code``,
  ``message`` with the location, ``componentIds``, ``connectionIds``);
- ``not_found``: an unknown scenario id, with the 404 message;
- ``rejected``: a project whose scenarios fail request validation (400 for every request on
  it), with the issues as the API reports them.
"""

import copy
import json
from typing import Any

from fastapi.testclient import TestClient

from opensolve_pipe.main import app
from opensolve_pipe.models.piping import MAX_PIPES
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.scenarios import MAX_OVERRIDES, MAX_SCENARIOS
from opensolve_pipe.services.scenarios import (
    ScenarioNotFoundError,
    ScenarioOverrideError,
    apply_scenario,
)
from tests.unit.helpers import (
    assigned_flow,
    connection,
    custom_pipe,
    plug,
    project_dict,
    reference_node,
    reservoir,
    tee,
)

GENERATED_BY = "apps/api/tests/fixtures/scenario_cases.py"


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": 0.1} for p in ids]


def _component(kind: str, cid: str, ports: tuple[str, ...], **fields: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": _ports(*ports),
        **fields,
    }


RATED_POINT = {"kind": "point", "pressureLoss": 5.0e4, "flow": 0.015, "density": 999.102621}
"""An equipment item's rated point (test input): 50 kPa at 15 L/s on water at 15 °C."""
CERTIFIED = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7, "overpressure": 0.08}
"""A relief valve's certified capacity (test inputs; proposal pressure-relief-valve.md §7.1 C15)."""


def base_project() -> dict[str, Any]:
    """Every component type (equipment rated by a point and by a Kv; an orifice plate with an
    entered C at flange taps and one on ISO 5167-2's C; a relief valve of each capacity kind, an
    API 526 letter, an API 520 effective area and a certified capacity with its overpressure),
    with statuses, speeds and resistances left unset (defaults), a connection of two pipes (the
    first a library pipe with a bore override) and water."""
    valve = ("inlet", "outlet")
    comps = [
        reservoir("R1", level=3.0),
        reference_node("N1", pressure=1.0e5),
        assigned_flow("A1", 0.01),
        plug("X1"),
        tee("T1"),
        _component("branch", "W1", ("inlet", "outlet_1", "outlet_2"), branchType="wye"),
        _component("pump", "P1", ("suction", "discharge"), curveId="C1"),
        _component(
            "pump",
            "P2",
            ("suction", "discharge"),
            curveId="C1",
            speed=0.9,
            control={"mode": "flow", "setpoint": 0.01, "minSpeed": 0.4},
        ),
        _component("valve", "G1", valve, valveType="gate"),
        _component("valve", "C1", valve, valveType="check"),
        _component("valve", "V1", valve, valveType="prv", setpoint=2.0e5),
        _component(
            "valve",
            "F1",
            valve,
            valveType="fcv",
            setpoint=0.01,
            resistance={"kind": "K", "value": 1.5},
        ),
        _component("equipment", "E1", valve, rating=RATED_POINT),
        _component("equipment", "E2", valve, rating={"kind": "Kv", "value": 60.0}),
        _component(
            "orifice", "O1", valve, boreDiameter=0.05, dischargeCoefficient=0.6, taps="flange"
        ),
        _component("orifice", "O2", valve, boreDiameter=0.05),
        _component(
            "relief_valve",
            "RV1",
            valve,
            setPressure=5.0e5,
            capacity={"kind": "api526", "letter": "F"},
        ),
        _component(
            "relief_valve",
            "RV2",
            valve,
            setPressure=4.0e5,
            capacity={"kind": "effective", "area": 4.0e-4},
        ),
        _component("relief_valve", "RV3", valve, setPressure=3.0e5, capacity=CERTIFIED),
    ]
    library = {
        "materialId": "carbon_steel",
        "schedule": "40",
        "nominalSize": 0.1016,
        "innerDiameter": 0.1,
        "length": 12.0,
    }
    conns = [
        connection(
            "L1",
            ("R1", "port_1"),
            ("P1", "suction"),
            pipes=[library, custom_pipe(5.0, 0.1, 4.5e-5)],
            fittings=[{"type": "elbow_90_lr", "pipeIndex": 1}],
        ),
        connection("L2", ("P1", "discharge"), ("G1", "inlet"), length=40.0),
    ]
    curve = {
        "id": "C1",
        "name": "curve",
        "points": [
            {"flow": 0.0, "head": 40.0},
            {"flow": 0.02, "head": 35.0},
            {"flow": 0.04, "head": 20.0},
        ],
    }
    water = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    data = project_dict(comps, conns, fluid=water, pump_library=[curve])
    dumped: dict[str, Any] = Project.model_validate(data).model_dump(
        mode="json", exclude_unset=True
    )
    return dumped


def comp(cid: str, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": field, "value": value}


def pipe(cid: str, index: int, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "pipe", "connectionId": cid, "pipeIndex": index, "field": field, "value": value}


def proj(field: str, value: Any) -> dict[str, Any]:
    return {"kind": "project", "field": field, "value": value}


def _with(base: dict[str, Any], *scenarios: dict[str, Any]) -> dict[str, Any]:
    project = copy.deepcopy(base)
    project["scenarios"] = list(scenarios)
    return project


def _scenario(sid: str, *overrides: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"id": sid, "name": f"Scenario {sid}", "overrides": list(overrides), **extra}


SPEC = {"materialId": "stainless_steel", "schedule": "40S", "nominalSize": 0.1524}
APPLIED: list[tuple[str, list[dict[str, Any]]]] = [
    (
        "every component and pipe value",
        [
            comp("R1", "liquidLevel", 7.5),
            comp("R1", "surfacePressure", 2.0e4),
            comp("N1", "pressure", 3.0e5),
            comp("A1", "flow", -0.02),
            comp("P1", "status", "off"),
            comp("P1", "speed", 0.8),
            comp("P2", "control.setpoint", 0.015),
            comp("G1", "status", "isolated"),
            comp("G1", "resistance", {"kind": "Cv", "value": 120.0}),
            comp("C1", "status", "locked_open"),
            comp("C1", "resistance", {"kind": "K", "value": 2.0}),
            comp("V1", "status", "failed_open"),
            comp("V1", "setpoint", 1.5e5),
            comp("F1", "resistance", None),
            comp("F1", "setpoint", 0.02),
            comp("E1", "rating.pressureLoss", 7.0e4),
            comp("E1", "rating.flow", 0.012),
            comp("E1", "rating.density", 1043.47),
            comp("E2", "rating.value", 72.0),
            comp("O1", "boreDiameter", 0.06),
            comp("O2", "dischargeCoefficient", 0.62),
            pipe("L1", 0, "spec", SPEC),
            pipe("L1", 1, "length", 33.0),
            proj("fluid.temperature", 278.15),
        ],
    ),
    (
        "a whole rating of another kind",
        [
            comp("E1", "rating", {"kind": "Cv", "value": 120.0}),
            comp(
                "E2",
                "rating",
                {"kind": "point", "pressureLoss": 3.0e4, "flow": 0.01, "density": 1043.47},
            ),
        ],
    ),
    (
        "an orifice plate's entered C set back to ISO 5167-2's (null)",
        [comp("O1", "dischargeCoefficient", None)],
    ),
    (
        "every relief valve value (proposal pressure-relief-valve.md decision 18)",
        [
            comp("RV1", "status", "locked_closed"),
            comp("RV1", "setPressure", 4.5e5),
            comp("RV1", "capacity.letter", "J"),
            comp("RV2", "capacity.area", 5.0e-4),
            comp("RV3", "capacity.area", 3.0e-4),
            comp("RV3", "capacity.dischargeCoefficient", 0.75),
            comp("RV3", "capacity.overpressure", 0.12),
        ],
    ),
    (
        "a whole capacity of another kind, and a certified overpressure set back to ASME's (null)",
        [
            comp("RV1", "capacity", {"kind": "effective", "area": 5.0e-4}),
            comp("RV2", "capacity", {**CERTIFIED, "overpressure": 0.1}),
            comp("RV3", "capacity.overpressure", None),
        ],
    ),
    (
        "a whole fluid",
        [
            proj(
                "fluid",
                {"kind": "custom", "name": "Brine", "density": 1100.0, "dynamicViscosity": 0.002},
            )
        ],
    ),
    (
        "a custom spec drops the library keys",
        [pipe("L1", 0, "spec", {"materialId": "custom", "innerDiameter": 0.09, "roughness": 1e-5})],
    ),
    (
        "a library spec without a bore drops the bore override",
        [
            pipe(
                "L1",
                0,
                "spec",
                {"materialId": "carbon_steel", "schedule": "80", "nominalSize": 0.1016},
            )
        ],
    ),
    (
        "values equal to the base still apply",
        [comp("R1", "liquidLevel", 3.0), comp("P1", "status", "on")],
    ),
    ("no overrides", []),
    (
        "orphaned and not applicable",
        [
            comp("P9", "status", "off"),
            pipe("L9", 0, "length", 10.0),
            pipe("L2", 1, "length", 10.0),
            comp("R1", "status", "off"),
            comp("T1", "status", "off"),
            comp("X1", "liquidLevel", 1.0),
            comp("A1", "control.setpoint", 0.01),
            comp("P1", "control.setpoint", 0.01),
            comp("E1", "rating.value", 50.0),
            comp("E2", "rating.pressureLoss", 1.0e4),
            comp("E1", "status", "off"),
            comp("R1", "dischargeCoefficient", 0.6),
            comp("O1", "status", "off"),
            comp("RV1", "capacity.area", 5.0e-4),
            comp("RV2", "capacity.dischargeCoefficient", 0.7),
            comp("RV3", "capacity.letter", "J"),
            comp("RV1", "boreDiameter", 0.05),
            comp("O1", "setPressure", 1.0e5),
            comp("R1", "liquidLevel", 4.0),
        ],
    ),
]
"""Scenarios of ``base_project()`` that apply (some overrides possibly ignored)."""

INVALID: list[tuple[str, list[dict[str, Any]]]] = [
    (
        "values their targets reject",
        [
            comp("P1", "speed", 1.5),
            comp("P1", "status", "isolated"),
            comp("P2", "speed", 0.3),
            comp("F1", "setpoint", 150.0),
            pipe("L1", 0, "spec", {"materialId": "custom", "roughness": 1e-5}),
            proj("fluid.temperature", {"value": 280.0}),
            comp("R1", "liquidLevel", 4.0),
        ],
    ),
    (
        "an element's rule fails at the value it rejects, not at the element's valid values",
        [
            comp("P2", "control.setpoint", 0.02),
            comp("P2", "speed", 0.3),
            comp("F1", "setpoint", 150.0),
            comp("F1", "status", "failed_open"),
            pipe("L1", 0, "spec", {"materialId": "custom"}),
            pipe("L1", 0, "length", 50.0),
        ],
    ),
    ("a spec with another key", [pipe("L1", 0, "spec", {**SPEC, "length": 3.0})]),
    (
        "an invalid whole fluid",
        [proj("fluid", {"kind": "builtin", "fluidId": "brine", "temperature": 300.0})],
    ),
    (
        "rating values their kinds reject, and a K, which is no rating kind",
        [
            comp("E1", "rating.pressureLoss", 0.0),
            comp("E2", "rating", {"kind": "K", "value": 2.0}),
        ],
    ),
    (
        "a whole rating with a value its kind rejects (the union's tag is not in the location)",
        [
            comp("E1", "rating", {**RATED_POINT, "density": 0.0}),
            comp("E2", "rating.value", 2.0e7),
        ],
    ),
    (
        "orifice values their bounds reject",
        [
            comp("O1", "dischargeCoefficient", 1.5),
            comp("O2", "boreDiameter", 0.0),
            comp("O1", "boreDiameter", 0.06),
        ],
    ),
    (
        "relief valve values their bounds reject, and a letter API 526 does not have",
        [
            comp("RV1", "setPressure", 0.0),
            comp("RV1", "capacity.letter", "Z"),
            comp("RV2", "capacity.area", 80.0),
            comp("RV3", "capacity.dischargeCoefficient", 1.5),
            comp("RV3", "capacity.overpressure", 0.0),
            comp("RV3", "setPressure", 3.5e5),
        ],
    ),
    (
        "a capacity of no kind, and a whole capacity with a value its kind rejects (the union's "
        "tag is not in the location)",
        [
            comp("RV1", "capacity", {"kind": "rupture_disc", "area": 1.0e-3}),
            comp("RV2", "capacity", {**CERTIFIED, "dischargeCoefficient": 0.0}),
        ],
    ),
]
"""Scenarios of ``base_project()`` whose values the models reject (400 for that scenario)."""


def _rejected_structures() -> list[tuple[str, list[dict[str, Any]]]]:
    level = comp("R1", "liquidLevel", 4.0)
    length = {"kind": "pipe", "connectionId": "L1", "pipeIndex": 0, "field": "length", "value": 1.0}
    return [
        ("the same value twice", [_scenario("S1", level, comp("R1", "liquidLevel", 5.0))]),
        (
            "a value and a part of it",
            [_scenario("S1", proj("fluid.temperature", 280.0), proj("fluid", {"kind": "custom"}))],
        ),
        (
            "a rating and a part of it",
            [_scenario("S1", comp("E1", "rating.flow", 0.02), comp("E1", "rating", RATED_POINT))],
        ),
        (
            "a capacity and a part of it",
            [
                _scenario(
                    "S1", comp("RV3", "capacity.area", 3.0e-4), comp("RV3", "capacity", CERTIFIED)
                )
            ],
        ),
        ("two scenarios with one id", [_scenario("S1"), _scenario("S2"), _scenario("S1")]),
        ("a field of another kind", [_scenario("S1", {**length, "field": "status"})]),
        ("an unknown kind", [_scenario("S1", {**level, "kind": "valve"})]),
        ("a pipe index beyond the bound", [_scenario("S1", {**length, "pipeIndex": MAX_PIPES})]),
        (
            "too many overrides",
            [
                _scenario(
                    "S1", *(comp(f"R{i}", "liquidLevel", 1.0) for i in range(MAX_OVERRIDES + 1))
                )
            ],
        ),
        ("too many scenarios", [_scenario(f"S{i}") for i in range(MAX_SCENARIOS + 1)]),
        ("a description too long", [_scenario("S1", description="x" * 501)]),
    ]


def _records(applied: Any) -> list[dict[str, Any]]:
    return [
        {
            "index": o.index,
            "state": o.state,
            "message": o.message,
            "value": o.value,
            "baseValue": o.base_value,
            "unit": o.unit,
        }
        for o in applied.overrides
    ]


def generate() -> dict[str, Any]:
    """The fixture (module docstring)."""
    base = base_project()
    cases: list[dict[str, Any]] = []
    for name, overrides in APPLIED:
        project = _with(base, _scenario("S0"), _scenario("S1", *overrides, description="Case"))
        applied = apply_scenario(Project.model_validate(project), "S1")
        cases.append(
            {
                "name": name,
                "kind": "applied",
                "project": project,
                "scenarioId": "S1",
                "expected": {
                    "project": applied.project.model_dump(mode="json", exclude_unset=True),
                    "overrides": _records(applied),
                },
            }
        )
    for name, overrides in INVALID:
        project = _with(base, _scenario("S1", *overrides))
        try:
            apply_scenario(Project.model_validate(project), "S1")
        except ScenarioOverrideError as exc:
            issues = [issue.model_dump(mode="json") for issue in exc.issues]
        else:  # pragma: no cover - a case that no longer fails is a generator bug
            raise AssertionError(f"{name}: expected invalid values")
        cases.append(
            {
                "name": name,
                "kind": "invalid",
                "project": project,
                "scenarioId": "S1",
                "issues": issues,
            }
        )
    project = _with(base, _scenario("S1"))
    try:
        apply_scenario(Project.model_validate(project), "S9")
    except ScenarioNotFoundError as exc:
        cases.append(
            {
                "name": "an unknown scenario id",
                "kind": "not_found",
                "project": project,
                "scenarioId": "S9",
                "message": str(exc),
            }
        )
    client = TestClient(app, client=("192.0.2.250", 50000))
    for name, scenarios in _rejected_structures():
        project = _with(base, *scenarios)
        response = client.post("/api/v1/solve", json={"project": project})
        assert response.status_code == 400, (name, response.text)
        cases.append(
            {
                "name": name,
                "kind": "rejected",
                "project": project,
                "issues": response.json()["issues"],
            }
        )
    return {"generatedBy": GENERATED_BY, "cases": cases}


def main() -> None:
    print(json.dumps(generate(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
