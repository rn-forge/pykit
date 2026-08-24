"""Caching helpers for model instance lookup."""

from __future__ import annotations

from operator import attrgetter
from typing import Any, Protocol, cast

from rn_forge.commons.utils import AppUtils

__all__ = ["ModelLookupCache"]


class _ModelClassProtocol[_ModelClassT_co](Protocol):
    objects: Any


def _cache_namespace(model_class: type[object]) -> str:
    """Return a stable cache namespace for a model class."""
    meta = getattr(model_class, "_meta", None)
    label_lower = getattr(meta, "label_lower", None)
    if isinstance(label_lower, str) and label_lower:
        return label_lower
    return f"{model_class.__module__}.{model_class.__qualname__}"


class ModelLookupCache:
    """In-memory cache for bulk-loaded model instances.

    Typical use: load all rows of a reference table once at startup, then
    resolve foreign-key values in O(1) rather than issuing per-row queries.

    Example::

        cache = ModelLookupCache()
        cache.load(Country, "iso_code")
        country = cache.get(Country, "AU")
    """

    __slots__ = ("__cache",)

    def __init__(self) -> None:
        self.__cache: dict[str, dict[str, object]] = {}

    def load[_ModelT](self, model_class: type[_ModelT], *model_keys: str) -> None:
        """Bulk-load all instances of *model_class* and index by *model_keys*."""
        key_getter = attrgetter(*model_keys)
        typed_model_class = cast(_ModelClassProtocol[_ModelT], model_class)
        self.__cache[_cache_namespace(model_class)] = {
            AppUtils.join_string(".", key_getter(instance)): instance
            for instance in typed_model_class.objects.select_related()
        }

    def get[_ModelT](
        self, model_class: type[_ModelT], *model_key_values: str
    ) -> _ModelT | None:
        """Return the cached instance matching *model_key_values*, or ``None``."""
        return cast(
            _ModelT | None,
            self.__cache.get(_cache_namespace(model_class), {}).get(
                AppUtils.join_string(".", model_key_values)
            ),
        )

    def set[_ModelT](
        self, model_class: type[_ModelT], instance: _ModelT, *model_keys: str
    ) -> None:
        """Insert or update *instance* in the cache."""
        key_getter = attrgetter(*model_keys)
        self.__cache.setdefault(_cache_namespace(model_class), {})[
            AppUtils.join_string(".", key_getter(instance))
        ] = instance
