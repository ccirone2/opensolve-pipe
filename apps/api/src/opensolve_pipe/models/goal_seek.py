"""Goal seek: its variables, goals and results (PRD §3.9, CLAUDE.md D16,
docs/proposals/goal-seek.md §2).

A variable is one numeric value of the scenario allow-list (D15), addressed exactly as a scenario
override addresses it (a target and a field), with SI bounds inside the field's own. A goal is one
result of an element, as the web's Compare rows name them, with a target and a tolerance. The
search (``services/goal_seek.py``) solves the case (the base project or a scenario) with the
variables written on top; its result never changes the project: each variable carries the
override that applies the value found.

The variable tables are derived from the allow-list (``models/scenarios.py``): every entry whose
value is a number, plus a valve's resistance through ``FlowCoefficient.value``. Every other entry
is in ``NOT_VARIABLES`` with the reason, and a unit test fails when the allow-list gains a value
that neither names.
"""

import types
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal, Self, Union, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    Tag,
    model_validator,
)
from pydantic.alias_generators import to_camel
from pydantic.config import JsonDict
from scipy import constants

from .base import CamelModel, Identifier, OutputModel
from .components import (
    AssignedFlow,
    BaseComponent,
    CheckValve,
    ControlValve,
    Equipment,
    FlowCoefficient,
    IdealReferenceNode,
    IsolationValve,
    Orifice,
    Pump,
    ReliefValve,
    Reservoir,
)
from .piping import MAX_PIPES, PipeConnection, PipeDefinition
from .project import Project
from .results import MethodsSection
from .scenarios import (
    COMPONENT_FIELDS,
    PIPE_FIELDS,
    PROJECT_FIELDS,
    Overridable,
    Override,
)

MAX_GOAL_VARIABLES = 4
"""Variables per goal seek, and as many goals (PRD §3.9; proposal §1.2 decision 8)."""

VariableComponentField = Literal[
    "speed",
    "control.setpoint",
    "setpoint",
    "resistance",
    "liquidLevel",
    "surfacePressure",
    "pressure",
    "flow",
    "rating.pressureLoss",
    "rating.flow",
    "rating.density",
    "rating.value",
    "boreDiameter",
    "dischargeCoefficient",
    "setPressure",
    "capacity.area",
    "capacity.dischargeCoefficient",
    "capacity.overpressure",
]
"""The numeric overridable values of components (x-goal-variables gives each type's)."""
VariablePipeField = Literal["length"]
VariableProjectField = Literal["fluid.temperature"]
Coefficient = Literal["K", "Cv", "Kv"]
"""A resistance variable's flow coefficient (FlowCoefficient.kind)."""
Scale = Literal["linear", "log"]


# --------------------------------------------------------------------------- variable tables


@dataclass(frozen=True)
class Variable:
    """How goal seek varies one allow-list value."""

    entry: Overridable
    """The allow-list entry (path, holder, unit, label)."""
    number: tuple[str, ...] = ()
    """snake_case attributes from the entry's value to the number: () or ('value',)."""
    schema: type[BaseModel] | None = None
    """The model whose property bounds the number (None: the entry's holder, else the target)."""
    scale: Scale = "linear"
    """The search coordinate: linear in x, or linear in log x (a value > 0 by its field)."""

    def bounding_schema(self, target: type[BaseModel]) -> type[BaseModel]:
        return self.schema or self.entry.holder or target


LOG_FIELDS = frozenset(
    {
        "length",
        "resistance",
        "rating.pressureLoss",
        "rating.flow",
        "rating.value",
        "boreDiameter",
        "capacity.area",
    }
)
"""Values searched in log x: each is > 0 by its field bounds, and spans decades (a K from 0.01
to 10⁵), proposal §1.2 decision 6; an equipment item's rated pressure drop, rated flow and Cv or
Kv likewise (equipment-pressure-drop.md decision 15; its rated density is linear), an orifice
plate's bore (orifice-plate.md decision 21; its discharge coefficient, in (0, 1], is linear) and
a relief valve's orifice area (pressure-relief-valve.md decision 19: API 526's D to T span 2.4
decades; its set pressure, rated coefficient of discharge and overpressure are linear)."""

