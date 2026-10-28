"""Pipe connections: the edges of the port graph, with their pipes and inline fittings."""

from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic.config import JsonDict

from .base import CamelModel, Identifier

CUSTOM_MATERIAL_ID = "custom"

MAX_PIPES = 100
"""Pipe segments one connection may hold (PipingSegment.pipes; a scenario's pipe override
addresses one of them by index)."""

FittingType = Literal[
    "elbow_90_lr",
    "elbow_90_sr",
    "elbow_45_lr",
    "elbow_45_sr",
    "elbow_90_threaded",
    "elbow_45_threaded",
    "bend",
    "entrance_sharp",
    "entrance_rounded",
    "entrance_projecting",
    "exit",
    "reducer_sudden",
    "reducer_conical",
    "gate_valve",
    "ball_valve",
    "globe_valve",
    "butterfly_valve",
    "plug_valve",
    "swing_check_valve",
    "lift_check_valve",
    "custom",
]
"""Inline fitting types. Each maps to one cited correlation in ``data/fittings.json``;
``custom`` takes a user-entered K. Tees and wyes are not inline fittings: they are branch
components, so that flow splitting is modeled."""

REDUCER_TYPES = ("reducer_sudden", "reducer_conical")
"""Fittings that sit between two pipe segments (pipeIndex and pipeIndex + 1)."""

ENTRANCE_TYPES = ("entrance_sharp", "entrance_rounded", "entrance_projecting")
"""Fittings for the loss where flow leaves a body of liquid (a reservoir) into a pipe."""

EXIT_TYPES = ("exit",)
"""Fittings for the loss where flow leaves a pipe into a body of liquid."""

# Fitting fields each type requires (beyond type, quantity and pipeIndex).
REQUIRED_PARAMETERS: dict[str, tuple[str, ...]] = {
    "bend": ("angle", "radius_ratio"),
    "entrance_rounded": ("radius_ratio",),
    "reducer_conical": ("angle",),
    "custom": ("k_override",),
}


@dataclass(frozen=True)
class ReferenceField:
    """A field that refers to an entry of the project library (CLAUDE.md D21), and the inline
    fields the entry stands in for (published as ``x-reference-fields``)."""

    replaces: tuple[str, ...]
    """snake_case fields the entry gives: none of them may be given beside the reference, and
    the reference meets any rule that requires one of them (x-required-parameters)."""
    required_without: tuple[str, ...] = ()
    """snake_case fields required when the reference is absent."""


SPEC_FIELDS = ("material_id", "schedule", "nominal_size", "inner_diameter", "roughness")
"""The fields of a pipe that a project-library pipe spec (specId) gives it: with a spec, only the
length sits beside it (proposal project-library.md §2.1)."""

PIPE_REFERENCES: dict[str, ReferenceField] = {
    "spec_id": ReferenceField(replaces=SPEC_FIELDS, required_without=("material_id",)),
}
"""A pipe's reference to a pipe spec (pipeLibrary)."""

FITTING_REFERENCES: dict[str, ReferenceField] = {
    "resistance_id": ReferenceField(replaces=("k_override",)),
}
"""A fitting's reference to a resistance entry (resistanceLibrary), in place of its K."""


def _published_references(references: dict[str, ReferenceField]) -> JsonDict:
    return {
        to_camel(name): {
            "replaces": [to_camel(f) for f in ref.replaces],
            "requiredWithout": [to_camel(f) for f in ref.required_without],
        }
        for name, ref in references.items()
    }


def _reference_problems(model: BaseModel, references: dict[str, ReferenceField]) -> list[str]:
    """What ``model`` breaks of its references' rules (``x-reference-fields``), naming fields
    only (never a submitted value)."""
    fields = type(model).model_fields
    problems: list[str] = []
    for name, ref in references.items():
        reference = fields[name].alias or name
        if getattr(model, name) is not None:
            given = [fields[f].alias or f for f in ref.replaces if getattr(model, f) is not None]
            if given:
                problems.append(
                    f"{', '.join(given)} cannot be given with {reference}: the project library "
                    "entry gives them"
                )
        else:
            missing = [
                fields[f].alias or f for f in ref.required_without if getattr(model, f) is None
            ]
            if missing:
                problems.append(f"{', '.join(missing)} is required without {reference}")
    return problems


FITTING_SCHEMA_EXTRA: JsonDict = {
    # The rules the validators below enforce, published as OpenAPI extensions so clients read
    # them instead of copying them (the frontend's utils/model-rules.ts).
    "x-required-parameters": {
        kind: [to_camel(f) for f in fields] for kind, fields in REQUIRED_PARAMETERS.items()
    },
    "x-reducer-types": list(REDUCER_TYPES),
    "x-entrance-types": list(ENTRANCE_TYPES),
    "x-exit-types": list(EXIT_TYPES),
    # {reference: {replaces, requiredWithout}}: with the reference given, none of the fields it
    # replaces may be, and it meets x-required-parameters' need for them; without it,
    # requiredWithout are required (CLAUDE.md D21).
    "x-reference-fields": _published_references(FITTING_REFERENCES),
}

PIPE_SCHEMA_EXTRA: JsonDict = {
    # As on Fitting: a pipe refers to a pipe spec (specId) or states its own; never both.
    "x-reference-fields": _published_references(PIPE_REFERENCES),
}


