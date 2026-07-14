"""Shared typing helpers for Django model metadata access.

This module centralizes the small protocol surface used by rn-forge-django when
working with Django's private ``_meta`` attribute. It is intentionally kept
inside the ``models`` package because both model infrastructure and model
utilities rely on it.
"""

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
    """Return the narrowed ``_meta`` shape for a Django model class.

    This helper centralizes access to Django's private ``_meta`` attribute so
    callers can rely on a small stable protocol instead of repeated ad-hoc
    casts.
    """
    meta = getattr(model_class, "_meta", None)
    if meta is None:
        raise TypeError(f"Not a Django model class: {model_class}")

    return cast(ModelMetaProtocol, meta)
