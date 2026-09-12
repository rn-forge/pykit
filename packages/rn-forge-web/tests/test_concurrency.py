"""Tests for rn_forge.web.concurrency."""

import pytest
from assertpy import assert_that

from rn_forge.web.concurrency import (
    EntityVersionETagCodec,
    VersionETagCodec,
    check_precondition,
)
from rn_forge.web.exceptions import (
    MalformedPrecondition,
    PreconditionRequired,
    VersionConflict,
)

pytestmark = pytest.mark.unit

ENTITY = EntityVersionETagCodec()
VERSION_ONLY = VersionETagCodec()


# --- the codecs -----------------------------------------------------------


def test_entity_codec_round_trip():
    raw = ENTITY.format(entity_id="a1", version=7)
    assert_that(raw).is_equal_to('W/"a1:7"')
    assert_that(ENTITY.parse(raw)).is_equal_to(("a1", 7))


def test_version_codec_round_trip():
    raw = VERSION_ONLY.format(entity_id="ignored", version=7)
    assert_that(raw).is_equal_to('W/"7"')
    assert_that(VERSION_ONLY.parse(raw)).is_equal_to((None, 7))


@pytest.mark.parametrize("entity_id", ["a1", "42", "some-slug", "3f2b1c9e-dead-beef"])
def test_entity_codec_accepts_non_uuid_identifiers(entity_id):
    """Deliberately not a UUID pattern: integer and slug primary keys are both real."""
    assert_that(
        ENTITY.parse(ENTITY.format(entity_id=entity_id, version=1))
    ).is_equal_to((entity_id, 1))


def test_entity_codec_refuses_to_format_an_unparseable_id():
    assert_that(ENTITY.format).raises(MalformedPrecondition).when_called_with(
        entity_id="a:b", version=1
    )


@pytest.mark.parametrize(
    "raw",
    [
        '"a1:7"',  # not weak
        "W/a1:7",  # unquoted
        'W/"a1:x"',  # non-integer version
        'W/"7"',  # missing the entity segment
        "",
        "garbage",
    ],
)
def test_entity_codec_rejects_malformed_validators(raw):
    assert_that(ENTITY.parse).raises(MalformedPrecondition).when_called_with(raw)


@pytest.mark.parametrize("raw", ['"7"', "W/7", 'W/"x"', 'W/"a1:7"'])
def test_version_codec_rejects_malformed_validators(raw):
    assert_that(VERSION_ONLY.parse).raises(MalformedPrecondition).when_called_with(raw)


def test_a_strong_validator_is_rejected_not_silently_accepted():
    """Decided in the module docstring: a version counter is not a strong validator."""
    assert_that(ENTITY.parse).raises(MalformedPrecondition).when_called_with('"a1:7"')


# --- check_precondition ---------------------------------------------------


def test_matching_precondition_passes():
    check_precondition('W/"a1:7"', current_version=7, entity_id="a1")


def test_surrounding_whitespace_is_tolerated():
    check_precondition('  W/"a1:7" ', current_version=7, entity_id="a1")


def test_version_mismatch_raises_version_conflict():
    assert_that(check_precondition).raises(VersionConflict).when_called_with(
        'W/"a1:6"', current_version=7, entity_id="a1"
    )


def test_entity_mismatch_raises_version_conflict():
    """A precondition replayed from a different entity — what the version alone misses."""
    assert_that(check_precondition).raises(VersionConflict).when_called_with(
        'W/"other:7"', current_version=7, entity_id="a1"
    )


def test_absent_header_passes_when_not_required():
    check_precondition(None, current_version=7, entity_id="a1")


def test_absent_header_raises_when_required():
    assert_that(check_precondition).raises(PreconditionRequired).when_called_with(
        None, current_version=7, entity_id="a1", required=True
    )


def test_star_matches_any_representation():
    """RFC 9110 §13.1.1. Neither surveyed implementation handled it."""
    check_precondition("*", current_version=7, entity_id="a1", required=True)


def test_malformed_header_is_a_400_not_a_crash():
    assert_that(check_precondition).raises(MalformedPrecondition).when_called_with(
        "not-an-etag", current_version=7, entity_id="a1"
    )


def test_the_version_only_codec_ignores_entity_identity():
    check_precondition(
        'W/"7"', current_version=7, entity_id="anything", codec=VERSION_ONLY
    )


def test_entity_is_not_compared_when_the_caller_supplies_none():
    check_precondition('W/"a1:7"', current_version=7)


def test_the_version_is_checked_before_the_entity():
    """A stale validator for the wrong entity is still reported as a version conflict."""
    assert_that(check_precondition).raises(VersionConflict).when_called_with(
        'W/"other:6"', current_version=7, entity_id="a1"
    )
