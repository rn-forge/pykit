"""Tests for rn_forge.web.tracing."""

import pytest
from assertpy import assert_that
from opentelemetry import trace

from rn_forge.web.tracing import (
    EXPOSED_HEADERS,
    current_span_id,
    current_trace_id,
    request_log_fields,
    trace_log_processor,
)

pytestmark = pytest.mark.unit

_TRACER = trace.get_tracer(__name__)


def test_exposed_headers_does_not_carry_a_correlation_header():
    assert_that(EXPOSED_HEADERS).contains("ETag", "Link", "Location", "Retry-After")
    assert_that(EXPOSED_HEADERS).does_not_contain("X-Correlation-ID")
    assert_that(EXPOSED_HEADERS).does_not_contain("traceresponse")


def test_current_trace_id_is_none_with_no_span():
    assert_that(current_trace_id()).is_none()


def test_current_span_id_is_none_with_no_span():
    assert_that(current_span_id()).is_none()


def test_current_ids_return_the_active_spans_ids():
    with _TRACER.start_as_current_span("test-span") as span:
        ctx = span.get_span_context()
        assert_that(current_trace_id()).is_equal_to(format(ctx.trace_id, "032x"))
        assert_that(current_span_id()).is_equal_to(format(ctx.span_id, "016x"))
    assert_that(current_trace_id()).is_none()


def test_request_log_fields_uses_otel_semantic_convention_names():
    fields = request_log_fields(
        method="GET", path="/orders", status=200, duration_ms=1.5
    )
    assert_that(fields).is_equal_to(
        {
            "http.request.method": "GET",
            "url.path": "/orders",
            "http.response.status_code": 200,
            "duration_ms": 1.5,
            "trace_id": None,
            "span_id": None,
        }
    )


def test_request_log_fields_carries_the_active_trace():
    with _TRACER.start_as_current_span("test-span"):
        fields = request_log_fields(
            method="GET", path="/orders", status=200, duration_ms=1.5
        )
        assert_that(fields["trace_id"]).is_equal_to(current_trace_id())
        assert_that(fields["span_id"]).is_equal_to(current_span_id())


def test_processor_injects_when_a_span_is_recording():
    with _TRACER.start_as_current_span("test-span"):
        event = {"event": "hello"}
        result = trace_log_processor(None, "info", event)
        assert_that(result["trace_id"]).is_equal_to(current_trace_id())
        assert_that(result["span_id"]).is_equal_to(current_span_id())


def test_processor_leaves_the_event_dict_untouched_when_no_span_is_recording():
    event = {"event": "hello"}
    assert_that(trace_log_processor(None, "info", event)).is_equal_to(
        {"event": "hello"}
    )
