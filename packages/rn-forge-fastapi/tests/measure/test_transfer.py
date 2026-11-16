"""Measure FastAPI transfer request costs."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import date
from time import perf_counter
from typing import cast

import pytest
import tablib
from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel, ConfigDict, Field
from rn_forge.fastapi.transfer import (
    BatchCreateStore,
    ImportStore,
    batch_create_router,
    import_router,
    tabular_export,
    tabular_format,
)
from rn_forge.web import ImportCounts
from rn_forge.web.transfer import TABULAR_FORMATS, TabularFormat
from starlette.types import Message, Scope

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
    ),
]

type Counts = dict[str, int | float]
type Measure = Callable[[str, dict[str, object], str], AbstractContextManager[Counts]]


class Row(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int = Field(alias="ID")
    sku: str = Field(alias="SKU")
    name: str = Field(alias="Name")
    note: str = Field(alias="Note")
    region: str = Field(alias="Region")
    owner: str = Field(alias="Owner")
    quantity: int = Field(alias="Quantity")
    price: float = Field(alias="Price")
    due: date = Field(alias="Due")
    active: bool = Field(alias="Active")


class Store(ImportStore[Row], BatchCreateStore[Row]):
    async def import_rows(
        self, rows: Sequence[Row], *, validate_only: bool
    ) -> ImportCounts:
        """Report every imported row as created."""
        return ImportCounts(created=len(rows), updated=0, skipped=0)

    async def create_many(self, items: Sequence[Row]) -> Sequence[Row]:
        """Return every created row unchanged."""
        return items


def make_row(index: int) -> dict[str, object]:
    """Return the fixed row for *index*."""
    return {
        "id": index,
        "sku": f"sku-{index}",
        "name": "Widget",
        "note": "Standard item",
        "region": "North",
        "owner": "Ops",
        "quantity": 3,
        "price": 12.5,
        "due": date(2026, 1, 2),
        "active": True,
    }


def export_body(rows: list[dict[str, object]], extension: str) -> bytes:
    """Encode *rows* as the import file for *extension*."""
    dataset = tablib.Dataset(
        headers=[field.alias for field in Row.model_fields.values()]
    )
    for row in rows:
        dataset.append([row[name] for name in Row.model_fields])
    exported = dataset.export(extension)
    return exported.encode() if isinstance(exported, str) else exported


def multipart_body(content: bytes, extension: str, boundary: str) -> bytes:
    """Wrap *content* in the upload part for *extension*."""
    return (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="rows.{extension}"\r\n'
            f"Content-Type: {TABULAR_FORMATS[extension].media_type}\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )


async def drive(
    app: FastAPI,
    path: str,
    method: str,
    body: bytes = b"",
    query: bytes = b"",
    content_type: str | None = None,
) -> tuple[int, int]:
    """Return the status and streamed response byte count for one ASGI request."""
    headers = [(b"content-length", str(len(body)).encode())]
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    scope = cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query,
            "headers": headers,
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        },
    )
    sent = False
    status = 0
    response_bytes = 0

    async def receive() -> Message:
        """Return the request body once, then wait for response completion."""
        nonlocal sent
        if sent:
            # StreamingResponse treats http.disconnect as cancellation.
            await asyncio.Event().wait()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        """Count response bytes and retain its status."""
        nonlocal status, response_bytes
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            response_bytes += len(message.get("body", b""))

    await app(scope, receive, send)
    return status, response_bytes


def make_app(rows: list[dict[str, object]]) -> FastAPI:
    """Build the adapter app over the in-memory store."""
    store = Store()
    app = FastAPI()
    format_dependency = tabular_format()

    @app.get("/rows/export")
    async def export(
        fmt: TabularFormat | None = Depends(format_dependency),
    ) -> Response:
        """Return the selected tabular export."""
        chosen = fmt or TABULAR_FORMATS["csv"]
        return await tabular_export(
            rows, Row, chosen, f"rows.{chosen.extension}", instance="/rows"
        )

    app.include_router(import_router("/rows", model=Row, store=lambda: store))
    app.include_router(
        batch_create_router(
            "/rows",
            model=Row,
            response_model=Row,
            resource_name="rows",
            store=lambda: store,
        )
    )
    return app


@pytest.mark.parametrize(
    ("operation", "extension", "row_count", "dry_run"),
    [
        ("export", "csv", 10_000, False),
        ("export", "csv", 100_000, False),
        ("export", "xlsx", 10_000, False),
        ("export", "xlsx", 100_000, False),
        ("import", "csv", 10_000, False),
        ("import", "csv", 100_000, False),
        ("import", "xlsx", 10_000, False),
        ("import", "xlsx", 100_000, False),
        ("import", "csv", 100_000, True),
        ("batch_create", "json", 10_000, False),
        ("batch_create", "json", 100_000, False),
    ],
    ids=[
        "export-csv-10000",
        "export-csv-100000",
        "export-xlsx-10000",
        "export-xlsx-100000",
        "import-csv-10000",
        "import-csv-100000",
        "import-xlsx-10000",
        "import-xlsx-100000",
        "import-csv-dry-run-100000",
        "batch-create-10000",
        "batch-create-100000",
    ],
)
async def test_transfer_measurement(
    measure: Measure, operation: str, extension: str, row_count: int, dry_run: bool
) -> None:
    """Record one transfer request's memory, time and event-loop delay."""
    rows = [make_row(index) for index in range(row_count)]
    app = make_app(rows)
    boundary = "measure-boundary"
    request_body = b""
    content_type: str | None = None
    query = b""
    path = "/rows/export"
    method = "GET"
    case = f"fastapi_{operation}"
    inputs: dict[str, object] = {
        "rows": row_count,
        "columns": 10,
    }
    if operation in ("export", "import"):
        inputs["format"] = extension
    if operation == "import":
        file_body = export_body(rows, extension)
        request_body = multipart_body(file_body, extension, boundary)
        content_type = f"multipart/form-data; boundary={boundary}"
        path = "/rows:import"
        method = "POST"
        if dry_run:
            query = b"validateOnly=true"
            inputs["dry_run"] = True
        else:
            inputs["dry_run"] = False
        inputs["request_bytes"] = len(request_body)
    elif operation == "batch_create":
        request_body = json.dumps(
            {"requests": rows}, separators=(",", ":"), default=str
        ).encode()
        content_type = "application/json"
        path = "/rows:batchCreate"
        method = "POST"
        inputs["request_bytes"] = len(request_body)
    else:
        query = f"format={extension}".encode()

    stop = asyncio.Event()
    lags: list[float] = []

    async def heartbeat() -> None:
        """Record event-loop delay at five-millisecond intervals."""
        while not stop.is_set():
            started = perf_counter()
            await asyncio.sleep(0.005)
            lags.append(perf_counter() - started - 0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.015)
    lags.clear()
    with measure(case, inputs, "io") as counts:
        status, response_bytes = await drive(
            app, path, method, request_body, query, content_type
        )
        stop.set()
        await heartbeat_task
        ordered_lags = sorted(lags)
        counts["status"] = status
        counts["response_bytes"] = response_bytes
        counts["loop_lag_max_s"] = max(lags, default=0.0)
        counts["loop_lag_p99_s"] = (
            ordered_lags[int(0.99 * (len(ordered_lags) - 1))] if ordered_lags else 0.0
        )
        counts["heartbeats"] = len(lags)
    assert status == 200
