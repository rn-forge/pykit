"""Tabular export and import, and batch create and delete, over FastAPI.

Requires the ``transfer`` extra. Not imported by :mod:`rn_forge.fastapi`.
Persistence is the application's: the route factories take a store dependency
that implements one of the store protocols, and :func:`read_rows` validates
without saving.
"""

import csv
import io
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import tablib
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    Query,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.params import Depends as DependsParam
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, TypeAdapter, ValidationError, create_model

from rn_forge.fastapi.openapi import operation_id

from rn_forge.commons.data.excel import write_xlsx
from rn_forge.web import (
    NULL_FIELD_DETAIL,
    PROBLEM_MEDIA_TYPE,
    REQUIRED_FIELD_DETAIL,
    ProblemResponse,
    RowsInvalid,
)
from rn_forge.web.transfer import (
    NON_EMPTY_LIST_DETAIL,
    TABULAR_FORMATS,
    ImportCounts,
    RowError,
    TabularFormat,
    content_disposition,
    export_cap_problem,
    import_report_body,
    negotiate_tabular_format,
    parse_flag,
    row_cap_problem,
    row_errors_problem,
    unreadable_file_detail,
    unsupported_file_detail,
)

__all__ = [
    "BatchCreateStore",
    "BatchDeleteStore",
    "ImportStore",
    "RowsResult",
    "TemplateSource",
    "batch_create_router",
    "batch_delete_router",
    "import_router",
    "import_template_router",
    "problem_response",
    "read_rows",
    "tabular_export",
    "tabular_format",
    "tabular_response",
]

_READABLE = ("csv", "tsv", "xlsx")


def tabular_format(
    allowed: Iterable[str] = ("csv", "xlsx"),
) -> Callable[..., TabularFormat | None]:
    """Return a dependency yielding the tabular format the request asks for.

    The ``format`` query parameter wins over ``Accept``; see
    :func:`rn_forge.web.transfer.negotiate_tabular_format`. The dependency
    yields ``None`` when the response should be the endpoint's JSON.

    Args:
        allowed: The extensions the endpoint offers.
    """
    offered = tuple(allowed)

    def dependency(
        accept: str | None = Header(default=None),
        format: str | None = Query(default=None),
    ) -> TabularFormat | None:
        return negotiate_tabular_format(accept, format, offered)

    return dependency


def problem_response(problem: ProblemResponse) -> JSONResponse:
    """Send a rendered problem, such as ``row_errors_problem(...)``, as a response."""
    return JSONResponse(
        problem.body,
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=dict(problem.headers),
    )


def _columns(model: type[BaseModel]) -> list[str]:
    fields = [
        info.serialization_alias or name for name, info in model.model_fields.items()
    ]
    computed = [
        info.alias or name for name, info in model.model_computed_fields.items()
    ]
    return [*fields, *computed]


def _records(
    rows: Iterable[Any], model: type[BaseModel], mode: str
) -> Iterator[dict[str, Any]]:
    for row in rows:
        yield model.model_validate(row, from_attributes=True).model_dump(
            by_alias=True,
            mode=mode,
        )


async def tabular_response(
    rows: Iterable[Any], model: type[BaseModel], fmt: TabularFormat, filename: str
) -> Response:
    """Render *rows* as a file download in *fmt*.

    Each row is validated into *model* with ``from_attributes=True`` and
    dumped by alias, so the model's serialization aliases are the column
    headers and its computed fields are columns. Use ``serialization_alias``
    for a header that differs from the attribute name: a plain ``alias`` would
    also rename the attribute read from an ORM object. CSV is streamed; the other
    formats are built in memory in a worker thread.

    Args:
        rows: ORM objects, mappings or *model* instances.
        model: The export model.
        fmt: The chosen format.
        filename: The download name, extension included.

    Returns:
        A ``StreamingResponse`` for CSV, otherwise a ``Response``.
    """
    headers = {"Content-Disposition": content_disposition(filename)}
    columns = _columns(model)
    if fmt.extension == "csv":

        def lines() -> Iterator[str]:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
            for record in _records(rows, model, "json"):
                writer.writerow([record[c] for c in columns])
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()

        return StreamingResponse(lines(), media_type=fmt.media_type, headers=headers)

    return Response(
        await run_in_threadpool(_build_body, rows, model, fmt, columns),
        media_type=fmt.media_type,
        headers=headers,
    )


