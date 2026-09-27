# Wiring rn-forge-web into plain Django

This is a composition recipe for an application using plain Django/DRF with
`rn-forge-web`. For the packaged adapters, use the `rn-forge-django` quickstart
and its Django/DRF guides. Several pieces below already ship there; the
examples show how an application can compose the shared HTTP primitives itself.

## 1. Tracing — instrument once, before Django loads

Tracing is W3C Trace Context, propagated and read through OpenTelemetry —
not a house header or a WSGI middleware.

```python
# manage.py, wsgi.py, asgi.py — before Django loads
from opentelemetry.instrumentation.django import DjangoInstrumentor

DjangoInstrumentor().instrument()
```

`DjangoInstrumentor` inserts its own middleware into `MIDDLEWARE` at position
0, so it wraps everything downstream — including the exception handler.
`rn_forge.django.tracing.instrument()` (the `otel` extra) does this call and
also installs a `TraceResponsePropagator` when the application has not
already set one.

## 2. Errors — a DRF exception handler

```python
# myapp/handlers.py
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from rn_forge.web import PROBLEM_MEDIA_TYPE, default_registry, field_error, render_problem

REGISTRY = default_registry()   # register your domain exceptions here, once

def problem_exception_handler(exc, context):
    request = context.get("request")
    extensions = {}
    if isinstance(exc, ValidationError) and isinstance(exc.detail, dict):
        # The DRF-shaped part: {field: [messages]} to RFC 9457 field errors.
        extensions["errors"] = [
            field_error((name,), str(message))
            for name, messages in exc.detail.items()
            for message in messages
        ]
    rendered = render_problem(
        REGISTRY,
        exc,
        instance=request.path if request is not None else "",
        extensions=extensions,
    )
    response = Response(
        rendered.body, status=rendered.status, content_type=PROBLEM_MEDIA_TYPE
    )
    for name, value in rendered.headers.items():
        response[name] = value
    return response
```

`render_problem` adds the current trace id, masks a 401's detail and adds its
challenge. `rn-forge-django`'s handler also walks nested serializer errors.

Set `EXCEPTION_HANDLER` to it in `REST_FRAMEWORK`. Register DRF's own
exception classes (`NotFound`, `PermissionDenied`, ...) on `REGISTRY` once,
rather than branching in the handler — the MRO walk then covers their
subclasses for free.

## 3. Concurrency

```python
from rn_forge.web import EntityVersionETagCodec, check_precondition

CODEC = EntityVersionETagCodec()

class VersionedMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        obj = getattr(self, "_etag_object", None)
        if obj is not None:
            response["ETag"] = CODEC.format(entity_id=obj.pk, version=obj.version)
        return super().finalize_response(request, response, *args, **kwargs)

    def check_version(self, obj, *, required=True):
        check_precondition(
            self.request.headers.get("If-Match"),
            current_version=obj.version,
            entity_id=obj.pk,
            required=required,
        )
```

## 4. Idempotency — a cache-backed store

**`cache.add()` is load-bearing.** It is an atomic set-if-absent; a
`get`-then-`set` adapter silently loses the race safety the protocol requires,
and no ordinary test will notice.

```python
from django.core.cache import cache
from rn_forge.web import IdempotencyKeyReuse, StoredResponse, request_hash

TTL = 60 * 60 * 24

class CacheIdempotencyStore:
    def record_or_replay(self, *, scope, key, request_body):
        slot = f"idempotency:{len(scope)}:{scope}:{key}"  # length prefix: no ":" collisions
        digest = request_hash(request_body)

        if cache.add(slot, {"hash": digest, "response": None}, TTL):
            return None                                  # we claimed it; first sight

        entry = cache.get(slot)
        if entry is None:                                # expired between add and get
            return None
        if entry["hash"] != digest:
            raise IdempotencyKeyReuse(
                "Idempotency key {} was replayed with a different request body",
                key, error_code=409,
            )
        stored = entry["response"]
        if stored is None:
            return None                                  # claimed, still in flight
        return StoredResponse(status=stored["status"], body=stored["body"], replayed=True)

    def complete(self, *, scope, key, status, response_body):
        slot = f"idempotency:{len(scope)}:{scope}:{key}"
        entry = cache.get(slot) or {"hash": None, "response": None}
        entry["response"] = {"status": status, "body": dict(response_body)}
        cache.set(slot, entry, TTL)
```

Use a shared cache backend. `LocMemCache` gives each worker process its own
dictionary, which makes the store a no-op under any real deployment.

## 5. Health — a view over the sync runner

```python
from django.db import connection
from django.http import JsonResponse
from rn_forge.web import CheckResult, run_checks_sync

def check_db():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return CheckResult(status="pass")

def readyz(request):
    report = run_checks_sync({"db": check_db}, required=["db"])
    return JsonResponse(report.as_body(), status=report.http_status)

def healthz(request):
    return JsonResponse({"status": "pass"})   # liveness touches nothing
```

`run_checks_sync`, not `run_checks` — and it will raise rather than let an
`async def` check be reported as passing.

## 6. Casing

Wire a camelCase renderer and parser through `REST_FRAMEWORK`, so the rule holds
by default rather than per serializer. `rn-forge-django` ships them; a recipe
here would be a convention that holds until the first hurried endpoint.

## 7. Pagination

Subclass DRF's own `CursorPagination` and emit the AIP-158 envelope from
`get_paginated_response` / `get_paginated_response_schema`. DRF's keyset filter
compares one position and skips ties with an offset held in its cursor; the
shared token carries a sort value and a primary key instead, so
`rn_forge.django.drf.pagination.CursorPagination` overrides `paginate_queryset`
to filter on that pair. Use it rather than writing another.

## Conformance

Once the above is wired, the driver is short:

```python
import pytest
from rn_forge.web.conformance import CASES, case_by_id, redact

def issue(client, case):
    return client.generic(
        case.request.method, case.request.path,
        data=case.request.body, headers=case.request.headers, **case.request.query,
    )

@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_conformance(client, case):          # `client` must be a FRESH app per case
    for prerequisite in case.depends_on:     # a replay only replays something
        issue(client, case_by_id(prerequisite))

    response = issue(client, case)
    assert response.status_code == case.expect_status
    for name, value in case.expect_headers.items():
        assert response[name] == value
    for name in case.expect_absent_headers:
        assert name not in response
    assert redact(response.json()) == dict(case.expect_body)
```

Two things this driver must get right: a **fresh application per case** (the
idempotency store must not carry over), and `depends_on` issued first.

Assert against the table, never against what FastAPI produced.
