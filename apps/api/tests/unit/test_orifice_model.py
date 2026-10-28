"""The orifice plate's model contract (proposal orifice-plate.md §2, §5.1, §5.2): its fields and
their bounds, its result's fields, the always-present result map, its scenario values, its
goal-seek variables and the start of a coefficient variable on ISO 5167-2's default, and request
validation that never echoes a submitted value (SDD §5.1.2)."""

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from opensolve_pipe.main import app
from opensolve_pipe.models.components import ORIFICE_BORE_MAX, Component, Orifice
from opensolve_pipe.models.goal_seek import (
    GOAL_COMPONENT_FIELDS,
    GOAL_QUANTITIES,
    ComponentVariable,
)
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import OrificeResult, SolvedState
from opensolve_pipe.models.scenarios import COMPONENT_FIELDS, ComponentOverride
from opensolve_pipe.services import goal_seek as service
from opensolve_pipe.services.scenarios import ScenarioOverrideError, apply_scenario
from opensolve_pipe.services.solver import solve_project

from .helpers import assigned_flow, connection, make_project, project_dict, reservoir

SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]
COMPONENTS = TypeAdapter(Component)
SECRET = "SECRET9x7"
_clients = iter(range(1, 250))


def _client() -> TestClient:
    return TestClient(app, client=(f"198.51.102.{next(_clients)}", 50000))


def orifice(cid: str = "O1", **fields: Any) -> dict[str, Any]:
    """An orifice plate (test input): a 50 mm bore, ISO 5167-2's C and no taps unless given."""
    return {
        "type": "orifice",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        "boreDiameter": 0.05,
        **fields,
    }


def line(**fields: Any) -> dict[str, Any]:
    """R1 -> P1 -> O1 -> P2 -> R2 (test input), as a project dict."""
    return project_dict(
        [reservoir("R1", level=20.0), orifice(**fields), reservoir("R2", level=10.0)],
        [
            connection("P1", ("R1", "port_1"), ("O1", "inlet")),
            connection("P2", ("O1", "outlet"), ("R2", "port_1")),
        ],
    )


def _valid(data: dict[str, Any]) -> bool:
    try:
        COMPONENTS.validate_python(data)
    except ValidationError:
        return False
    return True


# --------------------------------------------------------------------------- the component


def test_an_orifice_needs_only_its_bore() -> None:
    """ISO 5167-2's C and no taps (a restriction orifice) are what an absent field means; the
    bore has no default (decision 2)."""
    plate = COMPONENTS.validate_python(orifice())
    assert isinstance(plate, Orifice)
    assert (plate.bore_diameter, plate.discharge_coefficient, plate.taps) == (0.05, None, None)
    dumped = plate.model_dump(mode="json", exclude_unset=True)
    assert "dischargeCoefficient" not in dumped
    assert "taps" not in dumped
    assert [p.id for p in plate.ports] == ["inlet", "outlet"]
    data = orifice()
    del data["boreDiameter"]
    with pytest.raises(ValidationError) as caught:
        COMPONENTS.validate_python(data)
    assert [(e["type"], e["loc"][-1]) for e in caught.value.errors()] == [
        ("missing", "boreDiameter")
    ]
    schema = SCHEMAS["Orifice"]
    assert schema["required"] == ["id", "name", "elevation", "ports", "type", "boreDiameter"]
    assert schema["x-port-ids"] == ["inlet", "outlet"]
    assert schema["x-port-roles"] == {"inlet": "inlet", "outlet": "outlet"}


def test_an_orifice_has_no_status() -> None:
    """A plate always passes flow; valves isolate it (decision 1)."""
    assert "status" not in SCHEMAS["Orifice"]["properties"]
    assert not _valid(orifice(status="closed"))