_NUMBER_IN: dict[type[BaseModel], tuple[str, ...]] = {FlowCoefficient: ("value",)}
"""Values that are a model holding one number: the attributes to it."""


def _without_none(annotation: Any) -> Any:
    if get_origin(annotation) in (Union, types.UnionType):
        members = [a for a in get_args(annotation) if a is not type(None)]
        return members[0] if len(members) == 1 else annotation
    return annotation


def _variable(name: str, entry: Overridable, target: type[BaseModel]) -> Variable | None:
    """The variable of allow-list entry ``name`` on ``target``, or None when its value is not a
    number (a status, a group, a whole fluid)."""
    if entry.keys or not entry.path:
        return None
    holder = entry.holder or target
    annotation = _without_none(holder.model_fields[entry.path[-1]].annotation)
    scale: Scale = "log" if name in LOG_FIELDS else "linear"
    if annotation is float:
        return Variable(entry, scale=scale)
    if isinstance(annotation, type) and annotation in _NUMBER_IN:
        return Variable(entry, number=_NUMBER_IN[annotation], schema=annotation, scale=scale)
    return None


def _variables(fields: dict[str, Overridable], target: type[BaseModel]) -> dict[str, Variable]:
    found = {name: _variable(name, entry, target) for name, entry in fields.items()}
    return {name: v for name, v in found.items() if v is not None}


GOAL_COMPONENT_FIELDS: dict[type[BaseComponent], dict[str, Variable]] = {
    cls: _variables(fields, cls) for cls, fields in COMPONENT_FIELDS.items()
}
"""Variables by component type (every type of the Component union; {} for none)."""
GOAL_PIPE_FIELDS: dict[str, Variable] = _variables(PIPE_FIELDS, PipeDefinition)
"""Variables of one pipe of a connection."""
GOAL_PROJECT_FIELDS: dict[str, Variable] = _variables(PROJECT_FIELDS, Project)
"""Variables of the project itself."""

NOT_VARIABLES: dict[str, str] = {
    "status": "discrete: set it in a scenario and compare cases",
    "spec": "a library choice replaced as a group, not a number",
    "fluid": "a whole definition; vary its temperature",
    "rating": "a whole rating, a rated point or a flow coefficient; vary one of its values",
    "capacity": "a whole relief valve capacity of one kind; vary one of its values",
    "capacity.letter": (
        "a discrete API 526 letter: set it in a scenario, or size the valve by varying an "
        "effective area"
    ),
}
"""Allow-list fields that are not variables, with the reason."""


def _published_variable(variable: Variable, target: type[BaseModel]) -> JsonDict:
    schema = variable.bounding_schema(target)
    item: JsonDict = {
        "schema": schema.__name__,
        "path": [to_camel(p) for p in (*variable.entry.path, *variable.number)],
        "scale": variable.scale,
    }
    if schema is FlowCoefficient:
        item["coefficients"] = list(get_args(Coefficient))
    return item


def goal_variables() -> JsonDict:
    """The variable tables as published in x-goal-variables: by target schema (every component
    schema, PipeDefinition, Project), each variable field's bounding schema, the camelCase path
    from the target to the number, its scale and, for a resistance, its coefficients."""
    published: JsonDict = {
        cls.__name__: {name: _published_variable(v, cls) for name, v in fields.items()}
        for cls, fields in GOAL_COMPONENT_FIELDS.items()
    }
    published["PipeDefinition"] = {
        name: _published_variable(v, PipeDefinition) for name, v in GOAL_PIPE_FIELDS.items()
    }
    published["Project"] = {
        name: _published_variable(v, Project) for name, v in GOAL_PROJECT_FIELDS.items()
    }
    return published


# --------------------------------------------------------------------------- variables


def _bounds_schema_extra(schema: JsonDict, cls: type[Any]) -> None:
    """``x-ordered-fields`` (the components' extension, models/components.py): lower < upper."""
    ordered: tuple[tuple[str, str], ...] = getattr(cls, "ORDERED_FIELDS", ())
    if ordered:
        schema["x-ordered-fields"] = [
            {"lower": lower, "upper": upper, "strict": True} for lower, upper in ordered
        ]


