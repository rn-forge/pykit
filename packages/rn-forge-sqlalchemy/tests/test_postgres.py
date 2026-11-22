import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import pytest_asyncio
from assertpy import assert_that
from rn_forge.sqlalchemy import create_postgres_engine
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.conftest import POSTGRES_DSN

_URL = "postgresql://u:p@localhost/db"


class _Stop(Exception):
    pass


@pytest_asyncio.fixture
async def make_engine() -> AsyncIterator[Callable[..., AsyncEngine]]:
    engines: list[AsyncEngine] = []

    def make(url: Any = _URL, **kwargs: Any) -> AsyncEngine:
        engine = create_postgres_engine(url, **kwargs)
        engines.append(engine)
        return engine

    yield make
    for engine in engines:
        await engine.dispose()


async def _cparams(engine: AsyncEngine) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    @event.listens_for(engine.sync_engine, "do_connect")
    def _record(_dialect: Any, _rec: Any, _cargs: Any, cparams: dict[str, Any]) -> None:
        seen.update(cparams)
        raise _Stop

    with pytest.raises(Exception):  # noqa: B017
        await engine.connect()
    return seen


@pytest.mark.unit
@pytest.mark.parametrize(
    "url", ["postgresql://u@h/d", "postgres://u@h/d", "postgresql+asyncpg://u@h/d"]
)
def test_create_postgres_engine_rewrites_accepted_schemes(make_engine, url) -> None:
    assert_that(make_engine(url).url.drivername).is_equal_to("postgresql+asyncpg")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("url", "name"),
    [
        ("postgresql+psycopg://u@h/d", "postgresql+psycopg"),
        ("sqlite:///x.db", "sqlite"),
    ],
)
def test_create_postgres_engine_rejects_other_schemes(make_engine, url, name) -> None:
    assert_that(make_engine).raises(ValueError).when_called_with(url).contains(name)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_postgres_engine_sets_utc_timezone_server_setting(
    make_engine,
) -> None:
    cparams = await _cparams(make_engine())

    assert_that(cparams["server_settings"]).is_equal_to({"timezone": "UTC"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_postgres_engine_adds_optional_server_settings_only_when_given(
    make_engine,
) -> None:
    engine = make_engine(application_name="svc", statement_timeout_ms=1500)

    cparams = await _cparams(engine)

    assert_that(cparams["server_settings"]).is_equal_to(
        {"timezone": "UTC", "application_name": "svc", "statement_timeout": "1500"}
    )


@pytest.mark.unit
def test_create_postgres_engine_passes_pool_arguments(make_engine) -> None:
    engine = make_engine(
        pool_size=3, max_overflow=7, pool_pre_ping=False, pool_recycle_s=60
    )
    pool: Any = engine.pool

    assert_that(pool.size()).is_equal_to(3)
    assert_that(pool._max_overflow).is_equal_to(7)
    assert_that(pool._pre_ping).is_false()
    assert_that(pool._recycle).is_equal_to(60)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 25])
async def test_create_postgres_engine_passes_prepared_statement_cache_size(
    make_engine, size
) -> None:
    cparams = await _cparams(make_engine(prepared_statement_cache_size=size))

    assert_that(cparams["prepared_statement_cache_size"]).is_equal_to(size)
    assert_that(cparams["statement_cache_size"]).is_equal_to(size)


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    [
        "pool_size",
        "max_overflow",
        "pool_recycle_s",
        "prepared_statement_cache_size",
        "statement_timeout_ms",
    ],
)
def test_create_postgres_engine_rejects_negative_arguments(make_engine, name) -> None:
    assert_that(make_engine).raises(ValueError).when_called_with(
        _URL, **{name: -1}
    ).contains(name)


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_create_postgres_engine_connection_reports_utc(make_engine) -> None:
    dsn = os.environ.get(POSTGRES_DSN)
    if not dsn:
        pytest.skip(f"{POSTGRES_DSN} is not set")
    engine = make_engine(dsn, application_name="rn-forge-test")

    async with engine.connect() as connection:
        tz = (await connection.execute(text("SHOW timezone"))).scalar_one()
        app = (
            await connection.execute(text("SELECT current_setting('application_name')"))
        ).scalar_one()

    assert_that(tz).is_equal_to("UTC")
    assert_that(app).is_equal_to("rn-forge-test")
