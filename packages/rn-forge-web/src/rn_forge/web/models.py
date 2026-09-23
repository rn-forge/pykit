"""The pydantic base of every model that crosses the wire."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

__all__ = ["WireModel"]


class WireModel(BaseModel):
    """Base for every model that crosses the wire: camelCase out, either spelling in.

    Serialization uses aliases by default; validation accepts aliases and
    Python field names.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )
