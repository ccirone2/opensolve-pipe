"""Opt-in design checks (CLAUDE.md D19; proposal design-checks.md).

A check is on when its object is present in ``ProjectSettings.designChecks``; its limits are
user data. A preset only fills limits in, and its source says which (GOALS §4.1: no uncited
limit). Presets are published as the ``x-design-check-presets`` extension, with citations, so
the web app reads them instead of copying them.
"""

from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.config import JsonDict

from .base import CamelModel, OutputModel

PresetId = Literal["api610_por", "hi961_2012_general"]


class Preset(CamelModel):
    id: PresetId
    check: Literal["npshMargin", "operatingRegion"]
    values: dict[str, float]
    citation: str


PRESETS: tuple[Preset, ...] = (
    Preset(
        id="api610_por",
        check="operatingRegion",
        values={"preferredMin": 0.7, "preferredMax": 1.2},
        citation=(
            'API 610 (10th/11th ed.) 5.1.14: "Pumps shall have a preferred operating region '
            'of 70 % to 120 % of best efficiency flowrate of the pump as furnished", as quoted '
            'by Datacor, "Are you operating your pump off BEP?" (the standard itself was not '
            "read)"
        ),
    ),
    Preset(
        id="hi961_2012_general",
        check="npshMargin",
        values={"minimumRatio": 1.1, "minimumMargin": 1.0},
        citation=(
            'ANSI/HI 9.6.1-2012, "General" application: NPSH margin ratio 1.1 or 1.0 m, '
            'whichever is greater, as reproduced by Michael Smith Engineers, "NPSH" (the '
            "standard itself was not read; the 2024 edition's tables may differ)"
        ),
    ),
)
"""Cited presets (proposal design-checks.md §2)."""


def ordered_fields_extra(schema: JsonDict, cls: type[Any]) -> None:
    """``x-ordered-fields`` (the components' extension, models/components.py)."""
    ordered: tuple[tuple[str, str], ...] = getattr(cls, "ORDERED_FIELDS", ())
    if ordered:
        schema["x-ordered-fields"] = [
            {"lower": lower, "upper": upper, "strict": True} for lower, upper in ordered
        ]


class UserSource(CamelModel):
    kind: Literal["user"]


class PresetSource(CamelModel):
    kind: Literal["preset"]
    preset: PresetId


CheckSource = Annotated[UserSource | PresetSource, Field(discriminator="kind")]


class NpshMarginCheck(CamelModel):
    """NPSHa ≥ max(NPSHr + minimumMargin, minimumRatio × NPSHr), for the limits set."""

    minimum_margin: float | None = Field(
        default=None, ge=0.0, le=100.0, description="NPSHa − NPSHr at least this, m"
    )
    minimum_ratio: float | None = Field(
        default=None, ge=1.0, le=10.0, description="NPSHa / NPSHr at least this"
    )
    source: CheckSource


class OperatingRegionCheck(CamelModel):
    """A running pump's flow within [preferredMin, preferredMax] × its BEP flow; with it, the
    curve's manufacturer data (allowable region, minimum flows, motor rating) are checked."""

    model_config = ConfigDict(json_schema_extra=ordered_fields_extra)
    ORDERED_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (("preferredMin", "preferredMax"),)

    preferred_min: float | None = Field(
        default=None, gt=0.0, le=5.0, description="Fraction of the BEP flow"
    )
    preferred_max: float | None = Field(
        default=None, gt=0.0, le=5.0, description="Fraction of the BEP flow"
    )
    source: CheckSource

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        low, high = self.preferred_min, self.preferred_max
        if low is not None and high is not None and not low < high:
            raise ValueError("preferredMin must be below preferredMax")
        return self


class PipeVelocityCheck(CamelModel):
    """Every pipe segment's |velocity| within [minimum, maximum], for the limits set."""

    model_config = ConfigDict(json_schema_extra=ordered_fields_extra)
    ORDERED_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (("minimum", "maximum"),)

    minimum: float | None = Field(default=None, ge=0.0, le=100.0, description="m/s")
    maximum: float | None = Field(default=None, gt=0.0, le=100.0, description="m/s")
    source: CheckSource

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if (
            self.minimum is not None
            and self.maximum is not None
            and not self.minimum < self.maximum
        ):
            raise ValueError("minimum must be below maximum")
        return self


def _presets_extra(schema: JsonDict, cls: type[Any]) -> None:
    schema["x-design-check-presets"] = [p.model_dump(mode="json", by_alias=True) for p in PRESETS]


class DesignChecks(CamelModel):
    """The design checks a project turns on (each present object is one check). Opt-in, never
    a flag: a check's result never changes a solved value (GOALS §4.6)."""

    model_config = ConfigDict(json_schema_extra=_presets_extra)

    npsh_margin: NpshMarginCheck | None = None
    operating_region: OperatingRegionCheck | None = None
    pipe_velocity: PipeVelocityCheck | None = None


DesignCheckId = Literal[
    "npsh_margin",
    "operating_region",
    "allowable_region",
    "minimum_flow",
    "motor_power",
    "pipe_velocity",
]


class DesignCheckLimits(OutputModel):
    min: float | None
    max: float | None


class DesignCheckResult(OutputModel):
    """One check of one element (proposal design-checks.md §4). Not a flag."""

    check: DesignCheckId
    component_id: str | None = Field(description="The pump checked")
    connection_id: str | None = Field(description="The connection checked")
    outcome: Literal["pass", "fail", "not_evaluated"]
    value: float | None = Field(description="The value checked, SI (null: not evaluated)")
    pipe_index: int | None = Field(
        description="pipe_velocity: the connection's pipe (0-based) whose velocity is the value"
    )
    pipes_outside: list[int] = Field(
        description="pipe_velocity: the connection's pipes (0-based) outside the limits"
    )
    limits: DesignCheckLimits = Field(description="The limits it was checked against, SI")
    unit: str = Field(description="SI unit of value and limits")
    source: str = Field(description="'user', or the preset's citation")
    message: str = Field(description="The inequality that set the outcome, or why not evaluated")
