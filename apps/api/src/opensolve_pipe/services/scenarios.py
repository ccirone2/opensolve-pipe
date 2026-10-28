"""Scenarios (PRD §3.8, TSD §5.7, docs/proposals/scenario-manager.md §4-§5): apply one to the
base project, solve it, and say so in the results.

The solver never sees a scenario. ``apply_scenario`` builds the effective project as JSON: the
base project dumped with its set fields only, each override's value written at its target, and
``scenarios`` dropped; then the models validate it. So it equals the project a user would get by
editing the JSON by hand, fields_set included (trace sources depend on them), every model rule
checks the scenario's values, and its solve is that project's solve bit for bit. ``annotate``
then adds the scenario's text to the solved state, in one place: a first "Scenario" methods
section and one first note in the trace of each overridden element. Nothing under
``services/solver`` changes, and a request without a scenario takes today's call.
"""

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, JsonValue, ValidationError
from pydantic.alias_generators import to_camel
from pydantic_core import ErrorDetails

from ..models.api import SolveOptions, TopologyIssue
from ..models.components import (
    AssignedFlow,
    BaseComponent,
    CheckValve,
    ControlValve,
    Equipment,
    IdealReferenceNode,
    IsolationValve,
    Orifice,
    Plug,
    Pump,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from ..models.project import Project
from ..models.project_library import PipeSpec
from ..models.results import MethodsSection, SolvedState
from ..models.scenarios import (
    COMPONENT_FIELDS,
    MAX_OVERRIDES,
    PIPE_FIELDS,
    PROJECT_FIELDS,
    ComponentOverride,
    Overridable,
    OverrideResult,
    OverrideState,
    PipeOverride,
    ProjectOverride,
    Scenario,
    ScenarioResult,
    override_label,
    override_unit,
)
from .fluids import FluidError
from .solver import TopologyError, solve_project, system_curve
from .solver.labels import pipe_name
from .solver.project_library import resistance_label, spec_label
from .solver.system_curve import SystemCurve

SCENARIO_DECISION = (
    "OpenSolve Pipe design decision D15 (CLAUDE.md), from docs/proposals/scenario-manager.md."
)

COMPONENT_NAMES: dict[type[BaseComponent], str] = {
    Reservoir: "reservoir",
    IdealReferenceNode: "reference node",
    Plug: "plug",
    AssignedFlow: "assigned-flow node",
    TeeBranch: "tee",
    WyeBranch: "wye",
    Pump: "pump",
    IsolationValve: "isolation valve",
    CheckValve: "check valve",
    ControlValve: "control valve",
    Equipment: "equipment",
    Orifice: "orifice",
}
"""How messages name a component of each type."""

FIELD_LABELS = {
    name: override_label(entry)
    for fields in COMPONENT_FIELDS.values()
    for name, entry in fields.items()
}
"""The label of each component field, for a target that is gone or does not have it."""

MISSING_HOLDER = {
    "control.setpoint": (
        "pump {id} has no speed control in the base project (control.setpoint applies to a "
        "speed-controlled pump)"
    ),
    "fluid.temperature": (
        "the fluid is a custom fluid, whose properties do not depend on its temperature (set "
        "the whole fluid instead)"
    ),
    **{
        field: (
            "equipment {id} is rated by a Cv or Kv in the base project "  # {id}: .format below
            f"({field} applies to a rated point; set the whole rating instead)"
        )
        for field in ("rating.pressureLoss", "rating.flow", "rating.density")
    },
    "rating.value": (
        "equipment {id} is rated by a pressure drop at a flow in the base project (rating.value "
        "applies to a Cv or Kv rating; set the whole rating instead)"
    ),
}
"""Why a value whose holder the base project lacks does not apply (an equipment item's rating
holds the values of its own kind only: proposal equipment-pressure-drop.md §5.1)."""

AnyOverride = ComponentOverride | PipeOverride | ProjectOverride
Location = tuple[str | int, ...]


class ScenarioNotFoundError(LookupError):
    """The project has no scenario with the requested id (HTTP 404, NOT_FOUND)."""


class ScenarioOverrideError(ValueError):
    """Override values that their targets reject (HTTP 400, VALIDATION_ERROR). ``issues`` lists
    every problem, located by scenario and override index; no message quotes a value."""

    def __init__(self, scenario_id: str, issues: list[TopologyIssue]) -> None:
        self.scenario_id = scenario_id
        self.issues = issues
        super().__init__(f"scenario {scenario_id}: {len(issues)} invalid override value(s)")


class ScenarioTopologyError(TopologyError):
    """The effective project of a scenario has topology issues (HTTP 422): exactly the issues
    of the same project edited by hand."""

    def __init__(self, issues: list[TopologyIssue], scenario_id: str) -> None:
        super().__init__(issues)
        self.scenario_id = scenario_id


class ScenarioFluidError(FluidError):
    """The effective fluid of a scenario is outside the property source's range (HTTP 400)."""

    def __init__(self, scenario_id: str, error: FluidError) -> None:
        super().__init__(f"Scenario {scenario_id}: {error}")
        self.scenario_id = scenario_id


@dataclass(frozen=True)
class AppliedOverride:
    """How one override was used (``OverrideResult`` is its API form)."""

    index: int
    override: AnyOverride
    state: OverrideState
    value: JsonValue
    """The value used, as validated, SI (None unless applied)."""
    base_value: JsonValue
    """The base project's value, SI (None unless applied); an unset field gives its default."""
    unit: str
    message: str
    """Why it was not applied ('' when applied)."""
    target_label: str
    """'component P2 (pump)', 'connection L3, pipe 1', 'the fluid'."""
    label: str
    """'status', 'spec', 'fluid temperature', ..."""
    location: Location
    """Where the value was written in the project JSON (its holder for a group)."""
    element_id: str | None
    """The component or connection whose trace notes the change (None for the fluid)."""
    pipe_index: int | None


@dataclass(frozen=True)
class AppliedScenario:
    """A scenario applied to its project: ``project`` is the effective project (plain: no
    scenarios), ``index`` the scenario's index in the base project's scenarios."""

    scenario: Scenario
    index: int
    project: Project
    overrides: list[AppliedOverride]

    def result(self) -> ScenarioResult:
        """The record of the scenario solved, for the response."""
        return ScenarioResult(
            id=self.scenario.id,
            name=self.scenario.name,
            description=self.scenario.description,
            overrides=[
                OverrideResult(
                    index=o.index,
                    override=o.override,
                    state=o.state,
                    value=o.value,
                    base_value=o.base_value,
                    unit=o.unit,
                    message=o.message,
                )
                for o in self.overrides
            ],
        )


# --------------------------------------------------------------------------- applying


@dataclass(frozen=True)
class OverridePlan:
    """One override resolved against the base project, before it is written."""

    index: int
    override: AnyOverride
    state: OverrideState
    message: str
    target_label: str
    label: str
    target: BaseModel | None
    """The base model the override addresses (a component, a pipe or the project)."""
    entry: Overridable | None
    location: Location
    """The target's location in the project JSON."""
    element_id: str | None
    pipe_index: int | None
    component_ids: list[str]
    connection_ids: list[str]

    def value_locations(self) -> list[Location]:
        """The locations this override writes: its value's, or each key's of a group."""
        assert self.entry is not None
        if self.entry.keys:
            return [(*self.location, to_camel(k)) for k in self.entry.keys]
        return [self.location + tuple(to_camel(p) for p in self.entry.path)]


def _walk(model: BaseModel, path: tuple[str, ...]) -> Any:
    value: Any = model
    for attr in path:
        value = getattr(value, attr, None)
    return value


def plan_override(project: Project, j: int, override: AnyOverride) -> OverridePlan:
    """Resolve the target, the allow-list entry and the holder of override ``j`` (proposal §4.1
    step 3; goal seek plans its variables with it, docs/proposals/goal-seek.md §4.4)."""
    ids: dict[str, list[str]] = {"component_ids": [], "connection_ids": []}

    def ignored(state: OverrideState, message: str, target_label: str, label: str) -> OverridePlan:
        return OverridePlan(
            j, override, state, message, target_label, label, None, None, (), None, None, **ids
        )

    target: BaseModel
    location: Location
    element_id: str | None = None
    pipe_index: int | None = None
    if isinstance(override, ComponentOverride):
        cid = override.component_id
        found = [(i, c) for i, c in enumerate(project.components) if c.id == cid]
        label = FIELD_LABELS.get(override.field, override.field)
        if not found:
            return ignored(
                "orphaned", f"the project has no component {cid}", f"component {cid}", label
            )
        ci, component = found[0]
        kind = COMPONENT_NAMES[type(component)]
        ids["component_ids"] = [cid]
        target_label = f"component {cid} ({kind})"
        entry = COMPONENT_FIELDS[type(component)].get(override.field)
        if entry is None:
            message = f"{kind} {cid} has no {label} to override"
            return ignored("not_applicable", message, target_label, label)
        target, location, element_id = component, ("components", ci), cid
    elif isinstance(override, PipeOverride):
        cid, pipe_index = override.connection_id, override.pipe_index
        found_conn = [(i, c) for i, c in enumerate(project.connections) if c.id == cid]
        entry = PIPE_FIELDS[override.field]
        target_label = f"connection {cid}, {pipe_name(pipe_index)}"
        if not found_conn:
            return ignored(
                "orphaned",
                f"the project has no connection {cid}",
                target_label,
                override_label(entry),
            )
        k, conn = found_conn[0]
        ids["connection_ids"] = [cid]
        pipes = conn.piping.pipes
        if pipe_index >= len(pipes):
            count = f"{len(pipes)} pipe" + ("" if len(pipes) == 1 else "s")
            message = f"connection {cid} has {count}, no {pipe_name(pipe_index)}"
            return ignored("orphaned", message, target_label, override_label(entry))
        target, location, element_id = (
            pipes[pipe_index],
            ("connections", k, "piping", "pipes", pipe_index),
            cid,
        )
    else:
        entry = PROJECT_FIELDS[override.field]
        target, location, target_label = project, (), "the fluid"
    holder = _walk(target, entry.path[:-1]) if entry.path else target
    expected = entry.holder or type(target)
    if not isinstance(holder, expected):
        message = MISSING_HOLDER[override.field].format(id=getattr(target, "id", ""))
        return ignored("not_applicable", message, target_label, override_label(entry, target))
    return OverridePlan(
        j,
        override,
        "applied",
        "",
        target_label,
        override_label(entry, target),
        target,
        entry,
        location,
        element_id,
        pipe_index,
        **ids,
    )


def _at(data: Any, location: Location) -> Any:
    for key in location:
        data = data[key]
    return data


def _spec_is_valid(value: JsonValue, keys: tuple[str, ...]) -> bool:
    allowed = {to_camel(k) for k in keys}
    return isinstance(value, dict) and set(value) <= allowed


def write_override(data: dict[str, Any], plan: OverridePlan) -> None:
    """Write the override's raw value at its location in ``data`` (a group replaces all its
    keys: a spec without innerDiameter drops the base's bore override)."""
    assert plan.entry is not None
    value = copy.deepcopy(plan.override.value)
    if plan.entry.keys:
        holder = _at(data, plan.location)
        for key in plan.entry.keys:
            holder.pop(to_camel(key), None)
        assert isinstance(value, dict)
        holder.update(value)
        return
    *parents, leaf = (to_camel(p) for p in plan.entry.path)
    _at(data, plan.location + tuple(parents))[leaf] = value


RATING_TAGS = ("point", "coefficient")
"""The tags of an equipment rating's union (models/components.py ``_rating_tag``)."""
RESISTANCE_TAGS = ("coefficient", "library")
"""The tags of a valve resistance's union (models/components.py ``_resistance_tag``)."""


def _clean(loc: tuple[str | int, ...]) -> Location:
    """An error location in the project JSON without the union tags pydantic inserts: the
    component tag after a component index, an equipment rating's tag after 'rating' (proposal
    equipment-pressure-drop.md §2.1), a valve resistance's tag after 'resistance' (CLAUDE.md
    D21), the fluid kind after 'fluid'."""
    if len(loc) > 2 and loc[0] == "components":
        tag, rest = loc[2], loc[3:]
        if len(rest) > 1 and (
            (tag == "equipment" and rest[0] == "rating" and rest[1] in RATING_TAGS)
            or (
                str(tag).startswith("valve:")
                and rest[0] == "resistance"
                and rest[1] in RESISTANCE_TAGS
            )
        ):
            rest = rest[:1] + rest[2:]
        return loc[:2] + rest
    if len(loc) > 1 and loc[0] == "fluid":
        return loc[:1] + loc[2:]
    return loc


def _issue(code: str, where: str, message: str, plan: OverridePlan | None) -> TopologyIssue:
    return TopologyIssue(
        code=code,
        message=f"{where}: {message}",
        component_ids=list(plan.component_ids) if plan else [],
        connection_ids=list(plan.connection_ids) if plan else [],
    )


ErrorKey = tuple[str, str, Location]


def _error_key(error: ErrorDetails) -> ErrorKey:
    return (str(error["type"]), str(error["msg"]), _clean(tuple(error["loc"])))


def _matches(
    error: ErrorDetails, plans: list[OverridePlan]
) -> list[tuple[OverridePlan, Location | None]]:
    """The written overrides an error is about: each whose value location contains the error's
    (with the error's location inside the value), or lies inside it (None: an object-level
    validator, which reads the whole component, pipe or project)."""
    loc = _clean(tuple(error["loc"]))
    out: list[tuple[OverridePlan, Location | None]] = []
    for plan in plans:
        if plan.entry is None:
            continue
        around = False
        for value_loc in plan.value_locations():
            if loc[: len(value_loc)] == value_loc:
                start = len(plan.location) if plan.entry.keys else len(value_loc)
                out.append((plan, loc[start:]))
                break
            if value_loc[: len(loc)] == loc:
                around = True
        else:
            if around:
                out.append((plan, None))
    return out


def _error_issues(
    error: ErrorDetails,
    plans: list[OverridePlan],
    s: int,
    errors_without: Callable[[OverridePlan], set[ErrorKey]],
) -> list[tuple[int, TopologyIssue]]:
    """The issues of one error: one at each override whose value contains it, and an
    object-level error once, at the override(s) whose value its rule rejects, as the
    hand-edited project reports it once: of the overrides around it, those whose base value
    clears it (``errors_without``: the errors with that override not written), or all of them
    when no single one does. The message is the schema's own, never the input (the location
    replaces an unknown key, as for request validation)."""
    code, msg = str(error["type"]), str(error["msg"])
    matches = _matches(error, plans)
    around = [plan for plan, inside in matches if inside is None]
    if len(around) > 1:
        key = _error_key(error)
        causes = [plan for plan in around if key not in errors_without(plan)]
        around = causes or around
    out: list[tuple[int, TopologyIssue]] = []
    for plan, inside in matches:
        where = f"body.project.scenarios.{s}.overrides.{plan.index}"
        if inside is not None:
            parts = [str(p) for p in inside]
            if code == "extra_forbidden" and parts:
                parts[-1] = "(unknown field)"
            out.append((plan.index, _issue(code, ".".join([where, "value", *parts]), msg, plan)))
        elif plan in around:
            out.append((plan.index, _issue(code, where, msg, plan)))
    if not out:  # impossible while the base project is valid; never dropped
        out.append((MAX_OVERRIDES, _issue(code, f"body.project.scenarios.{s}", msg, None)))
    return out


def _json(value: Any) -> JsonValue:
    if isinstance(value, BaseModel):
        dumped: JsonValue = value.model_dump(mode="json", exclude_none=True)
        return dumped
    result: JsonValue = value
    return result


def entry_value(model: BaseModel, entry: Overridable) -> JsonValue:
    """The entry's value on ``model`` (the target), as JSON: a group gives its keys that are
    set and not null."""
    if entry.keys:
        return {to_camel(k): getattr(model, k) for k in entry.keys if getattr(model, k) is not None}
    return _json(_walk(model, entry.path))


def _effective_target(effective: Project, plan: OverridePlan) -> BaseModel:
    """The override's target in the effective project (its location's keys are attribute
    names there too: components, connections, piping, pipes)."""
    target: Any = effective
    for key in plan.location:
        target = target[key] if isinstance(key, int) else getattr(target, key)
    assert isinstance(target, BaseModel)
    return target


def _record(plan: OverridePlan, effective: Project) -> AppliedOverride:
    if plan.entry is None or plan.target is None:
        return AppliedOverride(
            plan.index,
            plan.override,
            plan.state,
            None,
            None,
            "",
            plan.message,
            plan.target_label,
            plan.label,
            (),
            plan.element_id,
            plan.pipe_index,
        )
    target = _effective_target(effective, plan)
    return AppliedOverride(
        index=plan.index,
        override=plan.override,
        state="applied",
        value=entry_value(target, plan.entry),
        base_value=entry_value(plan.target, plan.entry),
        unit=override_unit(plan.entry, plan.target),
        message="",
        target_label=plan.target_label,
        label=plan.label,
        location=plan.location if plan.entry.keys else plan.value_locations()[0],
        element_id=plan.element_id,
        pipe_index=plan.pipe_index,
    )


def apply_scenario(project: Project, scenario_id: str) -> AppliedScenario:
    """The effective project of scenario ``scenario_id`` and the record of every override
    (module docstring; proposal §4.1). Raises ScenarioNotFoundError for an unknown id and
    ScenarioOverrideError, with every problem, for values their targets reject."""
    found = [(i, s) for i, s in enumerate(project.scenarios) if s.id == scenario_id]
    if not found:
        raise ScenarioNotFoundError(f"the project has no scenario '{scenario_id}'")
    s, scenario = found[0]
    base: dict[str, Any] = project.model_dump(mode="json", exclude_unset=True)
    base.pop("scenarios", None)
    data = copy.deepcopy(base)
    plans = [plan_override(project, j, o) for j, o in enumerate(scenario.overrides)]
    issues: list[tuple[int, TopologyIssue]] = []
    written: list[OverridePlan] = []
    for plan in plans:
        if plan.entry is None:
            continue
        if plan.entry.keys and not _spec_is_valid(plan.override.value, plan.entry.keys):
            *own, reference = plan.entry.keys  # spec_id last (models/scenarios.PIPE_SPEC_KEYS)
            keys = ", ".join(to_camel(k) for k in own[1:])
            message = (
                f"a pipe spec is an object with {to_camel(own[0])} and optionally {keys}, or "
                f"with {to_camel(reference)} alone (a pipe spec of the project library), and no "
                "other key"
            )
            where = f"body.project.scenarios.{s}.overrides.{plan.index}.value"
            issues.append((plan.index, _issue("invalid_pipe_spec", where, message, plan)))
            continue
        write_override(data, plan)
        written.append(plan)
    effective: Project | None = None
    without: dict[int, set[ErrorKey]] = {}

    def errors_without(left_out: OverridePlan) -> set[ErrorKey]:
        """The validation errors of the effective project with ``left_out`` not written."""
        if left_out.index not in without:
            other = copy.deepcopy(base)
            for plan in written:
                if plan is not left_out:
                    write_override(other, plan)
            try:
                Project.model_validate(other)
                without[left_out.index] = set()
            except ValidationError as exc:
                without[left_out.index] = {_error_key(e) for e in exc.errors()}
        return without[left_out.index]

    try:
        effective = Project.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors():
            issues += _error_issues(error, written, s, errors_without)
    if issues or effective is None:
        ordered = sorted(enumerate(issues), key=lambda item: (item[1][0], item[0]))
        raise ScenarioOverrideError(scenario.id, [issue for _, (_, issue) in ordered])
    records = [_record(plan, effective) for plan in plans]
    return AppliedScenario(scenario, s, effective, records)


# --------------------------------------------------------------------------- text


TEXT_UNITS = {"Pa (difference)": "Pa"}
"""A trace unit as a text writes it after a number: a pressure difference (an equipment item's
rated pressure drop) as plain "Pa", which the value's label already names a difference ("rated
pressure drop 70000 Pa")."""


def _number(value: float, unit: str) -> str:
    unit = TEXT_UNITS.get(unit, unit)
    return f"{value:.6g} {unit}" if unit else f"{value:.6g}"


def _library_text(kind: str, entry_id: Any, project: Project | None) -> str:
    """A project library entry a value refers to (CLAUDE.md D21), by name and id as traces name
    it: 'project library pipe spec "NPS 60 STD" (PS1)'; by id only where the project does not
    have it (its solve is then a topology issue) or is not given."""
    entries = (
        ()
        if project is None
        else project.pipe_library
        if kind == "pipe spec"
        else project.resistance_library
    )
    for entry in entries:
        if entry.id == entry_id:
            if isinstance(entry, PipeSpec):
                return spec_label(entry)
            return resistance_label(entry)
    return f"project library {kind} {entry_id}"


def _spec_text(spec: dict[str, Any], project: Project | None = None) -> str:
    if spec.get("specId") is not None:
        return _library_text("pipe spec", spec["specId"], project)
    parts = [str(spec.get("materialId", ""))]
    if spec.get("schedule") is not None:
        parts.append(f"schedule {spec['schedule']}")
    for key, name in (
        ("nominalSize", "nominal size"),
        ("innerDiameter", "inner diameter"),
        ("roughness", "roughness"),
    ):
        if spec.get(key) is not None:
            parts.append(f"{name} {_number(spec[key], 'm')}")
    return ", ".join(parts)


FLUID_PROPERTIES = (
    ("density", "density", "kg/m³"),
    ("dynamicViscosity", "dynamic viscosity", "Pa·s"),
    ("vaporPressure", "vapor pressure", "Pa absolute"),
)
"""A custom fluid's properties, and a built-in fluid's property overrides, as value texts name
them (key, name, unit)."""


def _properties_text(values: dict[str, Any]) -> str:
    return ", ".join(
        f"{name} {_number(values[key], unit)}"
        for key, name, unit in FLUID_PROPERTIES
        if isinstance(values.get(key), int | float)
    )


def _fluid_text(fluid: dict[str, Any]) -> str:
    """A fluid with the values that define it, so that a change of a property is visible: a
    custom fluid's properties, a built-in fluid's property overrides."""
    if fluid.get("kind") == "custom":
        text = f"custom fluid '{fluid.get('name', '')}'"
        if fluid.get("temperature") is not None:
            text += f" at {_number(fluid['temperature'], 'K')}"
        return f"{text} ({_properties_text(fluid)})"
    text = f"{fluid.get('fluidId')} at {_number(fluid.get('temperature', 0.0), 'K')}"
    if fluid.get("concentration") is not None:
        text += f", mass fraction {fluid['concentration']:.6g}"
    given = _properties_text(fluid.get("overrides") or {})
    if given:
        text += f", with property overrides ({given})"
    return text


def _rating_text(rating: dict[str, Any]) -> str:
    """An equipment rating (proposal equipment-pressure-drop.md §5.1): a Cv or Kv as entered,
    as a resistance is written ('Cv 120'), a rated point in SI with its units ('50000 Pa at
    0.015 m³/s, 999.103 kg/m³'), never a Python dict's repr."""
    kind = rating.get("kind")
    if kind in ("Cv", "Kv"):
        number = rating.get("value")
        return f"{kind} {number:.6g}" if isinstance(number, int | float) else str(kind)
    parts = [
        _number(value, unit) if isinstance(value, int | float) else "?"
        for value, unit in (
            (rating.get("pressureLoss"), "Pa"),
            (rating.get("flow"), "m³/s"),
            (rating.get("density"), "kg/m³"),
        )
    ]
    return f"{parts[0]} at {parts[1]}, {parts[2]}"


NULL_TEXTS = {"dischargeCoefficient": "ISO 5167-2's (the default)"}
"""How a null value reads where null names a cited default rather than none (an orifice plate's
discharge coefficient, proposal orifice-plate.md §5.1)."""


def value_text(field: str, value: JsonValue, unit: str, project: Project | None = None) -> str:
    """A value in notes and the methods summary (proposal §5.4), SI with its unit; a project
    library entry by its name and id in ``project``'s library (by id without it)."""
    if value is None:
        return NULL_TEXTS.get(field, "none (the default)")
    if field == "spec" and isinstance(value, dict):
        return _spec_text(value, project)
    if field == "fluid" and isinstance(value, dict):
        return _fluid_text(value)
    if field == "rating" and isinstance(value, dict):
        return _rating_text(value)
    if field == "resistance" and isinstance(value, dict):
        if value.get("kind") == "library":
            return _library_text("resistance", value.get("id"), project)
        number = value.get("value")
        return f"{value.get('kind')} {number:.6g}" if isinstance(number, int | float) else "?"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return _number(float(value), unit)
    return str(value)


def _change(o: AppliedOverride, project: Project) -> str:
    """``project``: the scenario's, whose library names the entries values refer to (the base's
    library: entries are not scenario targets, proposal project-library.md §5.1)."""
    field = o.override.field
    used = value_text(field, o.value, o.unit, project)
    base = value_text(field, o.base_value, o.unit, project)
    if isinstance(o.override, ProjectOverride) and field == "fluid":
        return f"{used} (base: {base})"
    return f"{o.label} {used} (base: {base})"


def _capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


def _opening(applied: AppliedScenario, goal_seek: bool = False) -> str:
    """``goal_seek``: the state is a goal seek's, whose variables hold the values it found
    (docs/proposals/goal-seek.md §5.4; as built), so its values are named as the exception."""
    scenario = applied.scenario
    who = f"Scenario '{scenario.name}' (id {scenario.id}) of this project"
    rest = "A scenario changes values only, never the components or connections."
    base = (
        "the base project with the goal seek's values (see Goal seek)"
        if goal_seek
        else "the base project"
    )
    total = len(applied.overrides)
    used = sum(o.state == "applied" for o in applied.overrides)
    if total == 0:
        return (
            f"{who} overrides no base values: every result, trace and section below is of "
            f"{base}. {rest}"
        )
    if used == 0:
        return (
            f"{who}: none of its {total} override(s) of base values could be applied (each is "
            f"listed below), so every result, trace and section below is of {base}. {rest}"
        )
    other = (
        "Every other value is the base project's, except the goal seek's variables (see Goal seek)"
        if goal_seek
        else "Every other value is the base project's"
    )
    return (
        f"{who}: {used} of its {total} override(s) of base values were applied to the base "
        "project before the network was built, so every result, trace and section below is of "
        f"the project with those values. {other}; a scenario changes values only, never the "
        "components or connections."
    )


REPLACED = "In this goal seek the value found takes its place (see Goal seek)."
"""The mark of an override whose value a goal-seek variable replaced (docs/proposals/goal-seek.md
§5.4)."""
REPLACED_TEMPERATURE = (
    "In this goal seek the value found takes the place of its temperature (see Goal seek)."
)
"""The mark of a whole-fluid override whose temperature a goal-seek variable replaced."""

ReplacedParts = Mapping[int, Sequence[str]]
"""Per index of a whole-value override other than the fluid (an equipment rating), the labels
of its parts that goal-seek variables replaced (proposal equipment-pressure-drop.md §5.2); an
index absent: the variable replaced the whole value."""


def _parts_mark(parts: Sequence[str]) -> str:
    """The mark of a whole-value override some of whose parts goal-seek variables replaced: it
    names the parts, as REPLACED_TEMPERATURE names the fluid's temperature."""
    found = "the values found take" if len(parts) > 1 else "the value found takes"
    return f"In this goal seek {found} the place of its {' and '.join(parts)} (see Goal seek)."


def _replaced_mark(o: AppliedOverride, parts: ReplacedParts) -> str:
    fluid = isinstance(o.override, ProjectOverride) and o.override.field == "fluid"
    if fluid:
        return REPLACED_TEMPERATURE
    return _parts_mark(parts[o.index]) if parts.get(o.index) else REPLACED


def scenario_section(
    applied: AppliedScenario,
    replaced: frozenset[int] = frozenset(),
    goal_seek: bool = False,
    parts: ReplacedParts | None = None,
) -> MethodsSection:
    """The "Scenario" methods section of a scenario's solve (proposal §5.3). ``replaced``: the
    indexes of the overrides whose value a goal seek's variable replaced, each item marked so
    (docs/proposals/goal-seek.md §5.4), naming the parts replaced of a whole value (``parts``);
    ``goal_seek``: the opening names the goal seek's values as the exception. /solve passes
    none of them."""
    items = [_opening(applied, goal_seek)]
    if applied.scenario.description:
        items.append(f"Description: {applied.scenario.description}")
    for o in applied.overrides:
        if o.state == "applied":
            mark = f" {_replaced_mark(o, parts or {})}" if o.index in replaced else ""
            items.append(f"{_capitalized(o.target_label)}: {_change(o, applied.project)}.{mark}")
    for o in applied.overrides:
        if o.state != "applied":
            state = "orphaned" if o.state == "orphaned" else "not applicable"
            items.append(
                f"Not applied ({state}): {o.target_label}, {o.label}: {o.message}; the override "
                "is kept in the scenario and ignored."
            )
    return MethodsSection(title="Scenario", items=items, references=[SCENARIO_DECISION])


def _rating_part(o: AppliedOverride) -> bool:
    """An override of one value of an equipment rating (rating.pressureLoss, ...)."""
    return isinstance(o.override, ComponentOverride) and o.override.field.startswith("rating.")


def element_notes(
    applied: AppliedScenario,
    replaced: frozenset[int] = frozenset(),
    parts: ReplacedParts | None = None,
) -> dict[str, str]:
    """One note per component or connection with an applied override (proposal §5.2), ending
    with the goal-seek mark when a variable replaced one of its overrides' values
    (``replaced``, as for ``scenario_section``), naming the parts it replaced of a whole value
    (``parts``) in place of that value. Several equipment rating values found read "the values
    found take the place of its ...", whether the scenario set them as one whole rating or as
    value overrides; every other mark keeps the singular it has always had."""
    changes: dict[str, list[str]] = {}
    marks: dict[str, list[str]] = {}
    plural: set[str] = set()
    for o in applied.overrides:
        if o.state != "applied" or o.element_id is None:
            continue
        text = _change(o, applied.project)
        if o.pipe_index is not None:
            text = f"{pipe_name(o.pipe_index)} {text}"
        changes.setdefault(o.element_id, []).append(text)
        if o.index in replaced:
            named = (parts or {}).get(o.index)
            if named:
                marks.setdefault(o.element_id, []).extend(named)
                plural.add(o.element_id)
                continue
            label = o.label if o.pipe_index is None else f"{pipe_name(o.pipe_index)} {o.label}"
            marks.setdefault(o.element_id, []).append(label)
            if _rating_part(o):  # the same words as for parts of a whole rating
                plural.add(o.element_id)
    scenario = applied.scenario
    notes: dict[str, str] = {}
    for element, texts in changes.items():
        note = (
            f"Scenario '{scenario.name}' (id {scenario.id}) overrides the base project here: "
            f"{'; '.join(texts)}. The inputs below are the scenario's values."
        )
        if element in marks:
            found = (
                "the values found take"
                if element in plural and len(marks[element]) > 1
                else "the value found takes"
            )
            note += (
                f" In this goal seek {found} the place of its "
                f"{' and '.join(marks[element])} (see Goal seek)."
            )
        notes[element] = note
    return notes


def annotate(
    state: SolvedState,
    applied: AppliedScenario,
    replaced: frozenset[int] = frozenset(),
    goal_seek: bool = False,
    parts: ReplacedParts | None = None,
) -> SolvedState:
    """``state`` (the solve of the effective project) with the scenario's text: a first
    "Scenario" methods section and a first note in each overridden element's trace, with the
    goal-seek marks of ``replaced`` (naming the parts of a whole value in ``parts``) and opening
    (``goal_seek``; none of them for /solve). Every other field is unchanged."""
    methods = state.trace.methods
    methods = methods.model_copy(
        update={
            "sections": [scenario_section(applied, replaced, goal_seek, parts), *methods.sections]
        }
    )
    elements = dict(state.trace.elements)
    for element_id, note in element_notes(applied, replaced, parts).items():
        element = elements.get(element_id)
        if element is not None:
            elements[element_id] = element.model_copy(update={"notes": [note, *element.notes]})
    trace = state.trace.model_copy(update={"elements": elements, "methods": methods})
    return state.model_copy(update={"trace": trace})


# --------------------------------------------------------------------------- entry points


def solve_case(
    project: Project, options: SolveOptions | None, scenario_id: str | None
) -> tuple[SolvedState, ScenarioResult | None]:
    """Solve the base project (``scenario_id`` None: exactly ``solve_project``) or one of its
    scenarios: apply it, solve the effective project, annotate the result (proposal §4.2).
    Raises as apply_scenario does, then ScenarioTopologyError / ScenarioFluidError."""
    if scenario_id is None:
        return solve_project(project, options), None
    applied = apply_scenario(project, scenario_id)
    try:
        state = solve_project(applied.project, options)
    except TopologyError as exc:
        raise ScenarioTopologyError(exc.issues, applied.scenario.id) from exc
    except FluidError as exc:
        raise ScenarioFluidError(applied.scenario.id, exc) from exc
    return annotate(state, applied), applied.result()


def system_curve_case(
    project: Project,
    pump_id: str,
    scenario_id: str | None,
    *,
    flow_min: float = 0.0,
    flow_max: float | None = None,
    num_points: int = 41,
) -> tuple[SystemCurve, ScenarioResult | None]:
    """The system curve of one pump in the base project or one of its scenarios. Checks in
    order: the scenario (404), its values (400), the pump (404), then topology (422) and the
    fluid (400), as ``system_curve`` does for the effective project."""
    if scenario_id is None:
        curve = system_curve(
            project, pump_id, flow_min=flow_min, flow_max=flow_max, num_points=num_points
        )
        return curve, None
    applied = apply_scenario(project, scenario_id)
    try:
        curve = system_curve(
            applied.project, pump_id, flow_min=flow_min, flow_max=flow_max, num_points=num_points
        )
    except TopologyError as exc:
        raise ScenarioTopologyError(exc.issues, applied.scenario.id) from exc
    except FluidError as exc:
        raise ScenarioFluidError(applied.scenario.id, exc) from exc
    return curve, applied.result()