def _build_body(
    rows: Iterable[Any], model: type[BaseModel], fmt: TabularFormat, columns: list[str]
) -> bytes | str:
    dataset: Any = tablib.Dataset(headers=columns)
    for record in _records(rows, model, "python"):
        dataset.append([record[c] for c in columns])
    if fmt.extension == "xlsx":
        return write_xlsx(dataset)
    return dataset.export(fmt.tablib_name)


@dataclass
class RowsResult[T]:
    """The outcome of :func:`read_rows`: the valid rows and every failed cell."""

    valid: list[T] = field(default_factory=list[T])
    errors: list[RowError] = field(default_factory=list[RowError])
    total: int = 0


async def read_rows[T: BaseModel](
    upload: UploadFile, model: type[T], *, formats: Sequence[str] = _READABLE
) -> RowsResult[T]:
    """Load *upload* with tablib and validate each row against *model*.

    The format comes from the file extension, else from the part's content
    type, among *formats*. Row indexes
    are zero-based positions after the header row. An error's ``field`` is the
    column header (the model's alias); a validator that raises ``ValueError``
    reports its own message. ``total`` is the number of data rows read.

    Args:
        upload: The uploaded file.
        model: The row model.
        formats: The accepted extensions, a subset of csv, tsv and xlsx.

    Raises:
        ValueError: The file's type is not in *formats*, with
            :func:`~rn_forge.web.transfer.unsupported_file_detail` as its
            message, or its content cannot be parsed, with
            :func:`~rn_forge.web.transfer.unreadable_file_detail`.
    """
    accepted = tuple(e for e in formats if e in _READABLE)
    name = upload.filename or ""
    candidates = (
        [name.rpartition(".")[2].lower()]
        if "." in name
        else [
            f.extension
            for f in TABULAR_FORMATS.values()
            if f.media_type == upload.content_type
        ]
    )
    extension = next((ext for ext in candidates if ext in accepted), "")
    if not extension:
        raise ValueError(unsupported_file_detail(formats))
    raw = await upload.read()
    return await run_in_threadpool(_parse_rows, raw, extension, model)


def _parse_rows[T: BaseModel](
    raw: bytes, extension: str, model: type[T]
) -> RowsResult[T]:
    data: bytes | str = raw if extension == "xlsx" else raw.decode("utf-8-sig")
    try:
        dataset: Any = tablib.Dataset()
        dataset.load(data, format=TABULAR_FORMATS[extension].tablib_name)
    except Exception as exc:
        raise ValueError(unreadable_file_detail(extension)) from exc
    adapter = TypeAdapter(model)
    rows = _dicts(dataset)
    result = RowsResult[T](total=len(rows))
    for index, row in enumerate(rows):
        try:
            result.valid.append(adapter.validate_python(row))
        except ValidationError as exc:
            result.errors.extend(_row_errors(index, exc))
    return result


def _dicts(dataset: Any) -> list[Mapping[str, Any]]:
    return dataset.dict


def _row_errors(index: int, exc: ValidationError) -> Iterator[RowError]:
    for err in exc.errors():
        message = (
            str(err["ctx"]["error"])
            if err["type"] == "value_error" and "ctx" in err
            else err["msg"]
        )
        yield RowError(index, str(err["loc"][0]) if err["loc"] else "", message)


