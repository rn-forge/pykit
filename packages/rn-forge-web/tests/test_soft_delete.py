"""Tests for the soft-delete exceptions and the live-resource guard."""

from datetime import UTC, datetime

import pytest
from assertpy import assert_that

from rn_forge.web import (
    SHOW_DELETED_PARAM,
    DomainConflict,
    ResourceDeleted,
    ResourceNotDeleted,
    default_registry,
    render_problem,
    require_live,
)

pytestmark = pytest.mark.unit


def test_the_parameter_name_is_show_deleted():
    assert_that(SHOW_DELETED_PARAM).is_equal_to("showDeleted")


def test_require_live_accepts_a_live_resource():
    require_live(None, label="Note", id="1")


def test_require_live_rejects_a_deleted_resource():
    deleted = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(ResourceDeleted) as raised:
        require_live(deleted, label="Note", id="2")

    assert_that(raised.value.message).is_equal_to("Note 2 is deleted")


@pytest.mark.parametrize(
    ("exc", "detail"),
    [
        (ResourceDeleted("Note", 2), "Note 2 is deleted"),
        (ResourceNotDeleted("Note", "1"), "Note 1 is not deleted"),
    ],
)
def test_both_exceptions_render_a_409_problem(exc, detail):
    assert_that(exc).is_instance_of(DomainConflict)

    problem = render_problem(default_registry(), exc, instance="/notes/1")

    assert_that(problem.status).is_equal_to(409)
    assert_that(problem.body["status"]).is_equal_to(409)
    assert_that(problem.body["detail"]).is_equal_to(detail)


def test_braces_in_a_label_or_id_render_literally():
    assert_that(ResourceDeleted("{x}", "{0}").message).is_equal_to("{x} {0} is deleted")
