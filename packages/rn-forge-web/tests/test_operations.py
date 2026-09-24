"""Tests for rn_forge.web.operations."""

import pytest
from assertpy import assert_that
from pydantic import ValidationError

from rn_forge.web.operations import Operation
from rn_forge.web.problem import ProblemDetail

pytestmark = pytest.mark.unit

PROBLEM = ProblemDetail(
    type="about:blank", title="Conflict", status=409, detail="x", instance="/i"
)


def test_a_pending_operation_omits_every_outcome():
    body = Operation(name="operations/1", metadata={"progress": 10}).as_body()
    assert_that(body).is_equal_to(
        {"name": "operations/1", "done": False, "metadata": {"progress": 10}}
    )


def test_a_finished_operation_carries_its_response():
    body = Operation(name="operations/1", done=True, response={"id": "1"}).as_body()
    assert_that(body).is_equal_to(
        {"name": "operations/1", "done": True, "response": {"id": "1"}}
    )


def test_a_failed_operation_carries_a_problem():
    body = Operation(name="operations/1", done=True, error=PROBLEM).as_body()
    assert_that(body["error"]).is_equal_to(PROBLEM.as_body())


@pytest.mark.parametrize(
    "fields",
    [
        {"done": True},
        {"done": True, "response": {}, "error": PROBLEM},
        {"done": False, "response": {}},
    ],
)
def test_an_outcome_that_disagrees_with_done_is_rejected(fields):
    with pytest.raises(ValidationError):
        Operation(name="operations/1", **fields)