class PipeDefinition(CamelModel):
    """One pipe segment. Segments in a connection are in series, ordered from -> to. Its size
    comes from the materials library (materialId, schedule, nominalSize, with optional bore and
    roughness overrides), from its own values (materialId 'custom'), or from a pipe spec of the
    project library (specId, with nothing but the length beside it)."""

    model_config = ConfigDict(json_schema_extra=PIPE_SCHEMA_EXTRA)

    spec_id: Identifier | None = Field(
        default=None,
        # Left out of every dump when absent, so a pipe without one serializes as before.
        exclude_if=lambda spec_id: spec_id is None,
        description=(
            "Id of a pipe spec in the project's pipeLibrary: the pipe takes its material, inner "
            "diameter and roughness, and materialId, schedule, nominalSize, innerDiameter and "
            "roughness are absent (x-reference-fields). One the project does not have is a "
            "topology issue when solving"
        ),
    )
    material_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Key into the pipe materials library, or 'custom' with innerDiameter set. Required "
            "unless specId is given; absent with it"
        ),
    )
    schedule: str | None = Field(
        default=None,
        max_length=16,
        description="Schedule designation from the library (e.g. '40', '80', '10S')",
    )
    nominal_size: float | None = Field(
        default=None,
        gt=0,
        le=10.0,
        description="Nominal size, m (NPS in inches x 0.0254); resolved to an inner diameter",
    )
    inner_diameter: float | None = Field(
        default=None,
        gt=0,
        le=10.0,
        description="Inner diameter, m. Required for material 'custom'; overrides the library",
    )
    length: float = Field(gt=0, le=1.0e6, description="Pipe length, m")
    roughness: float | None = Field(
        default=None,
        ge=0,
        le=0.1,
        description="Absolute roughness, m. Required for material 'custom'; overrides the library",
    )

    @model_validator(mode="after")
    def _check_size_source(self) -> Self:
        problems = _reference_problems(self, PIPE_REFERENCES)
        if problems:
            raise ValueError("; ".join(problems))
        if self.spec_id is not None:
            return self
        if self.material_id == CUSTOM_MATERIAL_ID:
            if self.inner_diameter is None or self.roughness is None:
                raise ValueError("a custom pipe needs innerDiameter and roughness")
        elif self.inner_diameter is None and (self.schedule is None or self.nominal_size is None):
            raise ValueError("a library pipe needs schedule and nominalSize (or innerDiameter)")
        return self


class Fitting(CamelModel):
    """An inline fitting, with its loss referenced to the velocity in pipe ``pipeIndex``."""

    model_config = ConfigDict(json_schema_extra=FITTING_SCHEMA_EXTRA)

    type: FittingType
    quantity: int = Field(default=1, ge=1, le=1000)
    pipe_index: int = Field(
        default=0,
        ge=0,
        description=(
            "Index of the pipe segment the fitting sits in; its inner diameter and velocity "
            "are the fitting's reference. A reducer sits between pipeIndex and pipeIndex + 1 "
            "and acts as a contraction or an expansion depending on the flow direction."
        ),
    )
    k_override: float | None = Field(
        default=None,
        ge=0,
        le=1.0e4,
        description=(
            "User-specified K (referenced to pipe pipeIndex); required for 'custom' unless "
            "resistanceId is given, and absent with it"
        ),
    )
    resistance_id: Identifier | None = Field(
        default=None,
        # Left out of every dump when absent, so a fitting without one serializes as before.
        exclude_if=lambda resistance_id: resistance_id is None,
        description=(
            "Id of an entry of the project's resistanceLibrary, in place of kOverride (never "
            "both): its K, Cv or Kv on pipe pipeIndex, which meets a custom fitting's need for "
            "kOverride (x-reference-fields). One the project does not have is a topology issue "
            "when solving"
        ),
    )
    angle: float | None = Field(
        default=None,
        gt=0,
        le=180,
        description="Bend angle, or the included cone angle of a conical reducer, degrees",
    )
    radius_ratio: float | None = Field(
        default=None,
        gt=0,
        le=50,
        description="Bend radius / inner diameter (bend), or rounding radius / diameter (entrance)",
    )
    description: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_parameters(self) -> Self:
        problems = _reference_problems(self, FITTING_REFERENCES)
        if problems:
            raise ValueError("; ".join(problems))
        given = {
            f
            for name, ref in FITTING_REFERENCES.items()
            if getattr(self, name) is not None
            for f in ref.replaces
        }
        missing = [
            f
            for f in REQUIRED_PARAMETERS.get(self.type, ())
            if getattr(self, f) is None and f not in given
        ]
        if missing:
            fields = type(self).model_fields
            names = ", ".join(fields[f].alias or f for f in missing)
            instead = [
                fields[name].alias or name
                for name, ref in FITTING_REFERENCES.items()
                if set(missing) & set(ref.replaces)
            ]
            alternative = f" (or {', '.join(instead)}, a project library entry)" if instead else ""
            raise ValueError(f"a {self.type} fitting needs {names}{alternative}")
        return self


class PipingSegment(CamelModel):
    """The pipes (in series, from -> to) and inline fittings of one connection."""

    pipes: list[PipeDefinition] = Field(min_length=1, max_length=MAX_PIPES)
    fittings: list[Fitting] = Field(max_length=500)

    @model_validator(mode="after")
    def _check_fitting_indices(self) -> Self:
        n = len(self.pipes)
        for i, fitting in enumerate(self.fittings):
            last = n - 2 if fitting.type in REDUCER_TYPES else n - 1
            if fitting.pipe_index > last:
                raise ValueError(
                    f"fittings[{i}]: pipeIndex is beyond the connection's pipe segments"
                    + (" (a reducer needs a following segment)" if last == n - 2 else "")
                )
        return self


class PipeConnection(CamelModel):
    """An edge of the port graph. Positive flow runs from the 'from' port to the 'to' port."""

    id: Identifier
    from_component_id: Identifier
    from_port_id: Identifier
    to_component_id: Identifier
    to_port_id: Identifier
    piping: PipingSegment
