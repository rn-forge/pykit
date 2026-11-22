"""A pytest plugin that gives each test its own PostgreSQL schema.

Load it explicitly in the root ``conftest.py``::

    pytest_plugins = ["rn_forge.sqlalchemy.testing"]

It needs the ``testing`` and ``postgres`` extras. It registers the ``postgres``
marker and the ``rn_forge_postgres_dsn_env`` ini option, the name of the
environment variable that holds the DSN.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
import pytest_asyncio
from rn_forge.sqlalchemy.postgres import create_postgres_engine
from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = ["PostgresSchema", "postgres_schema"]


@dataclass(frozen=True)
class PostgresSchema:
    """A PostgreSQL schema created for one test.

    Attributes:
        name: The schema name, ``"t_"`` followed by 32 hexadecimal digits.
        url: The DSN with the ``postgresql+asyncpg`` driver, password included.
        engine: An engine whose connections use the schema as their
            ``search_path``.
    """

    name: str
    url: str
    engine: AsyncEngine


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``rn_forge_postgres_dsn_env`` ini option."""
    parser.addini(
        "rn_forge_postgres_dsn_env",
        help="Name of the environment variable that holds the PostgreSQL DSN",
        default="RN_FORGE_TEST_POSTGRES_DSN",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``postgres`` marker."""
    config.addinivalue_line(
        "markers",
        "postgres: needs a PostgreSQL server (DSN from rn_forge_postgres_dsn_env)",
    )


@pytest_asyncio.fixture
async def postgres_schema(
    request: pytest.FixtureRequest,
) -> AsyncIterator[PostgresSchema]:
    """Yield a `PostgresSchema` that exists for one test.

    The test skips when the environment variable named by
    ``rn_forge_postgres_dsn_env`` is unset or empty. The schema is dropped with
    ``CASCADE`` after the test, whether it passed or failed.
    """
    variable = str(request.config.getini("rn_forge_postgres_dsn_env"))
    dsn = os.environ.get(variable)
    if not dsn:
        pytest.skip(f"{variable} is not set")
    name = "t_" + uuid4().hex
    admin = create_postgres_engine(dsn)
    try:
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{name}"')
        engine = create_postgres_engine(dsn, search_path=name)
        url = engine.url.render_as_string(hide_password=False)
        try:
            yield PostgresSchema(name, url, engine)
        finally:
            await engine.dispose()
    finally:
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        await admin.dispose()
