# Tabular export, import and batch operations

`rn_forge.fastapi.transfer` serves spreadsheet download and upload, an import
template, and batch get, create, update and delete. It needs the `transfer` extra (tablib,
openpyxl and `python-multipart`) and is not imported by `rn_forge.fastapi`. The
wire contract is §17 of `rn-forge-web`'s API conventions. Persistence is the
application's: each route factory takes a **store**, a dependency that returns an
object with the methods the factory calls.

| Factory | Route | Store | Store methods |
| --- | --- | --- | --- |
| `import_router` | `POST {collection}:import` | `ImportStore` | `import_rows(rows, *, validate_only)` |
| `import_template_router` | `GET {collection}:importTemplate` | `TemplateSource` | `rows()` |
| `batch_create_router` | `POST {collection}:batchCreate` | `BatchCreateStore` | `create_many(items)` |
| `batch_delete_router` | `POST {collection}:batchDelete` | `BatchDeleteStore` | `find(ids)`, `delete_many(ids)` |
| `batch_get_router` | `GET {collection}:batchGet` | `BatchGetStore` | `get_many(ids)` |
| `batch_update_router` | `POST {collection}:batchUpdate` | `BatchUpdateStore` | `current(ids)`, `update_many(items)` |

The stores are structural protocols, so a store never imports them. A factory
validates the request, applies the row cap (`max_rows`) and calls the store only
with data that passed. The store makes the writes. Because the store is obtained
through `Depends`, it can take a database session, the principal or filter
parameters the ordinary FastAPI way. Every factory also takes `dependencies=` for
route-level dependencies such as authorization.

## A complete resource

The code below is **application code**, not part of rn-forge. It joins
`rn-forge-fastapi` and `rn-forge-sqlalchemy`, which do not import each other:
the application's store calls `upsert` and `keyset`, and `rn-forge-fastapi`
calls the store. It serves `/orders` with a paged list, CSV and xlsx export,
import, import template, batch create and batch delete.

The model and the three wire models. `OrderImport`'s aliases are the
spreadsheet headers, and it also serves as the export and template model, so a
downloaded file can be uploaded again.

```python
from collections.abc import Sequence

from fastapi import Depends, FastAPI
from pydantic import ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.fastapi import order_by_param, page_params, register_problem_handlers
from rn_forge.fastapi.transfer import (
    batch_create_router,
    batch_delete_router,
    import_router,
    import_template_router,
    tabular_format,
    tabular_export,
)
from rn_forge.sqlalchemy import AuditMixin, Base, keyset, next_page_token, upsert
from rn_forge.web import ItemsDenied, Page, WireModel
from rn_forge.web.transfer import ImportCounts


class Order(AuditMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    quantity: Mapped[int]


class OrderImport(WireModel):  # columns: the spreadsheet's headers
    model_config = ConfigDict(populate_by_name=True)

    order_no: str = Field(alias="Order No", serialization_alias="Order No")
    name: str = Field(alias="Name", serialization_alias="Name")
    quantity: int = Field(alias="Quantity", serialization_alias="Quantity")


class OrderCreate(WireModel):  # one item of :batchCreate
    order_no: str
    name: str
    quantity: int = 0


class OrderOut(WireModel):  # one created or listed order
    order_no: str
    name: str
    quantity: int
```

The store. It opens its own session for each operation, so each operation is one
transaction that it commits or discards itself.

