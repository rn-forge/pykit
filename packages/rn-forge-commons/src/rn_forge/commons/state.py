"""A locked, atomically-written, JSON-backed key -> entry state store.

Provides :class:`StateStore`, generic over a
:class:`~rn_forge.commons.dataclasses.DataclassMixin` entry type — the "what
did I last write where" file both a CLI and a long-running process use to
detect drift between recorded and current state.

Entry validation is the entry type's job: :class:`StateStore` round-trips
entries through ``entry_type.from_dict``/``entry.as_dict``, so a
``__dacite_config__ = dacite.Config(check_types=True)`` entry class gets
strict field validation on load for free — a hand-edited or truncated state
file surfaces as an immediate, clear error instead of an ``AttributeError``
deep inside a later apply.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generic, TypeVar, cast

from rn_forge.commons.dataclasses import DataclassMixin
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.utils import PathUtils

__all__ = ["StateStore"]

_LOGGER = AppLogger.get_logger(__name__)

E = TypeVar("E", bound=DataclassMixin)


class StateStore(Generic[E]):
    """A locked, atomically-written, JSON-backed key -> entry store.

    Args:
        path: The state file.
        entry_type: A :class:`~rn_forge.commons.dataclasses.DataclassMixin`
            subclass; entries round-trip through its ``from_dict``/``as_dict``,
            so validation is the dataclass's job.
        schema_version: Written to the file and checked on load.
    """

    def __init__(
        self, path: str | Path, *, entry_type: type[E], schema_version: str = "1"
    ) -> None:
        self.path = Path(path)
        self._entry_type = entry_type
        self._schema_version = schema_version

    def load(self) -> dict[str, E]:
        """Load and validate every entry, returning ``{}`` when the file is absent.

        Every entry is validated, not just the JSON root — a hand-edited or
        truncated state file that happens to parse would otherwise surface
        far later as an unrelated error deep inside a caller's apply logic.

        Raises:
            AppException: The file is unreadable, is not the expected shape,
                carries an unexpected ``schema_version``, or an entry fails
                ``entry_type.from_dict`` validation.
        """
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AppException("Invalid state file {}: {}", self.path, exc) from exc
        if not isinstance(raw, dict):
            raise AppException("Invalid state file {}: expected an object", self.path)
        document = cast(dict[str, Any], raw)

        file_version = document.get("schema_version")
        if file_version is not None and file_version != self._schema_version:
            raise AppException(
                "Invalid state file {}: schema_version {!r} does not match expected {!r}",
                self.path,
                file_version,
                self._schema_version,
            )

        entries = document.get("entries", {})
        if not isinstance(entries, dict):
            raise AppException(
                "Invalid state file {}: 'entries' must be an object", self.path
            )

        result: dict[str, E] = {}
        for key, value in cast(dict[str, Any], entries).items():
            if not isinstance(value, dict):
                raise AppException(
                    "Invalid state file {}: entry {!r} is not an object", self.path, key
                )
            try:
                result[key] = self._entry_type.from_dict(cast(dict[str, Any], value))
            except Exception as exc:
                raise AppException(
                    "Invalid state file {}: entry {!r} failed validation: {}",
                    self.path,
                    key,
                    exc,
                ) from exc
        return result

    def get(self, key: str) -> E | None:
        """Return the entry for *key*, or ``None`` if it does not exist."""
        return self.load().get(key)

    def record(self, key: str, entry: E) -> None:
        """Record a single entry. One read-modify-write cycle; see :meth:`record_many`."""
        self.record_many({key: entry})

    def record_many(self, entries: Mapping[str, E]) -> None:
        """Record several entries in a single read-modify-write cycle.

        One write per *operation* rather than per entry keeps the window in
        which a concurrent process can clobber entries as small as the file
        lock allows, and leaves the file consistent if the process dies
        mid-write.
        """
        with self.locked():
            data = self.load()
            data.update(entries)
            self._write(data)

    def remove(self, key: str) -> None:
        """Remove *key*'s entry, if present."""
        with self.locked():
            data = self.load()
            data.pop(key, None)
            self._write(data)

    def stale_keys(
        self, exists: Callable[[str], bool] = lambda key: Path(key).exists()
    ) -> list[str]:
        """Return recorded keys for which *exists* returns ``False``.

        Args:
            exists: A predicate deciding whether a key still refers to
                something real. Defaults to treating keys as filesystem
                paths; pass a different predicate when keys are something
                else (e.g. artifact ids).
        """
        return [key for key in self.load() if not exists(key)]

    def _write(self, data: dict[str, E]) -> None:
        payload = {
            "schema_version": self._schema_version,
            "entries": {key: entry.as_dict() for key, entry in data.items()},
        }
        PathUtils.atomic_write(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", self.path
        )

    @contextmanager
    def locked(self) -> Generator[None]:
        """Serialize read-modify-write cycles against other processes.

        Advisory and best-effort: on a platform/filesystem without ``flock``
        support the update proceeds unserialized rather than failing the
        caller — a personal dev tool must not fail a command because the
        filesystem underneath it is unusual. Use this (rather than
        :class:`~rn_forge.commons.utils.DirectoryLock`) when a failed lock
        should degrade to unlocked; use ``DirectoryLock`` when the lock must
        actually hold.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(".lock")
        try:
            handle = lock_path.open("w")
        except OSError:
            yield
            return
        try:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except ImportError, OSError:
                _LOGGER.trace(
                    "StateStore.locked: flock unavailable, proceeding unlocked"
                )
            yield
        finally:
            handle.close()
