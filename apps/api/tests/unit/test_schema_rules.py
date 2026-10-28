"""The model rules JSON Schema cannot express are published in the OpenAPI schema as
extensions (x-port-ids, x-port-roles, x-port-count, x-required-parameters, x-reducer-types,
x-entrance-types, x-exit-types, x-setpoint-bounds, x-ordered-fields, and the project library's
x-fields-by-value and x-reference-fields; goal seek's x-goal-variables, x-goal-quantities and
x-goal-seek-rules are checked in test_goal_seek_models.py), which the web app reads instead of
copying
(apps/web/src/lib/utils/model-rules.ts). These tests check that each extension states exactly
what the validators enforce, and that the web app's copy of the schema is the API's current
one, so a model change cannot leave the two apart."""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from opensolve_pipe.main import app
from opensolve_pipe.models.components import Component
from opensolve_pipe.models.design_checks import OperatingRegionCheck, PipeVelocityCheck
from opensolve_pipe.models.goal_seek import GoalVariable
from opensolve_pipe.models.piping import Fitting, PipeDefinition, PipingSegment
from opensolve_pipe.models.ports import PortDirection
from opensolve_pipe.models.project_library import PipeSpec, ResistanceSpec
from opensolve_pipe.models.pumps import AllowableOperatingRegion

SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]
WEB_OPENAPI = Path(__file__).parents[3] / "web" / "src" / "lib" / "api" / "openapi.json"
COMPONENTS = TypeAdapter(Component)

BASE: dict[str, dict[str, Any]] = {
    "Reservoir": {"type": "reservoir", "liquidLevel": 1.0},
    "IdealReferenceNode": {"type": "reference_node", "referenceType": "ideal", "pressure": 0.0},
    "Plug": {"type": "plug"},
    "AssignedFlow": {"type": "assigned_flow", "flow": 0.0},
    "TeeBranch": {"type": "branch", "branchType": "tee"},
    "WyeBranch": {"type": "branch", "branchType": "wye"},
    "Pump": {"type": "pump", "curveId": "C1"},
    "IsolationValve": {"type": "valve", "valveType": "gate"},
    "CheckValve": {"type": "valve", "valveType": "check"},
    "ControlValve": {"type": "valve", "valveType": "prv", "setpoint": 0.0},
    "Equipment": {"type": "equipment", "rating": {"kind": "Cv", "value": 90.0}},
    "Orifice": {"type": "orifice", "boreDiameter": 0.05},
}
"""One valid instance per component schema, without its ports (test inputs)."""


def _component(schema: str, port_ids: list[str], **fields: Any) -> dict[str, Any]:
    ports = [{"id": p, "nominalSize": 0.1} for p in port_ids]
    return {"id": "X1", "name": "X", "elevation": 0.0, **BASE[schema], "ports": ports, **fields}


def test_every_component_schema_is_covered() -> None:
    members = SCHEMAS["Project"]["properties"]["components"]["items"]["oneOf"]
    assert sorted(m["$ref"].rsplit("/", 1)[1] for m in members) == sorted(BASE)


@pytest.mark.parametrize("schema", sorted(BASE))
def test_port_ids_and_roles_are_what_the_validators_require(schema: str) -> None:
    published = SCHEMAS[schema]
    ids: list[str] | None = published.get("x-port-ids")
    roles: dict[str, str] | None = published.get("x-port-roles")
    count: int | None = published.get("x-port-count")
    if ids is None:
        assert roles is None
        free = ["port_1", "port_2", "port_3"][: count or 3]
        COMPONENTS.validate_python(_component(schema, free))
        if count is not None:
            with pytest.raises(ValidationError, match=f"exactly {count} port"):
                COMPONENTS.validate_python(_component(schema, [*free, "extra"]))
        return
    assert count is None
    assert roles is not None
    assert set(roles) <= set(ids)
    assert set(roles.values()) <= {PortDirection.INLET.value, PortDirection.OUTLET.value}
    COMPONENTS.validate_python(_component(schema, list(reversed(ids))))
    with pytest.raises(ValidationError, match="must have ports"):
        COMPONENTS.validate_python(_component(schema, [*ids[:-1], "other"]))
    if len(ids) > 1:
        with pytest.raises(ValidationError, match="must have ports"):
            COMPONENTS.validate_python(_component(schema, ids[:-1]))
    with pytest.raises(ValidationError, match="must have ports"):
        COMPONENTS.validate_python(_component(schema, [*ids, "extra"]))


