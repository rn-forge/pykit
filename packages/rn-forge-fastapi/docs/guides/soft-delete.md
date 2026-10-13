# Soft delete

`rn_forge.fastapi` serves AIP-164 soft delete: `DELETE {collection}/{id}` soft-deletes and answers
200 with the resource, `POST {collection}/{id}:undelete` restores it, and `showDeleted` brings
deleted resources back into a list. The wire contract is §21 of `rn-forge-web`'s API conventions.
Persistence is the application's: `soft_delete_router` takes a **store**, a dependency that returns
an object with these methods:

| Store method | Contract |
| --- | --- |
| `find(id)` | A `SoftDeleteState` of `row`, `version` (`None` when unversioned) and `delete_time`, or `None` when the resource does not exist. Deleted rows are found. |
| `soft_delete(id)` | Soft-deletes the row and returns it. |
| `undelete(id)` | Restores the row and returns it. |

The store owns the transaction and the clock. The router checks the resource's state first (404 or
409), then `If-Match` on a versioned row (428, 400 or 412), and only then calls the store to write.
It answers with `response_model` dumped by alias, and the new `ETag` read back through `find`.

## Over SQLAlchemy

The code below is **application code**. It joins `rn-forge-fastapi` and `rn-forge-sqlalchemy`, which
do not import each other.

```python
from datetime import datetime

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.fastapi import (
    SoftDeleteState,
    show_deleted_param,
    soft_delete_router,
)
from rn_forge.sqlalchemy import (
    AuditMixin,
    Base,
    SoftDeleteMixin,
    VersionMixin,
    live,
    soft_delete,
    undelete,
)
from rn_forge.web import Page, WireModel, require_live


class Note(SoftDeleteMixin, VersionMixin, AuditMixin, Base):
    __tablename__ = "note"

    id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str]


class NoteOut(WireModel):
    id: str
    text: str
    delete_time: datetime | None = None


class NoteStore:
    def __init__(self, sessions: async_sessionmaker, actor: str) -> None:
        self.sessions, self.actor = sessions, actor

    async def find(self, id: str) -> SoftDeleteState | None:
        async with self.sessions() as session:
            note = await session.get(Note, id)
        return None if note is None else SoftDeleteState(note, note.version, note.delete_time)

    async def soft_delete(self, id: str) -> Note:
        return await self._write(id, soft_delete)

    async def undelete(self, id: str) -> Note:
        return await self._write(id, undelete)

    async def _write(self, id, change) -> Note:
        async with self.sessions() as session:
            note = await session.get(Note, id)
            change(note, actor=self.actor)
            await session.commit()
            return note


app.include_router(
    soft_delete_router(
        "/notes",
        response_model=NoteOut,
        resource_label="Note",
        store=get_note_store,  # a dependency returning a NoteStore
        require_if_match=True,
    )
)


@app.get("/notes", response_model=Page[NoteOut])
async def list_notes(show_deleted: bool = Depends(show_deleted_param())): ...
```

The list route reads `showDeleted` with `show_deleted_param()` and passes it to
`live(select(Note), Note, show_deleted=show_deleted)`. The application's own `PUT` and `PATCH`
routes call `require_live(note.delete_time, label="Note", id=id)` before anything else that can
fail. `batch_delete_router` needs no change: its store's `find` returns only live ids and its
`delete_many` soft-deletes them, so a deleted id is a 404 for the whole batch.

## Conformance

The `soft-delete` cases in `rn_forge.web.conformance.CASES` run against this binding, and against
the same routes over SQLite with `rn-forge-sqlalchemy`.