class _Bounds(CamelModel):
    model_config = ConfigDict(json_schema_extra=_bounds_schema_extra)

    ORDERED_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (("lower", "upper"),)
    """lower < upper (published as x-ordered-fields)."""

    lower: float = Field(
        allow_inf_nan=False,
        description=(
            "SI, within the field's own bounds (x-goal-variables gives the schema that bounds "
            "it); below upper"
        ),
    )
    upper: float = Field(allow_inf_nan=False, description="SI, within the field's own bounds")

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if not self.lower < self.upper:
            raise ValueError("lower must be below upper")
        return self


class ComponentVariable(_Bounds):
    """A numeric value of a component, varied between lower and upper."""

    kind: Literal["component"]
    component_id: Identifier
    field: VariableComponentField = Field(
        description="camelCase path of the value relative to the component (x-goal-variables)"
    )
    coefficient: Coefficient | None = Field(
        default=None,
        description=(
            "resistance only (required there): the flow coefficient varied, written as "
            "resistance = {kind: coefficient, value}"
        ),
    )

    @model_validator(mode="after")
    def _check_coefficient(self) -> Self:
        if self.field == "resistance" and self.coefficient is None:
            raise ValueError("resistance needs a coefficient")
        if self.field != "resistance" and self.coefficient is not None:
            raise ValueError("coefficient applies to resistance only")
        return self


class PipeVariable(_Bounds):
    """A numeric value of one pipe of a connection, varied between lower and upper."""

    kind: Literal["pipe"]
    connection_id: Identifier
    pipe_index: int = Field(
        ge=0,
        le=MAX_PIPES - 1,
        description="0-based index into the connection's piping.pipes, as a pipe override's",
    )
    field: VariablePipeField = Field(description="length: m")


class ProjectVariable(_Bounds):
    """A numeric value of the project (a built-in fluid's temperature), varied between lower
    and upper."""

    kind: Literal["project"]
    field: VariableProjectField = Field(description="fluid.temperature: K, a built-in fluid's")


AnyVariable = ComponentVariable | PipeVariable | ProjectVariable


def _variable_tag(value: object) -> str | None:
    kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return kind if kind in ("component", "pipe", "project") else None


GoalVariable = Annotated[
    Annotated[ComponentVariable, Tag("component")]
    | Annotated[PipeVariable, Tag("pipe")]
    | Annotated[ProjectVariable, Tag("project")],
    Discriminator(
        # A callable discriminator, as Override's, so that the error never quotes the
        # submitted tag (SDD §5.1.2).
        _variable_tag,
        custom_error_type="invalid_variable",
        custom_error_message="unknown variable kind (expected 'component', 'pipe' or 'project')",
    ),
]


# --------------------------------------------------------------------------- goals

GoalQuantity = Literal[
    "port_pressure",
    "link_flow",
    "link_velocity",
    "link_head_loss",
    "pump_flow",
    "pump_head",
    "pump_npsh_available",
    "pump_npsh_margin",
    "valve_flow",
    "valve_pressure_drop",
    "equipment_flow",
    "equipment_pressure_loss",
    "equipment_pressure_drop",
    "orifice_flow",
    "orifice_pressure_loss",
    "orifice_differential_pressure",
    "orifice_pressure_drop",
    "relief_valve_flow",
    "relief_valve_pressure_drop",
    "boundary_outflow",
]
Category = Literal["pressure", "head", "flow", "velocity"]
ElementKind = Literal[
    "port", "connection", "pump", "valve", "equipment", "orifice", "relief_valve", "boundary"
]

RELATIVE_TOLERANCE = 0.005
"""The default tolerance's relative part, D6's 0.5 %."""
HEAD_FLOOR = 0.01
"""m: the default tolerance's floor for heads, D6's 0.01 m (pressures: ρg × 0.01 m)."""
FLOW_FLOOR = 1.0e-6
"""m³/s: the default tolerance's floor for flows, a designers' default (D16, not in D6); also
the flow below which an element carries no flow for state changes (services/goal_seek.py)."""
VELOCITY_FLOOR = 1.0e-3
"""m/s: the default tolerance's floor for velocity, a designers' default (D16, not in D6)."""
MIN_TOLERANCE_RELATIVE = 1.0e-6
"""The smallest user tolerance, relative to the target's magnitude."""
MIN_TOLERANCE: dict[Category, float] = {
    "pressure": 0.1,
    "head": 1.0e-5,
    "flow": 1.0e-9,
    "velocity": 1.0e-6,
}
"""The smallest user tolerance by category, SI: a thousandth of each floor (with ρg taken as
10⁴ N/m³ for pressures, so that it never depends on the fluid)."""