def test_ports_bound_is_in_the_schema() -> None:
    reservoir = SCHEMAS["Reservoir"]["properties"]["ports"]
    many = [f"port_{i}" for i in range(1, reservoir["maxItems"] + 1)]
    COMPONENTS.validate_python(_component("Reservoir", many))
    with pytest.raises(ValidationError, match="at most"):
        COMPONENTS.validate_python(_component("Reservoir", [*many, "one_more"]))


def test_setpoint_bounds_are_what_the_validator_enforces() -> None:
    bounds = SCHEMAS["ControlValve"]["x-setpoint-bounds"]
    assert set(bounds) == {"fcv"}
    field = SCHEMAS["ControlValve"]["properties"]["setpoint"]
    for valve, limits in bounds.items():
        low, high = limits["minimum"], limits["maximum"]
        assert field["minimum"] <= low < high <= field["maximum"]
        ports = ["inlet", "outlet"]
        for inside in (low, high):
            COMPONENTS.validate_python(
                _component("ControlValve", ports, valveType=valve, setpoint=inside)
            )
        for outside in (math.nextafter(low, -math.inf), math.nextafter(high, math.inf)):
            with pytest.raises(ValidationError, match="FCV setpoint is a flow"):
                COMPONENTS.validate_python(
                    _component("ControlValve", ports, valveType=valve, setpoint=outside)
                )
        # The pressure valves keep the field's own bounds.
        COMPONENTS.validate_python(_component("ControlValve", ports, setpoint=field["maximum"]))


def _nested(path: str, value: Any) -> dict[str, Any]:
    """{'a': {'b': value}} for the dotted camelCase path 'a.b'."""
    head, _, rest = path.partition(".")
    return {head: _nested(rest, value) if rest else value}


def test_a_speed_controlled_pump_is_a_valid_component() -> None:
    """A Pump instance with a control (CLAUDE.md D11): flow mode, a setpoint and a minimum
    speed below its speed; the control is optional (a fixed-speed pump)."""
    ports = ["suction", "discharge"]
    control = {"mode": "flow", "setpoint": 0.02, "minSpeed": 0.4}
    pump = COMPONENTS.validate_python(_component("Pump", ports, speed=0.9, control=control))
    assert pump.model_dump(by_alias=True)["control"] == control
    assert COMPONENTS.validate_python(_component("Pump", ports)).model_dump()["control"] is None
    for missing in ("mode", "setpoint", "minSpeed"):  # all required: no default speed limit
        partial = {k: v for k, v in control.items() if k != missing}
        with pytest.raises(ValidationError, match=missing):
            COMPONENTS.validate_python(_component("Pump", ports, control=partial))


PUMP_CONTROL = {"mode": "flow", "setpoint": 0.02}
"""The rest of a pump control (test inputs), merged with the ordered field it holds."""


def _ordered_pump(lower: str, upper: str, low: float, high: float) -> dict[str, Any]:
    """A pump with the values ``low`` at path ``lower`` and ``high`` at path ``upper``."""
    fields: dict[str, Any] = {}
    for path, value in ((upper, high), (lower, low)):
        for key, item in _nested(path, value).items():
            fields[key] = {**PUMP_CONTROL, **item} if isinstance(item, dict) else item
    return _component("Pump", ["suction", "discharge"], **fields)


