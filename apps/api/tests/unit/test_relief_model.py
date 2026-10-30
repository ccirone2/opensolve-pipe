"""The pressure relief valve's model contract (proposal pressure-relief-valve.md §2, decisions 1,
2, 6-8, 15, 16, 18, 19 and 27): its cited data file and the generator that writes it, its fields
and their bounds, the capacity union of three kinds never mixed, x-relief-data, its result's
fields, the always-present result map, its flag codes, its scenario values, its goal-seek
variables and goals, and request validation that never echoes a submitted value (SDD §5.1.2).

The solver's law, refusals, flags and traces are tested in test_relief.py and the reference
suite; this file pins only the contract the other parts are built on."""

import importlib.util
import inspect
import math
from pathlib import Path
from types import ModuleType
from typing import Any, get_args

import pytest
import scipy.constants
from fastapi.testclient import TestClient
from fluids.safety_valve import API526_A, API520_A_l, API526_A_sq_inch, API526_letters
from pydantic import TypeAdapter, ValidationError

from opensolve_pipe.main import app
from opensolve_pipe.models.components import (
    API520_EFFECTIVE_DISCHARGE_COEFFICIENT,
    API526_AREAS,
    ASME_MINIMUM_SET_PRESSURE,
    ASME_OVERPRESSURE_FLOOR,
    ASME_OVERPRESSURE_FRACTION,
    RATED_PRESSURE_LOSS_MAX,
    RELIEF_AREA_MAX,
    RELIEF_DATA,
    API526Letter,
    Api526Orifice,
    CertifiedOrifice,
    Component,
    EffectiveOrifice,
    ReliefValve,
)
from opensolve_pipe.models.goal_seek import (
    GOAL_COMPONENT_FIELDS,
    GOAL_QUANTITIES,
    LOG_FIELDS,
    NOT_VARIABLES,
    ComponentVariable,
    ElementKind,
    Goal,
)
from opensolve_pipe.models.results import FlagCode, ReliefValveResult, SolvedState
from opensolve_pipe.models.scenarios import (
    COMPONENT_FIELDS,
    Scenario,
    override_label,
    override_unit,
)
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.flags import FLAG_SEVERITY

from .helpers import assigned_flow, connection, make_project, project_dict, reservoir

API_ROOT = Path(__file__).parents[2]
DATA = API_ROOT / "src" / "opensolve_pipe" / "data" / "api526_orifices.json"
SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]
COMPONENTS = TypeAdapter(Component)
SECRET = "SECRET5r8"
_clients = iter(range(1, 250))

PENTAIR_TABLE_7_6 = {
    "D": 0.110,
    "E": 0.196,
    "F": 0.307,
    "G": 0.503,
    "H": 0.785,
    "J": 1.287,
    "K": 1.838,
    "L": 2.853,
    "M": 3.600,
    "N": 4.340,
    "P": 6.380,
    "Q": 11.05,
    "R": 16.00,
    "T": 26.00,
}
"""in²: API effective orifice areas, Pentair TP-V300 rev. 12-2012, Table 7-6 (liquid series,
K = 0.650), transcribed here from the handbook independently of fluids (test input)."""


def _client() -> TestClient:
    return TestClient(app, client=(f"198.51.105.{next(_clients)}", 50000))


def relief(cid: str = "RV1", **fields: Any) -> dict[str, Any]:
    """A relief valve (test input): a 500 kPa set on an API 526 F unless given."""
    return {
        "type": "relief_valve",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.05}, {"id": "outlet", "nominalSize": 0.08}],
        "setPressure": 5.0e5,
        "capacity": {"kind": "api526", "letter": "F"},
        **fields,
    }


def line(**fields: Any) -> dict[str, Any]:
    """R1 -> P1 -> RV1 -> P2 -> R2 (test input), as a project dict."""
    return project_dict(
        [reservoir("R1", level=20.0), relief(**fields), reservoir("R2", level=0.0)],
        [
            connection("P1", ("R1", "port_1"), ("RV1", "inlet")),
            connection("P2", ("RV1", "outlet"), ("R2", "port_1")),
        ],
    )


