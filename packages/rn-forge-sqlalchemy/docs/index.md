# rn-forge-sqlalchemy

`rn-forge-sqlalchemy` is the SQLAlchemy half of the kit's persistence story: the
columns, the concurrency check, the bulk write and the paging query that produce
what `rn-forge-web` puts on the wire. It is async only and runs on PostgreSQL
and SQLite.

It provides:

- **`models`** — `Base`, `UTCDateTime`, `AuditMixin`, `VersionMixin`,
  `SoftDeleteMixin`, `live`, `soft_delete` and `undelete`
- **`concurrency`** — `update_versioned`
- **`upsert`** — `upsert` and `UpsertCounts`
- **`pagination`** — `keyset` and `next_page_token`

It imports no web framework. See [Using the package](guides/usage.md).

## Install

```toml
dependencies = [
  "rn-forge-sqlalchemy>=0.2,<0.3",
  "rn-forge-web>=0.3,<0.4",
]
```

`[migrations]` adds `alembic`. Minimum example:
[Models](guides/usage.md#models). `update_versioned` raises `VersionConflict`
(412); see [Optimistic concurrency](guides/usage.md#optimistic-concurrency).
