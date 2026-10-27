"""Scenarios: named sets of overrides of base-project values (PRD §3.8, SDD §4.12, CLAUDE.md D15,
docs/proposals/scenario-manager.md).

A scenario changes values only, never topology. Each override names a target in the base
project (a component, one pipe of a connection, or the project itself) and one field the
allow-list names for that target's type. Its value is checked against the target's own field and
validators when the scenario is applied (services/scenarios.py). A scenario overrides each value
at most once, so the order of its overrides does not change the result.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Discriminator, Field, JsonValue, Tag, model_validator
from pydantic.alias_generators import to_camel
from pydantic.config import JsonDict

from .base import CamelModel, Identifier, Name, OutputModel
from .components import (
    AssignedFlow,
    BaseComponent,
    CheckValve,
    ControlValve,
    Equipment,
    IdealReferenceNode,
    IsolationValve,
    Plug,
    Pump,
    PumpControl,
    RatedFlowCoefficient,
    RatedPoint,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from .fluids import BuiltinFluid
from .piping import MAX_PIPES

MAX_SCENARIOS = 20
"""Scenarios per project: 20 of MAX_OVERRIDES fit the 1 MB body limit with the largest project
(proposal §2.5)."""
MAX_OVERRIDES = 30
"""Overrides per scenario (proposal §2.5)."""
MAX_DESCRIPTION = 500
"""Characters of a scenario's description."""

ComponentField = Literal[
    "status",
    "speed",
    "control.setpoint",
    "setpoint",
    "resistance",
    "liquidLevel",
    "surfacePressure",
    "pressure",
    "flow",
    "rating",
    "rating.pressureLoss",
    "rating.flow",
    "rating.density",
    "rating.value",
]
"""Overridable values of components; each component type takes the ones x-override-fields
lists for it."""
PipeField = Literal["spec", "length"]
"""Overridable values of one pipe: its spec (material, schedule, nominal size and the bore and
roughness overrides, replaced together) and its length."""
ProjectField = Literal["fluid", "fluid.temperature"]
"""Overridable values of the project: the whole fluid, or a built-in fluid's temperature."""


# --------------------------------------------------------------------------- the allow-list


@dataclass(frozen=True)
class Overridable:
    """One value a scenario may override on a target type (the allow-list, proposal §2.2)."""

    path: tuple[str, ...]
    """snake_case attributes from the target to the value (empty for a group)."""
    holder: type[BaseModel] | None = None
    """The model that must hold the value's last attribute; None: the target itself. A value
    whose holder is missing in the base project (a fixed-speed pump's control) is not
    applicable."""
    keys: tuple[str, ...] = ()
    """A group: these sibling attributes of the holder are replaced together."""
    unit: str | Callable[[Any], str] = ""
    """Trace unit of the value ('m', 'Pa(g)', 'Pa (difference)', 'm³/s', 'kg/m³', 'K', '' for
    none; never a bare 'Pa', SDD §4.10), or a function of the target giving it."""
    label: str | Callable[[Any], str] = ""
    """Name of the value in notes and the methods summary, or a function of the target (None
    where there is none: an orphaned override) giving it."""


def _setpoint_unit(valve: Any) -> str:
    """A control valve's setpoint is a flow (FCV) or a gauge pressure (PRV, PSV)."""
    return "m³/s" if getattr(valve, "valve_type", None) == "fcv" else "Pa(g)"


def _speed_label(pump: Any) -> str:
    """A speed-controlled pump's speed is its maximum speed (D11), as its trace input says."""
    return "maximum speed ratio" if getattr(pump, "control", None) is not None else "speed ratio"


def _coefficient_label(equipment: Any) -> str:
    """An equipment item's rating.value is its Cv or Kv, by the kind its rating holds; with no
    target, or a target rated by a point, the plain name."""
    kind = getattr(getattr(equipment, "rating", None), "kind", None)
    return kind if kind in ("Cv", "Kv") else "flow coefficient"


def override_unit(entry: Overridable, target: BaseModel) -> str:
    """The trace unit of ``entry``'s value on ``target``."""
    return entry.unit(target) if callable(entry.unit) else entry.unit


def override_label(entry: Overridable, target: BaseModel | None = None) -> str:
    """The name of ``entry``'s value on ``target`` (None: no target, the plain name)."""
    return entry.label(target) if callable(entry.label) else entry.label


_STATUS = Overridable(("status",), label="status")
_RESISTANCE = Overridable(("resistance",), label="resistance")