def _valid(data: dict[str, Any]) -> bool:
    try:
        COMPONENTS.validate_python(data)
    except ValidationError:
        return False
    return True


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_relief_data", API_ROOT / "scripts" / "generate_relief_data.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- the data file


def test_the_data_file_matches_a_fresh_regeneration() -> None:
    """Decision 27: the committed JSON is what the generator writes from fluids now, so a library
    change shows up as a diff, and its --check mode agrees."""
    gen = _generator()
    assert DATA.read_text(encoding="utf-8") == gen.render(gen.build_relief_data())
    assert gen.main(["--check"]) == 0


def test_the_letters_and_areas_are_fluids_api_526_data() -> None:
    orifices = RELIEF_DATA["orifices"]
    assert [o["letter"] for o in orifices] == API526_letters
    assert [o["areaSquareInches"] for o in orifices] == API526_A_sq_inch
    assert [o["area"] for o in orifices] == API526_A  # fluids' own m² values, bit for bit
    assert list(API526_AREAS) == API526_letters
    assert list(API526_AREAS.values()) == API526_A
    inch2 = scipy.constants.inch**2
    for o in orifices:
        assert o["area"] == pytest.approx(o["areaSquareInches"] * inch2, rel=1e-15)
        assert "API Standard 526" in o["source"]
        assert "fluids.safety_valve.API526_A" in o["source"]
        assert "Table 7-6" in o["source"]
    # Pentair's Table 7-6 gives the same effective areas (an independent transcription).
    assert {o["letter"]: o["areaSquareInches"] for o in orifices} == PENTAIR_TABLE_7_6


def test_the_letter_literal_is_the_data_files() -> None:
    assert get_args(API526Letter) == tuple(API526_AREAS) == tuple(API526_letters)
    letter = SCHEMAS["Api526Orifice"]["properties"]["letter"]
    assert letter["enum"] == API526_letters


def test_the_constants_and_their_sources() -> None:
    """API 520's 0.65 is fluids' API520_A_l default Kd; ASME's 10 % or 3 psi and its 15 psi scope
    are Pentair's quotations of ASME VIII, in Pa through the psi (scipy's, the same CODATA value
    as fluids')."""
    kd = RELIEF_DATA["effectiveDischargeCoefficient"]
    assert kd["value"] == API520_EFFECTIVE_DISCHARGE_COEFFICIENT == 0.65
    assert kd["value"] == inspect.signature(API520_A_l).parameters["Kd"].default
    assert "API520_A_l" in kd["source"]
    assert "0.65 normally" in kd["source"]
    fraction = RELIEF_DATA["asmeOverpressureFraction"]
    assert fraction["value"] == ASME_OVERPRESSURE_FRACTION == 0.1
    assert "10% or 3 psi" in fraction["source"]
    floor = RELIEF_DATA["asmeOverpressureFloor"]
    assert (floor["psi"], floor["value"]) == (3.0, ASME_OVERPRESSURE_FLOOR)
    assert 3.0 * scipy.constants.psi == ASME_OVERPRESSURE_FLOOR
    assert pytest.approx(20684.27, abs=0.005) == ASME_OVERPRESSURE_FLOOR
    scope = RELIEF_DATA["asmeMinimumSetPressure"]
    assert (scope["psi"], scope["value"]) == (15.0, ASME_MINIMUM_SET_PRESSURE)
    assert 15.0 * scipy.constants.psi == ASME_MINIMUM_SET_PRESSURE
    assert pytest.approx(103421.36, abs=0.005) == ASME_MINIMUM_SET_PRESSURE
    assert "below 15 psig" in scope["source"]
    for entry in (kd, fraction, floor, scope):
        assert "TP-V300" in entry["source"]
    # Within ASME's scope the default overpressure, max(10 %, 3 psi / set), is at most 20 %:
    # the range decision 6 states.
    assert pytest.approx(0.2, rel=1e-15) == ASME_OVERPRESSURE_FLOOR / ASME_MINIMUM_SET_PRESSURE


