"""Shared Pydantic base class: camelCase JSON, snake_case Python, unknown fields rejected."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for every API and project model.

    JSON uses camelCase (matching the TypeScript models); Python code uses snake_case.
    Unknown fields are rejected so that typos in a project never pass silently.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        serialize_by_alias=True,
    )


class OutputModel(CamelModel):
    """Base for response-only models. They declare no defaults, so every field is required
    in the generated schema and TypeScript types (the server always sends it, maybe null)."""


Identifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Letters, digits, '_' or '-' (no ':', so node keys stay unambiguous)",
    ),
]

Name = Annotated[str, Field(min_length=1, max_length=100)]

Elevation = Annotated[
    float, Field(ge=-1.0e4, le=1.0e4, description="Elevation above the project datum, m")
]

GaugePressure = Annotated[
    float,
    Field(
        ge=-1.0e5,
        le=1.0e8,
        description="Gauge pressure, Pa (relative to the project's atmospheric pressure)",
    ),
]
