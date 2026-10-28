"""The project library (CLAUDE.md D21, docs/proposals/project-library.md §2): pipe specs and
loss coefficients the user defines once, each with its source, and refers to by id from pipe
segments (``PipeDefinition.specId``), valves (``resistance: {kind: 'library', id}``) and inline
fittings (``Fitting.resistanceId``). An edit to an entry reaches every element that refers to it.

Not to be confused with ``models/library.py``, which describes the cited catalog the API serves
(pipe materials and fitting types). Entries are user data: their values are labelled as such,
with the entry's name and source, wherever they are used (GOALS §4.1, §4.2). A reference to an
entry that does not exist is valid here and a topology issue when solving, as a pump's curveId.
"""

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic.config import JsonDict

from .base import FLOW_COEFFICIENT_MAX, CamelModel, Identifier, Name
from .piping import CUSTOM_MATERIAL_ID

MAX_LIBRARY_ENTRIES = 100
"""Entries in each of the project's lists (pipeLibrary, resistanceLibrary), proposal §2."""

MAX_SOURCE = 300
"""Characters of an entry's source (owner's answer Q2, 2026-10-28)."""

DIAMETER_MAX = 10.0
"""m: the upper bound of a diameter, as a pipe's (``piping.PipeDefinition.inner_diameter``)."""

Source = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_SOURCE,
        # At least one character that is not white space: a blank source states no origin.
        pattern=r"\S",
        description=(
            "Where the values come from (a standard and its table, a datasheet, a measurement), "
            "as free text: shown in every trace that uses the entry and in the methods summary"
        ),
    ),
]
"""An entry's source (required, owner's answer Q2): never quoted in an error message."""


@dataclass(frozen=True)
class FieldsByValue:
    """Fields one field's value requires or forbids (published as ``x-fields-by-value``)."""

    field: str
    """The snake_case field whose value decides."""
    required: dict[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    """By value: snake_case fields that must be given (not null)."""
    forbidden: dict[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    """By value: snake_case fields that must be absent (or null)."""
    what: dict[str, str] = dataclasses.field(default_factory=dict)
    """By value: how messages name an object with it ('a custom pipe spec')."""


def _fields_by_value_extra(schema: JsonDict, cls: type[Any]) -> None:
    """Publish the rules the validators below enforce, which JSON Schema cannot express, as
    OpenAPI extensions, so clients read them instead of copying them (the frontend's
    ``utils/model-rules.ts``):

    - ``x-fields-by-value``: ``{field, required, forbidden}``, camelCase: the fields each value of
      ``field`` requires (given, not null) and forbids (absent or null); a value not listed adds
      no rule;
    - ``x-ordered-fields``: as on the components (models/components.py), checked when both are
      present.
    """
    rule: FieldsByValue | None = getattr(cls, "FIELDS_BY_VALUE", None)
    if rule is not None:
        schema["x-fields-by-value"] = {
            "field": to_camel(rule.field),
            "required": {v: [to_camel(f) for f in fs] for v, fs in rule.required.items()},
            "forbidden": {v: [to_camel(f) for f in fs] for v, fs in rule.forbidden.items()},
        }
    ordered: tuple[tuple[str, str], ...] = getattr(cls, "ORDERED_FIELDS", ())
    if ordered:
        schema["x-ordered-fields"] = [
            {"lower": lower, "upper": upper, "strict": True} for lower, upper in ordered
        ]


def _by_value_problems(model: CamelModel, rule: FieldsByValue) -> list[str]:
    """What ``model`` breaks of ``rule``, naming fields only (never a submitted value)."""
    value = getattr(model, rule.field)
    if not isinstance(value, str):
        return []
    fields = type(model).model_fields
    what = rule.what.get(value, "this entry")
    problems: list[str] = []
    missing = [
        fields[f].alias or f for f in rule.required.get(value, ()) if getattr(model, f) is None
    ]
    if missing:
        problems.append(f"{what} needs {', '.join(missing)}")
    extra = [
        fields[f].alias or f for f in rule.forbidden.get(value, ()) if getattr(model, f) is not None
    ]
    if extra:
        problems.append(f"{what} takes no {', '.join(extra)}")
    return problems


class PipeSpec(CamelModel):
    """A pipe size the user defines once, with its source, and refers to from any pipe segment
    (``PipeDefinition.specId``): every segment that refers to it is solved with its material,
    inner diameter and roughness, and its own length."""

    model_config = ConfigDict(json_schema_extra=_fields_by_value_extra)

    FIELDS_BY_VALUE: ClassVar[FieldsByValue] = FieldsByValue(
        "material_id",
        required={CUSTOM_MATERIAL_ID: ("roughness",)},
        what={CUSTOM_MATERIAL_ID: "a custom pipe spec"},
    )
    """A custom spec states its roughness (published as x-fields-by-value)."""
    ORDERED_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (("innerDiameter", "outerDiameter"),)
    """innerDiameter < outerDiameter, when the outer diameter is given (x-ordered-fields)."""

    id: Identifier = Field(description="Unique among the project's pipe specs")
    name: Name = Field(description="What the user calls it, e.g. 'NPS 60 STD carbon steel'")
    source: Source
    material_id: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "Key into the pipe materials library (its cited roughness applies unless roughness "
            "is given), or 'custom' (roughness required). An unknown material is a topology "
            "issue when solving"
        ),
    )
    inner_diameter: float = Field(
        gt=0,
        le=DIAMETER_MAX,
        description="Inner diameter, m: the bore of every pipe segment that refers to the spec",
    )
    roughness: float | None = Field(
        default=None,
        ge=0,
        le=0.1,
        description=(
            "Absolute roughness, m. Required for material 'custom'. Absent on a library "
            "material: that material's cited roughness (Farshad & Rieke 2006) evaluated at "
            "innerDiameter, as for a library pipe with an inner-diameter override"
        ),
    )
    outer_diameter: float | None = Field(
        default=None,
        gt=0,
        le=DIAMETER_MAX,
        description="Outer diameter, m, for display only; above innerDiameter when given",
    )
    nominal_size: float | None = Field(
        default=None,
        gt=0,
        le=DIAMETER_MAX,
        description=(
            "Nominal size, m (NPS in inches x 0.0254), for display and the web app's port sizes "
            "only; the solver uses innerDiameter"
        ),
    )

    @model_validator(mode="after")
    def _check_spec(self) -> Self:
        problems = _by_value_problems(self, self.FIELDS_BY_VALUE)
        if self.outer_diameter is not None and not self.inner_diameter < self.outer_diameter:
            problems.append("innerDiameter must be below outerDiameter")
        if problems:
            raise ValueError("; ".join(problems))
        return self


