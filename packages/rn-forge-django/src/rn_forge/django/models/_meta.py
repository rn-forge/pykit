"""Typing helpers for Django model metadata access."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, cast

__all__ = [
    "ModelFieldProtocol",
    "ModelMetaProtocol",
    "get_model_meta",
]


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class ModelFieldProtocol(Protocol):
    """Minimal field metadata used by rn-forge-django model helpers."""

    primary_key: bool
    name: str
    attname: str


class ModelMetaProtocol(Protocol):
    """Minimal narrowed shape of Django's private ``_meta`` object."""

    db_table: str
    model_name: str
    concrete_fields: Iterable[ModelFieldProtocol]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_model_meta(model_class: type[object]) -> ModelMetaProtocol:
    """Return the narrowed ``_meta`` shape for a Django model class."""
    meta = getattr(model_class, "_meta", None)
    if meta is None:
        raise TypeError(f"Not a Django model class: {model_class}")

    return cast(ModelMetaProtocol, meta)
