import asyncio
import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from assertpy import assert_that
from rn_forge.sqlalchemy import create_sqlite_engine
from rn_forge.sqlalchemy.migrate import run_migrations
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit

_ENV = """
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def _run(connection):
    context.configure(connection=connection, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def _online():
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


asyncio.run(_online())
"""

_REVISION = """
from alembic import op

revision = "{rev}"
down_revision = {down!r}
branch_labels = None
depends_on = None


def upgrade():
    {body}
"""

_INI = """
[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = ERROR
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic

[formatter_generic]
format = %(message)s
"""


def _scripts(root: Path, name: str, *, second: str | None = None) -> Path:
    """Write a two-revision script directory; module names are unique per test."""
    directory = root / name
    (directory / "versions").mkdir(parents=True)
    (directory / "env.py").write_text(_ENV)
    bodies = {
        "r1": 'op.execute("CREATE TABLE one (id INTEGER)")',
        "r2": second or 'op.execute("CREATE TABLE two (id INTEGER)")',
    }
    for rev, down in (("r1", None), ("r2", "r1")):
        (directory / "versions" / f"{name}_{rev}.py").write_text(
            _REVISION.format(
                rev=f"{name}_{rev}", down=down and f"{name}_{down}", body=bodies[rev]
            )
        )
    return directory


def _url(path: Path) -> str:
    return URL.create("sqlite+aiosqlite", database=str(path)).render_as_string(
        hide_password=False
    )


async def _state(path: Path) -> tuple[set[str], list[str]]:
    engine = create_sqlite_engine(path)
    try:
        async with AsyncSession(engine) as session:
            tables = {
                row[0]
                for row in await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'")
                )
            }
            versions = (
                [
                    r[0]
                    for r in await session.execute(
                        text("SELECT * FROM alembic_version")
                    )
                ]
                if "alembic_version" in tables
                else []
            )
    finally:
        await engine.dispose()
    return tables, versions


@pytest.mark.asyncio
async def test_reaches_head_and_is_idempotent(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path, "head")
    db = tmp_path / "app.db"

    for _ in range(2):
        await asyncio.to_thread(run_migrations, scripts, _url(db))
        tables, versions = await _state(db)
        assert_that(tables).contains("one", "two")
        assert_that(versions).is_equal_to(["head_r2"])


@pytest.mark.asyncio
async def test_specific_revision(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path, "pinned")
    db = tmp_path / "app.db"

    await asyncio.to_thread(run_migrations, scripts, _url(db), revision="pinned_r1")

    tables, versions = await _state(db)
    assert_that(tables).contains("one").does_not_contain("two")
    assert_that(versions).is_equal_to(["pinned_r1"])


@pytest.mark.asyncio
async def test_failing_revision_raises_unchanged(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path, "boom", second='raise RuntimeError("boom")')

    with pytest.raises(RuntimeError, match="boom"):
        await asyncio.to_thread(run_migrations, scripts, _url(tmp_path / "app.db"))


@pytest.mark.asyncio
async def test_percent_in_url_and_path(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path / "100%", "pct")
    db = tmp_path / "a%20b.db"

    await asyncio.to_thread(run_migrations, scripts, _url(db))

    assert_that((await _state(db))[1]).is_equal_to(["pct_r2"])


@pytest.mark.asyncio
async def test_package_resource_script_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "libs" / "mig_pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    _scripts(package, "migrations")
    monkeypatch.syspath_prepend(str(tmp_path / "libs"))
    db = tmp_path / "app.db"

    await asyncio.to_thread(run_migrations, "mig_pkg:migrations", _url(db))

    assert_that((await _state(db))[1]).is_equal_to(["migrations_r2"])


@pytest.mark.asyncio
async def test_root_logger_is_not_reconfigured(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path, "logs")
    ini = tmp_path / "alembic.ini"
    ini.write_text(_INI)
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level

    await asyncio.to_thread(
        run_migrations, scripts, _url(tmp_path / "app.db"), alembic_ini=ini
    )

    assert_that(root.handlers).is_equal_to(handlers)
    assert_that(root.level).is_equal_to(level)


def test_facade_imports_without_alembic() -> None:
    code = textwrap.dedent(
        """
        import sys
        sys.modules["alembic"] = None
        import rn_forge.sqlalchemy
        try:
            import rn_forge.sqlalchemy.migrate
        except ImportError:
            print("blocked")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert_that(result.returncode).is_equal_to(0)
    assert_that(result.stdout.strip()).is_equal_to("blocked")
