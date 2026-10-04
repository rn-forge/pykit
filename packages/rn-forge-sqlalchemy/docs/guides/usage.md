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
`Z` survives a round trip. The actors are explicit: the caller sets
`created_by` and `updated_by`.

## Optimistic concurrency

```python
order = await update_versioned(session, order, name="renamed")
```

The update matches on the version the object holds. A row at another version
raises `rn_forge.web.VersionConflict`, which the framework adapters render as
`412`, the same as `rn-forge-django`'s `VersionedModel`.

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
because the id breaks ties, and they may be nullable: rows whose value is
`NULL` come last in both directions. A token issued for another `orderBy`, or
holding a different number of values, is a `400`.

```python
columns = {"team": Person.team, "score": Person.score, "id": Person.id}
terms = parse_order_by("team, score desc", allowed=columns)  # score is nullable
stmt = keyset(
    select(Person), columns=columns, terms=terms, cursor=cursor, id_column=Person.id
)
```
