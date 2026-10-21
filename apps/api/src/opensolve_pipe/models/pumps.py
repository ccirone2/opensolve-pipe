"""Pump curves (project pump library)."""

from itertools import pairwise
from typing import Self

from pydantic import Field, model_validator

from .base import CamelModel, Identifier, Name


class FlowHeadPoint(CamelModel):
    flow: float = Field(ge=0, le=100.0, description="Flow, m³/s")
    head: float = Field(ge=0, le=1.0e4, description="Head, m")


class FlowEfficiencyPoint(CamelModel):
    flow: float = Field(ge=0, le=100.0, description="Flow, m³/s")
    efficiency: float = Field(gt=0, le=1.0, description="Pump efficiency, fraction 0-1")


class FlowNpshrPoint(CamelModel):
    flow: float = Field(ge=0, le=100.0, description="Flow, m³/s")
    npshr: float = Field(ge=0, le=1.0e3, description="NPSH required, m")


def _check_increasing(name: str, flows: list[float]) -> None:
    if any(b <= a for a, b in pairwise(flows)):
        raise ValueError(f"{name} flows must be strictly increasing")


class PumpCurve(CamelModel):
    """Pump performance at rated speed. Curves are fitted with a monotone piecewise cubic."""

    id: Identifier
    name: Name
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    points: list[FlowHeadPoint] = Field(min_length=3, max_length=50)
    efficiency_curve: list[FlowEfficiencyPoint] | None = Field(
        default=None, min_length=2, max_length=50
    )
    npshr_curve: list[FlowNpshrPoint] | None = Field(default=None, min_length=2, max_length=50)

    @model_validator(mode="after")
    def _check_curves(self) -> Self:
        _check_increasing("pump curve", [p.flow for p in self.points])
        if self.efficiency_curve is not None:
            _check_increasing("efficiency curve", [p.flow for p in self.efficiency_curve])
        if self.npshr_curve is not None:
            _check_increasing("NPSHr curve", [p.flow for p in self.npshr_curve])
        return self
