"""Reads tabular files into validated rows and writes rows as CSV chunks or tables."""

import csv
import io
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

import tablib
from pydantic import BaseModel, TypeAdapter, ValidationError
from rn_forge.data import write_xlsx
from rn_forge.web.transfer import (
    TABULAR_FORMATS,
    RowError,
    TabularFormat,
    unreadable_file_detail,
)

CSV_CHUNK_ROWS = 1_000


def columns(model: type[BaseModel]) -> list[str]:
    fields = [
        info.serialization_alias or name for name, info in model.model_fields.items()
    ]
    computed = [
        info.alias or name for name, info in model.model_computed_fields.items()
    ]
    return [*fields, *computed]


def records(
    rows: Iterable[Any], model: type[BaseModel], mode: str
) -> Iterator[dict[str, Any]]:
    for row in rows:
        yield model.model_validate(row, from_attributes=True).model_dump(
            by_alias=True,
            mode=mode,
        )


def csv_chunks(
    rows: Iterable[Any], model: type[BaseModel], names: list[str]
) -> Iterator[str]:
    """Yield the CSV text of *rows*, the header first, in chunks of ``CSV_CHUNK_ROWS`` rows."""
    # Streaming one row per chunk costs a worker-thread hop per row.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(names)
    count = 0
    for record in records(rows, model, "json"):
        writer.writerow([record[c] for c in names])
        count += 1
        if count == CSV_CHUNK_ROWS:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
            count = 0
    if buffer.tell():
        yield buffer.getvalue()


def build_body(
    rows: Iterable[Any], model: type[BaseModel], fmt: TabularFormat, names: list[str]
) -> bytes | str:
    dataset: Any = tablib.Dataset(headers=names)
    for record in records(rows, model, "python"):
        dataset.append([record[c] for c in names])
    if fmt.extension == "xlsx":
        return write_xlsx(dataset)
    return dataset.export(fmt.tablib_name)


def parse_table[T: BaseModel](
    raw: bytes, extension: str, model: type[T]
) -> tuple[list[T], list[RowError], int]:
    """Load *raw* as *extension* and validate each row; return the valid rows, errors and row count."""
    data: bytes | str = raw if extension == "xlsx" else raw.decode("utf-8-sig")
    try:
        dataset: Any = tablib.Dataset()
        dataset.load(data, format=TABULAR_FORMATS[extension].tablib_name)
    except Exception as exc:
        raise ValueError(unreadable_file_detail(extension)) from exc
    adapter = TypeAdapter(model)
    rows = dicts(dataset)
    valid: list[T] = []
    errors: list[RowError] = []
    for index, row in enumerate(rows):
        try:
            valid.append(adapter.validate_python(row))
        except ValidationError as exc:
            errors.extend(row_errors(index, exc))
    return valid, errors, len(rows)


def dicts(dataset: Any) -> list[Mapping[str, Any]]:
    return dataset.dict


def row_errors(index: int, exc: ValidationError) -> Iterator[RowError]:
    for err in exc.errors():
        message = (
            str(err["ctx"]["error"])
            if err["type"] == "value_error" and "ctx" in err
            else err["msg"]
        )
        yield RowError(index, str(err["loc"][0]) if err["loc"] else "", message)
