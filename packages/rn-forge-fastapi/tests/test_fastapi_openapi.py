"""Tests for rn_forge.fastapi.openapi."""

import pytest
from assertpy import assert_that
from fastapi import FastAPI

from rn_forge.fastapi import (
    OPENAPI_VERSION,
    WireModel,
    health_router,
    install_problem_schema,
    operation_id,
)
from rn_forge.web import ProblemRegistry, ProblemType

pytestmark = pytest.mark.unit

DEFAULT_PROBLEM_STATUSES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    412: "Precondition Failed",
    422: "Unprocessable Content",
    428: "Precondition Required",
    500: "Internal Server Error",
    502: "Bad Gateway",
}


class OrderOut(WireModel):
    order_id: str


def problem_response(description):
    return {
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemDetail"}
            }
        },
        "description": description,
    }


def build(**install_kwargs):
    app = FastAPI(generate_unique_id_function=operation_id)
    install_problem_schema(app, **install_kwargs)

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str) -> OrderOut: ...

    @app.post("/orders", responses={409: {"description": "Order already dispatched"}})
    async def create_order(body: OrderOut) -> OrderOut: ...

    return app


def test_the_document_is_openapi_3_1_0():
    assert_that(build().openapi()["openapi"]).is_equal_to(OPENAPI_VERSION).is_equal_to(
        "3.1.0"
    )


def test_problem_detail_is_injected_and_the_schema_stays_cached():
    app = build()
    first = app.openapi()
    assert_that(app.openapi()).is_same_as(first)
    problem = first["components"]["schemas"]["ProblemDetail"]
    assert_that(problem["properties"]).contains_key(
        "type", "title", "status", "detail", "instance"
    )


def test_installing_twice_changes_nothing():
    once = build().openapi()
    app = build()
    install_problem_schema(app)
    assert_that(app.openapi()).is_equal_to(once)


def test_a_declared_response_is_never_overwritten():
    responses = build().openapi()["paths"]["/orders"]["post"]["responses"]
    assert_that(responses["409"]).is_equal_to(
        {"description": "Order already dispatched"}
    )


def test_fastapis_422_is_replaced_and_its_schemas_removed():
    schema = build().openapi()
    responses = schema["paths"]["/orders"]["post"]["responses"]
    assert_that(responses["422"]).is_equal_to(problem_response("Unprocessable Content"))
    assert_that(schema["components"]["schemas"]).does_not_contain_key(
        "HTTPValidationError", "ValidationError"
    )


def test_without_default_responses_only_the_422_is_repaired():
    responses = build(default_responses=False).openapi()["paths"]["/orders/{order_id}"][
        "get"
    ]["responses"]
    assert_that(set(responses)).is_equal_to({"200", "422"})
    assert_that(responses["422"]).is_equal_to(problem_response("Unprocessable Content"))


def test_the_declared_statuses_are_the_registrys_plus_500():
    registry = ProblemRegistry().register(KeyError, ProblemType("gone", 410, "Gone"))
    responses = build(registry=registry).openapi()["paths"]["/orders/{order_id}"][
        "get"
    ]["responses"]
    assert_that(set(responses)).is_equal_to({"200", "410", "422", "500"})


def test_the_shared_components_carry_the_shared_names():
    app = build()
    app.include_router(health_router(checks={}))
    assert_that(app.openapi()["components"]["schemas"]).contains_key(
        "ProblemDetail", "CheckResult", "HealthReport"
    )


def test_one_operation_snapshot():
    """A FastAPI upgrade that changes schema collection fails here, not in a client build."""
    operation = build().openapi()["paths"]["/orders/{order_id}"]["get"]
    assert_that(operation).is_equal_to(
        {
            "operationId": "ordersGet",
            "summary": "Get Order",
            "parameters": [
                {
                    "in": "path",
                    "name": "order_id",
                    "required": True,
                    "schema": {"title": "Order Id", "type": "string"},
                }
            ],
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/OrderOut"}
                        }
                    },
                    "description": "Successful Response",
                },
                **{
                    str(status): problem_response(phrase)
                    for status, phrase in DEFAULT_PROBLEM_STATUSES.items()
                },
            },
        }
    )


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/orders", "ordersList"),
        ("GET", "/orders/{order_id}", "ordersGet"),
        ("POST", "/orders", "ordersCreate"),
        ("PUT", "/orders/{order_id}", "ordersUpdate"),
        ("PATCH", "/api/v1/work-items/{item_id}", "workItemsPartialUpdate"),
        ("DELETE", "/orders/{order_id}", "ordersDelete"),
    ],
)
def test_operation_ids_follow_the_resource_verb_convention(method, path, expected):
    app = FastAPI(generate_unique_id_function=operation_id)

    async def endpoint(): ...

    app.add_api_route(path, endpoint, methods=[method])
    operations = app.openapi()["paths"][path]
    assert_that(operations[method.lower()]["operationId"]).is_equal_to(expected)


def test_an_explicit_operation_id_wins():
    app = FastAPI(generate_unique_id_function=operation_id)

    @app.post("/orders/{order_id}/cancel", operation_id="ordersCancel")
    async def cancel(order_id: str): ...

    operation = app.openapi()["paths"]["/orders/{order_id}/cancel"]["post"]
    assert_that(operation["operationId"]).is_equal_to("ordersCancel")
