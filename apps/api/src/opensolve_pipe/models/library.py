"""Library data served to the frontend: pipe materials and sizes, fitting types, methods."""

from pydantic import Field

from .base import OutputModel


class PipeSize(OutputModel):
    nps: str = Field(description="Nominal pipe size designation, inches (e.g. '2-1/2')")
    nominal_size: float = Field(description="NPS in inches x 0.0254, m (the stored value)")
    outer_diameter: float = Field(description="m")
    wall_thickness: float = Field(description="m")
    inner_diameter: float = Field(description="m")


class PipeSchedule(OutputModel):
    id: str
    sizes: list[PipeSize]


class PipeMaterial(OutputModel):
    id: str
    name: str
    roughness: float = Field(description="Absolute roughness, m")
    roughness_source: str
    dimensions_source: str
    schedules: list[PipeSchedule]


class FittingInfo(OutputModel):
    type: str
    name: str
    correlation: str = Field(description="Library function that supplies K")
    parameters: list[str] = Field(description="Fitting fields the correlation uses")
    source: str


class LibraryResponse(OutputModel):
    materials: list[PipeMaterial]
    fittings: list[FittingInfo]


class MethodVersionInfo(OutputModel):
    version: str
    date: str
    changes: list[str]


class MethodVersionsResponse(OutputModel):
    current: str
    versions: list[MethodVersionInfo]
