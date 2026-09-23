# Wiring rn-forge-web into Django

The whole adapter layer, and it is intentionally about a page. If it grows much
past this, the package boundary is wrong.

Some of what follows ships in `rn-forge-django`; where it does, use that rather
than pasting these. They are written out so the boundary is legible, and so an
application on plain Django/DRF is not blocked on that package.

## 1. Correlation — a WSGI middleware

Django is sync and its worker threads are reused, so this is the
**`bind_correlation_id`** case, not `set_correlation_id`.

```python
# myapp/middleware.py
from rn_forge.web import (
    DEFAULT_CORRELATION_HEADER, bind_correlation_id, resolve_correlation_id,
)

class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # A malformed caller ID is replaced, never echoed.
        inbound = resolve_correlation_id(request.headers.get(DEFAULT_CORRELATION_HEADER))
        with bind_correlation_id(inbound) as correlation_id:
            response = self.get_response(request)
            response[DEFAULT_CORRELATION_HEADER] = correlation_id
            return response
```

Put it **first** in `MIDDLEWARE`, so everything downstream — including the
exception handler — sees the binding.

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

`render_problem` adds the correlation ID, masks a 401's detail and adds its
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

Subclass DRF's own `CursorPagination` for its keyset machinery — which is
proven and is the hard part — and override only the cursor codec and
`get_paginated_response` / `get_paginated_response_schema` to emit the AIP-158
envelope. Do not reimplement keyset SQL.

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
