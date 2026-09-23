# Quickstart

Five things nearly every application built on this kit wires. None of them
imports a web framework; the framework-specific glue is one page per stack in
[Wiring into Django](../adoption/wiring-django.md) and
[Wiring into FastAPI](../adoption/wiring-fastapi.md).

## 1. Tracing: W3C Trace Context through OpenTelemetry

There is no house request-id header. `traceparent` in, `traceresponse` out,
through OpenTelemetry's own ASGI/WSGI instrumentation (or
`opentelemetry-instrument`) — `rn_forge.web` reads the current span, and never
configures a `TracerProvider` or an exporter itself:

```python
from rn_forge.web import current_trace_id, current_span_id

current_trace_id()   # 32 lowercase hex chars, or None with no span recording
current_span_id()    # 16 lowercase hex chars, or None
```

For structured logs, `rn_forge.commons.logging.structlog.otel_processor` adds `trace_id` and
`span_id` to every event. `StructLogger` installs it itself; in a `structlog` chain of your own,
list it as a processor.

## 2. Every error as an RFC 9457 problem

```python
from rn_forge.web import default_registry, render_problem

registry = default_registry()          # a fresh instance; never a shared singleton

def to_response(exc, path):
    rendered = render_problem(registry, exc, instance=path)
    # Content-Type: application/problem+json; the body carries the current trace id
    return rendered.status, rendered.body, rendered.headers
```

Register your own domain exceptions once, and subclasses resolve for free:

```python
from rn_forge.web import ProblemType

registry.register(OrderLocked, ProblemType("order-locked", 409, "Order Locked"))
```

A 5xx never carries `str(exc)` — the detail is a fixed generic string unless
you pass one explicitly.

## 3. Optimistic concurrency

```python
from rn_forge.web import EntityVersionETagCodec, check_precondition

codec = EntityVersionETagCodec()

response["ETag"] = codec.format(entity_id=order.pk, version=order.version)   # on read

check_precondition(                                                          # on write
    request.headers.get("If-Match"),
    current_version=order.version,
    entity_id=order.pk,
    required=True,
)
```

Absent and required is 428; a mismatch is 412; unparseable is 400; `*` passes.

## 4. Cursor pagination

```python
from rn_forge.web import Page, clamp_page_size, decode_cursor, encode_cursor

size = clamp_page_size(request.query.get("pageSize"), default=20, cap=100)
cursor = decode_cursor(token) if (token := request.query.get("pageToken")) else None

rows = fetch(after=cursor, limit=size + 1)                # one extra row probes for a next page
has_more, rows = len(rows) > size, rows[:size]

page = Page(
    items=[serialize(r) for r in rows],
    next_page_token=encode_cursor(str(rows[-1].created_at), str(rows[-1].pk))
    if has_more
    else None,
)
return page.as_body()
```

An over-large `pageSize` is clamped, never rejected. A `Query(le=...)`
constraint would violate that, and the conformance table has a case for it.

## 5. Readiness

```python
from rn_forge.web import CheckResult, run_checks

report = await run_checks(
    {
        "db": check_db,
        "queue": lambda: CheckResult(status="skipped", reason="not configured"),
    },
    required=["db"],
)
return report.http_status, report.as_body()
```

A failing check outside `required` degrades the reported status but keeps the
endpoint at 200. A check that raises becomes a failure, never a 500.

## Next

The [API conventions](../adoption/api-conventions.md) page is the normative
version of all of the above, written so it can be pasted into an application's
specification.
