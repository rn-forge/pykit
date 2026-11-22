# Using the package

## Models

```python
from sqlalchemy.orm import Mapped, mapped_column
from rn_forge.sqlalchemy import AuditMixin, Base, VersionMixin


class Order(AuditMixin, VersionMixin, Base):
    __tablename__ = "order"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
```

`AuditMixin` adds `create_time`, `update_time`, `created_by` and `updated_by`,
named after AIP-148, so the wire names are `createTime` and `updateTime`. The
timestamps are Python-side UTC defaults stored through `UTCDateTime`, which
rejects a naive value and returns an aware UTC value on SQLite too, so AIP-142's
`Z` survives a round trip. The actors are explicit: the caller sets `created_by`
and `updated_by`.

## Optimistic concurrency

```python
order = await update_versioned(session, order, name="renamed")
```

The update matches on the version the object holds. A row at another version
raises `rn_forge.web.VersionConflict`, which the framework adapters render as
`412`, the same as `rn-forge-django`'s `VersionedModel`.

## Soft delete

```python
class Note(SoftDeleteMixin, VersionMixin, AuditMixin, Base):
    __tablename__ = "note"

    id: Mapped[str] = mapped_column(primary_key=True)


stmt = live(select(Note), Note)  # delete_time IS NULL
stmt = live(select(Note), Note, show_deleted=True)  # unchanged

soft_delete(note, actor=principal.subject)
undelete(note, actor=principal.subject)
await session.commit()
```

`SoftDeleteMixin` adds a nullable, indexed `delete_time` (AIP-164's
`deleteTime`). `soft_delete` and `undelete` set it, and set `updated_by` and
`update_time` on an `AuditMixin` row and bump `version` on a `VersionMixin` row.
They do not flush or commit. Pass `now=` to pin the time. Nothing hooks the
session: a query that should hide deleted rows says so with `live()`, and
`session.get()` still returns a deleted row.

## Import: `upsert`

```python
counts = await upsert(
    session, Order, [row.model_dump() for row in result.valid],
    key=["name"], fields=["id"], actor=principal.subject,
)
if validate_only:
    await session.rollback()
else:
    await session.commit()
```

`upsert` reads the existing rows for the keys, classifies each input row as
created, updated or skipped, and writes the first two with one
`INSERT … ON CONFLICT DO UPDATE`. It never commits, so an import is all or
nothing in the caller's transaction, and rolling back after the call is the
`validateOnly` dry run. Validate rows and look up foreign keys before calling; a
repeated key in the input raises `ValueError`.

## Keyset paging

```python
stmt = keyset(
    select(Order),
    columns={"name": Order.name, "id": Order.id},
    terms=order_by,          # parsed by rn_forge.web.parse_order_by
    cursor=cursor,           # decoded page token, or None
    id_column=Order.id,
)
rows = (await session.scalars(stmt.limit(page_size + 1))).all()
page, more = rows[:page_size], len(rows) > page_size
token = None
if more:
    last = page[-1]  # one value per orderBy term, in term order
    token = next_page_token(
        [getattr(last, t.field) for t in order_by], last.id, order_by
    )
```

`orderBy` is a comma-separated list, so `team, score desc` orders by `team`,
then by `score` descending, then by the id. The columns need not be unique,
because the id breaks ties, and they may be nullable: rows whose value is `NULL`
come last in both directions. A token issued for another `orderBy`, or holding a
different number of values, is a `400`.

```python
columns = {"team": Person.team, "score": Person.score, "id": Person.id}
terms = parse_order_by("team, score desc", allowed=columns)  # score is nullable
stmt = keyset(
    select(Person), columns=columns, terms=terms, cursor=cursor, id_column=Person.id
)
```

## SQLite engine

```python
from rn_forge.sqlalchemy import create_sqlite_engine

engine = create_sqlite_engine("var/app.db")
```

The helper creates the parent directory and returns an `AsyncEngine` that runs
these pragmas on every new connection:

| Argument | Pragma | Effect |
| -- | -- | -- |
| `busy_timeout_ms` | `busy_timeout` | How long a connection waits on a locked database |
| `wal=True` | `journal_mode=WAL` | Readers do not block the writer |
| `synchronous` | `synchronous` | `OFF`, `NORMAL`, `FULL` or `EXTRA`, in any case |
| `foreign_keys=True` | `foreign_keys=ON` | Enforces foreign-key constraints |

A false flag leaves that pragma at SQLite's default. The application declares
`aiosqlite`; the package declares no driver.

The exact string `":memory:"` opens an in-memory database for tests. It skips
the directory step and WAL, and uses a single shared connection, so every
session sees the same database. The helper never creates tables: schema is the
migrations' job.

## PostgreSQL engine

```python
from rn_forge.sqlalchemy import create_postgres_engine

engine = create_postgres_engine(
    "postgresql://user:pass@localhost/app",
    application_name="svc",
    statement_timeout_ms=5000,
    search_path="app,public",
)
```

