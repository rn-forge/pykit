"""An async SQLite engine with its pragmas set on every connection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

__all__ = ["create_sqlite_engine"]

_MEMORY = ":memory:"
_SYNCHRONOUS = frozenset({"OFF", "NORMAL", "FULL", "EXTRA"})


def create_sqlite_engine(
    path: str | Path,
    *,
    wal: bool = True,
    busy_timeout_ms: int = 5000,
    foreign_keys: bool = True,
    synchronous: str = "NORMAL",
) -> AsyncEngine:
    """Create an ``AsyncEngine`` on a SQLite file with pragmas set per connection.

    The parent directory of *path* is created. Every new connection runs
    ``busy_timeout``, then ``journal_mode=WAL`` when *wal* is true,
    ``synchronous``, and ``foreign_keys=ON`` when *foreign_keys* is true. A false
    flag leaves that pragma at SQLite's default. No tables are created.

    The exact string ``":memory:"`` opens an in-memory database: no directory is
    created, WAL is not enabled, and a ``StaticPool`` makes every session share
    one connection. ``Path(":memory:")`` is an ordinary file named ``:memory:``.

    Args:
        path: The database file, or the string ``":memory:"``.
        wal: Enable write-ahead logging.
        busy_timeout_ms: Milliseconds a connection waits on a locked database.
        foreign_keys: Enforce foreign-key constraints.
        synchronous: ``OFF``, ``NORMAL``, ``FULL`` or ``EXTRA``, in any case.

    Returns:
        The engine, using the ``sqlite+aiosqlite`` driver.

    Raises:
        ValueError: *synchronous* is not one of the allowed values.
        ValueError: *busy_timeout_ms* cannot be converted to an integer.
    """
    level = synchronous.upper()
    if level not in _SYNCHRONOUS:
        allowed = ", ".join(sorted(_SYNCHRONOUS))
        raise ValueError(f"synchronous must be one of {allowed}, got {synchronous!r}")
    timeout = int(busy_timeout_ms)

    in_memory = isinstance(path, str) and path == _MEMORY
    # PRAGMA values cannot be bound parameters, so they are validated above.
    # busy_timeout goes first so the caller's value also covers journal_mode,
    # whose first switch to WAL needs an exclusive lock.
    pragmas = [f"PRAGMA busy_timeout={timeout}"]
    if wal and not in_memory:
        pragmas.append("PRAGMA journal_mode=WAL")
    pragmas.append(f"PRAGMA synchronous={level}")
    if foreign_keys:
        pragmas.append("PRAGMA foreign_keys=ON")

    kwargs: dict[str, Any] = {}
    if in_memory:
        kwargs["poolclass"] = StaticPool
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    url = URL.create("sqlite+aiosqlite", database=str(path))
    engine = create_async_engine(url, **kwargs)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for pragma in pragmas:
                cursor.execute(pragma)
        finally:
            cursor.close()

    return engine