```python
SORT_ATTRS = {"orderNo": "order_no", "name": "name"}


class OrderStore:
    """Implements ImportStore, TemplateSource, BatchCreateStore and BatchDeleteStore."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], actor: str) -> None:
        self.sessions = sessions
        self.actor = actor

    async def import_rows(
        self, rows: Sequence[OrderImport], *, validate_only: bool
    ) -> ImportCounts:
        async with self.sessions() as session:
            counts = await upsert(
                session,
                Order,
                [row.model_dump(by_alias=False) for row in rows],
                key=["order_no"],
                fields=["name", "quantity"],
                actor=self.actor,
            )
            if validate_only:
                await session.rollback()
            else:
                await session.commit()
        return ImportCounts(counts.created, counts.updated, counts.skipped)

    async def rows(self) -> Sequence[Order]:
        async with self.sessions() as session:
            return (await session.scalars(select(Order).order_by(Order.id))).all()

    async def create_many(self, items: Sequence[OrderCreate]) -> Sequence[Order]:
        denied = {
            str(i): ["You may not create this order."]
            for i, item in enumerate(items)
            if item.name.startswith("internal-")
        }
        if denied:
            raise ItemsDenied(denied, root="requests")
        created = [Order(**item.model_dump(by_alias=False), created_by=self.actor) for item in items]
        async with self.sessions() as session:
            session.add_all(created)
            await session.commit()
        return created

    async def find(self, ids: Sequence[str]) -> list[str]:
        async with self.sessions() as session:
            stmt = select(Order.order_no).where(Order.order_no.in_(ids))
            return list(await session.scalars(stmt))

    async def delete_many(self, ids: Sequence[str]) -> None:
        async with self.sessions() as session:
            await session.execute(delete(Order).where(Order.order_no.in_(ids)))
            await session.commit()

    async def page(self, size, cursor, terms) -> Page[OrderOut]:
        stmt = keyset(
            select(Order),
            columns={"orderNo": Order.order_no, "name": Order.name},
            terms=terms,
            cursor=cursor,
            id_column=Order.id,
        )
        async with self.sessions() as session:
            found = (await session.scalars(stmt.limit(size + 1))).all()
        window = found[:size]
        token = None
        if len(found) > size:
            last = window[-1]
            values = [getattr(last, SORT_ATTRS[t.field]) for t in terms]
            token = next_page_token(values, last.id, terms)
        return Page[OrderOut](
            items=[OrderOut.model_validate(o, from_attributes=True) for o in window],
            next_page_token=token,
        )
```

The wiring.

```python
def build_app() -> FastAPI:
    engine = create_async_engine("sqlite+aiosqlite://")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    def order_store() -> OrderStore:
        return OrderStore(sessions, actor="alice")

    app = FastAPI()
    register_problem_handlers(app)
    app.include_router(import_router("/orders", model=OrderImport, store=order_store, max_rows=5000))
    app.include_router(import_template_router("/orders", model=OrderImport, source=order_store, max_rows=5000))
    app.include_router(batch_create_router("/orders", model=OrderCreate, response_model=OrderOut, resource_name="orders", store=order_store, max_rows=100))
    app.include_router(batch_delete_router("/orders", resource_label="Order", store=order_store, max_rows=100))

    @app.get("/orders")
    async def list_orders(
        fmt=Depends(tabular_format(("csv", "xlsx"))),
        params=Depends(page_params(cap=100, default=50)),
        terms=Depends(order_by_param(allowed=["orderNo", "name"])),
        store: OrderStore = Depends(order_store),
    ):
        if fmt is not None:
            return await tabular_export(await store.rows(), OrderImport, fmt, f"orders.{fmt.extension}", max_rows=5000, instance="/orders")
        return await store.page(*params, terms)

    return app
```

### All or nothing, and `validateOnly`

Each store method does all its writes in one session and commits once, at the
end:

- `import_rows` runs `upsert`, which never commits. A real import then commits.
  `validateOnly` rolls back instead, so the report shows the true
  `created`, `updated` and `skipped` counts and nothing is persisted. Any
  exception leaves the `async with` block before the commit, which discards the
  session's work.
- `create_many` checks every item for permission before it adds any, and raises
  `ItemsDenied` if one is refused: a 403 whose `errors[].pointer` is
  `/requests/<i>`. A database error before the commit discards the batch the
  same way.
- `delete_many` is one `DELETE` and one commit. The factory has already called
  `find` and answered a 404 for the first id that does not exist.

The factories do not open transactions, since they do not know the persistence
layer. A store that shares a request-scoped session instead must roll that
session back itself when it fails or when `validate_only` is set.

A row that fails a check only the store can make, such as a foreign-key lookup,
is reported by raising `RowsInvalid(errors)` (from `rn_forge.web`, built from `rn_forge.web.transfer.RowError`) from `import_rows`. It renders the
same 422 as a cell that failed validation, pointing at `/rows/<row>/<column>`.

### Batch get and update

`batch_get_router` reads a repeated `ids` query parameter. The store's `get_many(ids)` returns the
rows that exist within the caller's scope, keyed by id as a string. `batch_update_router` takes
`{"requests": [{"id", "patch", "ifMatch"}]}`: the store's `current(ids)` returns each existing row
as an object with `row` and `version` (`None` when the resource is unversioned), the factory merges
each patch into the row dumped through `model` by alias and validates the result as `model`, and
`update_many(items)` receives `(id, model instance)` pairs only after every check has passed. It
writes them in one transaction, bumps each version and returns the updated rows in the order given.

```python
app.include_router(batch_get_router("/orders", response_model=OrderOut, resource_name="orders", resource_label="Order", store=order_store, max_rows=100))
app.include_router(batch_update_router("/orders", model=OrderDocument, response_model=OrderOut, resource_name="orders", resource_label="Order", store=order_store, max_rows=100, require_if_match=True))
```