COMPONENT_FIELDS: dict[type[BaseComponent], dict[str, Overridable]] = {
    Reservoir: {
        "liquidLevel": Overridable(("liquid_level",), unit="m", label="liquid level"),
        "surfacePressure": Overridable(
            ("surface_pressure",), unit="Pa(g)", label="surface pressure"
        ),
    },
    IdealReferenceNode: {"pressure": Overridable(("pressure",), unit="Pa(g)", label="pressure")},
    Plug: {},
    AssignedFlow: {"flow": Overridable(("flow",), unit="m³/s", label="assigned flow")},
    TeeBranch: {},
    WyeBranch: {},
    Pump: {
        "status": _STATUS,
        "speed": Overridable(("speed",), label=_speed_label),
        "control.setpoint": Overridable(
            ("control", "setpoint"), holder=PumpControl, unit="m³/s", label="flow setpoint"
        ),
    },
    IsolationValve: {"status": _STATUS, "resistance": _RESISTANCE},
    CheckValve: {"status": _STATUS, "resistance": _RESISTANCE},
    ControlValve: {
        "status": _STATUS,
        "resistance": _RESISTANCE,
        "setpoint": Overridable(("setpoint",), unit=_setpoint_unit, label="setpoint"),
    },
    Equipment: {
        # The whole rating (another datasheet, of either kind), as "fluid" is the whole fluid,
        # and each of its values, held by the rating of its kind (a part the base element's
        # kind does not hold is not applicable).
        "rating": Overridable(("rating",), label="rating"),
        "rating.pressureLoss": Overridable(
            ("rating", "pressure_loss"),
            holder=RatedPoint,
            unit="Pa (difference)",
            label="rated pressure drop",
        ),
        "rating.flow": Overridable(
            ("rating", "flow"), holder=RatedPoint, unit="m³/s", label="rated flow"
        ),
        "rating.density": Overridable(
            ("rating", "density"), holder=RatedPoint, unit="kg/m³", label="rated fluid density"
        ),
        "rating.value": Overridable(
            ("rating", "value"), holder=RatedFlowCoefficient, label=_coefficient_label
        ),
    },
}
"""Overridable values by component type (every type of the Component union; {} for none)."""

PIPE_SPEC_KEYS = ("material_id", "schedule", "nominal_size", "inner_diameter", "roughness")
"""A pipe's spec: written as one value, so a scenario's pipe stays self-consistent (a material
change rewrites the schedule and size and drops the bore and roughness overrides)."""

PIPE_FIELDS: dict[str, Overridable] = {
    "spec": Overridable((), keys=PIPE_SPEC_KEYS, label="spec"),
    "length": Overridable(("length",), unit="m", label="length"),
}
"""Overridable values of one pipe (PipeDefinition)."""

PROJECT_FIELDS: dict[str, Overridable] = {
    "fluid": Overridable(("fluid",), label="fluid"),
    "fluid.temperature": Overridable(
        ("fluid", "temperature"), holder=BuiltinFluid, unit="K", label="fluid temperature"
    ),
}
"""Overridable values of the project itself (the target; Project is not imported here, which
would be an import cycle)."""


def _published(entry: Overridable, target: str) -> JsonDict:
    schema = entry.holder.__name__ if entry.holder is not None else target
    if entry.keys:
        return {"schema": schema, "keys": [to_camel(k) for k in entry.keys]}
    return {"schema": schema, "path": [to_camel(p) for p in entry.path]}


def override_fields() -> JsonDict:
    """The allow-list as published in x-override-fields: by target schema, each field's holder
    schema and its camelCase path from the target (or the keys of a group)."""
    published: JsonDict = {
        cls.__name__: {name: _published(e, cls.__name__) for name, e in fields.items()}
        for cls, fields in COMPONENT_FIELDS.items()
    }
    published["PipeDefinition"] = {
        name: _published(e, "PipeDefinition") for name, e in PIPE_FIELDS.items()
    }
    published["Project"] = {name: _published(e, "Project") for name, e in PROJECT_FIELDS.items()}
    return published


def _scenario_schema_extra(schema: JsonDict) -> None:
    """Publish the allow-list as ``x-override-fields`` (the frontend's utils/model-rules.ts):
    by target schema (each component schema, PipeDefinition, Project), the fields a scenario
    may override, with the schema that holds each value (its bounds are that schema's
    property) and its camelCase path from the target, or the keys of a group (a pipe's spec)."""
    schema["x-override-fields"] = override_fields()


# --------------------------------------------------------------------------- overrides

_VALUE_DESCRIPTION = (
    "The value, SI, of the target field's own type (checked when the scenario is applied); "
    "the fields each target type takes: x-override-fields"
)


class ComponentOverride(CamelModel):
    """An override of one value of a component."""

    kind: Literal["component"]
    component_id: Identifier
    field: ComponentField = Field(
        description="camelCase path of the value relative to the component"
    )
    value: JsonValue = Field(description=_VALUE_DESCRIPTION)


class PipeOverride(CamelModel):
    """An override of one value of one pipe of a connection."""

    kind: Literal["pipe"]
    connection_id: Identifier
    pipe_index: int = Field(
        ge=0,
        le=MAX_PIPES - 1,
        description=(
            "0-based index into the connection's piping.pipes, as Fitting.pipeIndex (messages "
            "number pipes from 1)"
        ),
    )
    field: PipeField = Field(
        description=(
            "spec: an object with materialId and optionally schedule, nominalSize, "
            "innerDiameter and roughness, which replace all five; length: m"
        )
    )
    value: JsonValue = Field(description=_VALUE_DESCRIPTION)