def test_the_bore_is_bounded_as_a_pipe_bore() -> None:
    """(0, 10] m, the pipe inner-diameter bound (decision 2)."""
    bore = SCHEMAS["Orifice"]["properties"]["boreDiameter"]
    (pipe,) = [
        o
        for o in SCHEMAS["PipeDefinition"]["properties"]["innerDiameter"]["anyOf"]
        if o.get("type") == "number"
    ]
    assert (bore["exclusiveMinimum"], bore["maximum"]) == (0, ORIFICE_BORE_MAX) == (0, 10.0)
    assert (pipe["exclusiveMinimum"], pipe["maximum"]) == (0, ORIFICE_BORE_MAX)
    for inside in (math.nextafter(0.0, 1.0), 0.05, ORIFICE_BORE_MAX):
        assert _valid(orifice(boreDiameter=inside)), inside
    for outside in (-0.05, 0.0, math.nextafter(ORIFICE_BORE_MAX, math.inf), math.inf, math.nan):
        assert not _valid(orifice(boreDiameter=outside)), outside


def test_an_entered_coefficient_lies_in_0_to_1() -> None:
    """(0, 1] or absent: in the loss relation C ≤ 1 is a jet no larger than the bore
    (decision 17); absent or null is ISO 5167-2's C."""
    prop = SCHEMAS["Orifice"]["properties"]["dischargeCoefficient"]
    number, null = prop["anyOf"]
    assert (number["exclusiveMinimum"], number["maximum"], null) == (0, 1.0, {"type": "null"})
    assert "dischargeCoefficient" not in SCHEMAS["Orifice"]["required"]
    for inside in (None, math.nextafter(0.0, 1.0), 0.6, 1.0):
        assert _valid(orifice(dischargeCoefficient=inside)), inside
    for outside in (-0.6, 0.0, math.nextafter(1.0, 2.0), 1.2, math.nan):
        assert not _valid(orifice(dischargeCoefficient=outside)), outside


def test_the_taps_are_iso_5167_2s_three_sets_or_none() -> None:
    prop = SCHEMAS["Orifice"]["properties"]["taps"]
    assert prop["anyOf"][0]["enum"] == ["corner", "flange", "d_and_d_2"]
    for taps in ("corner", "flange", "d_and_d_2", None):
        assert _valid(orifice(taps=taps)), taps
    for taps in ("D", "Corner", "radius", "", 1):
        assert not _valid(orifice(taps=taps)), taps


def test_the_schema_text_defines_the_entered_coefficient() -> None:
    """The field's meaning is stated, not inferred (D11; decision 2): ISO's C of eq. (1) at the
    plate's taps, not the flow coefficient α."""
    text = SCHEMAS["Orifice"]["properties"]["dischargeCoefficient"]["description"]
    assert "ISO 5167-2's Reader-Harris/Gallagher C" in text
    assert "eq. (1)" in text
    assert "between the plate's taps" in text
    assert "Not the flow coefficient α = C/√(1 - β⁴)" in text
    assert "moved to D and D/2 tappings" in text


@pytest.mark.parametrize(
    ("field", "value", "quoted"),
    [
        ("taps", SECRET, SECRET),
        ("boreDiameter", 12345.678, "12345.678"),
        ("boreDiameter", -0.0123457, "0.0123457"),
        ("dischargeCoefficient", 7.654321, "7.654321"),
        ("dischargeCoefficient", SECRET, SECRET),
    ],
)
def test_a_value_out_of_bounds_is_400_without_echo(field: str, value: Any, quoted: str) -> None:
    response = _client().post("/api/v1/solve", json={"project": line(**{field: value})})
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["error"] == "VALIDATION_ERROR"
    assert any(field in issue["message"] for issue in payload["issues"]), payload
    assert quoted not in response.text


# --------------------------------------------------------------------------- the result