def test_ordered_fields_are_what_the_validators_enforce() -> None:
    """x-ordered-fields: each pair (dotted camelCase paths) must hold lower < upper (strict)
    when both are present, which is what the model validator enforces; one alone is free."""
    published = {
        name: schema["x-ordered-fields"]
        for name, schema in SCHEMAS.items()
        if "x-ordered-fields" in schema
    }
    bounds = [{"lower": "lower", "upper": "upper", "strict": True}]
    assert published == {
        "Pump": [{"lower": "control.minSpeed", "upper": "speed", "strict": True}],
        # A goal-seek variable's bounds (docs/proposals/goal-seek.md §2.4).
        "ComponentVariable": bounds,
        "PipeVariable": bounds,
        "ProjectVariable": bounds,
        # Design checks (CLAUDE.md D19) and the pump curve's allowable operating region.
        "OperatingRegionCheck": [
            {"lower": "preferredMin", "upper": "preferredMax", "strict": True}
        ],
        "PipeVelocityCheck": [{"lower": "minimum", "upper": "maximum", "strict": True}],
        "AllowableOperatingRegion": [{"lower": "flowMin", "upper": "flowMax", "strict": True}],
        # A project library pipe spec's bore below its outer diameter (CLAUDE.md D21).
        "PipeSpec": [{"lower": "innerDiameter", "upper": "outerDiameter", "strict": True}],
    }
    user = {"source": {"kind": "user"}}
    spec = {"id": "PS1", "name": "S", "source": "B36.10M", "materialId": "carbon_steel"}
    for model, lower, upper, match, extra in (
        (OperatingRegionCheck, "preferredMin", "preferredMax", "preferredMin must be below", user),
        (PipeVelocityCheck, "minimum", "maximum", "minimum must be below maximum", user),
        (AllowableOperatingRegion, "flowMin", "flowMax", "flowMin must be below flowMax", {}),
        (PipeSpec, "innerDiameter", "outerDiameter", "innerDiameter must be below", spec),
    ):
        model.model_validate({lower: 0.5, upper: 0.8, **extra})
        model.model_validate({lower: math.nextafter(0.8, -math.inf), upper: 0.8, **extra})
        for low in (0.8, 0.95):
            with pytest.raises(ValidationError, match=match):
                model.model_validate({lower: low, upper: 0.8, **extra})
    PipeVelocityCheck.model_validate({"maximum": 0.8, **user})  # one alone is free
    PipeSpec.model_validate({"innerDiameter": 0.8, **spec})
    variables = {
        "ComponentVariable": {"kind": "component", "componentId": "R1", "field": "liquidLevel"},
        "PipeVariable": {"kind": "pipe", "connectionId": "L1", "pipeIndex": 0, "field": "length"},
        "ProjectVariable": {"kind": "project", "field": "fluid.temperature"},
    }
    for name, fields in variables.items():
        adapter = TypeAdapter(GoalVariable)
        adapter.validate_python({**fields, "lower": 0.5, "upper": 0.8})
        adapter.validate_python({**fields, "lower": math.nextafter(0.8, -math.inf), "upper": 0.8})
        for low in (0.8, 0.95):
            with pytest.raises(ValidationError, match="lower must be below upper"):
                adapter.validate_python({**fields, "lower": low, "upper": 0.8})
        assert {"lower", "upper"} <= set(SCHEMAS[name]["required"])
    for pair in published["Pump"]:
        lower, upper = pair["lower"], pair["upper"]
        COMPONENTS.validate_python(_ordered_pump(lower, upper, 0.5, 0.8))
        COMPONENTS.validate_python(_ordered_pump(lower, upper, math.nextafter(0.8, -math.inf), 0.8))
        for low in (0.8, 0.95):
            with pytest.raises(ValidationError, match="minSpeed must be below speed"):
                COMPONENTS.validate_python(_ordered_pump(lower, upper, low, 0.8))
        alone = _component("Pump", ["suction", "discharge"], **_nested(upper, 0.2))
        COMPONENTS.validate_python(alone)


VALID_PARAMETERS = {"angle": 45.0, "radiusRatio": 1.5, "kOverride": 0.5}
"""A valid value of each fitting parameter (test inputs within the field bounds)."""