`update_many` raises `ItemsDenied(errors, root="requests")` before writing to refuse an item.
`codec=` changes the validator format of `ifMatch`, which defaults to `VersionETagCodec`.

### What the factories answer

| Request | Response |
| --- | --- |
| `:import` succeeds | 200 `{created, updated, skipped, validateOnly}` |
| `:import` has no `file` part | 422, `errors[].pointer` `/file`, `This field is required.` |
| `:import` has an unsupported or unreadable file | 422 at `/file` with the shared detail |
| `:import` has a failed cell | 422, `errors[].pointer` `/rows/<row>/<column>`; the store is not called |
| `:import` or a batch is over `max_rows` | 422, `The import exceeds the limit of N rows.` or `The batch exceeds the limit of N rows.`, no `errors` member |
| a batch request has no `requests` or `ids` member | 422 at `/requests` or `/ids`, `This field is required.` |
| the member is an empty list or not a list | 422 at the member, `A non-empty list is required.` |
| `:batchCreate` item fails validation | 422, every failed field at `/requests/<i>/<field>`; the store is not called |
| `:batchCreate` raises `ItemsDenied` | 403, `errors[].pointer` `/requests/<i>` |
| `:batchCreate` succeeds | 200 `{"<resource_name>": [...]}` of `response_model` dumped by alias |
| `:batchGet` has no non-empty `ids`, or more than `max_rows` | 400, `A non-empty ids parameter is required.` or `The batch exceeds the limit of N rows.` |
| `:batchGet` or `:batchUpdate` names an unknown id | 404, `{resource_label} {id} not found` |
| `:batchGet` succeeds | 200 `{"<resource_name>": [...]}` in request order, duplicates repeated |
| `:batchUpdate` item is malformed or repeats an id | 422, every failing item at `/requests/<i>/id`, `/patch` or `/ifMatch`; the store is not called |
| `:batchUpdate` precondition fails | 428, 400 or 412, `errors[].pointer` `/requests/<i>/ifMatch` |
| `:batchUpdate` merged document is invalid | 422, every failed field at `/requests/<i>/patch/<field>`; the store is not asked to write |
| `:batchUpdate` raises `ItemsDenied` | 403, `errors[].pointer` `/requests/<i>` |
| `:batchUpdate` succeeds | 200 `{"<resource_name>": [...]}` of `response_model` dumped by alias, in request order |
| `:batchDelete` names an unknown id | 404, `{resource_label} {id} not found` |
| `:batchDelete` succeeds | 204 |

These need `register_problem_handlers(app)`, which renders `RowsInvalid`,
`ItemsDenied` and the request validation errors as `application/problem+json`.

## Export

`tabular_format()` is a dependency that negotiates `Accept` or `?format=`. A
`None` result means the client wants the JSON list. `tabular_export` answers a
tabular request from a list route: the file, or a 422 when there are more rows
than `max_rows`.

The export model is a pydantic model. Its `serialization_alias`es are the column
headers, and a `computed_field` is a column, which covers foreign-key
traversal, full names and enum display names. Rows are validated with
`from_attributes=True`, so ORM objects work directly. CSV is streamed; xlsx is
written with `rn_forge.commons.data.excel.write_xlsx`. `tabular_response` is the
same without the cap, for a route that applies its own.

## Reading a file yourself

`read_rows` loads an `UploadFile` (csv, tsv or xlsx) and validates each row
against a pydantic model whose aliases are the external headers. A bad cell is
never raised: `RowsResult.errors` holds a `RowError` for each, `valid` holds the
rows that passed and `total` counts the data rows. An unsupported or unreadable
file raises `ValueError` with the shared detail. The tablib work and per-row
validation run in a worker thread. A route that needs more than `import_router`
offers can call it and answer with `problem_response(row_errors_problem(...))`.

## Paging a SQLAlchemy list

`order_by_param` and `page_params` parse the request, `rn-forge-sqlalchemy`'s
`keyset` applies them to a `Select`, and `next_page_token` writes the next token.
The `page` method of the store above does this: it fetches `size + 1` rows to
learn whether another page exists. `keyset` takes the sort column and the unique
id column, so the order is stable when the sort column repeats.

## Conformance

`tests/test_conformance.py` serves `/conformance/orders*` and
`/conformance/capped*` through these factories over one in-memory store, and
passes every `transfer.*` case in the shared table. The `rn-forge-sqlalchemy`
test suite serves an application over SQLite and passes the pagination and
import cases.
