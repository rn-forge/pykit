"""Tests for rn_forge.web.pagination."""

import base64
import json

import pytest
from assertpy import assert_that

from rn_forge.web.exceptions import InvalidCursor
from rn_forge.web.pagination import (
    Cursor,
    Page,
    clamp_page_size,
    decode_cursor,
    encode_cursor,
    next_link_header,
)

pytestmark = pytest.mark.unit


# --- the cursor codec -----------------------------------------------------


def test_round_trip():
    token = encode_cursor("2026-09-11T10:00:00Z", "a1")
    assert_that(decode_cursor(token)).is_equal_to(
        Cursor(sort_key="2026-09-11T10:00:00Z", entity_id="a1")
    )


def test_the_token_is_url_safe():
    """It goes in a query string; base64's `+` and `/` would need escaping."""
    token = encode_cursor("z" * 40, "éè")
    assert_that(token).does_not_contain("+").does_not_contain("/")


def test_encoding_is_stable_for_the_same_input():
    assert_that(encode_cursor("k", "1")).is_equal_to(encode_cursor("k", "1"))


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ("!!!not base64!!!", "not base64"),
        (base64.urlsafe_b64encode(b"not json").decode(), "base64 of non-JSON"),
        (base64.urlsafe_b64encode(b'["a","b"]').decode(), "JSON of a non-object"),
        (base64.urlsafe_b64encode(b'"a string"').decode(), "JSON of a scalar"),
        (base64.urlsafe_b64encode(b'{"k":"x"}').decode(), "missing the id key"),
        (base64.urlsafe_b64encode(b'{"id":"x"}').decode(), "missing the sort key"),
        (base64.urlsafe_b64encode(b"null").decode(), "JSON null"),
        ("", "empty"),
    ],
)
def test_every_malformed_input_class_raises_invalid_cursor(raw, why):
    """Missing one of these turns a tampered token into a 500."""
    assert_that(decode_cursor).described_as(why).raises(InvalidCursor).when_called_with(
        raw
    )


def test_a_tampered_token_does_not_leak_its_contents():
    token = base64.urlsafe_b64encode(json.dumps({"k": "x"}).encode()).decode()
    try:
        decode_cursor(token)
    except InvalidCursor as exc:
        assert_that(exc.message).is_equal_to("Malformed page token")


# --- clamp_page_size ------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (None, 20),  # unspecified
        (0, 20),  # non-positive is unspecified
        (-5, 20),  # ditto
        (1, 1),  # below the default
        (20, 20),  # at the default
        (50, 50),  # between default and cap
        (100, 100),  # at the cap
        (1000, 100),  # above the cap: clamped, never rejected
    ],
)
def test_clamp_page_size(requested, expected):
    assert_that(clamp_page_size(requested, default=20, cap=100)).is_equal_to(expected)


def test_a_default_above_the_cap_is_itself_clamped():
    assert_that(clamp_page_size(None, default=500, cap=100)).is_equal_to(100)


# --- the page envelope ----------------------------------------------------


def test_page_body_carries_items_and_next_page_token():
    page = Page(items=[{"id": "1"}], next_page_token="tok")
    assert_that(page.as_body()).is_equal_to(
        {"items": [{"id": "1"}], "nextPageToken": "tok"}
    )


def test_the_last_page_has_a_null_next_page_token():
    """Present-and-null rather than omitted: a client's type must not change shape."""
    assert_that(Page(items=[], next_page_token=None).as_body()).is_equal_to(
        {"items": [], "nextPageToken": None}
    )


def test_total_size_is_omitted_when_none():
    assert_that(Page(items=[], next_page_token=None).as_body()).does_not_contain_key(
        "totalSize"
    )


def test_total_size_is_included_when_opted_into():
    page = Page(items=[], next_page_token=None, total_size=3)
    assert_that(page.as_body()["totalSize"]).is_equal_to(3)


def test_page_body_is_camel_case_and_omits_an_absent_total():
    page = Page(items=["a"], next_page_token="tok")
    assert_that(page.as_body()).is_equal_to({"items": ["a"], "nextPageToken": "tok"})


def test_page_body_keeps_a_null_next_page_token():
    page: Page[str] = Page(items=[], next_page_token=None)
    assert_that(page.as_body()).is_equal_to({"items": [], "nextPageToken": None})


def test_page_round_trips_through_its_body():
    page = Page[str](items=["a"], next_page_token="tok", total_size=1)
    assert_that(Page[str].model_validate(page.as_body())).is_equal_to(page)


def test_page_is_generic():
    page: Page[int] = Page(items=[1, 2], next_page_token=None)
    assert_that(page.items).is_equal_to([1, 2])


# --- the RFC 8288 Link header ---------------------------------------------


def test_next_link_header_appends_a_first_query_parameter():
    assert_that(next_link_header("https://api.example/items", "tok")).is_equal_to(
        '<https://api.example/items?pageToken=tok>; rel="next"'
    )


def test_next_link_header_appends_to_an_existing_query_string():
    assert_that(
        next_link_header("https://api.example/items?status=open", "tok")
    ).is_equal_to('<https://api.example/items?status=open&pageToken=tok>; rel="next"')


def test_next_link_header_escapes_the_token():
    value = next_link_header("https://api.example/items", "a b/c=")
    assert_that(value).contains("pageToken=a%20b%2Fc%3D")


def test_next_link_header_honours_a_custom_parameter_name():
    assert_that(next_link_header("https://x/y", "tok", param="cursor")).contains(
        "cursor=tok"
    )


def test_a_real_token_survives_the_link_header_round_trip():
    from urllib.parse import parse_qs, urlparse

    token = encode_cursor("2026-09-11T10:00:00Z", "a1")
    value = next_link_header("https://api.example/items", token)
    url = value[1 : value.index(">")]
    recovered = parse_qs(urlparse(url).query)["pageToken"][0]
    assert_that(decode_cursor(recovered).entity_id).is_equal_to("a1")
