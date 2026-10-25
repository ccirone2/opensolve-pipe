"""Library data served to the frontend: pipe materials and sizes, fitting types, methods, and
the server's own version and source."""

from pydantic import Field

from .base import OutputModel


class PipeSize(OutputModel):
    nps: str = Field(description="Nominal pipe size designation, inches (e.g. '2-1/2')")
    nominal_size: float = Field(description="NPS in inches x 0.0254, m (the stored value)")
    outer_diameter: float = Field(description="m")
    wall_thickness: float = Field(description="m")
    inner_diameter: float = Field(description="m")
    roughness: float = Field(description="Absolute roughness at this size, m")


class PipeSchedule(OutputModel):
    id: str
    sizes: list[PipeSize]


class PipeMaterial(OutputModel):
    id: str
    name: str
    roughness: float = Field(description="Representative absolute roughness, m")
    roughness_source: str
    dimensions_source: str
    notes: str
    schedules: list[PipeSchedule]


class FittingInfo(OutputModel):
    type: str
    name: str
    correlation: str = Field(description="Library function call that supplies K")
    parameters: list[str] = Field(description="Fitting fields the correlation uses")
    reference_diameter: str = Field(description="Pipe whose velocity K is referenced to")
    valid_in_laminar_flow: bool
    notes: list[str]
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


class AboutResponse(OutputModel):
    """The server's version and the source of the commit it runs (AGPL-3.0 §13; TSD §11.2)."""

    name: str
    version: str = Field(description="The API package version")
    method_version: str = Field(description="The current calculation-method version (GOALS §4.3)")
    commit: str | None = Field(
        description="The commit this server was built from; null when the image records none"
    )
    source: str = Field(description="The source code at that commit, else the repository")
    license: str = Field(description="SPDX license identifier")
    license_url: str = Field(description="The license text at that commit")