def test_x_relief_data_is_the_data_file() -> None:
    """Published on the ReliefValve schema (decision 27; at its top level, as every extension
    the web reads), read by the web instead of a copy."""
    published = SCHEMAS["ReliefValve"]["x-relief-data"]
    assert published == {
        "api526Areas": dict(zip(API526_letters, API526_A, strict=True)),
        "effectiveDischargeCoefficient": 0.65,
        "asmeOverpressureFraction": 0.1,
        "asmeOverpressureFloor": RELIEF_DATA["asmeOverpressureFloor"]["value"],
        "asmeMinimumSetPressure": RELIEF_DATA["asmeMinimumSetPressure"]["value"],
    }
    assert list(published["api526Areas"]) == API526_letters
    found: list[str] = []

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "x-relief-data":
                    found.append(where)
                else:
                    walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{where}.{i}")

    walk(SCHEMAS, "schemas")
    assert found == ["schemas.ReliefValve"]  # published once
    # The component extensions are published beside it.
    assert SCHEMAS["ReliefValve"]["x-port-ids"] == ["inlet", "outlet"]


# --------------------------------------------------------------------------- the component


def test_a_relief_valve_needs_its_set_and_capacity() -> None:
    """Decisions 1-2, 7: its own type with ports inlet -> outlet, a set pressure and a capacity
    with no default, active unless locked closed."""
    valve = COMPONENTS.validate_python(relief())
    assert isinstance(valve, ReliefValve)
    assert (valve.set_pressure, valve.status) == (5.0e5, "active")
    assert isinstance(valve.capacity, Api526Orifice)
    assert valve.capacity.letter == "F"
    assert "status" not in valve.model_dump(mode="json", exclude_unset=True)
    for missing in ("setPressure", "capacity"):
        data = relief()
        del data[missing]
        with pytest.raises(ValidationError) as caught:
            COMPONENTS.validate_python(data)
        assert [(e["type"], e["loc"][-1]) for e in caught.value.errors()] == [("missing", missing)]
    schema = SCHEMAS["ReliefValve"]
    assert schema["required"] == [
        "id",
        "name",
        "elevation",
        "ports",
        "type",
        "setPressure",
        "capacity",
    ]
    assert schema["x-port-ids"] == ["inlet", "outlet"]
    assert schema["x-port-roles"] == {"inlet": "inlet", "outlet": "outlet"}
    assert schema["properties"]["type"]["const"] == "relief_valve"
    assert schema["properties"]["status"]["enum"] == ["active", "locked_closed"]
    assert schema["properties"]["status"]["default"] == "active"
    assert _valid(relief(status="locked_closed"))
    for status in ("isolated", "failed_open", "closed", "locked_open"):
        assert not _valid(relief(status=status)), status


def test_it_is_not_a_valve_type() -> None:
    """Decision 1: `{type: 'valve', valveType: 'relief'}` stays an unknown component."""
    data = {**relief(), "type": "valve", "valveType": "relief"}
    with pytest.raises(ValidationError) as caught:
        COMPONENTS.validate_python(data)
    assert [e["type"] for e in caught.value.errors()] == ["invalid_component"]


def test_the_set_pressure_is_a_difference_bounded_as_a_pressure() -> None:
    """(0, 1e8] Pa, a difference. The 15 psi scope is a refusal, not a model rule (decision 14):
    a smaller set is a valid model."""
    prop = SCHEMAS["ReliefValve"]["properties"]["setPressure"]
    assert (prop["exclusiveMinimum"], prop["maximum"]) == (0, RATED_PRESSURE_LOSS_MAX) == (0, 1e8)
    for inside in (math.nextafter(0.0, 1.0), 5.0e4, ASME_MINIMUM_SET_PRESSURE, 1.0e8):
        assert _valid(relief(setPressure=inside)), inside
    for outside in (-1.0, 0.0, math.nextafter(1.0e8, math.inf), math.inf, math.nan):
        assert not _valid(relief(setPressure=outside)), outside


