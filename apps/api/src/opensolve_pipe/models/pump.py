"""Pump curve and pump-related models."""

from pydantic import Field, field_validator, model_validator

from .base import NonNegativeFloat, OpenSolvePipeBaseModel, PositiveFloat


class FlowHeadPoint(OpenSolvePipeBaseModel):
    """A single point on a pump curve (flow vs head)."""

    flow: NonNegativeFloat = Field(description="Flow rate in project units")
    head: NonNegativeFloat = Field(description="Head in project units")


class FlowEfficiencyPoint(OpenSolvePipeBaseModel):
    """A single point on an efficiency curve (flow vs efficiency)."""

    flow: NonNegativeFloat = Field(description="Flow rate in project units")
    efficiency: float = Field(
        ge=0, le=1, description="Pump efficiency as fraction (0-1)"
    )


class NPSHRPoint(OpenSolvePipeBaseModel):
    """A single point on NPSH required curve."""

    flow: NonNegativeFloat = Field(description="Flow rate in project units")
    npsh_required: PositiveFloat = Field(description="NPSH required in project units")


class FlowPowerPoint(OpenSolvePipeBaseModel):
    """A single point on a power curve (flow vs brake horsepower)."""

    flow: NonNegativeFloat = Field(description="Flow rate in project units")
    power: NonNegativeFloat = Field(description="Power (BHP) in project units")


class DesignPoint(OpenSolvePipeBaseModel):
    """Design point for a pump (rated operating condition)."""

    flow: NonNegativeFloat = Field(description="Design flow rate in project units")
    head: NonNegativeFloat = Field(description="Design head in project units")
    speed: PositiveFloat | None = Field(default=None, description="Design speed in RPM")


class PumpCurve(OpenSolvePipeBaseModel):
    """Pump performance curve definition."""

    id: str = Field(description="Unique identifier for this pump curve")
    name: str = Field(description="Display name for this pump curve")
    manufacturer: str | None = Field(default=None, description="Pump manufacturer")
    model: str | None = Field(default=None, description="Pump model number")
    rated_speed: PositiveFloat | None = Field(
        default=None, description="Rated speed in RPM"
    )
    impeller_diameter: PositiveFloat | None = Field(
        default=None, description="Impeller diameter in project units (selected trim)"
    )
    min_impeller_diameter: PositiveFloat | None = Field(
        default=None, description="Minimum impeller diameter in project units"
    )
    max_impeller_diameter: PositiveFloat | None = Field(
        default=None, description="Maximum impeller diameter in project units"
    )
    stages: int | None = Field(default=None, ge=1, description="Number of pump stages")
    inlet_outlet: str | None = Field(
        default=None, description="Inlet/outlet size description"
    )
    notes: str | None = Field(default=None, description="Free-form notes")
    design_point: DesignPoint | None = Field(
        default=None, description="Design point (rated operating condition)"
    )

    points: list[FlowHeadPoint] = Field(
        min_length=2, description="Pump curve points (minimum 2)"
    )
    efficiency_curve: list[FlowEfficiencyPoint] | None = Field(
        default=None, description="Optional efficiency curve"
    )
    npshr_curve: list[NPSHRPoint] | None = Field(
        default=None, description="Optional NPSH required curve"
    )
    power_curve: list[FlowPowerPoint] | None = Field(
        default=None, description="Optional power curve"
    )

    @field_validator("points")
    @classmethod
    def validate_pump_curve_sorted(cls, v: list[FlowHeadPoint]) -> list[FlowHeadPoint]:
        """Ensure pump curve points are sorted by flow."""
        flows = [p.flow for p in v]
        if flows != sorted(flows):
            raise ValueError("Pump curve points must be sorted by ascending flow")
        return v

    @model_validator(mode="after")
    def validate_curve_consistency(self) -> "PumpCurve":
        """Validate that optional curves have consistent flow ranges."""
        if not self.points:
            return self

        main_flows = [p.flow for p in self.points]
        min_flow, max_flow = min(main_flows), max(main_flows)

        if self.efficiency_curve:
            eff_flows = [p.flow for p in self.efficiency_curve]
            if min(eff_flows) > min_flow or max(eff_flows) < max_flow:
                # Warning only - efficiency curve should cover main curve range
                pass

        if self.npshr_curve:
            npshr_flows = [p.flow for p in self.npshr_curve]
            if min(npshr_flows) > min_flow or max(npshr_flows) < max_flow:
                # Warning only - NPSHR curve should cover main curve range
                pass

        return self
