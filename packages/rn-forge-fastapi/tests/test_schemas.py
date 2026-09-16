"""Tests for rn_forge.fastapi.schemas."""

import pytest
from assertpy import assert_that
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rn_forge import web
from rn_forge.fastapi import CheckResult, HealthReport, Page, ProblemDetail, WireModel

pytestmark = pytest.mark.unit


class Item(WireModel):
    display_name: str


def test_problem_detail_round_trips_through_the_web_dataclass():
    wire = web.ProblemDetail(
        type="about:blank",
        title="Conflict",
        status=409,
        detail="nope",
        instance="/orders/1",
        extensions={
            "correlation_id": "abc",
            "errors": [{"pointer": "/x", "message": "m"}],
        },
    )
    mirror = ProblemDetail.from_wire(wire)
    assert_that(mirror.model_dump()).is_equal_to(wire.as_body())
    assert_that(mirror.to_wire()).is_equal_to(wire)


def test_rfc9457_core_members_survive_the_alias_generator():
    """A future alias generator change must not silently rename the error contract."""
    aliases = [field.alias for field in ProblemDetail.model_fields.values()]
    assert_that(aliases).is_equal_to(["type", "title", "status", "detail", "instance"])


@pytest.mark.parametrize("total_size", [None, 3])
def test_page_round_trips_through_the_web_dataclass(total_size):
    wire = web.Page(items=[{"id": "1"}], next_page_token=None, total_size=total_size)
    mirror = Page[dict[str, str]].from_wire(wire)
    assert_that(mirror.model_dump()).is_equal_to(wire.as_body())
    assert_that(mirror.to_wire()).is_equal_to(wire)


def test_page_keeps_a_null_next_token_and_omits_an_absent_total():
    body = Page[Item](items=[Item(display_name="x")], next_page_token=None).model_dump()
    assert_that(body).is_equal_to(
        {"items": [{"displayName": "x"}], "nextPageToken": None}
    )


def test_check_result_round_trips_through_the_web_dataclass():
    wire = web.CheckResult(status="warn", reason="slow", details={"ms": 900})
    mirror = CheckResult.from_wire(wire)
    assert_that(mirror.model_dump()).is_equal_to(
        {
            "status": "warn",
            "reason": "slow",
            "remediation": None,
            "details": {"ms": 900},
        }
    )
    assert_that(mirror.to_wire()).is_equal_to(wire)


def test_health_report_round_trips_through_the_web_dataclass():
    wire = web.run_checks_sync(
        {"db": lambda: False, "queue": lambda: True}, required=["db"]
    )
    mirror = HealthReport.from_wire(wire)
    assert_that(mirror.model_dump()).is_equal_to(wire.as_body())
    assert_that(mirror.to_wire(http_status=wire.http_status)).is_equal_to(wire)


@pytest.mark.parametrize("body", [{"displayName": "x"}, {"display_name": "x"}])
def test_input_accepts_either_spelling(body):
    assert_that(Item.model_validate(body).display_name).is_equal_to("x")


def test_a_response_model_serializes_by_alias():
    app = FastAPI()

    @app.get("/items")
    async def items() -> Page[Item]:
        return Page[Item](items=[Item(display_name="x")], next_page_token="t")

    assert_that(TestClient(app).get("/items").json()).is_equal_to(
        {"items": [{"displayName": "x"}], "nextPageToken": "t"}
    )
