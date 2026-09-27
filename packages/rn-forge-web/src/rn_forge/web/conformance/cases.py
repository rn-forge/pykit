"""HTTP conformance cases consumed by framework-specific test drivers."""

from __future__ import annotations

from http import HTTPStatus
from typing import Final

from rn_forge.web.conformance.types import (
    REDACTED,
    ConformanceArea,
    ConformanceCase,
    RequestSpec,
)
from rn_forge.web.tracing import EXPOSED_HEADERS
from rn_forge.web.pagination import encode_cursor
from rn_forge.web.problem import (
    BAD_REQUEST,
    BLANK_TYPE,
    CONFLICT,
    CONTENT_TOO_LARGE,
    GENERIC_SERVER_DETAIL,
    INTERNAL_ERROR,
    NOT_FOUND,
    PRECONDITION_FAILED,
    PRECONDITION_REQUIRED,
    SERVICE_UNAVAILABLE,
    TOO_MANY_REQUESTS,
    UNAUTHORIZED,
    VALIDATION_ERROR,
    FORBIDDEN,
    ProblemType,
)

__all__ = ["CASES", "case_by_id", "cases_for"]

_JSON: Final = {"Content-Type": "application/json"}
_PROBLEM: Final = {"Content-Type": "application/problem+json"}
_LINKSET: Final = {"Content-Type": "application/linkset+json"}

_TRACEPARENT: Final = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
"""A well-formed W3C traceparent, from the standard's own example."""


def _problem_body(
    row: ProblemType, detail: str, **extensions: object
) -> dict[str, object]:
    """The problem body a driver must produce, already in redacted form.

    Every case here uses ``about:blank`` (no ``type_base`` configured), so per
    RFC 9457 §4.2.1 the title is the HTTP status phrase, not *row*'s
    kit-specific title.
    """
    return {
        "type": BLANK_TYPE,
        "title": HTTPStatus(row.status).phrase,
        "status": row.status,
        "detail": detail,
        "instance": REDACTED,
        "traceId": REDACTED,
        **extensions,
    }


PAGE_1_NEXT_TOKEN: Final = encode_cursor("2", "2")
ORDERED_PAGE_1_NEXT_TOKEN: Final = encode_cursor("2", "2", "id desc")
"""The token page one must return.

Asserted **exactly**, not redacted. A token is opaque to a *client*; between
two servers running the same codec over the same keyset it is deterministic,
and two stacks that emit different tokens for the same page have diverged in a
way no client-visible field would show.
"""


