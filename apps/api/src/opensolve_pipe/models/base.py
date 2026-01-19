"""Base model configuration and common types for OpenSolve Pipe."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class OpenSolvePipeBaseModel(BaseModel):
    """Base model with common configuration for all OpenSolve Pipe models."""

    model_config = ConfigDict(
        populate_by_name=True,  # Allow field aliases
        validate_assignment=True,  # Validate on attribute assignment
        extra="forbid",  # Fail on unknown fields
        str_strip_whitespace=True,  # Strip whitespace from strings
    )


# Type aliases for physical quantities with validation
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]

# Physical quantity type aliases (for documentation clarity)
Length = float  # In project units (typically ft or m)
Diameter = float  # In project units (typically in or mm)
Pressure = float  # In project units (typically psi or kPa)
Head = float  # In project units (typically ft or m)
Flow = float  # In project units (typically GPM or L/s)
Velocity = float  # In project units (typically ft/s or m/s)
Temperature = float  # In project units (typically F or C)
Elevation = float  # Can be negative (below sea level)