class ProjectOverride(CamelModel):
    """An override of a project value: the whole fluid, or a built-in fluid's temperature."""

    kind: Literal["project"]
    field: ProjectField = Field(description="camelCase path of the value relative to the project")
    value: JsonValue = Field(description=_VALUE_DESCRIPTION)


def _override_tag(value: object) -> str | None:
    kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return kind if kind in ("component", "pipe", "project") else None


Override = Annotated[
    Annotated[ComponentOverride, Tag("component")]
    | Annotated[PipeOverride, Tag("pipe")]
    | Annotated[ProjectOverride, Tag("project")],
    Discriminator(
        # A callable discriminator, as FluidDefinition's, so that the error never quotes the
        # submitted tag (SDD §5.1.2).
        _override_tag,
        custom_error_type="invalid_override",
        custom_error_message="unknown override kind (expected 'component', 'pipe' or 'project')",
    ),
]


def override_target(
    override: ComponentOverride | PipeOverride | ProjectOverride,
) -> tuple[Any, ...]:
    """The target an override addresses: ('component', id), ('pipe', id, index) or
    ('project',)."""
    if isinstance(override, ComponentOverride):
        return ("component", override.component_id)
    if isinstance(override, PipeOverride):
        return ("pipe", override.connection_id, override.pipe_index)
    return ("project",)


def overlap_problems(
    overrides: Sequence[ComponentOverride | PipeOverride | ProjectOverride],
) -> list[str]:
    """Pairs of overrides that set one value twice, or a value and a part of it (fluid with
    fluid.temperature, a rating with rating.flow), by index only: request-validation errors
    never echo submitted values (SDD §5.1.2)."""
    problems: list[str] = []
    for j, later in enumerate(overrides):
        path_j = later.field.split(".")
        for i in range(j):
            earlier = overrides[i]
            if override_target(earlier) != override_target(later):
                continue
            path_i = earlier.field.split(".")
            if path_i == path_j:
                problems.append(f"overrides {i} and {j} set the same value")
            elif path_i[: len(path_j)] == path_j or path_j[: len(path_i)] == path_i:
                problems.append(
                    f"overrides {i} and {j} set a value and a part of it: set the part in the "
                    "whole value's override"
                )
    return problems


class Scenario(CamelModel):
    """A named case of the project: the base project with these values overridden. It changes
    values only, never components, connections, ports or pipe counts (PRD §3.8)."""

    model_config = ConfigDict(json_schema_extra=_scenario_schema_extra)

    id: Identifier = Field(description="Unique among the project's scenarios (its own namespace)")
    name: Name
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    overrides: list[Override] = Field(
        default_factory=list,
        max_length=MAX_OVERRIDES,
        description=(
            "At most one per value: no two set the same value of one target, nor a value and "
            "a part of it (fluid and fluid.temperature; an equipment item's rating and "
            "rating.flow)"
        ),
    )

    @model_validator(mode="after")
    def _check_overrides(self) -> Self:
        problems = overlap_problems(self.overrides)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def duplicate_scenario_ids(scenarios: Sequence[Scenario]) -> list[str]:
    """Pairs of scenarios with one id, by index only."""
    first: dict[str, int] = {}
    problems: list[str] = []
    for j, scenario in enumerate(scenarios):
        if scenario.id in first:
            problems.append(f"scenarios {first[scenario.id]} and {j} have the same id")
        else:
            first[scenario.id] = j
    return problems


# --------------------------------------------------------------------------- results

OverrideState = Literal["applied", "orphaned", "not_applicable"]


class OverrideResult(OutputModel):
    """How one override of a solved scenario was used."""

    index: int = Field(description="0-based index into the scenario's overrides")
    override: Override = Field(description="The override as given")
    state: OverrideState = Field(
        description=(
            "applied; orphaned: its component, connection or pipe is not in the project; "
            "not applicable: its target has no such value. Orphaned and not-applicable "
            "overrides are kept in the scenario and ignored"
        )
    )
    value: JsonValue = Field(description="The value used, as validated, SI (null unless applied)")
    base_value: JsonValue = Field(
        description=(
            "The base project's value, SI (null unless applied); an unset field gives its default"
        )
    )
    unit: str = Field(description="Trace unit of value and baseValue ('' for none)")
    message: str = Field(description="Why the override was not applied ('' when applied)")


class ScenarioResult(OutputModel):
    """The scenario a result was solved for: every override, with its state, the value used
    and the base value (proposal §3.2)."""

    id: str
    name: str
    description: str | None
    overrides: list[OverrideResult] = Field(description="Every override, in the scenario's order")
