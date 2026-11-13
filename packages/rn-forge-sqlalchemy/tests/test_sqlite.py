from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from assertpy import assert_that
from rn_forge.sqlalchemy import create_sqlite_engine
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.unit


@pytest_asyncio.fixture
async def make_engine() -> AsyncIterator[Callable[..., AsyncEngine]]:
    engines: list[AsyncEngine] = []

    def make(path: str | Path, **kwargs: object) -> AsyncEngine:
        engine = create_sqlite_engine(path, **kwargs)  # type: ignore[arg-type]
        engines.append(engine)
        return engine

    yield make
    for engine in engines:
        await engine.dispose()


async def _pragma(engine: AsyncEngine, name: str) -> object:
    async with AsyncSession(engine) as session:
        return (await session.execute(text(f"PRAGMA {name}"))).scalar_one()


@pytest.mark.asyncio
async def test_defaults_are_applied(make_engine, tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "app.db", busy_timeout_ms=1234)

    assert_that(await _pragma(engine, "journal_mode")).is_equal_to("wal")
    assert_that(await _pragma(engine, "foreign_keys")).is_equal_to(1)
    assert_that(await _pragma(engine, "busy_timeout")).is_equal_to(1234)
    assert_that(await _pragma(engine, "synchronous")).is_equal_to(1)


@pytest.mark.asyncio
async def test_flags_false_leave_sqlite_defaults(make_engine, tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "app.db", wal=False, foreign_keys=False)

    assert_that(await _pragma(engine, "journal_mode")).is_equal_to("delete")
    assert_that(await _pragma(engine, "foreign_keys")).is_equal_to(0)


@pytest.mark.asyncio
async def test_synchronous_is_case_insensitive(make_engine, tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "app.db", synchronous="full")

    assert_that(await _pragma(engine, "synchronous")).is_equal_to(2)


@pytest.mark.asyncio
async def test_invalid_arguments_fail_before_any_side_effect(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "app.db"

    with pytest.raises(ValueError, match="synchronous"):
        create_sqlite_engine(target, synchronous="NORMAL; DROP TABLE x")
    with pytest.raises(ValueError, match="invalid literal"):
        create_sqlite_engine(target, busy_timeout_ms="1; --")  # type: ignore[arg-type]

    assert_that(target.parent.exists()).is_false()


@pytest.mark.asyncio
async def test_parent_directory_is_created(make_engine, tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "app.db"
    engine = make_engine(target)

    await _pragma(engine, "journal_mode")

    assert_that(target.is_file()).is_true()


@pytest.mark.asyncio
async def test_path_with_url_special_characters(make_engine, tmp_path: Path) -> None:
    target = tmp_path / "my dir#1?x" / "app db.sqlite"
    engine = make_engine(target)

    assert_that(await _pragma(engine, "journal_mode")).is_equal_to("wal")
    assert_that(target.is_file()).is_true()


@pytest.mark.asyncio
async def test_no_tables_are_created(make_engine, tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "app.db")

    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())

    assert_that(tables).is_empty()


@pytest.mark.asyncio
async def test_foreign_key_violation_raises(make_engine, tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "app.db")
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        await connection.execute(
            text(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parent (id))"
            )
        )

    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(text("INSERT INTO child VALUES (1, 99)"))


@pytest.mark.asyncio
async def test_foreign_key_violation_allowed_when_off(
    make_engine, tmp_path: Path
) -> None:
    engine = make_engine(tmp_path / "app.db", foreign_keys=False)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        await connection.execute(
            text(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parent (id))"
            )
        )
        await connection.execute(text("INSERT INTO child VALUES (1, 99)"))


@pytest.mark.asyncio
async def test_memory_sessions_share_one_database(make_engine) -> None:
    engine = make_engine(":memory:")
    async with AsyncSession(engine) as first:
        await first.execute(text("CREATE TABLE t (id INTEGER)"))
        await first.commit()

    async with AsyncSession(engine) as second:
        rows = (await second.execute(text("SELECT count(*) FROM t"))).scalar_one()

    assert_that(rows).is_equal_to(0)
    assert_that(await _pragma(engine, "journal_mode")).is_equal_to("memory")
    assert_that(await _pragma(engine, "foreign_keys")).is_equal_to(1)