def test_the_capacity_is_one_of_three_kinds() -> None:
    capacity = SCHEMAS["ReliefValve"]["properties"]["capacity"]
    members = [m["$ref"].rsplit("/", 1)[1] for m in capacity["oneOf"]]
    assert members == ["Api526Orifice", "EffectiveOrifice", "CertifiedOrifice"]
    assert SCHEMAS["Api526Orifice"]["required"] == ["kind", "letter"]
    assert SCHEMAS["EffectiveOrifice"]["required"] == ["kind", "area"]
    assert SCHEMAS["CertifiedOrifice"]["required"] == ["kind", "area", "dischargeCoefficient"]
    for name, kind in (
        ("Api526Orifice", "api526"),
        ("EffectiveOrifice", "effective"),
        ("CertifiedOrifice", "certified"),
    ):
        assert SCHEMAS[name]["properties"]["kind"]["const"] == kind
        assert SCHEMAS[name]["additionalProperties"] is False
    effective = COMPONENTS.validate_python(relief(capacity={"kind": "effective", "area": 1e-3}))
    assert isinstance(effective, ReliefValve)
    assert isinstance(effective.capacity, EffectiveOrifice)
    certified = COMPONENTS.validate_python(
        relief(capacity={"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7})
    )
    assert isinstance(certified, ReliefValve)
    assert isinstance(certified.capacity, CertifiedOrifice)
    assert certified.capacity.overpressure is None  # ASME's default


@pytest.mark.parametrize(
    "capacity",
    [
        {"kind": "api526", "letter": "F", "dischargeCoefficient": 0.9},
        {"kind": "api526", "letter": "F", "overpressure": 0.25},
        {"kind": "api526", "letter": "F", "area": 1e-3},
        {"kind": "effective", "area": 1e-3, "dischargeCoefficient": 0.9},
        {"kind": "effective", "area": 1e-3, "overpressure": 0.25},
        {"kind": "effective", "letter": "F"},
        {"kind": "certified", "area": 1e-3, "dischargeCoefficient": 0.9, "letter": "F"},
        {"kind": "certified", "area": 1e-3},
        {"kind": "certified", "dischargeCoefficient": 0.9},
        {"kind": "api526"},
        {"kind": "effective"},
    ],
)
def test_no_value_comes_from_another_kind(capacity: dict[str, Any]) -> None:
    """Decision 7: "IN NO CASE SHOULD AN API EFFECTIVE COEFFICIENT OF DISCHARGE OR EFFECTIVE AREA
    BE USED WITH THE RATED COEFFICIENT OF DISCHARGE OR ACTUAL AREA" (Pentair ch. 5): a letter or
    an effective area takes no coefficient or overpressure, and a certified capacity no letter."""
    assert not _valid(relief(capacity=capacity))


def test_an_unknown_kind_is_invalid_capacity() -> None:
    """As D18's invalid_rating: the custom error never quotes the submitted kind."""
    for kind in (SECRET, "K", "Cv", None):
        with pytest.raises(ValidationError) as caught:
            COMPONENTS.validate_python(relief(capacity={"kind": kind, "letter": "F"}))
        errors = caught.value.errors()
        assert [e["type"] for e in errors] == ["invalid_capacity"]
        assert SECRET not in str(errors[0]["msg"])


def test_the_letters_areas_and_coefficients_are_bounded() -> None:
    for letter in API526_letters:
        assert _valid(relief(capacity={"kind": "api526", "letter": letter}))
    for letter in ("A", "I", "O", "S", "U", "f", "", 1):
        assert not _valid(relief(capacity={"kind": "api526", "letter": letter})), letter
    for name in ("EffectiveOrifice", "CertifiedOrifice"):
        area = SCHEMAS[name]["properties"]["area"]
        assert (area["exclusiveMinimum"], area["maximum"]) == (0, RELIEF_AREA_MAX)
    assert math.pi * 10.0**2 / 4 == RELIEF_AREA_MAX  # a 10 m bore, the pipe inner-diameter bound

    def certified(**values: Any) -> dict[str, Any]:
        return relief(
            capacity={"kind": "certified", "area": 1e-3, "dischargeCoefficient": 0.7, **values}
        )

    for inside in (math.nextafter(0.0, 1.0), 1e-3, RELIEF_AREA_MAX):
        assert _valid(relief(capacity={"kind": "effective", "area": inside})), inside
        assert _valid(certified(area=inside)), inside
    for outside in (-1e-3, 0.0, math.nextafter(RELIEF_AREA_MAX, math.inf), math.inf, math.nan):
        assert not _valid(relief(capacity={"kind": "effective", "area": outside})), outside
        assert not _valid(certified(area=outside)), outside
    for inside in (math.nextafter(0.0, 1.0), 0.62, 0.975, 1.0):
        assert _valid(certified(dischargeCoefficient=inside)), inside
    for outside in (-0.5, 0.0, math.nextafter(1.0, 2.0), math.nan):
        assert not _valid(certified(dischargeCoefficient=outside)), outside
    for inside in (None, math.nextafter(0.0, 1.0), 0.08, 0.25, 1.0):
        assert _valid(certified(overpressure=inside)), inside
    for outside in (-0.1, 0.0, math.nextafter(1.0, 2.0), 1.5, math.nan):
        assert not _valid(certified(overpressure=outside)), outside


def test_the_schema_text_defines_each_value() -> None:
    """The fields' meanings are stated, not inferred (D11; §2.1), and the numbers in the text are
    the data file's."""
    props = SCHEMAS["ReliefValve"]["properties"]
    assert "static pressure difference, inlet minus outlet" in props["setPressure"]["description"]
    assert "bench setting" in props["setPressure"]["description"]
    assert "Never one value from each set" in props["capacity"]["description"]
    assert "gagged" in props["status"]["description"]
    overpressure = SCHEMAS["CertifiedOrifice"]["properties"]["overpressure"]["description"]
    assert "not the allowable accumulation" in overpressure
    assert "10 % of the set or 3 psi (20.68 kPa), whichever is greater" in overpressure
    assert "at least 15 psi (103.42 kPa)" in overpressure
    for name in ("Api526Orifice", "EffectiveOrifice"):
        assert (
            "coefficient of discharge, 0.65" in SCHEMAS[name]["properties"]["kind"]["description"]
        )
    assert (
        "0.9 × the measured coefficient"
        in (SCHEMAS["CertifiedOrifice"]["properties"]["dischargeCoefficient"]["description"])
    )


@pytest.mark.parametrize(
    ("fields", "where", "quoted"),
    [
        ({"setPressure": 123456789.5}, "setPressure", "123456789.5"),
        ({"setPressure": -98765.4}, "setPressure", "98765.4"),
        ({"status": SECRET}, "status", SECRET),
        ({"capacity": {"kind": SECRET, "letter": "F"}}, "capacity", SECRET),
        ({"capacity": {"kind": "api526", "letter": SECRET}}, "letter", SECRET),
        ({"capacity": {"kind": "effective", "area": 87.654321}}, "area", "87.654321"),
        (
            {"capacity": {"kind": "certified", "area": 1e-3, "dischargeCoefficient": 7.654321}},
            "dischargeCoefficient",
            "7.654321",
        ),
        (
            {
                "capacity": {
                    "kind": "certified",
                    "area": 1e-3,
                    "dischargeCoefficient": 0.7,
                    "overpressure": 5.432123,
                }
            },
            "overpressure",
            "5.432123",
        ),
        (
            {"capacity": {"kind": "api526", "letter": "F", "dischargeCoefficient": 0.6789012}},
            "capacity.api526",  # an unknown field is not named: its name is submitted input
            "0.6789012",
        ),
    ],
)
def test_a_value_out_of_bounds_is_400_without_echo(
    fields: dict[str, Any], where: str, quoted: str
) -> None:
    response = _client().post("/api/v1/solve", json={"project": line(**fields)})
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["error"] == "VALIDATION_ERROR"
    assert any(where in issue["message"] for issue in payload["issues"]), payload
    assert quoted not in response.text


# --------------------------------------------------------------------------- the result


def test_the_result_has_the_proposals_fields() -> None:
    """Proposal §2.2's table, in its order; every field is sent (OutputModel)."""
    fields = [
        "state",
        "flow",
        "lift",
        "headLoss",
        "totalPressureDifference",
        "pressureDrop",
        "inletPressure",
        "backPressure",
        "setPressure",
        "setRatio",
        "overpressure",
        "overpressureSource",
        "fullLiftPressureDifference",
        "fullLiftFlow",
        "flowRatio",
        "capacity",
        "reynoldsNumber",
    ]
    assert [f.alias for f in ReliefValveResult.model_fields.values()] == fields
    schema = SCHEMAS["ReliefValveResult"]
    assert sorted(schema["required"]) == sorted(fields)
    props = schema["properties"]
    assert props["state"]["enum"] == ["closed", "partial_lift", "full_lift"]
    assert props["overpressureSource"]["enum"] == ["asme_default", "user"]
    nullable = {name for name, prop in props.items() if {"type": "null"} in prop.get("anyOf", [])}
    assert nullable == {"inletPressure", "backPressure", "reynoldsNumber"}


def test_the_result_capacity_is_the_input_with_its_values_resolved() -> None:
    """§2.2: the capacity the solve used, of the input's kind, with its area and coefficient of
    discharge resolved and, for an effective area, the API 526 letter that covers it."""
    capacity = SCHEMAS["ReliefValveResult"]["properties"]["capacity"]
    members = {m["$ref"].rsplit("/", 1)[1] for m in capacity["oneOf"]}
    assert members == {"Api526OrificeResult", "EffectiveOrificeResult", "CertifiedOrificeResult"}
    assert capacity["discriminator"]["propertyName"] == "kind"
    required = {name: sorted(SCHEMAS[name]["required"]) for name in members}
    assert required == {
        "Api526OrificeResult": ["area", "dischargeCoefficient", "kind", "letter"],
        "EffectiveOrificeResult": ["area", "coveringLetter", "dischargeCoefficient", "kind"],
        "CertifiedOrificeResult": ["area", "dischargeCoefficient", "kind", "overpressure"],
    }
    covering = SCHEMAS["EffectiveOrificeResult"]["properties"]["coveringLetter"]["anyOf"]
    assert covering == [{"enum": API526_letters, "type": "string"}, {"type": "null"}]
    # Each input kind's values are in its result member, so the capacity used is the input's.
    for name in ("Api526Orifice", "EffectiveOrifice", "CertifiedOrifice"):
        assert set(SCHEMAS[name]["properties"]) <= set(SCHEMAS[f"{name}Result"]["properties"])


def test_the_result_map_is_always_present() -> None:
    """``reliefValveResults`` is required and {} without a relief valve, converged or not
    (decision 16, D18's and D20's rule)."""
    assert "reliefValveResults" in SCHEMAS["SolvedState"]["required"]
    solved = solve_project(
        make_project(
            [reservoir("R1", level=20.0), reservoir("R2", level=10.0)],
            [connection("P1", ("R1", "port_1"), ("R2", "port_1"))],
        )
    )
    assert solved.converged
    assert solved.relief_valve_results == {}
    assert solved.model_dump(mode="json")["reliefValveResults"] == {}
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
    assert unsolved.model_dump(mode="json")["reliefValveResults"] == {}
    SolvedState.model_validate(unsolved.model_dump(mode="json"))


def test_the_new_flag_codes_are_info() -> None:
    """Decision 15: RELIEF_VALVE_OPEN at full lift and RELIEF_VALVE_CLOSED on a closed valve with
    no result are states worth knowing; the band and viscosity warnings and the flashing flag
    reuse CORRELATION_OUT_OF_RANGE and BELOW_VAPOR_PRESSURE."""
    codes = get_args(FlagCode)
    assert {"RELIEF_VALVE_OPEN", "RELIEF_VALVE_CLOSED"} <= set(codes)
    assert FLAG_SEVERITY["RELIEF_VALVE_OPEN"] == FLAG_SEVERITY["RELIEF_VALVE_CLOSED"] == "info"
    assert FLAG_SEVERITY["CORRELATION_OUT_OF_RANGE"] == "warning"
    assert FLAG_SEVERITY["BELOW_VAPOR_PRESSURE"] == "invalid"
    published = SCHEMAS["Flag"]["properties"]["code"]["enum"]
    assert list(published) == list(codes)


# --------------------------------------------------------------------------- scenarios


def _override(field: str, value: Any, cid: str = "RV1") -> dict[str, Any]:
    return {"kind": "component", "componentId": cid, "field": field, "value": value}


def test_the_allow_list_entries() -> None:
    """Decision 18: the status, the set, the whole capacity and each of its values, held by the
    capacity of its kind; an effective and a certified capacity both hold an area."""
    fields = COMPONENT_FIELDS[ReliefValve]
    assert set(fields) == {
        "status",
        "setPressure",
        "capacity",
        "capacity.letter",
        "capacity.area",
        "capacity.dischargeCoefficient",
        "capacity.overpressure",
    }
    holders = {name: tuple(c.__name__ for c in e.holders) for name, e in fields.items()}
    assert holders == {
        "status": (),
        "setPressure": (),
        "capacity": (),
        "capacity.letter": ("Api526Orifice",),
        "capacity.area": ("EffectiveOrifice", "CertifiedOrifice"),
        "capacity.dischargeCoefficient": ("CertifiedOrifice",),
        "capacity.overpressure": ("CertifiedOrifice",),
    }
    # The holders of one value bound it alike, so the bounding schema's bounds hold for each.
    area = {
        name: {k: v for k, v in SCHEMAS[name]["properties"]["area"].items() if k != "description"}
        for name in ("EffectiveOrifice", "CertifiedOrifice")
    }
    assert area["EffectiveOrifice"] == area["CertifiedOrifice"]
    valve = ReliefValve.model_validate(relief())
    units = {name: override_unit(e, valve) for name, e in fields.items()}
    assert units == {
        "status": "",
        "setPressure": "Pa (difference)",
        "capacity": "",
        "capacity.letter": "",
        "capacity.area": "m²",
        "capacity.dischargeCoefficient": "",
        "capacity.overpressure": "",
    }
    labels = {
        kind: override_label(
            fields["capacity.area"], ReliefValve.model_validate(relief(capacity=c))
        )
        for kind, c in (
            ("api526", {"kind": "api526", "letter": "F"}),
            ("effective", {"kind": "effective", "area": 1e-3}),
            ("certified", {"kind": "certified", "area": 1e-3, "dischargeCoefficient": 0.7}),
        )
    }
    assert labels == {
        "api526": "orifice area",
        "effective": "API 520 effective area",
        "certified": "actual orifice area",
    }
    assert override_label(fields["capacity.area"]) == "orifice area"  # no target


def test_a_capacity_and_a_value_of_it_are_one_value_too_many() -> None:
    """D18's whole-and-part rule: the whole capacity and one of its values in one scenario is 400
    (by index, never quoting a value); two values of one capacity are two values."""
    with pytest.raises(ValidationError, match="overrides 0 and 1 set a value and a part of it"):
        Scenario.model_validate(
            {
                "id": "S1",
                "name": "S1",
                "overrides": [
                    _override("capacity", {"kind": "api526", "letter": "J"}),
                    _override("capacity.area", 1e-3),
                ],
            }
        )
    Scenario.model_validate(
        {
            "id": "S1",
            "name": "S1",
            "overrides": [
                _override("capacity.area", 1e-3),
                _override("capacity.overpressure", None),
                _override("setPressure", 4.0e5),
                _override("status", "locked_closed"),
                _override("capacity", {"kind": "api526", "letter": "J"}, cid="RV2"),
            ],
        }
    )
    body = {
        "project": line()
        | {
            "scenarios": [
                {
                    "id": "S1",
                    "name": "S1",
                    "overrides": [
                        _override("capacity.letter", SECRET),
                        _override("capacity", {"kind": SECRET}),
                    ],
                }
            ]
        }
    }
    response = _client().post("/api/v1/solve", json=body)
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert SECRET not in response.text


# --------------------------------------------------------------------------- goal seek


def test_the_goal_seek_variables() -> None:
    """Decision 19: the set (linear), the area (log; effective or certified), the rated
    coefficient (linear) and the overpressure (linear); not the letter or the whole capacity."""
    variables = GOAL_COMPONENT_FIELDS[ReliefValve]
    assert {name: v.scale for name, v in variables.items()} == {
        "setPressure": "linear",
        "capacity.area": "log",
        "capacity.dischargeCoefficient": "linear",
        "capacity.overpressure": "linear",
    }
    assert "capacity.area" in LOG_FIELDS
    assert {"capacity", "capacity.letter"} <= set(NOT_VARIABLES)
    bounding = {name: v.bounding_schema(ReliefValve).__name__ for name, v in variables.items()}
    assert bounding == {
        "setPressure": "ReliefValve",
        "capacity.area": "EffectiveOrifice",
        "capacity.dischargeCoefficient": "CertifiedOrifice",
        "capacity.overpressure": "CertifiedOrifice",
    }
    for field in variables:
        ComponentVariable.model_validate(
            {"kind": "component", "componentId": "RV1", "field": field, "lower": 0.1, "upper": 0.2}
        )
    for field in ("capacity", "capacity.letter", "status"):
        with pytest.raises(ValidationError):
            ComponentVariable.model_validate(
                {"kind": "component", "componentId": "RV1", "field": field, "lower": 1, "upper": 2}
            )


def test_the_goal_seek_goals() -> None:
    """§5: the flow and the static pressure drop, Compare's rows; the inlet pressure is the
    port static-pressure goal."""
    goals = {name: spec for name, spec in GOAL_QUANTITIES.items() if spec.element == "relief_valve"}
    assert {name: (s.unit, s.category, s.needs, s.label) for name, s in goals.items()} == {
        "relief_valve_flow": ("m³/s", "flow", (), "flow through {element}"),
        "relief_valve_pressure_drop": (
            "Pa (difference)",
            "pressure",
            (),
            "static pressure drop across {element}",
        ),
    }
    assert all(s.targets == (ReliefValve,) for s in goals.values())
    assert ReliefValve in GOAL_QUANTITIES["port_pressure"].targets
    assert "relief_valve" in get_args(ElementKind)
    for quantity in goals:
        Goal.model_validate({"quantity": quantity, "elementId": "RV1", "target": 0.01})


# --------------------------------------------------------------------------- existing projects


@pytest.mark.parametrize(
    "component",
    [
        {"type": "valve", "valveType": "psv", "setpoint": 5.0e5},
        {"type": "valve", "valveType": "check", "crackingPressure": 5.0e5},
        {"type": "orifice", "boreDiameter": 0.05},
        {"type": "equipment", "rating": {"kind": "Cv", "value": 90.0}},
    ],
)
def test_other_components_validate_as_before(component: dict[str, Any]) -> None:
    """The relief valve's fields belong to it alone: neighbouring types neither take them nor
    change (a set pressure or a capacity on a PSV is an unknown field)."""
    base = {
        "id": "X1",
        "name": "X1",
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **component,
    }
    assert _valid(base)
    assert not _valid({**base, "setPressure": 5.0e5})
    assert not _valid({**base, "capacity": {"kind": "api526", "letter": "F"}})
