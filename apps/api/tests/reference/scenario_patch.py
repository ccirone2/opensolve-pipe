"""An independent application of scenarios, for the scenario tests (``test_scenarios.py``).

Written from docs/proposals/scenario-manager.md (§2.2 the allow-list, §3.2 the record, §4.1 what
applying a scenario means) and the specs, by a tester who did not read ``services/``. It never
calls ``apply_scenario``, so the two implementations check each other (proposal §7.2). A scenario
is a list of overrides of base values, each naming a target and a field:

- ``{"kind": "component", "componentId", "field", "value"}``: a field the allow-list names for the
  component's type (``COMPONENT_FIELDS``);
- ``{"kind": "pipe", "connectionId", "pipeIndex", "field", "value"}``: one pipe's ``spec`` (its
  material, schedule, nominal size and bore and roughness overrides, or a pipe spec of the
  project library, ``specId``, CLAUDE.md D21: replaced together) or its ``length``, with
  ``pipeIndex`` 0-based;
- ``{"kind": "project", "field", "value"}``: the whole ``fluid``, or a built-in fluid's
  ``fluid.temperature``.

An equipment item (docs/proposals/equipment-pressure-drop.md §5.1, decisions 14 and 22) takes its
whole ``rating`` (another datasheet, of either kind, as ``fluid`` is the whole fluid) and each of
its values: ``rating.pressureLoss``, ``rating.flow`` and ``rating.density``, held by a rated point,
and ``rating.value``, held by a Cv or Kv. A value the base element's rating kind does not hold is
not applicable, as a flow setpoint on a fixed-speed pump is.

An orifice plate (docs/proposals/orifice-plate.md §5.1, decision 20) takes its ``boreDiameter``
(m) and its ``dischargeCoefficient`` (dimensionless: a number, or null for ISO 5167-2's C, the
default); its taps are installation and not overridable.

``by_hand`` edits the project's JSON the way a user would edit it by hand. It finds each target
with the model types (``opensolve_pipe.models``) and writes the raw value in place: a ``spec``
first removes the pipe's six spec keys. Then it drops ``scenarios``. An override whose target is
gone is orphaned, and one whose target has no such value is not applicable; both are left out
(proposal decision 4). ``expected_records`` derives what the API must report for each override
(§3.2): its state, the value used (read back from the hand-edited project as validated), the base
value (an unset field gives its default) and the unit. ``note_elements`` names the elements whose
trace gets the scenario's note (§5.2).
"""

import copy
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from pydantic.alias_generators import to_snake

