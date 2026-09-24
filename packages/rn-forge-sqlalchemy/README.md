# rn-forge-sqlalchemy

Async SQLAlchemy building blocks that match the `rn-forge-web` wire: audit and
version columns, a bulk upsert for imports, and keyset pagination over web's
opaque page token.

| Module | What it holds |
| --- | --- |
| `models` | `Base` (Alembic naming convention), `UTCDateTime`, `AuditMixin` (`create_time`, `update_time`, `created_by`, `updated_by`), `VersionMixin` |
| `concurrency` | `update_versioned` — optimistic concurrency, raising `rn_forge.web.VersionConflict` (412) |
| `upsert` | `upsert` — create or update rows by natural key, counting created, updated and skipped |
| `pagination` | `keyset`, `next_page_token` — AIP-132 `orderBy` and AIP-158 tokens over a `Select` |

Everything works on **PostgreSQL and SQLite**, through `AsyncSession` only.

## Where it sits

```text
commons ──► web ──► sqlalchemy      (this package)
              ├───► django
              └───► fastapi
```

It depends on `rn-forge-web` and SQLAlchemy. It imports neither `rn_forge.fastapi`
nor `rn_forge.django`, nor either framework; `uv run lint-imports` proves it.
An application wires this package to its framework itself: the FastAPI guide
shows the import and list endpoints.

## Installation

None of the `rn-forge-*` packages is on PyPI. A release is a git tag, declared
as a pinned direct URL:

```toml
dependencies = [
  "rn-forge-sqlalchemy @ git+https://github.com/rn-forge/pykit@rn-forge-sqlalchemy-v0.1.0#subdirectory=packages/rn-forge-sqlalchemy",
]
```

No database driver is declared. Add `asyncpg` for PostgreSQL or `aiosqlite` for
SQLite.

## Testing

```bash
uv run pytest packages/rn-forge-sqlalchemy
RN_FORGE_TEST_POSTGRES_DSN=postgresql+asyncpg://user:pw@localhost/db \
  uv run pytest packages/rn-forge-sqlalchemy -m postgres
```

The default run uses SQLite. Tests marked `postgres` run only when the DSN is set.

## Not included

The SQL idempotency store, session and unit-of-work helpers, readiness checks and
multi-tenant scoping wait for an application that needs them.
