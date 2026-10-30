"""Tests for rn_forge.auth.redirects."""

import pytest
from assertpy import assert_that

from rn_forge.auth import InvalidReturnTo, validate_return_to

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value",
    ["/app", "/app/", "/app/x", "/app/x?a=1#top", "/app?next=%2Fother", "/app/a%20b"],
)
def test_accepts_paths_under_a_prefix(value: str):
    assert_that(validate_return_to(value, prefixes=["/app"])).is_equal_to(value)


def test_root_prefix_allows_any_path():
    assert_that(validate_return_to("/x/y", prefixes=["/"])).is_equal_to("/x/y")


def test_any_listed_prefix_may_match():
    assert_that(validate_return_to("/b/1", prefixes=["/a", "/b"])).is_equal_to("/b/1")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "app",
        "https://evil.example/app",
        "javascript:alert(1)",
        "//evil.example/app",
        "/\\evil.example",
        "/app\\x",
        "/app/%2Fevil",
        "/app/%2fevil",
        "/app/%5Cevil",
        "/app/%5cevil",
        "/app/%2e%2e/x",
        "/app/../x",
        "/app/..",
        "/app/x\n",
        "/app/x\r\nSet-Cookie: a=b",
        "/app/\x00",
        "/app/\x7f",
        "/app/\x85",
        "/apple",
        "/other",
    ],
)
def test_rejects_unsafe_or_outside_values(value: str):
    with pytest.raises(InvalidReturnTo):
        validate_return_to(value, prefixes=["/app"])


def test_rejection_keeps_a_reason():
    with pytest.raises(InvalidReturnTo) as info:
        validate_return_to("/other", prefixes=["/app"])
    assert_that(info.value.reason).contains("prefixes")


def test_no_prefixes_allows_nothing():
    with pytest.raises(InvalidReturnTo):
        validate_return_to("/app", prefixes=[])
