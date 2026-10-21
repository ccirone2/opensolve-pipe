"""The model rules JSON Schema cannot express are published in the OpenAPI schema as
extensions (x-port-ids, x-port-roles, x-port-count, x-required-parameters, x-reducer-types,
x-entrance-types, x-exit-types, x-setpoint-bounds), which the web app reads instead of copying
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
from opensolve_pipe.models.piping import Fitting, PipingSegment
from opensolve_pipe.models.ports import PortDirection

SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]
WEB_OPENAPI = Path(__file__).parents[3] / "web" / "src" / "lib" / "api" / "openapi.json"
COMPONENTS = TypeAdapter(Component)

BASE: dict[str, dict[str, Any]] = {
    "Reservoir": {"type": "reservoir", "liquidLevel": 1.0},
    "IdealReferenceNode": {"type": "reference_node", "referenceType": "ideal", "pressure": 0.0},
    "Plug": {"type": "plug"},
    "TeeBranch": {"type": "branch", "branchType": "tee"},
    "WyeBranch": {"type": "branch", "branchType": "wye"},
    "Pump": {"type": "pump", "curveId": "C1"},
    "IsolationValve": {"type": "valve", "valveType": "gate"},
    "CheckValve": {"type": "valve", "valveType": "check"},
    "ControlValve": {"type": "valve", "valveType": "prv", "setpoint": 0.0},
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
