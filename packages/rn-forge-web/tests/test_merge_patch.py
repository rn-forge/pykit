"""Tests for rn_forge.web.merge_patch."""

import copy

import pytest
from assertpy import assert_that

from rn_forge.web.exceptions import InvalidMergePatch
from rn_forge.web.merge_patch import (
    MERGE_PATCH_MEDIA_TYPE,
    JsonValue,
    apply_merge_patch,
    merge_representation,
    require_patch_object,
)

pytestmark = pytest.mark.unit

# RFC 7396 Appendix A, in order: (original, patch, result).
RFC_7396_APPENDIX_A: list[tuple[JsonValue, JsonValue, JsonValue]] = [
    ({"a": "b"}, {"a": "c"}, {"a": "c"}),
    ({"a": "b"}, {"b": "c"}, {"a": "b", "b": "c"}),
    ({"a": "b"}, {"a": None}, {}),
    ({"a": "b", "b": "c"}, {"a": None}, {"b": "c"}),
    ({"a": ["b"]}, {"a": "c"}, {"a": "c"}),
    ({"a": "c"}, {"a": ["b"]}, {"a": ["b"]}),
    ({"a": {"b": "c"}}, {"a": {"b": "d", "c": None}}, {"a": {"b": "d"}}),
    ({"a": [{"b": "c"}]}, {"a": [1]}, {"a": [1]}),
    (["a", "b"], ["c", "d"], ["c", "d"]),
    ({"a": "b"}, ["c"], ["c"]),
    ({"a": "foo"}, None, None),
    ({"a": "foo"}, "bar", "bar"),
    ({"e": None}, {"a": 1}, {"e": None, "a": 1}),
    ([1, 2], {"a": "b", "c": None}, {"a": "b"}),
    ({}, {"a": {"bb": {"ccc": None}}}, {"a": {"bb": {}}}),
]


def test_the_media_type():
    assert_that(MERGE_PATCH_MEDIA_TYPE).is_equal_to("application/merge-patch+json")


@pytest.mark.parametrize(
    ("target", "patch", "expected"),
    RFC_7396_APPENDIX_A,
    ids=[f"appendix-a-{n}" for n in range(1, 16)],
)
def test_rfc_7396_appendix_a(target: JsonValue, patch: JsonValue, expected: JsonValue):
    assert_that(apply_merge_patch(target, patch)).is_equal_to(expected)


def test_nested_objects_merge():
    result = apply_merge_patch(
        {"s": {"color": "red", "size": "L"}}, {"s": {"color": "blue"}}
    )
    assert_that(result).is_equal_to({"s": {"color": "blue", "size": "L"}})


def test_null_for_an_absent_member_is_a_no_op():
    assert_that(apply_merge_patch({"a": 1}, {"b": None})).is_equal_to({"a": 1})


def test_arrays_are_replaced_whole():
    assert_that(apply_merge_patch({"t": ["a", "b"]}, {"t": ["c"]})).is_equal_to(
        {"t": ["c"]}
    )


@pytest.mark.parametrize("patch", ["x", 3, ["x"], True])
def test_a_non_object_patch_replaces_the_target(patch: JsonValue):
    assert_that(apply_merge_patch({"a": 1}, patch)).is_equal_to(patch)


def test_neither_argument_is_mutated():
    target: JsonValue = {"a": {"b": 1, "c": [1]}, "d": 2}
    patch: JsonValue = {"a": {"b": None, "e": {"f": 1}}, "d": [3]}
    target_before, patch_before = copy.deepcopy(target), copy.deepcopy(patch)
    result = apply_merge_patch(target, patch)
    assert_that(target).is_equal_to(target_before)
    assert_that(patch).is_equal_to(patch_before)
    assert isinstance(result, dict)
    result["a"]["e"]["f"] = 99  # pyright: ignore[reportIndexIssue,reportArgumentType]
    assert_that(patch).is_equal_to(patch_before)


def test_merge_representation_keeps_a_top_level_null():
    current: dict[str, JsonValue] = {"name": "w", "note": "fragile"}
    assert_that(merge_representation(current, {"note": None})).is_equal_to(
        {"name": "w", "note": None}
    )


def test_merge_representation_removes_a_nested_null():
    current: dict[str, JsonValue] = {"settings": {"color": "red", "size": "L"}}
    merged = merge_representation(current, {"settings": {"size": None}})
    assert_that(merged).is_equal_to({"settings": {"color": "red"}})


def test_merge_representation_applies_other_members_and_mutates_nothing():
    current: dict[str, JsonValue] = {"name": "w", "tags": ["a"], "settings": {"k": 1}}
    patch: dict[str, JsonValue] = {"name": "g", "tags": ["c"], "extra": 1}
    before = copy.deepcopy(current)
    merged = merge_representation(current, patch)
    assert_that(merged).is_equal_to(
        {"name": "g", "tags": ["c"], "settings": {"k": 1}, "extra": 1}
    )
    assert_that(current).is_equal_to(before)


def test_require_patch_object_returns_an_object():
    body: dict[str, JsonValue] = {"a": 1}
    assert_that(require_patch_object(body)).is_same_as(body)


@pytest.mark.parametrize("body", [["a"], "a", None, 1])
def test_require_patch_object_rejects_a_non_object(body: object):
    with pytest.raises(InvalidMergePatch) as info:
        require_patch_object(body)
    assert_that(info.value.message).is_equal_to("A merge patch must be a JSON object.")
