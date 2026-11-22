"""An engine per dialect: SQLite always, PostgreSQL when a DSN is set."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from rn_forge.sqlalchemy import Base
from rn_forge.sqlalchemy.testing import PostgresSchema
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

pytest_plugins = ["rn_forge.sqlalchemy.testing"]

POSTGRES_DSN = "RN_FORGE_TEST_POSTGRES_DSN"


@pytest_asyncio.fixture
async def sqlite_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def dialect_engine(request: pytest.FixtureRequest) -> AsyncEngine:
    # An async fixture cannot resolve another async fixture while its loop runs,
    # so a sync fixture picks the dialect.
    if request.param == "sqlite":
        return request.getfixturevalue("sqlite_engine")
    schema: PostgresSchema = request.getfixturevalue("postgres_schema")
    return schema.engine


@pytest_asyncio.fixture
async def engine(dialect_engine: AsyncEngine) -> AsyncEngine:
    async with dialect_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return dialect_engine


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