def test_the_result_has_the_proposals_fields() -> None:
    """Proposal §2.2's table, in its order; every field is sent (OutputModel)."""
    fields = [
        "flow",
        "headLoss",
        "pressureLoss",
        "pressureDrop",
        "differentialPressure",
        "venaContractaPressure",
        "beta",
        "pipeDiameter",
        "boreDiameter",
        "reynoldsNumber",
        "dischargeCoefficient",
        "coefficientSource",
        "coefficientReynoldsNumber",
        "tapCoefficientRatio",
        "lossCoefficient",
        "taps",
        "meterDischargeCoefficient",
    ]
    assert [f.alias for f in OrificeResult.model_fields.values()] == fields
    schema = SCHEMAS["OrificeResult"]
    assert sorted(schema["required"]) == sorted(fields)
    assert schema["properties"]["coefficientSource"]["enum"] == ["iso_5167_2", "entered"]
    nullable = {
        name
        for name, prop in schema["properties"].items()
        if {"type": "null"} in prop.get("anyOf", [])
    }
    assert nullable == {
        "differentialPressure",
        "venaContractaPressure",
        "coefficientReynoldsNumber",
        "tapCoefficientRatio",
        "taps",
        "meterDischargeCoefficient",
    }


def test_the_result_map_is_always_present() -> None:
    """``orificeResults`` is required and {} without an orifice, converged or not (decision 18,
    D18's equipmentResults rule)."""
    assert "orificeResults" in SCHEMAS["SolvedState"]["required"]
    solved = solve_project(
        make_project(
            [reservoir("R1", level=20.0), reservoir("R2", level=10.0)],
            [connection("P1", ("R1", "port_1"), ("R2", "port_1"))],
        )
    )
    assert solved.converged
    assert solved.orifice_results == {}
    assert solved.model_dump(mode="json")["orificeResults"] == {}
    gate = {
        "type": "valve",
        "valveType": "gate",
        "status": "isolated",
        "id": "V1",
        "name": "V1",
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }
    unsolved = solve_project(
        make_project(
            [reservoir("R1", level=20.0), gate, assigned_flow("D1", 0.01)],
            [
                connection("P1", ("R1", "port_1"), ("V1", "inlet")),
                connection("P2", ("V1", "outlet"), ("D1", "port_1")),
            ],
        )
    )
    assert not unsolved.converged
    assert unsolved.model_dump(mode="json")["orificeResults"] == {}
    SolvedState.model_validate(unsolved.model_dump(mode="json"))


# --------------------------------------------------------------------------- scenarios


def _with_scenario(base: dict[str, Any], *overrides: dict[str, Any]) -> Project:
    data = {**base, "scenarios": [{"id": "S1", "name": "S1", "overrides": list(overrides)}]}
    return Project.model_validate(data)


def _override(field: str, value: Any, cid: str = "O1") -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": field, "value": value}


def test_a_scenario_sets_the_bore_and_the_coefficient() -> None:
    """A second plate is one bore change, a calibrated plate one C, and null sets ISO 5167-2's
    C back (§5.1)."""
    assert set(COMPONENT_FIELDS[Orifice]) == {"boreDiameter", "dischargeCoefficient"}
    project = _with_scenario(
        line(dischargeCoefficient=0.6, taps="flange"),
        _override("boreDiameter", 0.06),
        _override("dischargeCoefficient", None),
        _override("dischargeCoefficient", 0.61, cid="R1"),
    )
    applied = apply_scenario(project, "S1")
    plate = next(c for c in applied.project.components if c.id == "O1")
    assert isinstance(plate, Orifice)
    assert (plate.bore_diameter, plate.discharge_coefficient, plate.taps) == (0.06, None, "flange")
    records = [(r.state, r.value, r.base_value, r.unit) for r in applied.result().overrides]
    assert records == [
        ("applied", 0.06, 0.05, "m"),
        ("applied", None, 0.6, ""),
        ("not_applicable", None, None, ""),
    ]
    assert applied.overrides[2].message == "reservoir R1 has no discharge coefficient to override"
    # An entered C on a base on ISO's C: its base value is null, ISO's.
    entered = apply_scenario(_with_scenario(line(), _override("dischargeCoefficient", 0.62)), "S1")
    assert [(r.value, r.base_value) for r in entered.overrides] == [(0.62, None)]


