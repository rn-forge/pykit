"""The same ten endpoints on Django + DRF.

Not executed by this package's tests — installing Django here would put a web
framework in `rn-forge-web`'s dependency graph, which is the boundary the
package exists to hold. It is symbol-checked against the public API, and its
end-to-end proof is the conformance driver `rn-forge-django` ships.

Compare it with `asgi_app.py` and `fastapi_app.py`: the handlers differ, and
every wire decision is made by the same call into `rn_forge.web`. That is the
point of the package.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from rn_forge.web import (
    IDEMPOTENCY_KEY_HEADER,
    PROBLEM_MEDIA_TYPE,
    AuthenticationFailed,
    CheckResult,
    DomainConflict,
    EntityVersionETagCodec,
    IdempotencyKeyReuse,
    Page,
    Principal,
    Requirement,
    ScopeAuthorizer,
    StoredResponse,
    check_idempotency_key,
    check_precondition,
    check_cursor_order,
    clamp_page_size,
    format_order_by,
    parse_order_by,
    decode_cursor,
    default_registry,
    encode_cursor,
    field_error,
    render_problem,
    request_hash,
    run_checks_sync,
)

REGISTRY = default_registry()
REGISTRY.register(NotFound, REGISTRY.problem_for(LookupError()))

CODEC = EntityVersionETagCodec()
AUTHORIZER = ScopeAuthorizer()
ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
ITEM_VERSION, PAGE_DEFAULT, PAGE_CAP, REALM = 7, 2, 2, "conformance"


# --- 1. tracing: rn_forge.django.tracing.instrument(), called once from
# wsgi.py/asgi.py and manage.py, before Django loads — not a middleware.
# DjangoInstrumentor inserts its own middleware into MIDDLEWARE at position 0.
# Left out of this endpoint-only example — see `rn-forge-django`'s own
# `docs/guides/quickstart.md`.


# --- 2. errors: one handler, set as REST_FRAMEWORK["EXCEPTION_HANDLER"] ----


def problem_exception_handler(exc: BaseException, context: dict[str, Any]) -> Response:
    request = context.get("request")
    extensions: dict[str, Any] = {}
    if isinstance(detail := getattr(exc, "detail", None), dict):
        # Flat serializers only; rn_forge.django also walks nested ones.
        extensions["errors"] = [
            field_error((name,), str(message))
            for name, messages in detail.items()
            for message in messages
        ]
    rendered = render_problem(
        REGISTRY,
        exc,
        instance=request.path if request is not None else "",
        extensions=extensions,
        realm=REALM,
    )
    response = Response(
        rendered.body, status=rendered.status, content_type=PROBLEM_MEDIA_TYPE
    )
    for name, value in rendered.headers.items():
        response[name] = value
    return response


# --- 3-5. the endpoints ----------------------------------------------------


class BoomView(APIView):
    def get(self, request):
        raise RuntimeError("connection to db-primary.internal failed: password=hunter2")


class ConflictView(APIView):
    def get(self, request):
        raise DomainConflict("Order already dispatched")


class ItemView(APIView):
    def patch(self, request, pk: str):
        check_precondition(
            request.headers.get("If-Match"),
            current_version=ITEM_VERSION,
            entity_id=pk,
            required=True,
        )
        response = Response({"id": pk, "version": ITEM_VERSION})
        response["ETag"] = CODEC.format(entity_id=pk, version=ITEM_VERSION)
        return response


class ItemListView(APIView):
    def get(self, request):
        raw = request.query_params.get("pageSize")
        # No validator on pageSize: AIP-158 clamps, and a 422 here is a violation.
        size = clamp_page_size(
            int(raw) if raw and raw.lstrip("-").isdigit() else None,
            default=PAGE_DEFAULT,
            cap=PAGE_CAP,
        )
        order = parse_order_by(  # InvalidOrderBy → 400
            request.query_params.get("orderBy"), allowed=["id"]
        )
        rows = ROWS[::-1] if order and order[0].descending else ROWS
        start = 0
        if token := request.query_params.get("pageToken"):
            cursor = decode_cursor(token)  # InvalidCursor → 400
            check_cursor_order(cursor, order)
            start = next(
                (i + 1 for i, r in enumerate(rows) if r["id"] == cursor.entity_id), 0
            )
        window = rows[start : start + size]
        more = start + size < len(rows)
        page = Page(
            items=window,
            next_page_token=encode_cursor(
                window[-1]["id"], window[-1]["id"], format_order_by(order)
            )
            if more
            else None,
        )
        return Response(page.as_body())


class CacheIdempotencyStore:
    """`cache.add()` is the atomic claim. A get-then-set loses the race safety."""

    TTL = 60 * 60 * 24

    def record_or_replay(self, *, scope: str, key: str, request_body: Any):
        slot, digest = f"idempotency:{scope}:{key}", request_hash(request_body)
        if cache.add(slot, {"hash": digest, "response": None}, self.TTL):
            return None
        entry = cache.get(slot)
        if entry is None:
            return None
        if entry["hash"] != digest:
            raise IdempotencyKeyReuse(
                "Idempotency key {} was replayed with a different request body",
                key,
                error_code=409,
            )
        stored = entry["response"]
        if stored is None:
            return None
        return StoredResponse(
            status=stored["status"], body=stored["body"], replayed=True
        )

    def complete(self, *, scope: str, key: str, status: int, response_body) -> None:
        slot = f"idempotency:{scope}:{key}"
        entry = cache.get(slot) or {"hash": None, "response": None}
        entry["response"] = {"status": status, "body": dict(response_body)}
        cache.set(slot, entry, self.TTL)


class ChargeView(APIView):
    store = CacheIdempotencyStore()

    def post(self, request):
        key = check_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        stored = self.store.record_or_replay(
            scope="charges", key=key, request_body=request.data
        )
        if stored is not None:
            return Response({**stored.body, "replayed": True}, status=stored.status)
        body = {"charged": request.data["amount"]}
        self.store.complete(scope="charges", key=key, status=201, response_body=body)
        return Response({**body, "replayed": False}, status=201)


class PrivateView(APIView):
    def get(self, request):
        header = request.headers.get("Authorization")
        if header is None or not header.startswith("Bearer "):
            raise AuthenticationFailed("No credentials were supplied")
        principal = Principal(subject="u1", scopes=frozenset())
        AUTHORIZER.authorize(
            principal, requires=Requirement(all_scopes=frozenset({"read"}))
        )
        return Response({"subject": principal.subject})


def readyz(request: HttpRequest) -> JsonResponse:
    failing = request.GET.get("fail")

    def make(name: str):
        return lambda: CheckResult(
            status="fail" if name == failing else "pass",
            reason="unreachable" if name == failing else None,
        )

    # run_checks_sync, not run_checks: it raises rather than let an async check
    # be reported as passing.
    report = run_checks_sync(
        {"db": make("db"), "queue": make("queue")}, required=["db"]
    )
    return JsonResponse(report.as_body(), status=report.http_status)


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "pass"})  # liveness touches nothing
