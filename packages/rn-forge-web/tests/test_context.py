"""Tests for rn_forge.web.context."""

import asyncio

import pytest
from assertpy import assert_that

from rn_forge.web.context import (
    DEFAULT_CORRELATION_HEADER,
    EXPOSED_HEADERS,
    MAX_CORRELATION_ID_LENGTH,
    bind_correlation_id,
    correlation_id_var,
    correlation_log_processor,
    get_correlation_id,
    is_valid_correlation_id,
    new_correlation_id,
    request_log_fields,
    require_correlation_id,
    resolve_correlation_id,
    set_correlation_id,
)
from rn_forge.web.exceptions import WebError

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_contextvar():
    token = correlation_id_var.set(None)
    yield
    correlation_id_var.reset(token)


def test_default_header_is_x_correlation_id():
    assert_that(DEFAULT_CORRELATION_HEADER).is_equal_to("X-Correlation-ID")


def test_exposed_headers_carries_the_correlation_header():
    assert_that(EXPOSED_HEADERS).contains(DEFAULT_CORRELATION_HEADER)
    assert_that(EXPOSED_HEADERS).contains("ETag", "Link", "Location", "Retry-After")


def test_request_log_fields_uses_otel_semantic_convention_names():
    fields = request_log_fields(
        method="GET", path="/orders", status=200, duration_ms=1.5, correlation_id="c1"
    )
    assert_that(fields).is_equal_to(
        {
            "http.request.method": "GET",
            "url.path": "/orders",
            "http.response.status_code": 200,
            "duration_ms": 1.5,
            "correlation_id": "c1",
        }
    )


def test_set_and_get_round_trip():
    set_correlation_id("abc123")
    assert_that(get_correlation_id()).is_equal_to("abc123")


def test_get_returns_none_when_unbound():
    assert_that(get_correlation_id()).is_none()


def test_require_returns_the_bound_value():
    set_correlation_id("abc123")
    assert_that(require_correlation_id()).is_equal_to("abc123")


def test_require_raises_when_unbound():
    assert_that(require_correlation_id).raises(WebError).when_called_with()


def test_new_correlation_id_returns_distinct_values():
    values = {new_correlation_id() for _ in range(100)}
    assert_that(values).is_length(100)


def test_bind_yields_and_resets_on_exit():
    with bind_correlation_id("abc123") as bound:
        assert_that(bound).is_equal_to("abc123")
        assert_that(get_correlation_id()).is_equal_to("abc123")
    assert_that(get_correlation_id()).is_none()


def test_bind_generates_a_value_when_none_is_given():
    with bind_correlation_id() as bound:
        assert_that(bound).is_not_empty()
        assert_that(get_correlation_id()).is_equal_to(bound)


def test_bind_resets_on_exception():
    with pytest.raises(RuntimeError), bind_correlation_id("abc123"):
        raise RuntimeError("boom")
    assert_that(get_correlation_id()).is_none()


def test_bind_restores_the_outer_value_rather_than_clearing():
    set_correlation_id("outer")
    with bind_correlation_id("inner"):
        assert_that(get_correlation_id()).is_equal_to("inner")
    assert_that(get_correlation_id()).is_equal_to("outer")


def test_processor_injects_when_bound():
    set_correlation_id("abc123")
    event = {"event": "hello"}
    assert_that(correlation_log_processor(None, "info", event)).is_equal_to(
        {"event": "hello", "correlation_id": "abc123"}
    )


def test_processor_leaves_the_event_dict_untouched_when_unbound():
    event = {"event": "hello"}
    assert_that(correlation_log_processor(None, "info", event)).is_equal_to(
        {"event": "hello"}
    )


def test_is_valid_accepts_a_conforming_id():
    assert_that(is_valid_correlation_id("abc-123_ok:v1.0")).is_true()


def test_is_valid_rejects_an_empty_string():
    assert_that(is_valid_correlation_id("")).is_false()


def test_is_valid_rejects_an_over_long_id():
    assert_that(
        is_valid_correlation_id("a" * (MAX_CORRELATION_ID_LENGTH + 1))
    ).is_false()


def test_is_valid_accepts_the_maximum_length():
    assert_that(is_valid_correlation_id("a" * MAX_CORRELATION_ID_LENGTH)).is_true()


@pytest.mark.parametrize("value", ["has space", "has\nnewline", "has%percent"])
def test_is_valid_rejects_disallowed_characters(value):
    assert_that(is_valid_correlation_id(value)).is_false()


def test_contextvar_is_isolated_across_tasks():
    """The property the no-reset ASGI design depends on. Asserted, not assumed."""
    seen: dict[str, str | None] = {}

    async def worker(name: str) -> None:
        set_correlation_id(name)
        await asyncio.sleep(0)
        seen[name] = get_correlation_id()

    async def main() -> None:
        await asyncio.gather(worker("one"), worker("two"))

    asyncio.run(main())
    assert_that(seen).is_equal_to({"one": "one", "two": "two"})
    # And nothing leaked back into the parent context.
    assert_that(get_correlation_id()).is_none()


def test_resolve_keeps_a_well_formed_inbound_id():
    assert_that(resolve_correlation_id("abc-123")).is_equal_to("abc-123")


@pytest.mark.parametrize("inbound", [None, "", "bad id\r\n"])
def test_resolve_replaces_an_absent_or_malformed_id(inbound):
    assert_that(resolve_correlation_id(inbound, generator=lambda: "fresh")).is_equal_to(
        "fresh"
    )