async def tabular_export(
    rows: Sequence[Any],
    model: type[BaseModel],
    fmt: TabularFormat,
    filename: str,
    *,
    max_rows: int | None = None,
    instance: str,
) -> Response:
    """Answer an export request: *rows* as a download, or the cap problem.

    Call it from a list route once :func:`tabular_format` yielded a format.

    Args:
        rows: The rows to export, as for :func:`tabular_response`.
        model: The export model.
        fmt: The chosen format.
        filename: The download name, extension included.
        max_rows: The most rows an export may hold; ``None`` for no limit.
        instance: The ``instance`` of the problem, in practice the request path.

    Returns:
        A 422 problem when ``len(rows) > max_rows``, otherwise
        :func:`tabular_response`'s response.
    """
    if max_rows is not None and len(rows) > max_rows:
        return problem_response(export_cap_problem(max_rows, instance=instance))
    return await tabular_response(rows, model, fmt, filename)


class ImportStore[T](Protocol):
    """Persists the rows of an import."""

    async def import_rows(
        self, rows: Sequence[T], *, validate_only: bool
    ) -> ImportCounts:
        """Upsert every row in one transaction, rolling back when *validate_only*.

        Raises:
            RowsInvalid: A row fails a check only the store can make.
        """
        ...


class TemplateSource(Protocol):
    """Supplies the rows that prefill an import template."""

    async def rows(self) -> Iterable[Any]:
        """Return the current filtered rows; called only when ``prefill`` is set."""
        ...


class BatchCreateStore[T](Protocol):
    """Persists a batch of new resources."""

    async def create_many(self, items: Sequence[T]) -> Sequence[Any]:
        """Create every item in one transaction and return the created objects.

        Raises:
            ItemsDenied: An item is not permitted, raised before anything is written.
        """
        ...


class BatchDeleteStore(Protocol):
    """Finds and deletes a batch of resources."""

    async def find(self, ids: Sequence[str]) -> Collection[str]:
        """Return which of *ids* exist within the caller's scope."""
        ...

    async def delete_many(self, ids: Sequence[str]) -> None:
        """Delete every id in one transaction.

        Raises:
            ItemsDenied: An id may not be deleted, raised before anything is deleted.
        """
        ...


def _router(dependencies: Sequence[DependsParam]) -> APIRouter:
    return APIRouter(
        dependencies=list(dependencies), generate_unique_id_function=operation_id
    )


def _list_model(name: str, member: str, item: Any) -> type[BaseModel]:
    """Build ``{member: [item]}``, the schema FastAPI documents and validates."""
    make = cast("Callable[..., type[BaseModel]]", create_model)
    return make(name, **{member: (list[item], ...)})


def _rejection(loc: str, kind: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": kind, "loc": ("body", loc), "msg": message}]
    )


def _item_errors(index: int, exc: ValidationError) -> Iterator[RowError]:
    for err in exc.errors():
        if err["type"] == "missing":
            message = REQUIRED_FIELD_DETAIL
        elif "input" in err and err["input"] is None:
            message = NULL_FIELD_DETAIL
        elif err["type"] == "value_error" and "ctx" in err:
            message = str(err["ctx"]["error"])
        else:
            message = err["msg"]
        yield RowError(index, ".".join(str(part) for part in err["loc"]), message)


def _list_guard(
    key: str, max_rows: int | None, item_model: type[BaseModel] | None = None
) -> DependsParam:
    """Check the raw body's *key* member, and its items against *item_model*.

    Runs before FastAPI validates the body, so the checks fire in the order
    the wire contract states and item failures use the row-error wording.
    """
    items = TypeAdapter(item_model) if item_model is not None else None

    async def guard(request: Request) -> None:
        try:
            body: object = await request.json()
        except ValueError:
            body = None
        members: Mapping[str, object] = (
            cast("Mapping[str, object]", body) if isinstance(body, Mapping) else {}
        )
        if key not in members:
            raise _rejection(key, "missing", "Field required")
        value: object = members[key]
        if not isinstance(value, list) or not value:
            raise _rejection(key, "value_error", NON_EMPTY_LIST_DETAIL)
        if max_rows is not None and len(cast("list[object]", value)) > max_rows:
            raise ValueError(
                row_cap_problem(
                    "batch", max_rows, instance=request.url.path
                ).problem.detail
            )
        if items is not None:
            errors: list[RowError] = []
            for index, item in enumerate(cast("list[object]", value)):
                try:
                    items.validate_python(item)
                except ValidationError as exc:
                    errors.extend(_item_errors(index, exc))
            if errors:
                raise RowsInvalid(errors, root=key)

    return Depends(guard)


