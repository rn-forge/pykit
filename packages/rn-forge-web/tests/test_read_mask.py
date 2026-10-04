"""Tests for the ``readMask`` parser and the pruning it performs."""

import pytest
from assertpy import assert_that

from rn_forge.web import (
    READ_MASK_PARAM,
    InvalidReadMask,
    default_registry,
    parse_read_mask,
    render_problem,
)
from rn_forge.web.read_mask import FieldTree

pytestmark = pytest.mark.unit

FIELDS: FieldTree = {
    "id": None,
    "displayName": None,
    "address": {"city": None, "postcode": None},
    "phones": {"kind": None, "number": None},
    "tags": None,
    "settings": None,
}

PROFILE = {
    "id": "1",
    "displayName": "Ada",
    "address": {"city": "London", "postcode": "N1"},
    "phones": [
        {"kind": "home", "number": "1"},
        {"kind": "work", "number": "2"},
    ],
    "tags": ["a", "b"],
    "settings": {"theme": "dark"},
}


def masked(raw, body=PROFILE):
    mask = parse_read_mask(raw, fields=FIELDS)
    assert mask is not None
    return mask.apply(body)


def test_the_parameter_is_named_read_mask():
    assert_that(READ_MASK_PARAM).is_equal_to("readMask")


@pytest.mark.parametrize("raw", [None, "", "   ", "*", " * "])
def test_absent_blank_or_star_is_the_whole_resource(raw):
    assert_that(parse_read_mask(raw, fields=FIELDS)).is_none()


def test_top_level_paths_keep_only_those_fields():
    assert_that(masked("displayName,settings")).is_equal_to(
        {"displayName": "Ada", "settings": {"theme": "dark"}}
    )


def test_whitespace_around_a_path_is_ignored():
    assert_that(masked(" displayName , address.city ")).is_equal_to(
        {"displayName": "Ada", "address": {"city": "London"}}
    )


def test_a_dotted_path_selects_a_sub_field():
    assert_that(masked("address.city")).is_equal_to({"address": {"city": "London"}})


def test_a_path_through_a_list_applies_to_each_element():
    assert_that(masked("phones.number")).is_equal_to(
        {"phones": [{"number": "1"}, {"number": "2"}]}
    )


def test_a_list_of_objects_named_whole_is_returned_whole():
    assert_that(masked("phones")).is_equal_to({"phones": PROFILE["phones"]})


def test_an_empty_list_stays_empty():
    assert_that(masked("phones.number", {**PROFILE, "phones": []})).is_equal_to(
        {"phones": []}
    )


def test_a_null_object_stays_null():
    assert_that(masked("address.city", {**PROFILE, "address": None})).is_equal_to(
        {"address": None}
    )


@pytest.mark.parametrize("raw", ["address,address.city", "address.city,address"])
def test_overlapping_paths_merge_to_the_whole_object(raw):
    assert_that(masked(raw)).is_equal_to({"address": PROFILE["address"]})


def test_paths_into_the_same_object_merge():
    assert_that(masked("address.city,address.postcode,address.city")).is_equal_to(
        {"address": PROFILE["address"]}
    )


def test_a_whole_object_absorbs_a_deeper_path_that_follows_it():
    assert_that(masked("address,address.city,address.postcode")).is_equal_to(
        {"address": PROFILE["address"]}
    )


def test_a_field_the_body_lacks_is_not_added():
    assert_that(masked("id,address.city", {"address": {}})).is_equal_to({"address": {}})


def test_no_field_is_added_implicitly():
    assert_that(masked("displayName")).does_not_contain_key("id")


def test_apply_returns_a_copy_and_leaves_the_body_alone():
    original = {"id": "1", "address": {"city": "London", "postcode": "N1"}}
    result = masked("address.city", original)
    assert_that(original["address"]).contains_key("postcode")
    assert_that(result["address"]).is_not_same_as(original["address"])


@pytest.mark.parametrize(
    "raw",
    [
        "nickname",
        "address.street",
        "address.city.name",
        "settings.theme",
        "tags.first",
        "phones.number.digits",
        "phones.",
        "address..city",
        "address.*",
        "DisplayName",
        "display_name",
    ],
)
def test_a_path_that_names_no_declared_field_is_rejected(raw):
    with pytest.raises(InvalidReadMask) as raised:
        parse_read_mask(raw, fields=FIELDS)
    assert_that(raised.value.message).is_equal_to(f"Unknown readMask path '{raw}'")


@pytest.mark.parametrize("raw", [",", " , ", "displayName,,id", "displayName,", ",id"])
def test_an_empty_entry_is_rejected(raw):
    with pytest.raises(InvalidReadMask) as raised:
        parse_read_mask(raw, fields=FIELDS)
    assert_that(raised.value.message).is_equal_to("Unknown readMask path ''")


def test_one_unknown_path_rejects_the_whole_mask():
    with pytest.raises(InvalidReadMask, match="Unknown readMask path 'nickname'"):
        parse_read_mask("displayName,nickname", fields=FIELDS)


@pytest.mark.parametrize("raw", ["*,displayName", "displayName,*", "*,*"])
def test_star_with_other_paths_is_rejected(raw):
    with pytest.raises(InvalidReadMask) as raised:
        parse_read_mask(raw, fields=FIELDS)
    assert_that(raised.value.message).is_equal_to(
        "readMask '*' cannot be combined with other paths"
    )


def test_an_invalid_mask_renders_as_a_400_problem():
    response = render_problem(
        default_registry(),
        InvalidReadMask("Unknown readMask path 'nickname'"),
        instance="/profiles/1",
    )
    assert_that(response.status).is_equal_to(400)
    assert_that(response.body["detail"]).is_equal_to("Unknown readMask path 'nickname'")
