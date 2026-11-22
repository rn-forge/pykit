"""An async PostgreSQL engine on asyncpg with UTC sessions and pool settings."""

from __future__ import annotations

import importlib
from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

__all__ = ["create_postgres_engine"]

_DRIVERNAMES = frozenset({"postgresql", "postgres", "postgresql+asyncpg"})


def create_postgres_engine(
    url: str | URL,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_pre_ping: bool = True,
    pool_recycle_s: int = 1800,
    statement_timeout_ms: int | None = None,
    application_name: str | None = None,
    prepared_statement_cache_size: int = 100,
) -> AsyncEngine:
    """Create an ``AsyncEngine`` on PostgreSQL through ``asyncpg``.

    Every connection sets the session time zone to UTC, plus
    ``application_name`` and ``statement_timeout`` when given. The engine does
    not connect and creates no tables.

    Args:
        url: A ``postgresql://``, ``postgres://`` or ``postgresql+asyncpg://``
            URL, as a string or a SQLAlchemy ``URL``. The driver is rewritten
            to ``postgresql+asyncpg``.
        pool_size: Connections kept in the pool.
        max_overflow: Connections allowed beyond *pool_size*.
        pool_pre_ping: Test a connection before handing it out.
        pool_recycle_s: Seconds after which a connection is replaced.
        statement_timeout_ms: Milliseconds before the server cancels a
            statement; ``None`` leaves the server default.
        application_name: The ``application_name`` the server reports;
            ``None`` leaves the driver default.
        prepared_statement_cache_size: Size of both the SQLAlchemy and asyncpg
            prepared-statement caches; ``0`` turns them off.

    Returns:
        The engine, using the ``postgresql+asyncpg`` driver.

    Raises:
        ValueError: *url* names a driver other than PostgreSQL with asyncpg.
        ValueError: *pool_size*, *max_overflow*, *pool_recycle_s*,
            *prepared_statement_cache_size* or *statement_timeout_ms* is
            negative.
        ImportError: ``asyncpg`` is not installed.
    """
    parsed = make_url(url)
    if parsed.drivername not in _DRIVERNAMES:
        raise ValueError(
            f"create_postgres_engine needs a postgresql:// URL, "
            f"got {parsed.drivername!r}"
        )
    numbers = {
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_recycle_s": pool_recycle_s,
        "prepared_statement_cache_size": prepared_statement_cache_size,
    }
    if statement_timeout_ms is not None:
        numbers["statement_timeout_ms"] = statement_timeout_ms
    for name, value in numbers.items():
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")
    try:
        importlib.import_module("asyncpg")
    except ImportError as error:
        raise ImportError(
            "create_postgres_engine needs asyncpg; install rn-forge-sqlalchemy[postgres]"
        ) from error

    # asyncpg needs string values for server settings.
    settings = {"timezone": "UTC"}
    if application_name is not None:
        settings["application_name"] = application_name
    if statement_timeout_ms is not None:
        settings["statement_timeout"] = str(statement_timeout_ms)
    # SQLAlchemy's dialect reads prepared_statement_cache_size as a connect
    # argument; statement_cache_size is asyncpg's own cache.
    connect_args: dict[str, Any] = {
        "server_settings": settings,
        "prepared_statement_cache_size": prepared_statement_cache_size,
        "statement_cache_size": prepared_statement_cache_size,
    }
    return create_async_engine(
        parsed.set(drivername="postgresql+asyncpg"),
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=pool_recycle_s,
        connect_args=connect_args,
    )
