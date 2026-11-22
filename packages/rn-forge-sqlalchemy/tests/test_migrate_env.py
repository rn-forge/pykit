import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from assertpy import assert_that
from rn_forge.sqlalchemy import create_sqlite_engine
from rn_forge.sqlalchemy.migrate import run_migrations
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit

_ENV = """
from sqlalchemy import Column, Integer, MetaData, Table
from rn_forge.sqlalchemy.migrate import run_env

metadata = MetaData()
Table("thing", metadata, Column("id", Integer, primary_key=True))
run_env(metadata{extra})
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

_MAKO = """\
from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade():
    ${upgrades if upgrades else "pass"}
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


def _scripts(root: Path, name: str, *, extra: str = "", revisions: bool = True) -> Path:
    """Write a script directory whose env.py calls run_env; module names are unique per test."""
    directory = root / name
    (directory / "versions").mkdir(parents=True)
    (directory / "env.py").write_text(_ENV.replace("{extra}", extra))
    (directory / "script.py.mako").write_text(_MAKO)
    if revisions:
        bodies = {
            "r1": 'op.execute("CREATE TABLE one (id INTEGER)")',
            "r2": 'op.execute("CREATE TABLE two (id INTEGER)")',
        }
        for rev, down in (("r1", None), ("r2", "r1")):
            (directory / "versions" / f"{name}_{rev}.py").write_text(
                _REVISION.format(
                    rev=f"{name}_{rev}",
                    down=down and f"{name}_{down}",
                    body=bodies[rev],
                )
            )
    return directory


def _url(path: Path) -> str:
    return URL.create("sqlite+aiosqlite", database=str(path)).render_as_string(
        hide_password=False
    )


def _config(scripts: Path, db: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(scripts))
    config.set_main_option("sqlalchemy.url", _url(db).replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


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
async def test_run_env_reaches_head(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path, "head")
    db = tmp_path / "app.db"

    await asyncio.to_thread(run_migrations, scripts, _url(db))

    tables, versions = await _state(db)
    assert_that(tables).contains("one", "two")
    assert_that(versions).is_equal_to(["head_r2"])


@pytest.mark.asyncio
async def test_run_env_leaves_root_logger_alone(tmp_path: Path) -> None:
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


@pytest.mark.asyncio
async def test_run_env_passes_target_metadata(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path, "meta", revisions=False)
    config = _config(scripts, tmp_path / "app.db")

    await asyncio.to_thread(command.revision, config, message="init", autogenerate=True)

    (revision,) = (scripts / "versions").glob("*.py")
    assert_that(revision.read_text()).matches(r"op\.create_table\(['\"]thing['\"]")


@pytest.mark.asyncio
async def test_run_env_offline_raises(tmp_path: Path) -> None:
    scripts = _scripts(tmp_path, "offline")
    config = _config(scripts, tmp_path / "app.db")

    with pytest.raises(NotImplementedError, match="offline"):
        await asyncio.to_thread(command.upgrade, config, "head", sql=True)


@pytest.mark.asyncio
async def test_run_env_configure_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[dict[str, Any]] = []
    original = EnvironmentContext.configure

    def spy(self: EnvironmentContext, *args: Any, **kwargs: Any) -> None:
        recorded.append(kwargs)
        original(self, *args, **kwargs)

    monkeypatch.setattr(EnvironmentContext, "configure", spy)
    overridden = _scripts(tmp_path, "over", extra=", render_as_batch=False")
    default = _scripts(tmp_path, "dflt")

    await asyncio.to_thread(run_migrations, overridden, _url(tmp_path / "a.db"))
    await asyncio.to_thread(run_migrations, default, _url(tmp_path / "b.db"))

    assert_that([r["render_as_batch"] for r in recorded]).is_equal_to([False, True])
