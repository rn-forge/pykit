"""Tests for rn_forge.web.tracing."""

import pytest
from assertpy import assert_that
from opentelemetry import trace

from rn_forge.web.tracing import (
    EXPOSED_HEADERS,
    current_span_id,
    current_trace_id,
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