_FLOORS: dict[Category, tuple[str, float]] = {
    "pressure": ("head", HEAD_FLOOR),
    "head": ("head", HEAD_FLOOR),
    "flow": ("flow", FLOW_FLOOR),
    "velocity": ("velocity", VELOCITY_FLOOR),
}
"""Each category's default-tolerance floor: in head (m; a pressure's through ρg), flow (m³/s)
or velocity (m/s)."""

STANDARD_GRAVITY = float(constants.g)
"""m/s², the solver's g (fluids.constants.g, the same CODATA value)."""

_VALVES: tuple[type[BaseComponent], ...] = (IsolationValve, CheckValve, ControlValve)


@dataclass(frozen=True)
class QuantitySpec:
    """One goal quantity: what it reads and where (proposal §2.2)."""

    unit: str
    category: Category
    element: ElementKind
    targets: tuple[type[BaseModel], ...]
    label: str
    """'{element}' is the element ('pump P1'), '{port}' the port id."""
    needs: tuple[str, ...] = ()
    """What the case must have: 'vaporPressure' (the fluid's), 'npshrCurve' (the pump's), 'taps'
    (the orifice plate's: a reading needs pressure taps)."""


GOAL_QUANTITIES: dict[str, QuantitySpec] = {
    "port_pressure": QuantitySpec(
        "Pa(g)",
        "pressure",
        "port",
        tuple(COMPONENT_FIELDS),
        "static pressure at port {port} of {element}",
    ),
    "link_flow": QuantitySpec(
        "m³/s", "flow", "connection", (PipeConnection,), "flow in connection {element}"
    ),
    "link_velocity": QuantitySpec(
        "m/s",
        "velocity",
        "connection",
        (PipeConnection,),
        "largest velocity in connection {element}",
    ),
    "link_head_loss": QuantitySpec(
        "m", "head", "connection", (PipeConnection,), "head loss in connection {element}"
    ),
    "pump_flow": QuantitySpec("m³/s", "flow", "pump", (Pump,), "flow through {element}"),
    "pump_head": QuantitySpec("m", "head", "pump", (Pump,), "head of {element}"),
    "pump_npsh_available": QuantitySpec(
        "m", "head", "pump", (Pump,), "NPSH available at {element}", ("vaporPressure",)
    ),
    "pump_npsh_margin": QuantitySpec(
        "m",
        "head",
        "pump",
        (Pump,),
        "NPSH margin of {element}",
        ("vaporPressure", "npshrCurve"),
    ),
    "valve_flow": QuantitySpec("m³/s", "flow", "valve", _VALVES, "flow through {element}"),
    "valve_pressure_drop": QuantitySpec(
        "Pa (difference)", "pressure", "valve", _VALVES, "pressure drop across {element}"
    ),
    "equipment_flow": QuantitySpec(
        "m³/s", "flow", "equipment", (Equipment,), "flow through {element}"
    ),
    "equipment_pressure_loss": QuantitySpec(
        "Pa (difference)",
        "pressure",
        "equipment",
        (Equipment,),
        "pressure loss across {element}",
    ),
    "equipment_pressure_drop": QuantitySpec(
        "Pa (difference)",
        "pressure",
        "equipment",
        (Equipment,),
        "static pressure drop across {element}",
    ),
    "orifice_flow": QuantitySpec("m³/s", "flow", "orifice", (Orifice,), "flow through {element}"),
    "orifice_pressure_loss": QuantitySpec(
        "Pa (difference)",
        "pressure",
        "orifice",
        (Orifice,),
        "permanent pressure loss across {element}",
    ),
    "orifice_differential_pressure": QuantitySpec(
        "Pa (difference)",
        "pressure",
        "orifice",
        (Orifice,),
        "differential pressure at the taps of {element}",
        ("taps",),
    ),
    "orifice_pressure_drop": QuantitySpec(
        "Pa (difference)",
        "pressure",
        "orifice",
        (Orifice,),
        "static pressure drop across {element}",
    ),
    "relief_valve_flow": QuantitySpec(
        "m³/s", "flow", "relief_valve", (ReliefValve,), "flow through {element}"
    ),
    "relief_valve_pressure_drop": QuantitySpec(
        "Pa (difference)",
        "pressure",
        "relief_valve",
        (ReliefValve,),
        "static pressure drop across {element}",
    ),
    "boundary_outflow": QuantitySpec(
        "m³/s", "flow", "boundary", (Reservoir, IdealReferenceNode), "outflow of {element}"
    ),
}
"""Every goal quantity (the Literal's names, in its order)."""

