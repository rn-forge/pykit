import asyncio
import os
import subprocess
import sys

import pytest
from assertpy import assert_that
from rn_forge.sqlalchemy import create_postgres_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.conftest import POSTGRES_DSN

pytest_plugins = ["pytester"]

_CONFTEST = 'pytest_plugins = ["rn_forge.sqlalchemy.testing"]\n'
_SKIPPING_TEST = """
import pytest

@pytest.mark.asyncio
async def test_uses_schema(postgres_schema):
    pass
"""
_ARGS = ("-p", "no:randomly", "-p", "no:cacheprovider")


async def _schema_names(dsn: str) -> set[str]:
    admin = create_postgres_engine(dsn)
    try:
        async with admin.connect() as connection:
            rows = await connection.execute(
                text("SELECT schema_name FROM information_schema.schemata")
            )
            return {row[0] for row in rows}
    finally:
        await admin.dispose()


@pytest.mark.unit
def test_postgres_schema_skips_without_dsn(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RN_FORGE_TEST_POSTGRES_DSN", raising=False)
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(_SKIPPING_TEST)
    result = pytester.runpytest("-rs", *_ARGS)
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*RN_FORGE_TEST_POSTGRES_DSN is not set*"])


@pytest.mark.unit
def test_postgres_schema_reads_configured_variable(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_DSN", raising=False)
    pytester.makeini("[pytest]\nrn_forge_postgres_dsn_env = APP_DSN\n")
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(_SKIPPING_TEST)
    result = pytester.runpytest("-rs", *_ARGS)
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*APP_DSN is not set*"])


@pytest.mark.unit
def test_postgres_schema_registers_marker(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.postgres
        def test_marked():
            pass
        """
    )
    result = pytester.runpytest("--strict-markers", *_ARGS)
    result.assert_outcomes(passed=1)


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("run", [1, 2])
async def test_postgres_schema_isolates_tables(postgres_schema, run: int) -> None:
    engine: AsyncEngine = postgres_schema.engine
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE probe (id int)"))
        current = await connection.scalar(text("SELECT current_schema()"))
    assert_that(current).is_equal_to(postgres_schema.name)


@pytest.mark.postgres
def test_postgres_schema_dropped_after_test(pytester: pytest.Pytester) -> None:
    dsn = os.environ.get(POSTGRES_DSN)
    if not dsn:
        pytest.skip(f"{POSTGRES_DSN} is not set")
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        """
        import pytest

        def _record(name):
            with open("names.txt", "a") as handle:
                handle.write(name + "\\n")

        @pytest.mark.asyncio
        async def test_passes(postgres_schema):
            _record(postgres_schema.name)

        @pytest.mark.asyncio
        async def test_fails(postgres_schema):
            _record(postgres_schema.name)
            assert False
        """
    )
    result = pytester.runpytest(*_ARGS)
    result.assert_outcomes(passed=1, failed=1)
    names = (pytester.path / "names.txt").read_text().split()
    assert_that(names).is_length(2)
    assert_that(asyncio.run(_schema_names(dsn)).intersection(names)).is_empty()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_postgres_schema_yields_asyncpg_url(postgres_schema) -> None:
    assert_that(make_url(postgres_schema.url).drivername).is_equal_to(
        "postgresql+asyncpg"
    )
    assert_that(postgres_schema.name).matches(r"^t_[0-9a-f]{32}$")


@pytest.mark.unit
def test_package_root_does_not_import_testing() -> None:
    code = (
        "import sys, rn_forge.sqlalchemy; "
        "print('rn_forge.sqlalchemy.testing' in sys.modules, "
        "'pytest_asyncio' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert_that(completed.stdout.split()).is_equal_to(["False", "False"])
