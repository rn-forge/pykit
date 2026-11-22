"""Run Alembic migrations from inside the application process."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import command, context
from alembic.config import Config
from sqlalchemy import MetaData, make_url, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

__all__ = ["run_env", "run_migrations"]


def run_env(target_metadata: MetaData | None, **configure: Any) -> None:
    """Run the migrations from an Alembic ``env.py``, online only.

    Replaces the whole body of ``env.py``:

    ```python
    from rn_forge.sqlalchemy.migrate import run_env
    from myapp.db.models import Base

    run_env(Base.metadata)
    ```

    Logging is configured from the config file only when one is set and
    ``config.attributes["configure_logger"]`` is true, which it is unless
    ``run_migrations`` set it. The migrations run on an async engine built from
    the config's ``sqlalchemy.`` options with ``NullPool``, inside
    ``asyncio.run``. ``render_as_batch`` is on for SQLite and off otherwise.

    When ``config.attributes["schema"]`` is set, which ``run_migrations`` does
    for its ``schema`` argument, the connection's ``search_path`` is that schema
    and ``alembic_version`` is kept in it.

    Args:
        target_metadata: The metadata autogenerate compares against, or ``None``.
        **configure: Keyword arguments for ``context.configure``; they override
            the defaults above.

    Raises:
        NotImplementedError: Alembic is in offline mode (``--sql``).
    """
    config = context.config
    if config.config_file_name and config.attributes.get("configure_logger", True):
        fileConfig(config.config_file_name)
    if context.is_offline_mode():
        msg = (
            "run_env runs migrations online only; "
            "offline mode (alembic upgrade --sql) is not supported"
        )
        raise NotImplementedError(msg)

    def _configure_and_run(connection: Connection) -> None:
        schema = config.attributes.get("schema")
        options: dict[str, Any] = {
            "target_metadata": target_metadata,
            "render_as_batch": connection.dialect.name == "sqlite",
        }
        if schema:
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            # Without the commit, Alembic's transaction rolls the setting back.
            connection.commit()
            connection.dialect.default_schema_name = schema
            options["version_table_schema"] = schema
        options.update(configure)
        context.configure(connection=connection, **options)
        with context.begin_transaction():
            context.run_migrations()

    async def _online() -> None:
        engine = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        try:
            async with engine.connect() as connection:
                await connection.run_sync(_configure_and_run)
        finally:
            await engine.dispose()

    asyncio.run(_online())


def run_migrations(
    script_location: str | Path,
    db_url: str,
    *,
    alembic_ini: str | Path | None = None,
    revision: str = "head",
    schema: str | None = None,
) -> None:
    """Upgrade the database at *db_url* to *revision*.

    Blocks until the upgrade finishes. From a running event loop, call it as
    ``await asyncio.to_thread(run_migrations, ...)``. A failing migration
    propagates unchanged.

    ``config.attributes["configure_logger"]`` is set to ``False``. The
    application's logging is left alone by ``run_env``, which honours the
    attribute; an ``env.py`` that calls ``fileConfig`` itself must read it.

    Args:
        script_location: A script directory, or a package resource such as
            ``"myapp:migrations"``.
        db_url: The SQLAlchemy URL handed to ``env.py`` as ``sqlalchemy.url``.
        alembic_ini: An ``alembic.ini`` to start from; an empty configuration
            when omitted.
        revision: The target revision.
        schema: A PostgreSQL schema, which must already exist, to migrate into;
            ``alembic_version`` is kept in it too. The database's own default
            schema when omitted.

    Raises:
        ValueError: *schema* is empty, or *db_url* is not a PostgreSQL URL.
    """
    if schema is not None:
        if not schema:
            msg = "schema must not be empty"
            raise ValueError(msg)
        backend = make_url(db_url).get_backend_name()
        if backend != "postgresql":
            msg = f"schema needs a PostgreSQL URL, got {backend!r}"
            raise ValueError(msg)
    config = Config(str(alembic_ini)) if alembic_ini is not None else Config()
    # Config values pass through ConfigParser, where a bare "%" is interpolation.
    config.set_main_option("script_location", str(script_location).replace("%", "%%"))
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    if schema is not None:
        config.attributes["schema"] = schema
    command.upgrade(config, revision)