from opensolve_pipe.models.components import (
    AssignedFlow,
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
from opensolve_pipe.models.fluids import BuiltinFluid
from opensolve_pipe.models.project import Project

State = Literal["applied", "orphaned", "not_applicable"]

COMPONENT_FIELDS: dict[type[BaseModel], dict[str, str | None]] = {
    Reservoir: {"liquidLevel": "m", "surfacePressure": "Pa(g)"},
    IdealReferenceNode: {"pressure": "Pa(g)"},
    AssignedFlow: {"flow": "m³/s"},
    Pump: {"status": "", "speed": "", "control.setpoint": "m³/s"},
    IsolationValve: {"status": "", "resistance": None},
    CheckValve: {"status": "", "resistance": None},
    ControlValve: {"status": "", "resistance": None, "setpoint": None},
    Plug: {},
    TeeBranch: {},
    WyeBranch: {},
    Equipment: {
        "rating": "",
        "rating.pressureLoss": "Pa (difference)",
        "rating.flow": "m³/s",
        "rating.density": "kg/m³",
        "rating.value": "",
    },
    Orifice: {"boreDiameter": "m", "dischargeCoefficient": ""},
}
"""The allow-list for components (proposal §2.2): field -> the unit its record states ('' for
none). None means the design leaves the unit open and it is not checked: a resistance is K, Cv or
Kv as entered, and a control valve's setpoint unit depends on its type (``SETPOINT_UNITS``). An
equipment item's rated pressure drop is a difference, "Pa (difference)" (never a bare "Pa",
SDD §4.10); its whole rating and its Cv or Kv have none (proposal §5.1). An orifice plate's bore
is in m and its discharge coefficient has none (orifice-plate.md §5.1)."""
RATING_PARTS: dict[str, tuple[str, ...]] = {
    "rating.pressureLoss": ("point",),
    "rating.flow": ("point",),
    "rating.density": ("point",),
    "rating.value": ("Cv", "Kv"),
}
"""The rating kinds that hold each part of an equipment rating (proposal decision 22)."""
SETPOINT_UNITS = {"prv": "Pa(g)", "psv": "Pa(g)", "fcv": "m³/s"}
PIPE_FIELDS: dict[str, str | None] = {"spec": None, "length": "m"}
PROJECT_FIELDS: dict[str, str | None] = {"fluid": None, "fluid.temperature": "K"}
COMPONENT_FIELD_NAMES = (
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
    "boreDiameter",
    "dischargeCoefficient",
)
"""Every field a component override may name. A field its target's type lacks is not applicable."""
SPEC_KEYS = ("materialId", "schedule", "nominalSize", "innerDiameter", "roughness", "specId")
"""The keys a pipe's ``spec`` replaces together (proposal decision 10): its five values, or a
pipe spec of the project library (docs/proposals/project-library.md §5.1, CLAUDE.md D21), so a
spec change moves a pipe to, from or between library specs."""

Where = tuple[Any, ...]
"""Where an applied override's value sits: ('component', index, field),
('pipe', connection index, pipe index, field) or ('project', field)."""


@dataclass(frozen=True)
class Outcome:
    """What applying one override did."""

    index: int
    override: dict[str, Any]
    state: State
    where: Where | None
    element_id: str | None
    """The component or connection whose trace gets the scenario's note (None: a project value,
    or not applied)."""


@dataclass(frozen=True)
class HandApplied:
    """A scenario applied by hand: the edited project's JSON, without scenarios."""

    project: dict[str, Any]
    base: Project
    outcomes: list[Outcome]

    def applied(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.state == "applied"]

    def count(self, state: State) -> int:
        return sum(o.state == state for o in self.outcomes)


def without_scenarios(project: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in project.items() if k != "scenarios"}


def resolve(base: Project, override: dict[str, Any]) -> tuple[State, Where | None, str | None]:
    """The state of ``override`` on ``base``, where its value sits, and the element whose trace
    gets the scenario's note."""
    kind, field = override["kind"], override["field"]
    if kind == "component":
        index = next(
            (i for i, c in enumerate(base.components) if c.id == override["componentId"]), None
        )
        if index is None:
            return "orphaned", None, None
        component = base.components[index]
        if field not in COMPONENT_FIELDS[type(component)]:
            return "not_applicable", None, None
        if field == "control.setpoint" and getattr(component, "control", None) is None:
            return "not_applicable", None, None
        if (
            isinstance(component, Equipment)
            and field in RATING_PARTS
            and component.rating.kind not in RATING_PARTS[field]
        ):
            return "not_applicable", None, None
        return "applied", ("component", index, field), component.id
    if kind == "pipe":
        index = next(
            (i for i, c in enumerate(base.connections) if c.id == override["connectionId"]), None
        )
        if index is None or override["pipeIndex"] >= len(base.connections[index].piping.pipes):
            return "orphaned", None, None
        return (
            "applied",
            ("pipe", index, override["pipeIndex"], field),
            base.connections[index].id,
        )
    if field == "fluid.temperature" and not isinstance(base.fluid, BuiltinFluid):
        return "not_applicable", None, None
    return "applied", ("project", field), None


def _write(data: dict[str, Any], where: Where, value: Any) -> None:
    value = copy.deepcopy(value)
    if where[0] == "component":
        target = data["components"][where[1]]
        *head, leaf = where[2].split(".")
        for key in head:
            target = target[key]
        target[leaf] = value
    elif where[0] == "pipe":
        pipe = data["connections"][where[1]]["piping"]["pipes"][where[2]]
        if where[3] == "spec":
            for key in SPEC_KEYS:
                pipe.pop(key, None)
            pipe.update(value)
        else:
            pipe["length"] = value
    elif where[1] == "fluid":
        data["fluid"] = value
    else:
        data["fluid"]["temperature"] = value


def by_hand(project: dict[str, Any], scenario: dict[str, Any]) -> HandApplied:
    """``project`` (API JSON, with or without scenarios) with ``scenario``'s overrides written
    into its JSON by hand, and what each override did."""
    data = copy.deepcopy(without_scenarios(project))
    base = Project.model_validate(data)
    outcomes = []
    for i, override in enumerate(scenario["overrides"]):
        state, where, element = resolve(base, override)
        if where is not None:
            _write(data, where, override["value"])
        outcomes.append(Outcome(i, override, state, where, element))
    return HandApplied(data, base, outcomes)


def _json(value: Any) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def read(project: Project, where: Where) -> Any:
    """The JSON value at ``where`` in ``project``: a spec is the pipe's spec keys that are set
    and not null, a fluid the fluid's set fields; an unset field gives its default."""
    if where[0] == "component":
        value: Any = project.components[where[1]]
        for part in where[2].split("."):
            value = getattr(value, to_snake(part))
        return _json(value)
    if where[0] == "pipe":
        pipe = project.connections[where[1]].piping.pipes[where[2]]
        if where[3] == "length":
            return pipe.length
        dumped = pipe.model_dump(mode="json", exclude_unset=True)
        return {k: v for k, v in dumped.items() if k in SPEC_KEYS and v is not None}
    if where[1] == "fluid":
        return project.fluid.model_dump(mode="json", exclude_unset=True)
    return project.fluid.temperature


def unit(project: Project, where: Where) -> str | None:
    """The unit the record of the override at ``where`` must state (None: not checked)."""
    if where[0] == "component":
        component = project.components[where[1]]
        if isinstance(component, ControlValve) and where[2] == "setpoint":
            return SETPOINT_UNITS[component.valve_type]
        return COMPONENT_FIELDS[type(component)][where[2]]
    if where[0] == "pipe":
        return PIPE_FIELDS[where[3]]
    return PROJECT_FIELDS[where[1]]


def expected_records(hand: HandApplied) -> list[dict[str, Any]]:
    """The record the API must report for each override (proposal §3.2), with ``unit`` None
    where it is not checked. The hand-edited project must be valid."""
    effective = Project.model_validate(hand.project)
    records = []
    for o in hand.outcomes:
        records.append(
            {
                "index": o.index,
                "override": o.override,
                "state": o.state,
                "value": read(effective, o.where) if o.where is not None else None,
                "baseValue": read(hand.base, o.where) if o.where is not None else None,
                "unit": unit(hand.base, o.where) if o.where is not None else None,
            }
        )
    return records


def note_elements(hand: HandApplied) -> Counter[str]:
    """Elements whose trace gets the scenario's note, with how many applied overrides each."""
    return Counter(o.element_id for o in hand.applied() if o.element_id is not None)


def same_json(a: Any, b: Any) -> bool:
    """JSON equality in which a missing key equals null (a model dumped with or without its
    unset fields) and 1 equals 1.0, but true never equals 1."""
    if isinstance(a, dict) and isinstance(b, dict):
        return all(same_json(a.get(k), b.get(k)) for k in a.keys() | b.keys())
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_json(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return bool(a == b)
