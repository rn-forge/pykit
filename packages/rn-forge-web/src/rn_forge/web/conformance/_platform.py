"""HTTP conformance cases for platform behavior."""

from __future__ import annotations

from typing import Final

from rn_forge.web.conformance._shared import (
    _CSV_TYPE,
    _CSV_TYPE_PATTERN,
    _ITEMS_PATH,
    _JSON,
    _ORDERS_CSV,
    _PROBLEM,
    PAGE_1_NEXT_TOKEN,
    _problem_body,
)
from rn_forge.web.conformance.types import ConformanceCase, RequestSpec
from rn_forge.web.problem import GENERIC_SERVER_DETAIL, INTERNAL_ERROR
from rn_forge.web.tracing import EXPOSED_HEADERS

__all__ = ["PLATFORM_CASES"]

_LINKSET: Final = {"Content-Type": "application/linkset+json"}

_TRACEPARENT: Final = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
"""A well-formed W3C traceparent."""

_READYZ_PATH: Final = "/conformance/readyz"

_ECHO_PATH: Final = "/conformance/echo"
_ORIGIN: Final = "https://example.com"

PLATFORM_CASES: Final[tuple[ConformanceCase, ...]] = (
    ConformanceCase(
        id="health.all-pass-is-200",
        area="health",
        description="Every check passes; the aggregate is pass and the status is 200.",
        request=RequestSpec("GET", _READYZ_PATH),
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
        request=RequestSpec("GET", _READYZ_PATH, query={"fail": "db"}),
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
        request=RequestSpec("GET", _READYZ_PATH, query={"fail": "queue"}),
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
        id="health.liveness-is-200",
        area="health",
        description="Liveness touches no dependency and always answers 200.",
        request=RequestSpec("GET", "/conformance/livez"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"status": "pass"},
    ),
    ConformanceCase(
        id="casing.response-bodies-are-camel-case",
        area="casing",
        description=(
            "Asserted structurally by the driver rather than per case: every key in "
            "every response body above, at every depth, matches ^[a-z][a-zA-Z0-9]*$ "
            "or is an RFC 9457 core member. RFC 9457's own members are single "
            "lowercase words and are unaffected."
        ),
        request=RequestSpec("GET", _ITEMS_PATH, query={"pageSize": "2"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "1"}, {"id": "2"}],
            "nextPageToken": PAGE_1_NEXT_TOKEN,
        },
    ),
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
            _ECHO_PATH,
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
        request=RequestSpec("GET", _ECHO_PATH, headers={"traceparent": "garbage"}),
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
        request=RequestSpec("GET", _ECHO_PATH, headers={"X-Correlation-ID": "abc123"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_absent_headers=frozenset({"X-Correlation-ID"}),
        expect_body={},
    ),
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
    ConformanceCase(
        id="security.owasp-headers-are-present",
        area="security",
        description="The OWASP REST Security Cheat Sheet response headers, on every response.",
        request=RequestSpec("GET", _ECHO_PATH),
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
    ConformanceCase(
        id="cors.exposed-headers-are-comma-joined",
        area="cors",
        description=(
            "A CORS response exposes the kit's own headers to a browser, in "
            "configured order. traceresponse is exposed by the OpenTelemetry "
            "response propagator itself, not by this list."
        ),
        request=RequestSpec("GET", _ECHO_PATH, headers={"Origin": _ORIGIN}),
        expect_status=200,
        expect_headers={
            **_JSON,
            "Access-Control-Allow-Origin": _ORIGIN,
            "Access-Control-Expose-Headers": ", ".join(
                (*EXPOSED_HEADERS, "traceresponse")
            ),
        },
        expect_body={},
    ),
    ConformanceCase(
        id="cors.export-exposes-content-disposition",
        area="cors",
        description=(
            "A cross-origin CSV export exposes Content-Disposition, so a "
            "browser client can read the file name."
        ),
        request=RequestSpec(
            "GET",
            "/conformance/orders",
            headers={"Accept": _CSV_TYPE, "Origin": _ORIGIN},
        ),
        expect_status=200,
        expect_headers={"Access-Control-Allow-Origin": _ORIGIN},
        expect_header_patterns={
            "Content-Type": _CSV_TYPE_PATTERN,
            "Access-Control-Expose-Headers": r"(.+, )?Content-Disposition(, .+)?",
        },
        expect_text=_ORDERS_CSV,
    ),
)