def test_required_fitting_parameters_are_what_the_validator_enforces() -> None:
    fitting = SCHEMAS["Fitting"]
    kinds = fitting["properties"]["type"]["enum"]
    required: dict[str, list[str]] = fitting["x-required-parameters"]
    assert set(required) <= set(kinds)
    assert set(VALID_PARAMETERS) == {p for names in required.values() for p in names}
    for kind in kinds:
        names = required.get(kind, [])
        Fitting.model_validate({"type": kind, **{n: VALID_PARAMETERS[n] for n in names}})
        for missing in names:
            given = {n: VALID_PARAMETERS[n] for n in names if n != missing}
            with pytest.raises(ValidationError, match=missing):
                Fitting.model_validate({"type": kind, **given})


def test_reducer_entrance_and_exit_types() -> None:
    fitting = SCHEMAS["Fitting"]
    kinds = fitting["properties"]["type"]["enum"]
    for key in ("x-reducer-types", "x-entrance-types", "x-exit-types"):
        assert fitting[key], key
        assert set(fitting[key]) <= set(kinds), key
    assert set(fitting["x-entrance-types"]).isdisjoint(fitting["x-exit-types"])
    pipe = {"materialId": "custom", "innerDiameter": 0.1, "roughness": 1e-5, "length": 1.0}
    params = fitting["x-required-parameters"]
    for kind in kinds:
        on_last = {
            "type": kind,
            "pipeIndex": 1,
            **{n: VALID_PARAMETERS[n] for n in params.get(kind, [])},
        }
        two_pipes = {"pipes": [pipe, pipe], "fittings": [on_last]}
        if kind in fitting["x-reducer-types"]:
            with pytest.raises(ValidationError, match="reducer needs a following segment"):
                PipingSegment.model_validate(two_pipes)
            PipingSegment.model_validate({**two_pipes, "fittings": [{**on_last, "pipeIndex": 0}]})
        else:
            PipingSegment.model_validate(two_pipes)


def test_the_web_app_reads_the_current_schema() -> None:
    """apps/web/src/lib/api/openapi.json (pnpm gen:types) is the API's schema as it is now: the
    web app's validation, bounds and model rules come from that file."""
    web = json.loads(WEB_OPENAPI.read_text(encoding="utf-8"))
    assert web == json.loads(json.dumps(app.openapi())), (
        "apps/web/src/lib/api/openapi.json is out of date: run `pnpm gen:types` in apps/web"
    )


FIELD_VALUES: dict[str, Any] = {
    "materialId": "carbon_steel",
    "schedule": "40",
    "nominalSize": 0.1016,
    "innerDiameter": 0.1,
    "roughness": 4.5e-5,
    "kOverride": 0.5,
    "referenceDiameter": 0.7366,
}
"""A valid value of each field the project library's rules name (test inputs)."""

BY_VALUE_BASE: dict[str, dict[str, Any]] = {
    "PipeSpec": {"id": "PS1", "name": "S", "source": "B36.10M", "innerDiameter": 0.1},
    "ResistanceSpec": {"id": "RS1", "name": "R", "source": "datasheet", "value": 2.0},
}
"""The rest of a valid instance of each schema that publishes x-fields-by-value."""

BY_VALUE_MODELS: dict[str, type[PipeSpec] | type[ResistanceSpec]] = {
    "PipeSpec": PipeSpec,
    "ResistanceSpec": ResistanceSpec,
}