def test_a_scenario_value_out_of_bounds_is_rejected_at_its_override() -> None:
    project = _with_scenario(line(), _override("dischargeCoefficient", 1.5))
    with pytest.raises(ScenarioOverrideError) as caught:
        apply_scenario(project, "S1")
    (issue,) = caught.value.issues
    assert issue.message.startswith("body.project.scenarios.0.overrides.0.value")
    assert "1.5" not in issue.message


def test_the_taps_are_not_a_scenario_value() -> None:
    """The taps are installation, the same in every case (decision 20)."""
    with pytest.raises(ValidationError):
        ComponentOverride.model_validate(_override("taps", "corner"))


# --------------------------------------------------------------------------- goal seek


def test_the_goal_seek_variables_and_goals() -> None:
    variables = GOAL_COMPONENT_FIELDS[Orifice]
    assert {name: v.scale for name, v in variables.items()} == {
        "boreDiameter": "log",
        "dischargeCoefficient": "linear",
    }
    goals = {name: spec for name, spec in GOAL_QUANTITIES.items() if spec.element == "orifice"}
    assert {name: (s.unit, s.category, s.needs) for name, s in goals.items()} == {
        "orifice_flow": ("m³/s", "flow", ()),
        "orifice_pressure_loss": ("Pa (difference)", "pressure", ()),
        "orifice_differential_pressure": ("Pa (difference)", "pressure", ("taps",)),
        "orifice_pressure_drop": ("Pa (difference)", "pressure", ()),
    }
    assert all(s.targets == (Orifice,) for s in goals.values())


def _resolved(project: Project, field: str, lower: float, upper: float) -> Any:
    variable = ComponentVariable.model_validate(
        {"kind": "component", "componentId": "O1", "field": field, "lower": lower, "upper": upper}
    )
    not_found: list[Any] = []
    problems: list[Any] = []
    var = service._resolve_variable(0, variable, project, project, None, not_found, problems)
    assert (not_found, problems) == ([], [])
    assert var is not None
    return var


def test_a_coefficient_on_iso_5167_2s_default_starts_in_the_middle() -> None:
    """A case on ISO's C holds no number: the search starts in the middle of the bounds, as for
    a resistance on its default, and the texts name ISO's C (§5.2)."""
    var = _resolved(Project.model_validate(line(taps="corner")), "dischargeCoefficient", 0.5, 0.7)
    assert (var.case_number, var.case_value, var.base_value) == (None, None, None)
    assert var.label == "discharge coefficient of orifice O1"
    assert var.default_text.startswith("ISO 5167-2's Reader-Harris/Gallagher coefficient")
    axis = service.Axis.of(
        service.AxisSpec(0.5, 0.7, var.variable.scale, var.case_number, var.label, var.unit)
    )
    assert (axis.source, axis.start) == ("middle", pytest.approx(0.6, rel=1e-15))
    assert (
        service._case_value_text(var) == ": none, ISO 5167-2's Reader-Harris/Gallagher coefficient"
    )
    item = service._variable_item(var, axis, None)
    assert (
        "(the middle of the bounds: the case's discharge coefficient is ISO 5167-2's "
        "Reader-Harris/Gallagher coefficient at the solved flow, the orifice plate's default)"
    ) in item
    # An entered C, and the bore, start at the case's value.
    entered = _resolved(
        Project.model_validate(line(dischargeCoefficient=0.6)), "dischargeCoefficient", 0.5, 0.7
    )
    assert (entered.case_number, entered.default_text) == (0.6, "")
    bore = _resolved(Project.model_validate(line()), "boreDiameter", 0.01, 0.08)
    assert (bore.case_number, bore.variable.scale, bore.unit) == (0.05, "log", "m")
    assert bore.label == "bore diameter of orifice O1"
