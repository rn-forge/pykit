"""HTTP conformance cases for problem behavior."""

from __future__ import annotations

from typing import Final

from rn_forge.web.auth import CSRF_FAILED_DETAIL
from rn_forge.web.conformance._shared import _JSON, _PROBLEM, _problem_body
from rn_forge.web.conformance.types import ConformanceCase, RequestSpec
from rn_forge.web.problem import (
    CONFLICT,
    CONTENT_TOO_LARGE,
    CSRF_FAILED,
    FORBIDDEN,
    GENERIC_SERVER_DETAIL,
    INTERNAL_ERROR,
    NOT_FOUND,
    SERVICE_UNAVAILABLE,
    TOO_MANY_REQUESTS,
    UNAUTHORIZED,
    VALIDATION_ERROR,
)

__all__ = ["PROBLEM_CASES"]

_SESSION_PATH: Final = "/conformance/session"

PROBLEM_CASES: Final[tuple[ConformanceCase, ...]] = (
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
    ConformanceCase(
        id="auth.session-only-401-has-no-challenge",
        area="auth",
        description=(
            "RFC 9110 §15.5.2 deviation. A session-only route has no registered "
            "scheme to challenge with, so its 401 carries no WWW-Authenticate."
        ),
        request=RequestSpec("GET", _SESSION_PATH),
        requires=frozenset({"session-routes"}),
        expect_status=401,
        expect_headers=_PROBLEM,
        expect_absent_headers=frozenset({"WWW-Authenticate"}),
        expect_body=_problem_body(UNAUTHORIZED, "Authentication failed."),
    ),
    ConformanceCase(
        id="auth.csrf-rejection-is-403-csrf-failed",
        area="auth",
        description=(
            "An unsafe request from a foreign origin is a 403 csrf-failed problem, "
            "not a permission denial. The detail is generic and never names the "
            "check that failed; with a type_base the type member is csrf-failed."
        ),
        request=RequestSpec(
            "POST",
            _SESSION_PATH,
            headers={**_JSON, "Origin": "https://evil.example"},
            body={},
        ),
        requires=frozenset({"session-routes", "csrf"}),
        expect_status=403,
        expect_headers=_PROBLEM,
        expect_absent_headers=frozenset({"WWW-Authenticate"}),
        expect_body=_problem_body(CSRF_FAILED, CSRF_FAILED_DETAIL),
    ),
)
