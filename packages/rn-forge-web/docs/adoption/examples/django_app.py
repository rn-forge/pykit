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
    AUTH_FAILED_DETAIL,
    PROBLEM_MEDIA_TYPE,
    AuthenticationFailed,
    CheckResult,
    DomainConflict,
    EntityVersionETagCodec,
    IdempotencyKeyRequired,
    IdempotencyKeyReuse,
    Page,
    Principal,
    Requirement,
    ScopeAuthorizer,
    StoredResponse,
    bind_correlation_id,
    challenge_header,
    check_precondition,
    clamp_page_size,
    decode_cursor,
    default_registry,
    encode_cursor,
    errors_from_field_map,
    get_correlation_id,
    request_hash,
    run_checks_sync,
)

REGISTRY = default_registry()
REGISTRY.register(NotFound, REGISTRY.problem_for(LookupError()))

CODEC = EntityVersionETagCodec()
AUTHORIZER = ScopeAuthorizer()
ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
ITEM_VERSION, PAGE_DEFAULT, PAGE_CAP, REALM = 7, 2, 2, "conformance"


# --- 1. correlation: the WSGI form, which resets ---------------------------


class CorrelationIdMiddleware:
    """First in MIDDLEWARE, so the exception handler below sees the binding."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        with bind_correlation_id(request.headers.get("X-Correlation-ID")) as cid:
            response = self.get_response(request)
            response["X-Correlation-ID"] = cid
            return response


# --- 2. errors: one handler, set as REST_FRAMEWORK["EXCEPTION_HANDLER"] ----


def problem_exception_handler(exc: BaseException, context: dict[str, Any]) -> Response:
    request = context.get("request")
    row = REGISTRY.problem_for(exc)

    extensions: dict[str, Any] = {"correlation_id": get_correlation_id()}
    if detail := getattr(exc, "detail", None):
        if isinstance(detail, dict):
            extensions["errors"] = errors_from_field_map(detail)

    problem = REGISTRY.build(
        exc,
        instance=request.path if request is not None else "",
        detail=AUTH_FAILED_DETAIL if row.status == 401 else None,
        extensions=extensions,
    )
    response = Response(
        problem.as_body(), status=problem.status, content_type=PROBLEM_MEDIA_TYPE
    )
    if problem.status == 401:
        response["WWW-Authenticate"] = challenge_header(realm=REALM)
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
        start = 0
        if token := request.query_params.get("pageToken"):
            cursor = decode_cursor(token)  # InvalidCursor → 400
            start = next(
                (i + 1 for i, r in enumerate(ROWS) if r["id"] == cursor.entity_id), 0
            )
        window = ROWS[start : start + size]
        more = start + size < len(ROWS)
        page = Page(
            items=window,
            next_page_token=encode_cursor(window[-1]["id"], window[-1]["id"])
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
        key = request.headers.get("Idempotency-Key")
        if key is None:
            raise IdempotencyKeyRequired("Idempotency-Key is required", error_code=400)
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
