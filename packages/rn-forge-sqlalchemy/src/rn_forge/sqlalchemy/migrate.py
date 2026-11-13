"""Run Alembic migrations from inside the application process."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

__all__ = ["run_migrations"]


def run_migrations(
    script_location: str | Path,
    db_url: str,
    *,
    alembic_ini: str | Path | None = None,
    revision: str = "head",
) -> None:
    """Upgrade the database at *db_url* to *revision*.

    Blocks until the upgrade finishes. From a running event loop, call it as
    ``await asyncio.to_thread(run_migrations, ...)``. A failing migration
    propagates unchanged.

    ``config.attributes["configure_logger"]`` is set to ``False``. The
    application's ``env.py`` must read it before calling ``fileConfig`` for the
    application's logging to be left alone.

    Args:
        script_location: A script directory, or a package resource such as
            ``"myapp:migrations"``.
        db_url: The SQLAlchemy URL handed to ``env.py`` as ``sqlalchemy.url``.
        alembic_ini: An ``alembic.ini`` to start from; an empty configuration
            when omitted.
        revision: The target revision.
    """
    config = Config(str(alembic_ini)) if alembic_ini is not None else Config()
    # Config values pass through ConfigParser, where a bare "%" is interpolation.
    config.set_main_option("script_location", str(script_location).replace("%", "%%"))
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    command.upgrade(config, revision)
