"""Piping, pipe definition, and fitting models."""

from enum import StrEnum

from pydantic import Field

from .base import OpenSolvePipeBaseModel, PositiveFloat, PositiveInt


class PipeMaterial(StrEnum):
    """Available pipe materials."""

    CARBON_STEEL = "carbon_steel"
    STAINLESS_STEEL = "stainless_steel"
    PVC = "pvc"
    CPVC = "cpvc"
    HDPE = "hdpe"
    DUCTILE_IRON = "ductile_iron"
    CAST_IRON = "cast_iron"
    COPPER = "copper"
    GRP = "grp"  # Glass Reinforced Plastic (Fiberglass)


class PipeSchedule(StrEnum):
    """Common pipe schedules."""

    SCH_5 = "5"
    SCH_10 = "10"
    SCH_40 = "40"
    SCH_80 = "80"
    SCH_160 = "160"
    STD = "STD"
    XS = "XS"
    XXS = "XXS"


class FittingType(StrEnum):
    """Types of pipe fittings."""

    # Elbows
    ELBOW_90_LR = "elbow_90_lr"  # 90° Long Radius (r/D = 1.5)
    ELBOW_90_SR = "elbow_90_sr"  # 90° Short Radius (r/D = 1.0)
    ELBOW_45 = "elbow_45"  # 45° Elbow

    # Tees
    TEE_THROUGH = "tee_through"  # Flow through run
    TEE_BRANCH = "tee_branch"  # Flow into branch

    # Reducers
    REDUCER_CONCENTRIC = "reducer_concentric"
    REDUCER_ECCENTRIC = "reducer_eccentric"
    EXPANDER_CONCENTRIC = "expander_concentric"
    EXPANDER_ECCENTRIC = "expander_eccentric"

    # Valves (as fittings - for K-factor calculation)
    GATE_VALVE = "gate_valve"
    BALL_VALVE = "ball_valve"
    BUTTERFLY_VALVE = "butterfly_valve"
    GLOBE_VALVE = "globe_valve"
    CHECK_VALVE_SWING = "check_valve_swing"
    CHECK_VALVE_LIFT = "check_valve_lift"

    # Entrances and exits
    ENTRANCE_SHARP = "entrance_sharp"
    ENTRANCE_ROUNDED = "entrance_rounded"
    ENTRANCE_PROJECTING = "entrance_projecting"
    EXIT = "exit"

    # Other
    STRAINER_BASKET = "strainer_basket"
    STRAINER_Y = "strainer_y"
    UNION = "union"
    COUPLING = "coupling"


class PipeDefinition(OpenSolvePipeBaseModel):
    """Definition of a pipe segment."""

    material: PipeMaterial = Field(description="Pipe material")
    nominal_diameter: PositiveFloat = Field(
        description="Nominal pipe diameter in project units (typically inches)"
    )
    schedule: str = Field(default="40", description="Pipe schedule or class")
    length: PositiveFloat = Field(description="Pipe length in project units")
    roughness_override: PositiveFloat | None = Field(
        default=None,
        description="Override calculated roughness (absolute roughness in project units)",
    )


class Fitting(OpenSolvePipeBaseModel):
    """A fitting or valve in a piping segment."""

    type: FittingType = Field(description="Type of fitting")
    quantity: PositiveInt = Field(default=1, description="Number of this fitting")
    k_factor_override: PositiveFloat | None = Field(
        default=None,
        description="User-specified K-factor override",
    )
    description: str | None = Field(
        default=None, description="Optional description or notes"
    )


class PipingSegment(OpenSolvePipeBaseModel):
    """A piping segment consisting of a pipe and zero or more fittings."""

    pipe: PipeDefinition = Field(description="The pipe definition")
    fittings: list[Fitting] = Field(
        default_factory=list, description="List of fittings in this segment"
    )
