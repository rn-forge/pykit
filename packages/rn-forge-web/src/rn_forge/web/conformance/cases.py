"""The cases themselves: one per wire decision this package settles.

Every case here encodes a decision made elsewhere in the package, and the
comment above each group names it. A decision with no case is treated as
unfinished, so this file grows in the same change as the module it constrains.

The fixture endpoints a driver must expose
------------------------------------------

The paths below are not arbitrary; a driver builds a small application that
serves exactly these, over the primitives in this package:

| Path | Behaviour the driver wires |
| --- | --- |
| `/conformance/boom` | raises an unregistered exception |
| `/conformance/conflict` | raises `DomainConflict("Order already dispatched")` |
| `/conformance/missing` | the framework's own 404, mapped through the registry |
| `/conformance/validate` | validates a body with one required `name` field |
| `/conformance/items/1` | `PATCH`, `check_precondition(..., current_version=7, entity_id="1", required=True)` |
| `/conformance/items` | `GET`, a three-item collection paginated with `default=2, cap=2` |
| `/conformance/charges` | `POST`, guarded by an `InMemoryIdempotencyStore` |
| `/conformance/readyz` | `run_checks({"db": ..., "queue": ...}, required=["db"])` |
| `/conformance/private` | requires `Requirement(all_scopes={"read"})` |
| `/conformance/echo` | `GET`, returns `{}` and nothing else |

Each of those is one or two lines over this package's primitives, which is the
point: if a driver needs more than that, the split is wrong.
"""

from __future__ import annotations

from typing import Final

from rn_forge.web.conformance.types import (
    REDACTED,
    ConformanceArea,
    ConformanceCase,
    RequestSpec,
)
from rn_forge.web.pagination import encode_cursor
from rn_forge.web.problem import (
    BAD_REQUEST,
    BLANK_TYPE,
    CONFLICT,
    GENERIC_SERVER_DETAIL,
    INTERNAL_ERROR,
    NOT_FOUND,
    PRECONDITION_FAILED,
    PRECONDITION_REQUIRED,
    UNAUTHORIZED,
    VALIDATION_ERROR,
    FORBIDDEN,
    ProblemType,
)

__all__ = ["CASES", "case_by_id", "cases_for"]

_JSON: Final = {"Content-Type": "application/json"}
_PROBLEM: Final = {"Content-Type": "application/problem+json"}


def _problem_body(
    row: ProblemType, detail: str, **extensions: object
) -> dict[str, object]:
    """The problem body a driver must produce, already in redacted form."""
    return {
        "type": BLANK_TYPE,
        "title": row.title,
        "status": row.status,
        "detail": detail,
        "instance": REDACTED,
        "correlation_id": REDACTED,
        **extensions,
    }


PAGE_1_NEXT_TOKEN: Final = encode_cursor("2", "2")
"""The token page one must return.

Asserted **exactly**, not redacted. A token is opaque to a *client*; between
two servers running the same codec over the same keyset it is deterministic,
and two stacks that emit different tokens for the same page have diverged in a
way no client-visible field would show.
"""


CASES: Final[tuple[ConformanceCase, ...]] = (
    # --- Problem bodies (problem.py §2.2, §2.3) -------------------------------
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
            errors=[{"pointer": "/name", "message": "This field is required."}],
        ),
    ),
    # --- Concurrency (concurrency.py §3.1, §3.3) ------------------------------
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
            "RFC 9110 §15.5.13: the precondition evaluated to false. 409 is the "
            "resolved disagreement — see the web plan §3.1."
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
    # --- Pagination (pagination.py §4.1) --------------------------------------
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
    # --- Idempotency (idempotency.py §5.2) ------------------------------------
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
        id="idempotency.same-key-different-body-is-409",
        area="idempotency",
        description=(
            "Body hashing is the whole point of the module: a replayed key with a "
            "different body is a detectable client bug, not a silently-wrong replay."
        ),
        depends_on=("idempotency.first-call-executes",),
        request=RequestSpec(
            "POST",
            "/conformance/charges",
            headers={**_JSON, "Idempotency-Key": "k-1"},
            body={"amount": 999},
        ),
        expect_status=409,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            CONFLICT,
            "Idempotency key k-1 was replayed with a different request body",
        ),
    ),
    # --- Health (health.py §6) ------------------------------------------------
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
    # --- Auth (auth.py §10.4) -------------------------------------------------
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
            "lowercase words and are unaffected; `correlation_id` is the one "
            "documented exception, and the driver's checker exempts it by name."
        ),
        request=RequestSpec("GET", "/conformance/items", query={"pageSize": "2"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "1"}, {"id": "2"}],
            "nextPageToken": PAGE_1_NEXT_TOKEN,
        },
    ),
    # --- Correlation (context.py §1, asgi.py §7) ------------------------------
    ConformanceCase(
        id="correlation.inbound-id-is-echoed-never-replaced",
        area="correlation",
        description="A caller-supplied X-Correlation-ID comes back verbatim.",
        request=RequestSpec(
            "GET", "/conformance/echo", headers={"X-Correlation-ID": "abc123"}
        ),
        expect_status=200,
        expect_headers={**_JSON, "X-Correlation-ID": "abc123"},
        expect_body={},
    ),
    ConformanceCase(
        id="correlation.generated-id-reaches-the-problem-body",
        area="correlation",
        description=(
            "With no inbound header the server generates one, stamps it on the "
            "response, and carries it as a problem extension — which is what makes "
            "a user-reported error id findable in the logs."
        ),
        request=RequestSpec("GET", "/conformance/boom"),
        expect_status=500,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(INTERNAL_ERROR, GENERIC_SERVER_DETAIL),
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
