"""Tests for rn_forge.web.deprecation."""

from datetime import UTC, datetime

import pytest
from assertpy import assert_that

from rn_forge.web.deprecation import deprecation_headers

pytestmark = pytest.mark.unit


def test_deprecated_at_is_a_structured_field_date():
    headers = deprecation_headers(deprecated_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert_that(headers["Deprecation"]).is_equal_to("@1767225600")


def test_sunset_is_an_http_date():
    headers = deprecation_headers(
        deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
        sunset=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert_that(headers["Sunset"]).is_equal_to("Wed, 01 Jul 2026 00:00:00 GMT")


def test_no_sunset_omits_the_header():
    headers = deprecation_headers(deprecated_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert_that(headers).does_not_contain_key("Sunset")


def test_link_carries_the_deprecation_relation():
    headers = deprecation_headers(
        deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
        link="https://example.com/deprecated",
    )
    assert_that(headers["Link"]).is_equal_to(
        '<https://example.com/deprecated>; rel="deprecation"'
    )


def test_no_link_omits_the_header():
    headers = deprecation_headers(deprecated_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert_that(headers).does_not_contain_key("Link")