NOT_GOALS: dict[str, dict[type[BaseComponent], str]] = {
    "boundary_outflow": {
        AssignedFlow: "an assigned-flow node's outflow is its input (−flow): vary it instead",
    },
}
"""Components a quantity does not take for a reason of their own, with it (a plug's outflow is
always 0: it takes the plain wrong-element message)."""


def tolerance_floor(quantity: str, density: float) -> float:
    """The default tolerance's floor, SI: a head floor converted with ρg for a pressure."""
    category = GOAL_QUANTITIES[quantity].category
    _, floor = _FLOORS[category]
    return floor * density * STANDARD_GRAVITY if category == "pressure" else floor


def default_tolerance(quantity: str, target: float, density: float) -> float:
    """max(0.5 % × |target|, the quantity's floor), SI (ρ: the case fluid's density)."""
    return max(RELATIVE_TOLERANCE * abs(target), tolerance_floor(quantity, density))


def minimum_tolerance(quantity: str, target: float) -> float:
    """The smallest user tolerance: max(10⁻⁶ × |target|, the quantity's fixed minimum)."""
    category = GOAL_QUANTITIES[quantity].category
    return max(MIN_TOLERANCE_RELATIVE * abs(target), MIN_TOLERANCE[category])


def goal_quantities() -> JsonDict:
    """The quantities as published in x-goal-quantities: by quantity, its unit, the schemas
    its elementId may name, whether it takes a port, the default tolerance (relative part and
    floor: a head floor applies to a pressure through ρg of the case fluid), the smallest user
    tolerance (relative part and an absolute minimum in the quantity's unit, independent of
    the fluid) and what the case needs for it."""
    published: JsonDict = {}
    for name, spec in GOAL_QUANTITIES.items():
        kind, floor = _FLOORS[spec.category]
        published[name] = {
            "unit": spec.unit,
            "targets": [cls.__name__ for cls in spec.targets],
            "port": spec.element == "port",
            "relativeTolerance": RELATIVE_TOLERANCE,
            "floor": {kind: floor},
            "minimum": {
                "relative": MIN_TOLERANCE_RELATIVE,
                "absolute": MIN_TOLERANCE[spec.category],
            },
            "needs": list(spec.needs),
        }
    return published


class Goal(CamelModel):
    """A result of one element brought to a target."""

    quantity: GoalQuantity
    element_id: Identifier = Field(
        description="The component or connection (x-goal-quantities gives each quantity's)"
    )
    port_id: Identifier | None = Field(
        default=None, description="port_pressure only (required there): the component's port"
    )
    target: float = Field(
        ge=-1.0e8, le=1.0e8, allow_inf_nan=False, description="SI, in the quantity's unit"
    )
    tolerance: float | None = Field(
        default=None,
        gt=0,
        le=1.0e8,
        allow_inf_nan=False,
        description=(
            "SI, in the quantity's unit; omitted: max(0.5 % of |target|, the quantity's floor); "
            "at least max(1e-6 |target|, the quantity's minimum in x-goal-quantities)"
        ),
    )

    @model_validator(mode="after")
    def _check_port(self) -> Self:
        if self.quantity == "port_pressure" and self.port_id is None:
            raise ValueError("port_pressure needs portId")
        if self.quantity != "port_pressure" and self.port_id is not None:
            raise ValueError("portId applies to port_pressure only")
        return self


# --------------------------------------------------------------------------- request rules

UNIQUE_BY: dict[str, tuple[str, ...]] = {
    "variables": ("kind", "componentId", "connectionId", "pipeIndex", "field"),
    "goals": ("quantity", "elementId", "portId"),
}
"""Items of each list must differ on these keys (camelCase; an absent key counts as null):
two variables never vary one value, two goals never read one result."""
SAME_LENGTH: tuple[tuple[str, str], ...] = (("variables", "goals"),)
"""Lists of equal length: as many goals as variables (PRD §3.9)."""


