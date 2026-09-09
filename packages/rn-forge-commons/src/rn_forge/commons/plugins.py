"""Failure-isolated plugin discovery via Python entry points.

Provides :class:`EntryPointLoader`, generic over the expected plugin type. A
third-party entry point runs arbitrary code at import time — one broken
plugin must never take down the host process, so each is loaded in isolation
and its failure recorded as a :class:`PluginError` rather than raised.

What stays out of this module (and belongs in the consumer instead): name
validation rules, "is this name reserved" policy, and any domain-specific
compatibility checks between plugins — those are the consumer's contract, not
a generic plugin-loading concern. This loader also generalizes to isolating
other late-bound extension points (e.g. a CLI's own extension-mounting step)
beyond entry points specifically, though only the entry-point case is
implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Generic, TypeVar

from rn_forge.commons.dataclasses import DataclassMixin

__all__ = ["EntryPointLoader", "PluginError"]

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PluginError(DataclassMixin):
    """One entry point that could not be turned into a usable plugin."""

    entry_point: str
    reason: str


class EntryPointLoader(Generic[T]):
    """Load an entry-point group, isolating each plugin's failure.

    A third-party entry point runs arbitrary code at import time. One broken
    plugin must never take down the host process, so each is loaded in
    isolation and its failure recorded rather than raised.
    """

    def __init__(self, group: str, *, expected_type: type[T]) -> None:
        """Initialize :class:`EntryPointLoader`.

        Args:
            group: The entry-point group to discover, e.g. ``"myapp.plugins"``.
            expected_type: The type every loaded plugin object must be an
                instance of.
        """
        self._group = group
        self._expected_type = expected_type
        self._cache: tuple[list[T], list[PluginError]] | None = None

    def load(self, *, refresh: bool = False) -> tuple[list[T], list[PluginError]]:
        """Return loaded plugins and any failures, sorted by entry-point name.

        Sorting by name means discovery order — and anything depending on
        it — never depends on install order. A loaded object that is a class
        or other callable is instantiated with no arguments; an
        already-constructed instance is used as-is.

        Args:
            refresh: Rebuild the cache instead of reusing a prior call's
                result.

        Returns:
            A ``(plugins, errors)`` pair.
        """
        if self._cache is not None and not refresh:
            return self._cache

        plugins: list[T] = []
        errors: list[PluginError] = []
        for point in sorted(entry_points(group=self._group), key=lambda p: p.name):
            try:
                loaded: Any = point.load()
                instance = (
                    loaded() if isinstance(loaded, type) or callable(loaded) else loaded
                )
                if not isinstance(instance, self._expected_type):
                    raise TypeError(
                        f"{point.value} did not produce a {self._expected_type.__name__}"
                    )
            except Exception as exc:  # noqa: BLE001 - one plugin must not break all
                errors.append(PluginError(point.name, f"{type(exc).__name__}: {exc}"))
                continue
            plugins.append(instance)

        self._cache = (plugins, errors)
        return self._cache