The helper returns an `AsyncEngine` on `asyncpg` that sets these on every new
connection:

| Argument | Setting | Effect |
| -- | -- | -- |
| always | `timezone` | The session time zone is `UTC` |
| `application_name` | `application_name` | The name the server reports |
| `statement_timeout_ms` | `statement_timeout` | Milliseconds before the server cancels a statement |
| `search_path` | `search_path` | The schema search path, as PostgreSQL's comma-separated list |

A setting left as `None` stays at the server default. Install the `postgres`
extra, which adds `asyncpg`; without it the helper raises `ImportError`. The URL
scheme is `postgresql://`, `postgres://` or `postgresql+asyncpg://`, and the
driver is rewritten to `postgresql+asyncpg`. The engine does not connect and
creates no tables.

## Testing against PostgreSQL

Install `rn-forge-sqlalchemy[postgres,testing]`, then load the plugin in the
root `conftest.py`. The plugin is never loaded by installing the extra.

```python
pytest_plugins = ["rn_forge.sqlalchemy.testing"]
```

The `postgres_schema` fixture gives each test a fresh schema and a
`PostgresSchema` with its `name`, `url` and `engine`. The engine's connections
use the schema as their `search_path`. The fixture drops the schema with
`CASCADE` after the test, whether it passed or failed, and skips the test when
the DSN variable is unset or empty.

```python
import pytest
from sqlalchemy import text


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_creates_a_table(postgres_schema):
    async with postgres_schema.engine.begin() as connection:
        await connection.execute(text("CREATE TABLE probe (id int)"))
```

The `rn_forge_postgres_dsn_env` ini option names the environment variable that
holds the DSN; the default is `RN_FORGE_TEST_POSTGRES_DSN`. The plugin registers
the `postgres` marker.

In CI, a `[tool.workspace-ci.integration.postgres]` table starts the server and
exports the DSN:

```toml
[tool.workspace-ci.integration.postgres]
image = "postgres:17"
ports = ["5432:5432"]
health-cmd = "pg_isready -U ci"

[tool.workspace-ci.integration.postgres.env]
POSTGRES_USER = "ci"
POSTGRES_PASSWORD = "ci"
POSTGRES_DB = "ci"

[tool.workspace-ci.integration.postgres.expose]
RN_FORGE_TEST_POSTGRES_DSN = "postgresql://ci:ci@localhost:5432/ci"
```

## Embedded migrations

Install the extra, which adds `alembic`:

```toml
dependencies = ["rn-forge-sqlalchemy[migrations]>=0.2.3,<0.3"]
```

```python
import asyncio
from contextlib import asynccontextmanager

from rn_forge.sqlalchemy import create_sqlite_engine
from rn_forge.sqlalchemy.migrate import run_migrations

DB_PATH = "var/app.db"


@asynccontextmanager
async def lifespan(app):
    # The engine helper creates the database's directory; it connects lazily.
    engine = create_sqlite_engine(DB_PATH)
    await asyncio.to_thread(
        run_migrations,
        "myapp:migrations",
        f"sqlite+aiosqlite:///{DB_PATH}",
    )
    yield
    await engine.dispose()
```

`run_migrations` is not re-exported from `rn_forge.sqlalchemy`; importing it
without the extra raises `ImportError`, and the rest of the package works
without it. Run it from application startup, not from the engine helper.

It blocks, and `run_env` calls `asyncio.run()`, which cannot run inside a
running event loop. `asyncio.to_thread` gives it a thread with no loop. A
failing migration propagates unchanged.

If the path holds characters that are special in a URL, build `db_url` with
`sqlalchemy.engine.URL.create("sqlite+aiosqlite", database=path)` and
`.render_as_string(hide_password=False)`.

### `env.py`

```python
from rn_forge.sqlalchemy.migrate import run_env
from myapp.db.models import Base

run_env(Base.metadata)
```

`run_env` replaces Alembic's stock `env.py` template; it does not extend it. It
runs the migrations on an async engine built from the `sqlalchemy.` options of
the config.

- Offline mode (`alembic upgrade --sql`) is not supported and raises
  `NotImplementedError`.
- `render_as_batch` is on only for SQLite, where `ALTER` cannot change most
  columns in place.
- Keyword arguments override `context.configure`'s defaults, for example
  `run_env(Base.metadata, compare_type=True)`.
- `run_env` honours `config.attributes["configure_logger"]`, which
  `run_migrations` sets to `False`, so the application's logging is not
  reconfigured.

### Script location

`script_location` is a directory, or a package resource such as
`"myapp:migrations"`, meaning the `migrations` directory inside the `myapp`
package. The resource form keeps working once the application is installed as a
wheel, where a filesystem path relative to the source tree no longer exists.
