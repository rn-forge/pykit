"""Tabular export and import over FastAPI, on tablib and pydantic.

Requires the ``transfer`` extra. Not imported by :mod:`rn_forge.fastapi`.
Persistence is the application's: :func:`read_rows` validates, it does not save.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import tablib
from fastapi import Header, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, TypeAdapter, ValidationError

from rn_forge.commons.data.excel import write_xlsx
from rn_forge.web import PROBLEM_MEDIA_TYPE, ProblemResponse
from rn_forge.web.transfer import (
    TABULAR_FORMATS,
    RowError,
    TabularFormat,
    content_disposition,
    negotiate_tabular_format,
)

__all__ = [
    "RowsResult",
    "problem_response",
    "read_rows",
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


async def read_rows[T: BaseModel](upload: UploadFile, model: type[T]) -> RowsResult[T]:
    """Load *upload* with tablib and validate each row against *model*.

    The format comes from the file extension, else from the part's content
    type (csv, tsv or xlsx). Row indexes
    are zero-based positions after the header row. An error's ``field`` is the
    column header (the model's alias); a validator that raises ``ValueError``
    reports its own message.

    Raises:
        ValueError: The file's extension is not a readable tabular format, or
            its content cannot be parsed.
    """
    extension = next(
        (
            ext
            for ext in (
                (upload.filename or "").rpartition(".")[2].lower(),
                *(
                    f.extension
                    for f in TABULAR_FORMATS.values()
                    if f.media_type == upload.content_type
                ),
            )
            if ext in _READABLE
        ),
        "",
    )
    if not extension:
        raise ValueError(
            f"Unsupported file type; upload one of {', '.join(_READABLE)}."
        )
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
        raise ValueError("The file could not be read.") from exc
    adapter = TypeAdapter(model)
    result = RowsResult[T]()
    for index, row in enumerate(_dicts(dataset)):
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