CASES: Final[tuple[ConformanceCase, ...]] = (
    # --- Problem bodies (problem.py) -------------------------------
    ConformanceCase(
        id="problem.unregistered-is-500-without-detail",
        area="problem",
        description=(
            "An exception with no registry row falls back to internal-error, and "
            "its detail is the generic string — str(exc) at 5xx leaks internals."
        ),
        request=RequestSpec("GET", "/conformance/boom"),
        expect_status=500,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(INTERNAL_ERROR, GENERIC_SERVER_DETAIL),
    ),
    ConformanceCase(
        id="problem.registered-domain-conflict-is-409",
        area="problem",
        description="A registered DomainConflict resolves to conflict/409 with str(exc) as the detail.",
        request=RequestSpec("GET", "/conformance/conflict"),
        expect_status=409,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(CONFLICT, "Order already dispatched"),
    ),
    ConformanceCase(
        id="problem.framework-404-is-a-problem-body",
        area="problem",
        description=(
            "A 404 raised by the framework's own routing, not by application code, "
            "still comes back as problem+json rather than the framework's default page."
        ),
        request=RequestSpec("GET", "/conformance/missing"),
        expect_status=404,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(NOT_FOUND, "Not Found"),
    ),
    ConformanceCase(
        id="problem.validation-errors-are-rfc6901-pointers",
        area="problem",
        description=(
            "The single most drift-prone case: DRF's {field: [msg]} and pydantic's "
            "loc/msg list must normalize to the identical pointer list."
        ),
        request=RequestSpec("POST", "/conformance/validate", headers=_JSON, body={}),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "Validation Error",
            errors=[{"pointer": "/name", "detail": "This field is required."}],
        ),
    ),
    # --- Concurrency (concurrency.py) ------------------------------
    ConformanceCase(
        id="concurrency.absent-if-match-on-required-route-is-428",
        area="concurrency",
        description="RFC 6585 §3: the route demands a precondition and none was sent.",
        request=RequestSpec("PATCH", "/conformance/items/1", headers=_JSON, body={}),
        expect_status=428,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            PRECONDITION_REQUIRED, "This endpoint requires an If-Match precondition"
        ),
    ),
    ConformanceCase(
        id="concurrency.stale-if-match-is-412-not-409",
        area="concurrency",
        description=(
            "RFC 9110 §15.5.13: the precondition evaluated to false. 412, not 409."
        ),
        request=RequestSpec(
            "PATCH",
            "/conformance/items/1",
            headers={**_JSON, "If-Match": 'W/"1:6"'},
            body={},
        ),
        expect_status=412,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            PRECONDITION_FAILED, "Precondition failed: expected version 7, got 6"
        ),
    ),
    ConformanceCase(
        id="concurrency.star-if-match-passes",
        area="concurrency",
        description="RFC 9110 §13.1.1: `*` matches any current representation.",
        request=RequestSpec(
            "PATCH",
            "/conformance/items/1",
            headers={**_JSON, "If-Match": "*"},
            body={},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"id": "1", "version": 7},
    ),
    ConformanceCase(
        id="concurrency.malformed-if-match-is-400",
        area="concurrency",
        description="An unparseable validator is a 400, never a crash and never a 412.",
        request=RequestSpec(
            "PATCH",
            "/conformance/items/1",
            headers={**_JSON, "If-Match": "not-an-etag"},
            body={},
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            BAD_REQUEST, "Malformed If-Match validator: not-an-etag"
        ),
    ),
    ConformanceCase(
        id="concurrency.if-none-match-matches-is-304",
        area="concurrency",
        description=(
            "RFC 9110 §13.1.2, §15.4.5: a GET whose If-None-Match weakly matches "
            "the current ETag gets 304, no body, ETag repeated."
        ),
        request=RequestSpec(
            "GET", "/conformance/items/1", headers={"If-None-Match": 'W/"1:7"'}
        ),
        expect_status=304,
        expect_headers={"ETag": 'W/"1:7"'},
        expect_body={},
    ),
    ConformanceCase(
        id="concurrency.if-none-match-mismatch-is-200",
        area="concurrency",
        description="A stale If-None-Match is an ordinary 200 with the current ETag.",
        request=RequestSpec(
            "GET", "/conformance/items/1", headers={"If-None-Match": 'W/"1:1"'}
        ),
        expect_status=200,
        expect_headers={**_JSON, "ETag": 'W/"1:7"'},
        expect_body={"id": "1", "version": 7},
    ),
    # --- Pagination (pagination.py) --------------------------------------
    ConformanceCase(
        id="pagination.first-page-carries-a-next-token",
        area="pagination",
        description="The AIP-158 envelope: items + nextPageToken, and totalSize absent by default.",
        request=RequestSpec("GET", "/conformance/items", query={"pageSize": "2"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "1"}, {"id": "2"}],
            "nextPageToken": PAGE_1_NEXT_TOKEN,
        },
    ),
    ConformanceCase(
        id="pagination.last-page-has-a-null-next-token",
        area="pagination",
        description=(
            "nextPageToken is present and null on the last page rather than omitted, "
            "so a generated client's type does not change shape between pages."
        ),
        request=RequestSpec(
            "GET",
            "/conformance/items",
            query={"pageSize": "2", "pageToken": PAGE_1_NEXT_TOKEN},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": [{"id": "3"}], "nextPageToken": None},
    ),
    ConformanceCase(
        id="pagination.oversized-page-size-is-clamped-not-rejected",
        area="pagination",
        description=(
            "AIP-158: coerce down to the maximum. A FastAPI Query(le=...) would 422 here, "
            "and that is the divergence this case exists to catch."
        ),
        request=RequestSpec("GET", "/conformance/items", query={"pageSize": "1000"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "1"}, {"id": "2"}],
            "nextPageToken": PAGE_1_NEXT_TOKEN,
        },
    ),
    ConformanceCase(
        id="pagination.tampered-page-token-is-400",
        area="pagination",
        description="A malformed opaque token is InvalidCursor → 400, never a 500.",
        request=RequestSpec(
            "GET", "/conformance/items", query={"pageToken": "!!!not-base64!!!"}
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "Malformed page token"),
    ),
    ConformanceCase(
        id="pagination.order-by-descending-binds-the-token",
        area="pagination",
        description=(
            "AIP-132: orderBy reorders the list, and the next token carries that "
            "order so it cannot be replayed under another."
        ),
        request=RequestSpec(
            "GET",
            "/conformance/items",
            query={"pageSize": "2", "orderBy": "id desc"},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "3"}, {"id": "2"}],
            "nextPageToken": ORDERED_PAGE_1_NEXT_TOKEN,
        },
    ),
    ConformanceCase(
        id="pagination.order-by-unlisted-field-is-400",
        area="pagination",
        description="An orderBy field the endpoint does not list is a 400, never silently ignored.",
        request=RequestSpec("GET", "/conformance/items", query={"orderBy": "secret"}),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "Cannot order by 'secret'; allowed: id"),
    ),
    ConformanceCase(
        id="pagination.order-by-two-fields-is-400",
        area="pagination",
        description=(
            "A list sorts by one field; a second term is a 400, never silently ignored."
        ),
        request=RequestSpec(
            "GET", "/conformance/items", query={"orderBy": "id desc,id"}
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "orderBy accepts one field; got 2"),
    ),
    ConformanceCase(
        id="pagination.token-under-a-different-order-by-is-400",
        area="pagination",
        description="A token issued for the default order is rejected once orderBy changes.",
        request=RequestSpec(
            "GET",
            "/conformance/items",
            query={"orderBy": "id desc", "pageToken": PAGE_1_NEXT_TOKEN},
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "pageToken does not match orderBy"),
    ),
    # --- Idempotency (idempotency.py) ------------------------------------
    ConformanceCase(
        id="idempotency.first-call-executes",
        area="idempotency",
        description="First sight of a key: the handler runs and its response is stored.",
        request=RequestSpec(
            "POST",
            "/conformance/charges",
            headers={**_JSON, "Idempotency-Key": "k-1"},
            body={"amount": 100},
        ),
        expect_status=201,
        expect_headers=_JSON,
        expect_body={"charged": 100, "replayed": False},
    ),
    ConformanceCase(
        id="idempotency.replay-returns-the-stored-response",
        area="idempotency",
        description=(
            "The same key and the same body replays the stored response, "
            "including its original status."
        ),
        depends_on=("idempotency.first-call-executes",),
        request=RequestSpec(
            "POST",
            "/conformance/charges",
            headers={**_JSON, "Idempotency-Key": "k-1"},
            body={"amount": 100},
        ),
        expect_status=201,
        expect_headers=_JSON,
        expect_body={"charged": 100, "replayed": True},
    ),
    ConformanceCase(
        id="idempotency.same-key-different-body-is-422",
        area="idempotency",
        description=(
            "Body hashing is the whole point of the module: a replayed key with a "
            "different body is a detectable client bug, not a silently-wrong replay. "
            "422 per draft-ietf-httpapi-idempotency-key-header §2.7."
        ),
        depends_on=("idempotency.first-call-executes",),
        request=RequestSpec(
            "POST",
            "/conformance/charges",
            headers={**_JSON, "Idempotency-Key": "k-1"},
            body={"amount": 999},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "Idempotency key k-1 was replayed with a different request body",
        ),
    ),
    # --- Health (health.py) ------------------------------------------------
    ConformanceCase(
        id="health.all-pass-is-200",
        area="health",
        description="Every check passes; the aggregate is pass and the status is 200.",
        request=RequestSpec("GET", "/conformance/readyz"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "status": "pass",
            "checks": {
                "db": {
                    "status": "pass",
                    "reason": None,
                    "remediation": None,
                    "details": {},
                },
                "queue": {
                    "status": "pass",
                    "reason": None,
                    "remediation": None,
                    "details": {},
                },
            },
        },
    ),
    ConformanceCase(
        id="health.required-failure-is-503",
        area="health",
        description="A failing check named in `required` takes the endpoint to 503.",
        request=RequestSpec("GET", "/conformance/readyz", query={"fail": "db"}),
        expect_status=503,
        # Not problem+json: a readiness report is the endpoint's normal
        # representation, and the 503 is its verdict rather than an error.
        expect_headers=_JSON,
        expect_body={
            "status": "fail",
            "checks": {
                "db": {
                    "status": "fail",
                    "reason": "unreachable",
                    "remediation": None,
                    "details": {},
                },
                "queue": {
                    "status": "pass",
                    "reason": None,
                    "remediation": None,
                    "details": {},
                },
            },
        },
    ),
    ConformanceCase(
        id="health.optional-failure-is-200-degraded",
        area="health",
        description=(
            "A failing check outside `required` degrades the aggregate status but "
            "leaves the HTTP status at 200 — the load balancer keeps sending traffic."
        ),
        request=RequestSpec("GET", "/conformance/readyz", query={"fail": "queue"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "status": "fail",
            "checks": {
                "db": {
                    "status": "pass",
                    "reason": None,
                    "remediation": None,
                    "details": {},
                },
                "queue": {
                    "status": "fail",
                    "reason": "unreachable",
                    "remediation": None,
                    "details": {},
                },
            },
        },
    ),
    ConformanceCase(
        id="problem.content-too-large-is-413",
        area="problem",
        description="RFC 9110 §15.5.14. A body over the configured limit is 413.",
        request=RequestSpec("POST", "/conformance/validate", body={"name": "x" * 250}),
        expect_status=413,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            CONTENT_TOO_LARGE, "Request body exceeds the configured limit"
        ),
    ),
    ConformanceCase(
        id="problem.too-many-requests-carries-retry-after",
        area="problem",
        description="RFC 6585 §4. A 429 carries `Retry-After` in seconds.",
        request=RequestSpec("GET", "/conformance/throttled"),
        expect_status=429,
        expect_headers={**_PROBLEM, "Retry-After": "30"},
        expect_body=_problem_body(TOO_MANY_REQUESTS, "Too many requests"),
    ),
    ConformanceCase(
        id="problem.service-unavailable-carries-retry-after",
        area="problem",
        description="RFC 9110 §15.6.4. A 503 problem carries `Retry-After` in seconds.",
        request=RequestSpec("GET", "/conformance/unavailable"),
        expect_status=503,
        expect_headers={**_PROBLEM, "Retry-After": "5"},
        expect_body=_problem_body(SERVICE_UNAVAILABLE, GENERIC_SERVER_DETAIL),
    ),
    ConformanceCase(
        id="health.liveness-is-200",
        area="health",
        description="Liveness touches no dependency and always answers 200.",
        request=RequestSpec("GET", "/conformance/livez"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"status": "pass"},
    ),
    # --- Auth (auth.py) -------------------------------------------------
    ConformanceCase(
        id="auth.no-credentials-is-401-with-a-challenge",
        area="auth",
        description=(
            "RFC 6750 §3. DRF's stock behaviour does not match this and must be "
            "overridden rather than inherited."
        ),
        request=RequestSpec("GET", "/conformance/private"),
        expect_status=401,
        expect_headers={
            **_PROBLEM,
            "WWW-Authenticate": 'Bearer realm="conformance"',
        },
        expect_body=_problem_body(UNAUTHORIZED, "Authentication failed."),
    ),
    ConformanceCase(
        id="auth.insufficient-scope-is-403-without-a-challenge",
        area="auth",
        description=(
            "Valid credentials lacking the scope is 403 and carries NO challenge — "
            "a challenge here would tell a browser to re-prompt for credentials "
            "that were already correct."
        ),
        request=RequestSpec(
            "GET", "/conformance/private", headers={"Authorization": "Bearer no-scopes"}
        ),
        expect_status=403,
        expect_headers=_PROBLEM,
        expect_absent_headers=frozenset({"WWW-Authenticate"}),
        expect_body=_problem_body(
            FORBIDDEN, "The authenticated principal lacks the required access"
        ),
    ),
    # --- Casing (api-conventions.md) ------------------------------------------
    ConformanceCase(
        id="casing.response-bodies-are-camel-case",
        area="casing",
        description=(
            "Asserted structurally by the driver rather than per case: every key in "
            "every response body above, at every depth, matches ^[a-z][a-zA-Z0-9]*$ "
            "or is an RFC 9457 core member. RFC 9457's own members are single "
            "lowercase words and are unaffected."
        ),
        request=RequestSpec("GET", "/conformance/items", query={"pageSize": "2"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "1"}, {"id": "2"}],
            "nextPageToken": PAGE_1_NEXT_TOKEN,
        },
    ),
    # --- Tracing (tracing.py, asgi.py) -----------------------------------
    ConformanceCase(
        id="tracing.inbound-traceparent-continues-the-trace",
        area="tracing",
        description=(
            "A caller-supplied W3C traceparent continues that trace: the "
            "response's traceresponse carries the same trace id with a new "
            "span id."
        ),
        request=RequestSpec(
            "GET",
            "/conformance/echo",
            headers={
                "traceparent": _TRACEPARENT,
            },
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_header_patterns={
            "traceresponse": r"00-4bf92f3577b34da6a3ce929d0e0e4736-[0-9a-f]{16}-[0-9a-f]{2}",
        },
        expect_body={},
    ),
    ConformanceCase(
        id="tracing.malformed-traceparent-starts-a-new-trace",
        area="tracing",
        description=(
            "A malformed traceparent is never an error: the server discards "
            "it and starts a new trace."
        ),
        request=RequestSpec(
            "GET", "/conformance/echo", headers={"traceparent": "garbage"}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_header_patterns={
            "traceresponse": r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}",
        },
        expect_body={},
    ),
    ConformanceCase(
        id="tracing.problem-body-carries-the-trace-id",
        area="tracing",
        description=(
            "The current trace id reaches the problem body as the traceId "
            "extension, which is what makes a user-reported error findable in "
            "the trace backend and the logs."
        ),
        request=RequestSpec(
            "GET", "/conformance/boom", headers={"traceparent": _TRACEPARENT}
        ),
        expect_status=500,
        expect_headers=_PROBLEM,
        expect_header_patterns={
            "traceresponse": r"00-4bf92f3577b34da6a3ce929d0e0e4736-[0-9a-f]{16}-[0-9a-f]{2}",
        },
        expect_body=_problem_body(INTERNAL_ERROR, GENERIC_SERVER_DETAIL),
    ),
    ConformanceCase(
        id="tracing.house-header-is-not-echoed",
        area="tracing",
        description="X-Correlation-ID is a removed house header: not read, and never sent back.",
        request=RequestSpec(
            "GET", "/conformance/echo", headers={"X-Correlation-ID": "abc123"}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_absent_headers=frozenset({"X-Correlation-ID"}),
        expect_body={},
    ),
    # --- Deprecation (deprecation.py) -----------------------------------
    ConformanceCase(
        id="deprecation.endpoint-carries-rfc9745-headers",
        area="deprecation",
        description=(
            "RFC 9745's Deprecation (a structured-field date) and RFC 8594's "
            "Sunset (an HTTP-date), plus a Link rel=deprecation."
        ),
        request=RequestSpec("GET", "/conformance/legacy"),
        expect_status=200,
        expect_headers={
            **_JSON,
            "Deprecation": "@1767225600",
            "Sunset": "Wed, 01 Jul 2026 00:00:00 GMT",
            "Link": '<https://example.com/deprecated>; rel="deprecation"',
        },
        expect_body={"legacy": True},
    ),
    # --- Discovery (openapi.py) ------------------------------------------
    ConformanceCase(
        id="discovery.api-catalog-is-an-rfc9264-linkset",
        area="discovery",
        description=(
            "RFC 9727's /.well-known/api-catalog: an RFC 9264 linkset naming the "
            "OpenAPI document, the docs UI, and the readiness path."
        ),
        request=RequestSpec("GET", "/.well-known/api-catalog"),
        expect_status=200,
        expect_headers=_LINKSET,
        expect_body={
            "linkset": [
                {
                    "anchor": "/",
                    "service-desc": [{"href": "/openapi.json"}],
                    "service-doc": [{"href": "/docs"}],
                    "status": [{"href": "/readyz"}],
                }
            ]
        },
    ),
    # --- Security headers (security.py) -----------------------------------
    ConformanceCase(
        id="security.owasp-headers-are-present",
        area="security",
        description="The OWASP REST Security Cheat Sheet response headers, on every response.",
        request=RequestSpec("GET", "/conformance/echo"),
        expect_status=200,
        expect_headers={
            **_JSON,
            "Cache-Control": "no-store",
            "Content-Security-Policy": "frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
        expect_body={},
    ),
    # --- CORS (tracing.py: EXPOSED_HEADERS) --------------------------------
    ConformanceCase(
        id="cors.exposed-headers-are-comma-joined",
        area="cors",
        description=(
            "A CORS response exposes the kit's own headers to a browser, in "
            "configured order. traceresponse is exposed by the OpenTelemetry "
            "response propagator itself, not by this list."
        ),
        request=RequestSpec(
            "GET", "/conformance/echo", headers={"Origin": "https://example.com"}
        ),
        expect_status=200,
        expect_headers={
            **_JSON,
            "Access-Control-Allow-Origin": "https://example.com",
            "Access-Control-Expose-Headers": ", ".join(
                (*EXPOSED_HEADERS, "traceresponse")
            ),
        },
        expect_body={},
    ),  # --- Tabular transfer and bulk operations (transfer.py) ----------------
    ConformanceCase(
        id="transfer.export-is-negotiated-from-accept",
        area="transfer",
        description=(
            "RFC 9110 §12: a list asked for as text/csv is answered as CSV, "
            "as an attachment (RFC 6266)."
        ),
        request=RequestSpec(
            "GET", "/conformance/orders", headers={"Accept": "text/csv"}
        ),
        expect_status=200,
        expect_header_patterns={"Content-Type": r"text/csv(; charset=utf-8)?"},
        expect_headers={
            "Content-Disposition": (
                "attachment; filename=\"orders.csv\"; filename*=UTF-8''orders.csv"
            ),
        },
        expect_text="id,name\r\n1,widget\r\n",
    ),
    ConformanceCase(
        id="transfer.export-format-param-is-the-fallback",
        area="transfer",
        description="?format=csv selects CSV for a plain link that cannot send Accept.",
        request=RequestSpec("GET", "/conformance/orders", query={"format": "csv"}),
        expect_status=200,
        expect_header_patterns={"Content-Type": r"text/csv(; charset=utf-8)?"},
        expect_headers={
            "Content-Disposition": (
                "attachment; filename=\"orders.csv\"; filename*=UTF-8''orders.csv"
            ),
        },
        expect_text="id,name\r\n1,widget\r\n",
    ),
    ConformanceCase(
        id="transfer.export-filename-carries-rfc8187-encoding",
        area="transfer",
        description=(
            "A non-ASCII filename gets an ASCII fallback in filename= and the "
            "percent-encoded UTF-8 in filename*= (RFC 8187)."
        ),
        request=RequestSpec(
            "GET", "/conformance/orders/named", headers={"Accept": "text/csv"}
        ),
        expect_status=200,
        expect_header_patterns={"Content-Type": r"text/csv(; charset=utf-8)?"},
        expect_headers={
            "Content-Disposition": (
                'attachment; filename="Ord_rs 2026.csv"; '
                "filename*=UTF-8''Ord%C3%A9rs%202026.csv"
            ),
        },
        expect_text="id,name\r\n1,widget\r\n",
    ),
    ConformanceCase(
        id="transfer.export-over-the-cap-is-422",
        area="transfer",
        description="An export above the configured cap is a 422 problem naming the cap.",
        request=RequestSpec(
            "GET", "/conformance/orders/over-cap", headers={"Accept": "text/csv"}
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "The export exceeds the limit of 1 rows; narrow the filter.",
        ),
    ),
    ConformanceCase(
        id="transfer.import-report-counts-and-validate-only",
        area="transfer",
        description=(
            "AIP-136/AIP-163: a multipart upload with validateOnly=true is 200 "
            "with the counts it would produce."
        ),
        request=RequestSpec(
            "POST",
            "/conformance/orders:import",
            headers={"Content-Type": "multipart/form-data"},
            query={"validateOnly": "true"},
            body={"file": "id,name,Quantity\n2,gadget,3\n"},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"created": 1, "updated": 0, "skipped": 0, "validateOnly": True},
    ),
    ConformanceCase(
        id="transfer.import-row-errors-are-422-pointers",
        area="transfer",
        description=(
            "Any row error fails the whole import as a 422 whose errors[].pointer "
            "is /rows/<row>/<column>."
        ),
        request=RequestSpec(
            "POST",
            "/conformance/orders:import",
            headers={"Content-Type": "multipart/form-data"},
            body={"file": "id,name,Quantity\n2,gadget,three\n"},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "One or more rows are invalid.",
            errors=[{"pointer": "/rows/0/Quantity", "detail": "Enter a whole number."}],
        ),
    ),
    ConformanceCase(
        id="transfer.batch-create-item-failure-is-422-pointer",
        area="transfer",
        description=(
            "AIP-233: one invalid item fails the whole batch; the pointer names "
            "the item in the requests array."
        ),
        request=RequestSpec(
            "POST",
            "/conformance/orders:batchCreate",
            headers=_JSON,
            body={"requests": [{"name": "ok"}, {}]},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "One or more rows are invalid.",
            errors=[
                {"pointer": "/requests/1/name", "detail": "This field is required."}
            ],
        ),
    ),
    ConformanceCase(
        id="transfer.failed-batch-create-persists-nothing",
        area="transfer",
        description="All or nothing: after the failed batch, the collection still has one order.",
        request=RequestSpec("GET", "/conformance/orders/count"),
        depends_on=("transfer.batch-create-item-failure-is-422-pointer",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"count": 1},
    ),
    ConformanceCase(
        id="transfer.batch-create-returns-the-created-resources",
        area="transfer",
        description="AIP-233: a successful batch is 200 with the created resources under the plural name.",
        request=RequestSpec(
            "POST",
            "/conformance/orders:batchCreate",
            headers=_JSON,
            body={"requests": [{"name": "gadget"}]},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"orders": [{"id": "2", "name": "gadget"}]},
    ),
    ConformanceCase(
        id="transfer.batch-delete-with-unknown-id-is-404",
        area="transfer",
        description="AIP-235: one id that does not exist fails the whole batch.",
        request=RequestSpec(
            "POST",
            "/conformance/orders:batchDelete",
            headers=_JSON,
            body={"ids": ["1", "missing"]},
        ),
        expect_status=404,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(NOT_FOUND, "Order missing not found"),
    ),
    ConformanceCase(
        id="transfer.failed-batch-delete-deletes-nothing",
        area="transfer",
        description="All or nothing: the order named alongside the unknown id is still there.",
        request=RequestSpec("GET", "/conformance/orders/1"),
        depends_on=("transfer.batch-delete-with-unknown-id-is-404",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"id": "1", "name": "widget"},
    ),
    ConformanceCase(
        id="transfer.batch-delete-is-204",
        area="transfer",
        description="AIP-235: a successful batch delete is 204 with no body.",
        request=RequestSpec(
            "POST",
            "/conformance/orders:batchDelete",
            headers=_JSON,
            body={"ids": ["1"]},
        ),
        expect_status=204,
        expect_body={},
    ),
    # --- Timestamps (api-conventions.md §18) -----------------------------
    ConformanceCase(
        id="timestamps.rfc-3339-utc-with-z",
        area="timestamps",
        description=(
            "AIP-142: an instant is an RFC 3339 string in UTC with a Z suffix, "
            "not an offset and not a zone name."
        ),
        request=RequestSpec("GET", "/conformance/stamped"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"id": "1", "createTime": "2026-09-23T14:05:00Z"},
    ),
    # --- Long-running operations (operations.py) -------------------------
    ConformanceCase(
        id="operations.start-is-202-with-location",
        area="operations",
        description=(
            "AIP-151: the call answers 202, names the operation in Location, and "
            "returns it unfinished."
        ),
        request=RequestSpec("POST", "/conformance/exports", headers=_JSON, body={}),
        expect_status=202,
        expect_headers={**_JSON, "Location": "/conformance/operations/1"},
        expect_body={"name": "operations/1", "done": False},
    ),
    ConformanceCase(
        id="operations.finished-carries-its-response",
        area="operations",
        description="A finished operation has done=true and a response, and no error.",
        request=RequestSpec("GET", "/conformance/operations/1"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "name": "operations/1",
            "done": True,
            "response": {"id": "1"},
        },
    ),
    ConformanceCase(
        id="operations.failed-carries-a-problem",
        area="operations",
        description=(
            "A failed operation has done=true and an RFC 9457 problem as its error, "
            "never google.rpc.Status."
        ),
        request=RequestSpec("GET", "/conformance/operations/2"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "name": "operations/2",
            "done": True,
            "error": {
                "type": BLANK_TYPE,
                "title": "Conflict",
                "status": 409,
                "detail": "Order already dispatched",
                "instance": REDACTED,
            },
        },
    ),
)


def cases_for(area: ConformanceArea) -> tuple[ConformanceCase, ...]:
    """Return every case in *area*, in table order."""
    return tuple(case for case in CASES if case.area == area)


def case_by_id(case_id: str) -> ConformanceCase:
    """Return the case with *case_id*, for resolving ``depends_on``.

    Raises:
        KeyError: No case has that id.
    """
    for case in CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)