def _key(item: BaseModel, keys: tuple[str, ...]) -> tuple[Any, ...]:
    dumped = item.model_dump(mode="json", by_alias=True)
    return tuple(dumped.get(k) for k in keys)


def list_problems(variables: Sequence[BaseModel], goals: Sequence[BaseModel]) -> list[str]:
    """The request's list rules (x-goal-seek-rules), by index only: request-validation errors
    never echo submitted values (SDD §5.1.2)."""
    problems: list[str] = []
    if len(variables) != len(goals):
        problems.append("as many goals as variables (PRD §3.9)")
    for name, items, what in (
        ("variables", variables, "vary the same value"),
        ("goals", goals, "read the same result"),
    ):
        first: dict[tuple[Any, ...], int] = {}
        for j, item in enumerate(items):
            key = _key(item, UNIQUE_BY[name])
            if key in first:
                problems.append(f"{name} {first[key]} and {j} {what}")
            else:
                first[key] = j
    return problems


def goal_seek_schema_extra(schema: JsonDict) -> None:
    """Publish on GoalSeekRequest (the frontend's utils/model-rules.ts): ``x-goal-variables``
    (the variable tables), ``x-goal-quantities`` (the goal quantities and their tolerance
    rules) and ``x-goal-seek-rules`` (the request validator's list rules)."""
    schema["x-goal-variables"] = goal_variables()
    schema["x-goal-quantities"] = goal_quantities()
    schema["x-goal-seek-rules"] = {
        "sameLength": [list(pair) for pair in SAME_LENGTH],
        "uniqueBy": {name: list(keys) for name, keys in UNIQUE_BY.items()},
    }


# --------------------------------------------------------------------------- results

GoalSeekStop = Literal[
    "met_at_start",
    "met",
    "not_reachable",
    "jump",
    "unsolved_crossing",
    "no_progress",
    "evaluation_limit",
    "time_budget",
    "no_usable_evaluation",
]
Purpose = Literal["start", "scan", "root", "probe", "minimize", "step", "slope"]
Outcome = Literal[
    "usable", "not_converged", "no_value", "topology_error", "fluid_error", "not_computed"
]
NoteCode = Literal[
    "other_crossing",
    "met_range",
    "met_without_crossing",
    "closest_at_bound",
    "closest_on_plateau",
    "closest_inside",
    "jump",
    "unsolved_crossing",
    "state_changes",
    "start_clipped",
    "unusable_evaluations",
    "goal_no_effect",
    "variable_no_effect",
    "variables_collinear",
    "slope_unknown",
    "sensitive",
]
StateAspect = Literal["pump_status", "pump_control", "valve_state", "branch_pattern"]


class StateChange(OutputModel):
    """An element whose state differs between two evaluations (one that carries flow in at
    least one of them, D13)."""

    element_id: str
    aspect: StateAspect
    before: str | None = Field(description="null: the element has no result in that state")
    after: str | None


class GoalSeekEvaluation(OutputModel):
    """One evaluation: a full network solve of the case with the variables at these values."""

    index: int = Field(description="0-based; 0 is the start")
    purpose: Purpose = Field(
        description=(
            "start; scan (one variable: the 9 values across the bounds; several: the values "
            "solved for a usable point when the start has no usable result); root (Brent's "
            "method); probe (around failed solves); minimize (the closest value); step (least "
            "squares); slope (a Jacobian column)"
        )
    )
    variable_values: list[float] = Field(description="SI, in the variables' order")
    outcome: Outcome = Field(
        description=(
            "usable; not_converged; no_value (a goal has no value in this state); "
            "topology_error / fluid_error (the network rejects these values); not_computed "
            "(the request's time budget ran out during it)"
        )
    )
    goal_values: list[float | None] = Field(description="SI; null where the state has no value")
    residuals: list[float | None] = Field(description="Goal value minus target, SI")
    message: str = Field(description="Why it is not usable ('' when usable)")
    seconds: float = Field(description="Inside the worker")
    state_changes: list[StateChange] = Field(
        description="Against the first evaluation with a solved state, elements with flow only"
    )


