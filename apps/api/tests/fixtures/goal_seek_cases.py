"""The shared goal-seek fixture of the web app (docs/proposals/goal-seek.md §7.5).

    cd apps/api && uv run python -m tests.fixtures.goal_seek_cases \
        > ../web/src/lib/utils/__fixtures__/goal-seek-cases.json

``apps/web/scripts/gen-api-types.sh`` (``pnpm gen:types``) writes it with ``openapi.json``; it is
generated, never edited by hand, and ``tests/unit/test_goal_seek_cases.py`` fails while it is
stale. Everything in it comes from the real goal-seek code (``services/goal_seek.py``: the checks,
the trial builder and the goal readers), so the web's ``utils/goal-seek.ts`` is checked against
the API by Vitest:

- ``apply``: a request (``project`` as API JSON with its set fields only, ``scenarioId`` or null,
  ``variables``) with found ``values`` (SI), among them an orifice plate's bore and its
  discharge coefficient on ISO 5167-2's (no number held, proposal orifice-plate.md §5.2) and a
  relief valve's set, effective area, certified area and rated coefficient, and overpressure on
  ASME's default (no number held, proposal pressure-relief-valve.md decision 19); each
  variable's ``override`` and ``replacedOverride`` as ``result.variables`` gives them (an
  override of a whole value the scenario sets, a whole fluid, a whole equipment rating or a
  whole relief valve capacity, built from the case with every value written, as the API builds
  it from the reported evaluation: proposal equipment-pressure-drop.md §5.2); and ``trial``, the
  case project the goal seek solves at those values (the same JSON form, without
  ``scenarios``). Applying the overrides to the case they ran on (written into the base, or
  upserted into the scenario by target and field) and taking that case's project gives
  ``trial``.
  A resistance variable on a valve that refers to a project library entry (CLAUDE.md D22)
  writes an inline coefficient of its kind in place of the reference, in ``trial`` and in its
  ``override`` (proposal project-library.md §5.2).
- ``goals``: a solved ``state`` (a SolvedState without its ``trace`` and ``timestamp``) and, for
  goals on it
  (``goal`` as a request's), the ``value`` the API reads (SI, null when there is none) and its
  ``message`` ('' with a value). Each quantity's Compare reader gives the same value.
"""

import copy
import json
from typing import Any

from opensolve_pipe.models.api import GoalSeekRequest
from opensolve_pipe.models.goal_seek import GOAL_QUANTITIES
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.goal_seek import goal_value, prepare
from opensolve_pipe.services.scenarios import COMPONENT_NAMES
from opensolve_pipe.services.solver import solve_project
from tests.unit.helpers import connection, custom_pipe, project_dict, reference_node, reservoir

GENERATED_BY = "apps/api/tests/fixtures/goal_seek_cases.py"

WATER = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
CURVE = {
    "id": "C1",
    "name": "curve",
    "points": [
        {"flow": 0.0, "head": 40.0},
        {"flow": 0.02, "head": 35.0},
        {"flow": 0.04, "head": 20.0},
    ],
    "npshrCurve": [{"flow": 0.0, "npshr": 1.0}, {"flow": 0.04, "npshr": 4.0}],
}


def _ports(*ids: str) -> list[dict[str, Any]]:
    return [{"id": p, "nominalSize": 0.1} for p in ids]


RATING = {"kind": "point", "pressureLoss": 30000.0, "flow": 0.02, "density": 999.102621}
"""The equipment item E1's rating (test input): 30 kPa at 20 L/s on water at 15 °C."""
METER_BORE = 0.06
"""m: the orifice flow meter O1's bore (test input), β 0.6 in its 0.1 m inlet pipe."""
RESTRICTION_BORE, RESTRICTION_C = 0.07, 0.62
"""m and -: the restriction orifice O2's bore and entered C (test inputs)."""
RELIEF_SET, RELIEF_AREA = 1.5e5, 3.0e-4
"""Pa (a difference) and m²: the relief valve RV1's set and API 520 effective area (test
inputs); R2's 20 m of water hold it at full lift."""
CERTIFIED = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}
"""A certified relief valve capacity on ASME's default overpressure (test inputs)."""


