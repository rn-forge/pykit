# rn-forge-sqlalchemy

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-sqlalchemy/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-sqlalchemy/CHANGELOG.md)
·
[Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-sqlalchemy)
· [All pykit packages](https://rn-forge.github.io/pykit/)

Async SQLAlchemy building blocks that match the `rn-forge-web` wire: audit and
version columns, a bulk upsert for imports, and keyset pagination over web's
opaque page token.

| Module | What it holds |
| -- | -- |
| `models` | `Base` (Alembic naming convention), `UTCDateTime`, `AuditMixin` (`create_time`, `update_time`, `created_by`, `updated_by`), `VersionMixin`, `SoftDeleteMixin`, `live`, `soft_delete`, `undelete` |
| `concurrency` | `update_versioned` — optimistic concurrency, raising `rn_forge.web.VersionConflict` (412) |
| `upsert` | `upsert` — create or update rows by natural key, counting created, updated and skipped |
| `postgres` | `create_postgres_engine` — an async PostgreSQL engine (asyncpg) with UTC sessions, pool settings and an optional statement timeout and application name |
| `testing` | `postgres_schema` — a pytest plugin whose fixture gives each test its own PostgreSQL schema; needs the `testing` and `postgres` extras and is loaded with `pytest_plugins`, not imported from the facade |
| `sqlite` | `create_sqlite_engine` — an async SQLite engine with WAL, foreign keys, busy timeout and `synchronous` set on every connection |
| `migrate` | `run_migrations` — Alembic `upgrade` from inside the process; needs the `migrations` extra and is imported directly, not from the facade |
| `pagination` | `keyset`, `next_page_token` — AIP-132 `orderBy` and AIP-158 tokens over a `Select` |

Everything works on **PostgreSQL and SQLite**, through `AsyncSession` only.

## Where it sits

It depends on `rn-forge-web` and SQLAlchemy and imports no web framework or
framework package; `task lint` proves it. An application wires it to its
framework itself: the FastAPI guide shows the import and list endpoints.

## Installation

Require the packages by version range:

```toml
dependencies = [
  "rn-forge-sqlalchemy>=0.2,<0.3",
  "rn-forge-web>=0.3,<0.4",
]
```

Application code catches `rn_forge.web.VersionConflict` and passes
`rn_forge.web` pagination terms, so declare `rn-forge-web` as well.

The core install carries no database driver.
`rn-forge-sqlalchemy[postgres]>=0.2.5,<0.3` installs `asyncpg` and
`rn-forge-sqlalchemy[sqlite]>=0.2.5,<0.3` installs `aiosqlite`.

`run_migrations` needs the `migrations` extra:
`rn-forge-sqlalchemy[migrations]>=0.2.3,<0.3`.

## Minimum example

```python
from sqlalchemy.orm import Mapped, mapped_column
from rn_forge.sqlalchemy import AuditMixin, Base, VersionMixin


class Order(AuditMixin, VersionMixin, Base):
    __tablename__ = "order"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
```

## Errors

`update_versioned` raises `rn_forge.web.VersionConflict` (412) when the row is
at another version and `LookupError` when it is gone. `upsert` raises
`ValueError` for an empty key, a row missing a column or a duplicate key,
`TypeError` for a model without `AuditMixin`, and `NotImplementedError` for a
dialect other than PostgreSQL or SQLite.

## Testing

The default test run uses SQLite. Tests marked `postgres` run when
`RN_FORGE_TEST_POSTGRES_DSN` is set;
`task ci:integration -- rn-forge-sqlalchemy` starts PostgreSQL and sets it.

## Not included

The SQL idempotency store, session and unit-of-work helpers, readiness checks
and multi-tenant scoping wait for an application that needs them.