class VariableResult(OutputModel):
    index: int
    variable: GoalVariable = Field(description="As given")
    label: str = Field(description="'maximum speed ratio of pump P1'")
    unit: str = Field(description="Trace unit ('' for none)")
    scale: Scale
    start: float = Field(description="SI: the value evaluation 0 solved")
    start_source: Literal["case", "clipped", "middle"] = Field(
        description=(
            "case: the case's value; clipped: the case's value lies outside the bounds, and the "
            "nearer bound is used; middle: the case holds no value of this coefficient (a "
            "resistance on its default, or of another kind; an orifice plate's discharge "
            "coefficient on ISO 5167-2's default; a certified relief valve's overpressure on "
            "ASME's default), and the middle of the bounds on the variable's scale is used"
        )
    )
    case_value: JsonValue = Field(
        description=(
            "The case's value of the field, SI (a resistance: its FlowCoefficient or null; an "
            "orifice plate's discharge coefficient: null on ISO 5167-2's default; a relief "
            "valve's overpressure: null on ASME's default)"
        )
    )
    base_value: JsonValue = Field(
        description=(
            "The base project's value (equal to caseValue for a base run); null where the base "
            "holds no value of this variable (an equipment item the base rates by another kind: "
            "a point, or the other of Cv and Kv; an orifice plate's discharge coefficient on "
            "ISO 5167-2's default; a relief valve whose base capacity is of another kind, an "
            "effective area not being an actual area, or whose overpressure is ASME's default)"
        )
    )
    value: float | None = Field(description="At the reported evaluation (null: none usable)")
    at_bound: Literal["lower", "upper"] | None = Field(
        description="The value equals lower or upper exactly"
    )
    override: Override | None = Field(
        description=(
            "The scenario override that sets the value found: upserted into a scenario by "
            "target and field, or written into the base at its path, it reproduces solvedState; "
            "null when value is null"
        )
    )
    replaced_override: int | None = Field(
        description=(
            "Scenario run: the index in the scenario's overrides whose value this variable took "
            "the place of (a whole-fluid override: its temperature), or null; the response's "
            "scenario record states that override's value, which the reported solve did not use"
        )
    )


class GoalResult(OutputModel):
    index: int
    goal: Goal = Field(description="As given")
    label: str = Field(description="'static pressure at port outlet of tee T3'")
    unit: str = Field(description="'Pa(g)', 'Pa (difference)', 'm³/s', 'm/s' or 'm'")
    tolerance: float = Field(description="SI, as used")
    tolerance_source: Literal["user", "default"]
    value: float | None = Field(description="At the reported evaluation, SI")
    residual: float | None = Field(description="value - target, SI")
    met: bool = Field(description="|residual| <= tolerance")
    message: str = Field(description="Why there is no value ('' otherwise)")
    evaluated_min: float | None = Field(description="Over the usable evaluations, SI")
    evaluated_max: float | None


class GoalSeekNote(OutputModel):
    """Something the search found or did, with its data (SI) and a sentence."""

    code: NoteCode
    message: str = Field(description="SI sentence (the web words the code itself)")
    variables: list[int] = Field(description="Indexes into variables")
    goals: list[int] = Field(description="Indexes into goals")
    evaluations: list[int] = Field(description="Indexes into evaluations")
    variable_values: list[float] = Field(description="SI")
    goal_values: list[float] = Field(description="SI")
    state_changes: list[StateChange]


class GoalSeekResult(OutputModel):
    met: bool = Field(description="Every goal met at the reported evaluation")
    stop_reason: GoalSeekStop
    message: str = Field(description="Why the search stopped, SI")
    method: Literal["scan_brent", "least_squares"]
    method_version: str = Field(description="The solves' METHOD_VERSION")
    evaluation_limit: int = Field(description="60 for one variable, 20(n + 1) for n")
    time_budget: float = Field(description="s: the request's")
    reported_evaluation: int | None = Field(
        description="The evaluation whose values and state are reported (null: none usable)"
    )
    variables: list[VariableResult]
    goals: list[GoalResult]
    evaluations: list[GoalSeekEvaluation]
    notes: list[GoalSeekNote]
    methods: MethodsSection = Field(
        description="The 'Goal seek' methods section, also first in solvedState's methods"
    )