def base_project(*, pump: dict[str, Any] | None = None) -> dict[str, Any]:
    """R1 (5 m) -> L1 (two pipes, the second narrower) -> P1 -> L2 -> G1 (gate) -> L3 -> E1
    (equipment rated by a point, its outlet port 1 m up, so that its static pressure drop is not
    its pressure loss) -> L4 -> O1 (an orifice flow meter with flange taps on ISO 5167-2's C, its
    outlet port 0.5 m up, likewise) -> L5 -> O2 (a restriction orifice: no taps, so no reading,
    and an entered C) -> L6 -> R2 (20 m), whose second port L7 -> RV1 (a relief valve on an API
    520 effective area, relieving) -> L8 (with an exit) -> N1 (0 Pa(g): a discharge to
    atmosphere) water with a vapor-pressure override."""
    comps = [
        reservoir("R1", level=5.0),
        {
            "type": "pump",
            "id": "P1",
            "name": "Transfer pump",
            "elevation": 0.0,
            "curveId": "C1",
            "ports": _ports("suction", "discharge"),
            **(pump or {}),
        },
        {
            "type": "valve",
            "id": "G1",
            "name": "Discharge valve",
            "elevation": 0.0,
            "valveType": "gate",
            "ports": _ports("inlet", "outlet"),
        },
        {
            "type": "equipment",
            "id": "E1",
            "name": "Coil",
            "elevation": 0.0,
            "rating": RATING,
            "ports": [
                {"id": "inlet", "nominalSize": 0.1},
                {"id": "outlet", "nominalSize": 0.1, "elevation": 1.0},
            ],
        },
        {
            "type": "orifice",
            "id": "O1",
            "name": "Flow meter",
            "elevation": 0.0,
            "boreDiameter": METER_BORE,
            "taps": "flange",
            "ports": [
                {"id": "inlet", "nominalSize": 0.1},
                {"id": "outlet", "nominalSize": 0.1, "elevation": 0.5},
            ],
        },
        {
            "type": "orifice",
            "id": "O2",
            "name": "Restriction orifice",
            "elevation": 0.0,
            "boreDiameter": RESTRICTION_BORE,
            "dischargeCoefficient": RESTRICTION_C,
            "ports": _ports("inlet", "outlet"),
        },
        reservoir("R2", level=20.0, ports=("port_1", "port_2")),
        {
            "type": "relief_valve",
            "id": "RV1",
            "name": "Relief valve",
            "elevation": 0.0,
            "setPressure": RELIEF_SET,
            "capacity": {"kind": "effective", "area": RELIEF_AREA},
            "ports": _ports("inlet", "outlet"),
        },
        reference_node("N1", pressure=0.0),
    ]
    conns = [
        connection(
            "L1",
            ("R1", "port_1"),
            ("P1", "suction"),
            pipes=[custom_pipe(4.0, 0.1, 4.5e-5), custom_pipe(6.0, 0.08, 4.5e-5)],
        ),
        connection("L2", ("P1", "discharge"), ("G1", "inlet"), length=50.0),
        connection("L3", ("G1", "outlet"), ("E1", "inlet"), length=10.0),
        connection("L4", ("E1", "outlet"), ("O1", "inlet"), length=5.0),
        connection("L5", ("O1", "outlet"), ("O2", "inlet"), length=5.0),
        connection("L6", ("O2", "outlet"), ("R2", "port_1"), length=5.0),
        connection("L7", ("R2", "port_2"), ("RV1", "inlet"), length=2.0),
        connection(
            "L8",
            ("RV1", "outlet"),
            ("N1", "port_1"),
            length=1.0,
            fittings=[{"type": "exit", "quantity": 1, "pipeIndex": 0}],
        ),
    ]
    fluid = {**WATER, "overrides": {"vaporPressure": 2339.0}}
    data = project_dict(comps, conns, fluid=fluid, pump_library=[CURVE])
    dumped: dict[str, Any] = Project.model_validate(data).model_dump(
        mode="json", exclude_unset=True
    )
    return dumped


