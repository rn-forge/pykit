"""Tests for rn_forge.fastapi.problem."""

import pytest
from assertpy import assert_that
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from rn_forge.fastapi import WireModel, register_problem_handlers
from rn_forge.fastapi.problem import _validation_errors
from rn_forge.web import (
    AUTH_FAILED_DETAIL,
    GENERIC_SERVER_DETAIL,
    PROBLEM_MEDIA_TYPE,
    REQUIRED_FIELD_DETAIL,
    AuthenticationFailed,
    CorrelationIdMiddleware,
    DomainConflict,
    PermissionDenied,
    ProblemType,
    default_registry,
)

pytestmark = pytest.mark.unit

CORE_MEMBERS = {"type", "title", "status", "detail", "instance", "correlation_id"}


class Payload(WireModel):
    display_name: str


class OrderLocked(Exception):
    pass


def build(*, middleware=True, registry=None, log=None, raise_server_exceptions=False):
    app = FastAPI()
    if middleware:
        app.add_middleware(CorrelationIdMiddleware)
    register_problem_handlers(app, registry=registry, realm="api", log=log)

    @app.get("/conflict")
    async def conflict():
        raise DomainConflict("Order already dispatched")

    @app.get("/gone")
    async def gone():
        raise HTTPException(status_code=404)

    @app.post("/validate")
    async def validate(body: Payload):
        return {}

    @app.get("/boom")
    async def boom():
        return 1 / 0

    @app.get("/locked")
    async def locked():
        raise OrderLocked("Order 17 is locked")

    @app.get("/unauthenticated")
    async def unauthenticated():
        raise AuthenticationFailed("token expired at 12:00")

    @app.get("/forbidden")
    async def forbidden():
        raise PermissionDenied("The authenticated principal lacks the required access")

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def assert_problem(response, status):
    assert_that(response.status_code).is_equal_to(status)
    assert_that(response.headers["content-type"]).is_equal_to(PROBLEM_MEDIA_TYPE)
    body = response.json()
    assert_that(set(body)).contains(*CORE_MEMBERS)
    assert_that(body["status"]).is_equal_to(status)
    return body


def test_a_registered_exception_renders_its_row():
    response = build().get("/conflict", headers={"X-Correlation-ID": "abc"})
    body = assert_problem(response, 409)
    assert_that(body["detail"]).is_equal_to("Order already dispatched")
    assert_that(body["instance"]).is_equal_to("/conflict")
    assert_that(body["correlation_id"]).is_equal_to("abc")


def test_a_registered_exception_is_handled_not_re_raised():
    """Keyed on its own class, the handler runs in ExceptionMiddleware and swallows it."""
    client = build(raise_server_exceptions=True)
    assert_problem(client.get("/conflict"), 409)


def test_an_application_row_registered_first_is_honoured():
    registry = default_registry().register(
        OrderLocked, ProblemType("order-locked", 423, "Locked")
    )
    body = assert_problem(
        build(registry=registry, raise_server_exceptions=True).get("/locked"), 423
    )
    assert_that(body["detail"]).is_equal_to("Order 17 is locked")


def test_a_bare_http_exception_maps_through_its_status():
    body = assert_problem(build().get("/gone"), 404)
    assert_that(body["title"]).is_equal_to("Not Found")
    assert_that(body["detail"]).is_equal_to("Not Found")


def test_a_routing_404_is_a_problem_body():
    assert_problem(build().get("/nowhere"), 404)


def test_a_routing_405_keeps_its_allow_header():
    response = build().get("/validate")
    body = assert_problem(response, 405)
    assert_that(body["title"]).is_equal_to("Method Not Allowed")
    assert_that(response.headers["allow"]).is_equal_to("POST")


def test_a_validation_error_is_rfc6901_pointers():
    body = assert_problem(build().post("/validate", json={}), 422)
    assert_that(body["title"]).is_equal_to("Unprocessable Content")
    assert_that(body["detail"]).is_equal_to("Validation Error")
    assert_that(body["errors"]).is_equal_to(
        [{"pointer": "/displayName", "detail": "This field is required."}]
    )


def test_an_unhandled_exception_is_a_500_that_leaks_nothing():
    records = []
    response = build(log=lambda event, context: records.append((event, context))).get(
        "/boom", headers={"X-Correlation-ID": "abc"}
    )
    body = assert_problem(response, 500)
    assert_that(body["detail"]).is_equal_to(GENERIC_SERVER_DETAIL)
    assert_that(response.text).does_not_contain("division")
    [(event, context)] = records
    assert_that(event).is_equal_to("problem.server_error")
    assert_that(context["exc"]).is_instance_of(ZeroDivisionError)
    assert_that(context["correlation_id"]).is_equal_to("abc")


def test_the_500_path_still_stamps_the_correlation_header():
    """ServerErrorMiddleware sits outside the correlation middleware."""
    response = build().get("/boom", headers={"X-Correlation-ID": "abc"})
    assert_that(response.headers["x-correlation-id"]).is_equal_to("abc")


def test_a_generated_correlation_id_reaches_both_body_and_header():
    response = build().get("/boom")
    assert_that(response.json()["correlation_id"]).is_equal_to(
        response.headers["x-correlation-id"]
    )


def test_without_the_middleware_the_body_is_still_a_valid_problem():
    body = assert_problem(build(middleware=False).get("/conflict"), 409)
    assert_that(body["correlation_id"]).is_none()


def test_a_401_carries_the_challenge_and_not_the_reason():
    response = build().get("/unauthenticated")
    body = assert_problem(response, 401)
    assert_that(body["detail"]).is_equal_to(AUTH_FAILED_DETAIL)
    assert_that(response.text).does_not_contain("expired")
    assert_that(response.headers["www-authenticate"]).is_equal_to('Bearer realm="api"')


def test_a_403_carries_no_challenge():
    response = build().get("/forbidden")
    assert_problem(response, 403)
    assert_that("www-authenticate" in response.headers).is_false()


def test_nothing_is_registered_until_asked():
    app = FastAPI()
    before = dict(app.exception_handlers)
    register_problem_handlers(app)
    assert_that(len(app.exception_handlers)).is_greater_than(len(before))


# --- pydantic errors to field errors ---------------------------------------


def test_validation_errors_from_pydantic():
    """A missing field reads the same detail DRF gives it."""
    raw = [
        {"loc": ("body", "name"), "msg": "Field required", "type": "missing"},
        {"loc": ("body", "items", 0, "qty"), "msg": "must be > 0"},
    ]
    assert_that(_validation_errors(raw)).is_equal_to(
        [
            {"pointer": "/name", "detail": REQUIRED_FIELD_DETAIL},
            {"pointer": "/items/0/qty", "detail": "must be > 0"},
        ]
    )


def test_validation_errors_keep_the_prefix_of_a_non_body_location():
    raw = [{"loc": ("query", "pageSize"), "msg": "Input should be a valid integer"}]
    assert_that(_validation_errors(raw)).is_equal_to(
        [{"pointer": "/query/pageSize", "detail": "Input should be a valid integer"}]
    )


def test_validation_errors_handle_an_empty_loc():
    assert_that(_validation_errors([{"loc": (), "msg": "bad"}])).is_equal_to(
        [{"pointer": "", "detail": "bad"}]
    )