def import_router[T: BaseModel](
    collection: str,
    *,
    model: type[T],
    store: Callable[..., ImportStore[T]],
    formats: Sequence[str] = ("csv", "xlsx"),
    max_rows: int | None = None,
    dependencies: Sequence[DependsParam] = (),
) -> APIRouter:
    """Build ``POST {collection}:import``, a multipart upload of a ``file`` part.

    Each row is validated into *model*, whose aliases are the column headers.
    Any failed row answers a 422 problem and nothing reaches the store. The
    ``validateOnly`` query parameter is parsed by
    :func:`~rn_forge.web.transfer.parse_flag`. The response is 200 with
    :func:`~rn_forge.web.transfer.import_report_body`.

    Args:
        collection: The collection path, for example ``/orders``.
        model: The row model.
        store: A dependency returning the :class:`ImportStore`.
        formats: The accepted file extensions.
        max_rows: The most data rows an import may hold; ``None`` for no limit.
        dependencies: Dependencies of the route, as for ``APIRouter``.

    Returns:
        The router.
    """
    router = _router(dependencies)
    offered = tuple(formats)

    async def import_items(
        request: Request,
        file: UploadFile,
        validate_only: str | None = Query(default=None, alias="validateOnly"),
        target: ImportStore[T] = Depends(store),
    ) -> Response:
        try:
            result = await read_rows(file, model, formats=offered)
        except ValueError as exc:
            raise _rejection("file", "value_error", str(exc)) from exc
        path = request.url.path
        if max_rows is not None and result.total > max_rows:
            return problem_response(row_cap_problem("import", max_rows, instance=path))
        if result.errors:
            return problem_response(row_errors_problem(result.errors, instance=path))
        flag = parse_flag(validate_only)
        counts = await target.import_rows(result.valid, validate_only=flag)
        return JSONResponse(
            import_report_body(
                created=counts.created,
                updated=counts.updated,
                skipped=counts.skipped,
                validate_only=flag,
            )
        )

    router.add_api_route(f"{collection}:import", import_items, methods=["POST"])
    return router


def import_template_router[T: BaseModel](
    collection: str,
    *,
    model: type[T],
    source: Callable[..., TemplateSource],
    formats: Sequence[str] = ("csv", "xlsx"),
    max_rows: int | None = None,
    dependencies: Sequence[DependsParam] = (),
) -> APIRouter:
    """Build ``GET {collection}:importTemplate``, the import columns as a file.

    The format is negotiated as for :func:`tabular_format`, else the first of
    *formats*. The columns are *model*'s aliases, so the file round-trips
    through :func:`import_router`. Without ``prefill`` the file holds the
    header row only; with it, the rows of :class:`TemplateSource`. The download
    is named ``import-template.<ext>``.

    Args:
        collection: The collection path, for example ``/orders``.
        model: The import model.
        source: A dependency returning the :class:`TemplateSource`.
        formats: The offered file extensions.
        max_rows: The most rows a prefilled template may hold; ``None`` for no limit.
        dependencies: Dependencies of the route, as for ``APIRouter``.

    Returns:
        The router.
    """
    router = _router(dependencies)
    offered = tuple(formats)

    async def import_template(
        request: Request,
        fmt: TabularFormat | None = Depends(tabular_format(offered)),
        prefill: str | None = Query(default=None),
        supplier: TemplateSource = Depends(source),
    ) -> Response:
        chosen = fmt or TABULAR_FORMATS[offered[0]]
        rows = list(await supplier.rows()) if parse_flag(prefill) else []
        return await tabular_export(
            rows,
            model,
            chosen,
            f"import-template.{chosen.extension}",
            max_rows=max_rows,
            instance=request.url.path,
        )

    router.add_api_route(
        f"{collection}:importTemplate", import_template, methods=["GET"]
    )
    return router