def test_fields_by_value_are_what_the_validators_enforce() -> None:
    """x-fields-by-value: with ``field`` at a listed value, each required field must be given
    and each forbidden one absent (or null), which is what the model validators enforce; the
    other values add no rule (CLAUDE.md D21)."""
    published = {
        name: schema["x-fields-by-value"]
        for name, schema in SCHEMAS.items()
        if "x-fields-by-value" in schema
    }
    assert published == {
        "PipeSpec": {"field": "materialId", "required": {"custom": ["roughness"]}, "forbidden": {}},
        "ResistanceSpec": {
            "field": "kind",
            "required": {"K": ["referenceDiameter"]},
            "forbidden": {"Cv": ["referenceDiameter"], "Kv": ["referenceDiameter"]},
        },
    }
    for name, rule in published.items():
        model, base, key = BY_VALUE_MODELS[name], BY_VALUE_BASE[name], rule["field"]
        assert key in SCHEMAS[name]["required"]
        for value, fields in rule["required"].items():
            given = {f: FIELD_VALUES[f] for f in fields}
            model.model_validate({**base, key: value, **given})
            for missing in fields:
                partial = {f: v for f, v in given.items() if f != missing}
                for absent in (partial, {**partial, missing: None}):
                    with pytest.raises(ValidationError, match=f"needs {missing}"):
                        model.model_validate({**base, key: value, **absent})
        for value, fields in rule["forbidden"].items():
            model.model_validate({**base, key: value})
            model.model_validate({**base, key: value, **dict.fromkeys(fields)})
            for extra in fields:
                with pytest.raises(ValidationError, match=f"takes no {extra}"):
                    model.model_validate({**base, key: value, extra: FIELD_VALUES[extra]})
    # A value the rule does not list adds none: a library material may omit or give roughness.
    for roughness in (None, 4.5e-5):
        PipeSpec.model_validate(
            {**BY_VALUE_BASE["PipeSpec"], "materialId": "carbon_steel", "roughness": roughness}
        )


REFERENCE_BASE: dict[str, dict[str, Any]] = {
    "PipeDefinition": {"length": 10.0},
    "Fitting": {"type": "elbow_90_lr"},
}
"""The rest of a valid instance of each schema that publishes x-reference-fields."""

REFERENCE_MODELS: dict[str, type[PipeDefinition] | type[Fitting]] = {
    "PipeDefinition": PipeDefinition,
    "Fitting": Fitting,
}


def test_reference_fields_are_what_the_validators_enforce() -> None:
    """x-reference-fields: with a reference to a project library entry given, none of the fields
    it replaces may be (null counts as absent), and it meets x-required-parameters' need for
    them; without it, requiredWithout are required (CLAUDE.md D21)."""
    published = {
        name: schema["x-reference-fields"]
        for name, schema in SCHEMAS.items()
        if "x-reference-fields" in schema
    }
    assert published == {
        "PipeDefinition": {
            "specId": {
                "replaces": ["materialId", "schedule", "nominalSize", "innerDiameter", "roughness"],
                "requiredWithout": ["materialId"],
            }
        },
        "Fitting": {"resistanceId": {"replaces": ["kOverride"], "requiredWithout": []}},
    }
    for name, references in published.items():
        model, base = REFERENCE_MODELS[name], REFERENCE_BASE[name]
        for reference, rule in references.items():
            assert reference not in SCHEMAS[name].get("required", [])
            model.model_validate({**base, reference: "E1"})
            model.model_validate({**base, reference: "E1", **dict.fromkeys(rule["replaces"])})
            for field in rule["replaces"]:
                with pytest.raises(ValidationError, match=f"{field} cannot be given with"):
                    model.model_validate({**base, reference: "E1", field: FIELD_VALUES[field]})
            for field in rule["requiredWithout"]:
                assert field not in SCHEMAS[name].get("required", [])
                for absent in ({}, {field: None}):
                    with pytest.raises(ValidationError, match=f"{field} is required without"):
                        model.model_validate({**base, **absent})
    # Without the reference the inline rules are today's.
    PipeDefinition.model_validate(
        {"length": 10.0, "materialId": "custom", "innerDiameter": 0.1, "roughness": 1e-5}
    )
    with pytest.raises(ValidationError, match="a custom pipe needs"):
        PipeDefinition.model_validate({"length": 10.0, "materialId": "custom"})
    # The reference meets a custom fitting's need for kOverride (x-required-parameters).
    required = SCHEMAS["Fitting"]["x-required-parameters"]["custom"]
    assert required == ["kOverride"]
    Fitting.model_validate({"type": "custom", "resistanceId": "RS1"})
    with pytest.raises(ValidationError, match="needs kOverride \\(or resistanceId"):
        Fitting.model_validate({"type": "custom"})