ResistanceKind = Literal["K", "Cv", "Kv"]
"""How a datasheet gives a loss coefficient (as ``components.FlowCoefficient.kind``)."""


class ResistanceSpec(CamelModel):
    """A loss coefficient from a datasheet, with its source, referred to by valves (a valve's
    ``resistance`` as ``{kind: 'library', id}``) and inline fittings (``Fitting.resistanceId``).
    A K is stated at a bore and needs it: an element of bore D takes K·(D/referenceDiameter)⁴,
    the same head loss at a given flow. A Cv or Kv needs no bore (proposal §3.3)."""

    model_config = ConfigDict(json_schema_extra=_fields_by_value_extra)

    FIELDS_BY_VALUE: ClassVar[FieldsByValue] = FieldsByValue(
        "kind",
        required={"K": ("reference_diameter",)},
        forbidden={"Cv": ("reference_diameter",), "Kv": ("reference_diameter",)},
        what={
            "K": "a K entry (a K is stated at a bore)",
            "Cv": "a Cv entry (it needs no bore)",
            "Kv": "a Kv entry (it needs no bore)",
        },
    )
    """A K states its bore; a Cv or Kv takes none (published as x-fields-by-value)."""

    id: Identifier = Field(description="Unique among the project's resistance entries")
    name: Name = Field(description="What the user calls it, e.g. '30 in butterfly valve, open'")
    source: Source
    kind: ResistanceKind = Field(
        description=(
            "K (dimensionless, on the velocity in a bore of referenceDiameter), Cv (US gpm of "
            "water at 1 psi) or Kv (m³/h of water at 1 bar)"
        )
    )
    value: float = Field(
        gt=0,
        le=FLOW_COEFFICIENT_MAX,
        description=(
            "The coefficient as the datasheet prints it, stored as entered (as a valve's "
            "resistance): K, Cv in US gpm at 1 psi, or Kv in m³/h at 1 bar"
        ),
    )
    reference_diameter: float | None = Field(
        default=None,
        gt=0,
        le=DIAMETER_MAX,
        description=(
            "The bore a K is stated at, m: required for K, absent for Cv and Kv. An element of "
            "bore D (a valve's inlet pipe, a fitting's pipe pipeIndex) takes "
            "K·(D/referenceDiameter)⁴"
        ),
    )

    @model_validator(mode="after")
    def _check_bore(self) -> Self:
        problems = _by_value_problems(self, self.FIELDS_BY_VALUE)
        if problems:
            raise ValueError("; ".join(problems))
        return self


class ResistanceRef(CamelModel):
    """A valve's resistance taken from the project library: the entry's K, Cv or Kv on the
    valve's inlet pipe, as if entered on the valve (proposal §2.2)."""

    kind: Literal["library"] = Field(
        description="library: an entry of the project's resistanceLibrary"
    )
    id: Identifier = Field(
        description=(
            "The id of a resistanceLibrary entry; one the project does not have is a topology "
            "issue when solving"
        )
    )


def duplicate_entry_ids(entries: Sequence[PipeSpec | ResistanceSpec], what: str) -> list[str]:
    """Pairs of entries of one list with one id, by index only (``what``: 'pipe specs')."""
    first: dict[str, int] = {}
    problems: list[str] = []
    for j, entry in enumerate(entries):
        if entry.id in first:
            problems.append(f"{what} {first[entry.id]} and {j} have the same id")
        else:
            first[entry.id] = j
    return problems