def batch_create_router[T: BaseModel](
    collection: str,
    *,
    model: type[T],
    response_model: type[BaseModel],
    resource_name: str,
    store: Callable[..., BatchCreateStore[T]],
    max_rows: int | None = None,
    dependencies: Sequence[DependsParam] = (),
) -> APIRouter:
    """Build ``POST {collection}:batchCreate``, taking ``{"requests": [...]}``.

    Every item is validated into *model* and every failure is reported, as a
    422 problem pointing at ``/requests/<i>/<field>``, and the store is not called. The response is 200 with
    the created objects, as *response_model* dumped by alias, under
    *resource_name*.

    Args:
        collection: The collection path, for example ``/orders``.
        model: The create model of one item.
        response_model: The model of one created resource.
        resource_name: The response member that holds the created resources.
        store: A dependency returning the :class:`BatchCreateStore`.
        max_rows: The most items a batch may hold; ``None`` for no limit.
        dependencies: Dependencies of the route, as for ``APIRouter``.

    Returns:
        The router.
    """
    router = _router(dependencies)
    request_model = _list_model(
        f"{model.__name__}BatchCreateRequest", "requests", model
    )
    result_model = _list_model(
        f"{response_model.__name__}BatchCreateResponse", resource_name, response_model
    )

    async def batch_create(
        body: Any = Body(),
        target: BatchCreateStore[T] = Depends(store),
    ) -> dict[str, Any]:
        created = await target.create_many(body.requests)
        return {
            resource_name: [
                response_model.model_validate(c, from_attributes=True).model_dump(
                    by_alias=True, mode="json"
                )
                for c in created
            ]
        }

    batch_create.__annotations__["body"] = request_model
    router.add_api_route(
        f"{collection}:batchCreate",
        batch_create,
        methods=["POST"],
        response_model=result_model,
        dependencies=[_list_guard("requests", max_rows, model)],
    )
    return router


def batch_delete_router(
    collection: str,
    *,
    resource_label: str,
    store: Callable[..., BatchDeleteStore],
    max_rows: int | None = None,
    dependencies: Sequence[DependsParam] = (),
) -> APIRouter:
    """Build ``POST {collection}:batchDelete``, taking ``{"ids": [...]}``.

    Ids may be strings or integers and are compared as strings. The first id
    that :meth:`BatchDeleteStore.find` does not return is a 404 reading
    ``{resource_label} {id} not found``. The response is 204.

    Args:
        collection: The collection path, for example ``/orders``.
        resource_label: The resource's name in the 404 detail, for example ``Order``.
        store: A dependency returning the :class:`BatchDeleteStore`.
        max_rows: The most ids a batch may hold; ``None`` for no limit.
        dependencies: Dependencies of the route, as for ``APIRouter``.

    Returns:
        The router.
    """
    router = _router(dependencies)
    request_model = _list_model("BatchDeleteRequest", "ids", str | int)

    async def batch_delete(
        body: Any = Body(),
        target: BatchDeleteStore = Depends(store),
    ) -> Response:
        ids = [str(i) for i in body.ids]
        found = set(await target.find(ids))
        for item in ids:
            if item not in found:
                raise LookupError(f"{resource_label} {item} not found")
        await target.delete_many(ids)
        return Response(status_code=204)

    batch_delete.__annotations__["body"] = request_model
    router.add_api_route(
        f"{collection}:batchDelete",
        batch_delete,
        methods=["POST"],
        status_code=204,
        response_class=Response,
        dependencies=[_list_guard("ids", max_rows)],
    )
    return router