def comp(cid: str, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": field, "value": value}


def variable(cid: str, field: str, lower: float, upper: float, **kw: Any) -> dict[str, Any]:
    return {
        "kind": "component",
        "componentId": cid,
        "field": field,
        "lower": lower,
        "upper": upper,
        **kw,
    }


PIPE_VARIABLE = {
    "kind": "pipe",
    "connectionId": "L1",
    "pipeIndex": 1,
    "field": "length",
    "lower": 0.6,
    "upper": 60.0,
}
TEMPERATURE = {"kind": "project", "field": "fluid.temperature", "lower": 275.0, "upper": 340.0}
GLYCOL = {
    "kind": "builtin",
    "fluidId": "propylene_glycol",
    "temperature": 300.0,
    "concentration": 0.3,
    "overrides": {"vaporPressure": 2000.0},
}


def _with_scenario(project: dict[str, Any], *overrides: dict[str, Any]) -> dict[str, Any]:
    project = copy.deepcopy(project)
    project["scenarios"] = [
        {"id": "S1", "name": "Winter", "overrides": list(overrides)},
        {"id": "S2", "name": "Other", "overrides": [comp("R2", "liquidLevel", 15.0)]},
    ]
    return project


RESISTANCES = [
    {"id": "RS1", "name": "Gate, open", "source": "test input", "kind": "Cv", "value": 900.0},
    {
        "id": "RS2",
        "name": "Gate, open (K)",
        "source": "test input",
        "kind": "K",
        "value": 0.2,
        "referenceDiameter": 0.09,
    },
]
"""The project library of ``library_project()`` (test inputs)."""


def library_project() -> dict[str, Any]:
    """``base_project()`` whose gate G1 takes its resistance from the project library entry RS1
    (a Cv) and whose L3 refers to a pipe spec (CLAUDE.md D22)."""
    data = base_project()
    data["pipeLibrary"] = [
        {
            "id": "PS1",
            "name": "Measured bore",
            "source": "test input",
            "materialId": "custom",
            "innerDiameter": 0.1,
            "roughness": 4.5e-5,
        }
    ]
    data["resistanceLibrary"] = copy.deepcopy(RESISTANCES)
    [l3] = [c for c in data["connections"] if c["id"] == "L3"]
    l3["piping"]["pipes"] = [{"specId": "PS1", "length": 10.0}]
    [g1] = [c for c in data["components"] if c["id"] == "G1"]
    g1["resistance"] = {"kind": "library", "id": "RS1"}
    dumped: dict[str, Any] = Project.model_validate(data).model_dump(
        mode="json", exclude_unset=True
    )
    return dumped


def _apply_cases() -> list[tuple[str, dict[str, Any], str | None, list[Any], list[float]]]:
    base = base_project()
    library = library_project()
    speed = variable("P1", "speed", 0.2, 1.0)
    level = variable("R1", "liquidLevel", 0.0, 20.0)
    rated_loss = variable("E1", "rating.pressureLoss", 1.0e3, 1.0e6)
    rated_flow = variable("E1", "rating.flow", 1.0e-3, 0.1)
    rated_density = variable("E1", "rating.density", 500.0, 2000.0)
    bore = variable("O1", "boreDiameter", 0.03, 0.075)
    meter_c = variable("O1", "dischargeCoefficient", 0.5, 0.75)
    vendor = {"kind": "point", "pressureLoss": 45000.0, "flow": 0.025, "density": 1043.47}
    winter = _with_scenario(
        base,
        comp("R1", "liquidLevel", 4.0),
        {"kind": "pipe", "connectionId": "L2", "pipeIndex": 0, "field": "length", "value": 70.0},
    )
    return [
        ("base run: a pump speed", base, None, [speed], [0.8611744213850658]),
        ("base run: a value equal to the base", base, None, [level], [5.0]),
        ("base run: a pipe length", base, None, [PIPE_VARIABLE], [7.123456789]),
        (
            "base run: a resistance on its default",
            base,
            None,
            [variable("G1", "resistance", 0.01, 100.0, coefficient="Cv"), speed],
            [18.2345678, 0.9123],
        ),
        ("base run: a fluid temperature", base, None, [TEMPERATURE], [301.234567]),
        ("scenario run: a field the scenario sets", winter, "S1", [level], [3.30000000001]),
        ("scenario run: a field the scenario does not set", winter, "S1", [speed], [0.777]),
        ("scenario run: a value equal to the base", winter, "S1", [level], [5.0]),
        ("scenario run: a pipe length", winter, "S1", [PIPE_VARIABLE], [12.5]),
        (
            "scenario run: a temperature inside a whole-fluid override",
            _with_scenario(base, {"kind": "project", "field": "fluid", "value": GLYCOL}),
            "S1",
            [TEMPERATURE],
            [288.1234],
        ),
        (
            "scenario run: a resistance the scenario sets as another kind",
            _with_scenario(base, comp("G1", "resistance", {"kind": "K", "value": 2.0})),
            "S1",
            [variable("G1", "resistance", 0.01, 100.0, coefficient="Cv")],
            [33.3],
        ),
        ("base run: a rated pressure drop", base, None, [rated_loss], [23456.789]),
        (
            "base run: a rated flow and a rated density",
            base,
            None,
            [rated_flow, rated_density],
            [0.0123, 1043.47],
        ),
        (
            "scenario run: two values inside a whole-rating override",
            _with_scenario(base, comp("E1", "rating", vendor)),
            "S1",
            [rated_loss, rated_flow],
            [51234.5, 0.0187],
        ),
        (
            "scenario run: a Cv inside a whole-rating override of another kind",
            _with_scenario(base, comp("E1", "rating", {"kind": "Cv", "value": 120.0})),
            "S1",
            [variable("E1", "rating.value", 10.0, 1000.0)],
            [95.5],
        ),
        ("base run: an orifice plate's bore", base, None, [bore], [0.0567891234]),
        (
            "base run: a discharge coefficient on ISO 5167-2's (no number held)",
            base,
            None,
            [meter_c],
            [0.6234567891],
        ),
        (
            "base run: an entered discharge coefficient",
            base,
            None,
            [variable("O2", "dischargeCoefficient", 0.5, 0.75)],
            [0.6512345678],
        ),
        (
            "base run: a resistance from a project library entry of its kind",
            library,
            None,
            [variable("G1", "resistance", 10.0, 5000.0, coefficient="Cv")],
            [1234.5678],
        ),
        (
            "base run: a resistance from a project library entry of another kind",
            library,
            None,
            [variable("G1", "resistance", 0.01, 100.0, coefficient="K")],
            [0.4321],
        ),
        (
            "scenario run: a resistance the scenario points at a project library entry",
            _with_scenario(library, comp("G1", "resistance", {"kind": "library", "id": "RS2"})),
            "S1",
            [variable("G1", "resistance", 0.01, 100.0, coefficient="K")],
            [0.55],
        ),
        (
            "scenario run: a bore and a coefficient the scenario sets",
            _with_scenario(
                base, comp("O1", "boreDiameter", 0.055), comp("O1", "dischargeCoefficient", 0.61)
            ),
            "S1",
            [bore, meter_c],
            [0.0512345678, 0.6345678912],
        ),
        (
            "base run: a relief valve's set pressure",
            base,
            None,
            [variable("RV1", "setPressure", 1.2e5, 3.0e5)],
            [167890.12345],
        ),
        (
            "base run: an API 520 effective area (sizing)",
            base,
            None,
            [variable("RV1", "capacity.area", 1.0e-4, 1.0e-3)],
            [4.56789012e-4],
        ),
        (
            "scenario run: an area and a rated coefficient inside a whole-capacity override",
            _with_scenario(base, comp("RV1", "capacity", {**CERTIFIED, "overpressure": 0.1})),
            "S1",
            [
                variable("RV1", "capacity.area", 1.0e-4, 1.0e-3),
                variable("RV1", "capacity.dischargeCoefficient", 0.5, 0.9),
            ],
            [3.12345678e-4, 0.7234567891],
        ),
        (
            "scenario run: an overpressure on ASME's default (no number held) inside a "
            "whole-capacity override",
            _with_scenario(base, comp("RV1", "capacity", CERTIFIED)),
            "S1",
            [variable("RV1", "capacity.overpressure", 0.05, 0.3)],
            [0.1234567891],
        ),
    ]


def _goal(quantity: str, element: str, port: str | None = None) -> dict[str, Any]:
    goal: dict[str, Any] = {"quantity": quantity, "elementId": element, "target": 0.0}
    if port is not None:
        goal["portId"] = port
    return goal


GOALS = [
    _goal("port_pressure", "P1", "discharge"),
    _goal("port_pressure", "G1", "outlet"),
    _goal("link_flow", "L1"),
    _goal("link_velocity", "L1"),
    _goal("link_head_loss", "L2"),
    _goal("pump_flow", "P1"),
    _goal("pump_head", "P1"),
    _goal("pump_npsh_available", "P1"),
    _goal("pump_npsh_margin", "P1"),
    _goal("valve_flow", "G1"),
    _goal("valve_pressure_drop", "G1"),
    _goal("equipment_flow", "E1"),
    _goal("equipment_pressure_loss", "E1"),
    _goal("equipment_pressure_drop", "E1"),
    _goal("orifice_flow", "O1"),
    _goal("orifice_pressure_loss", "O1"),
    _goal("orifice_differential_pressure", "O1"),
    _goal("orifice_differential_pressure", "O2"),
    _goal("orifice_pressure_drop", "O1"),
    _goal("relief_valve_flow", "RV1"),
    _goal("relief_valve_pressure_drop", "RV1"),
    _goal("boundary_outflow", "R1"),
    _goal("boundary_outflow", "R2"),
]
"""Goals on every quantity (test input)."""


def _goal_cases() -> list[dict[str, Any]]:
    cases = []
    for name, pump in (("a running pump", None), ("a pump that is off", {"status": "off"})):
        project = base_project(pump=pump)
        model = Project.model_validate(project)
        state = solve_project(model)
        names = {c.id: f"{COMPONENT_NAMES[type(c)]} {c.id}" for c in model.components}
        request = GoalSeekRequest.model_validate(
            {
                "project": project,
                "variables": [variable("R1", "liquidLevel", 0.0, 20.0)],
                "goals": [GOALS[0]],
            }
        )
        readings = []
        for goal in GOALS:
            parsed = request.goals[0].model_validate(goal)
            element = goal["elementId"]
            value, message = goal_value(state, parsed, names.get(element, element))
            readings.append({"goal": goal, "value": value, "message": message})
        cases.append(
            {
                "name": name,
                "project": project,
                "state": state.model_dump(mode="json", exclude={"trace", "timestamp"}),
                "goals": readings,
            }
        )
    return cases


def generate() -> dict[str, Any]:
    """The fixture (module docstring)."""
    apply = []
    for name, project, scenario_id, variables, values in _apply_cases():
        goals = [{**_goal("pump_flow", "P1"), "target": 0.02}]
        if len(variables) == 2:
            goals.append({**_goal("pump_head", "P1"), "target": 30.0})
        body: dict[str, Any] = {"project": project, "variables": variables, "goals": goals}
        if scenario_id is not None:
            body["scenarioId"] = scenario_id
        prepared = prepare(GoalSeekRequest.model_validate(body))
        trial = prepared.trial(values).model_dump(mode="json", exclude_unset=True)
        found = prepared.written(values)  # the case with every value found, as the API reports
        apply.append(
            {
                "name": name,
                "project": project,
                "scenarioId": scenario_id,
                "variables": variables,
                "values": values,
                "overrides": [
                    v.override(x, found).model_dump(mode="json")
                    for v, x in zip(prepared.variables, values, strict=True)
                ],
                "replacedOverrides": [v.replaced for v in prepared.variables],
                "trial": trial,
            }
        )
    return {
        "generatedBy": GENERATED_BY,
        "quantities": sorted(GOAL_QUANTITIES),
        "apply": apply,
        "goals": _goal_cases(),
    }


def main() -> None:
    print(json.dumps(generate(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
