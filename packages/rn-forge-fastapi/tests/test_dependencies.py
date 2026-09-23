"""Tests for rn_forge.fastapi.dependencies."""

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from rn_forge.fastapi import (
    conditional_get,
    page_params,
    register_problem_handlers,
    require_idempotency_key,
    require_if_match,
)
from rn_forge.web import PROBLEM_MEDIA_TYPE, encode_cursor

pytestmark = pytest.mark.unit


def build_app():
    app = FastAPI()
    register_problem_handlers(app)

    @app.get("/items")
    async def items(params=Depends(page_params(cap=50, default=20))):
        size, cursor = params
        return {"size": size, "cursor": cursor and [cursor.sort_key, cursor.entity_id]}

    @app.post("/charges")
    async def charges(key: str = Depends(require_idempotency_key())):
        return {"key": key}

    @app.post("/custom")
    async def custom(
        key: str = Depends(require_idempotency_key(header="X-Request-Key")),
    ):
        return {"key": key}

    @app.patch("/things/{pk}")
    async def patch_thing(pk: str, if_match: str = Depends(require_if_match())):
        return {"ifMatch": if_match}

    @app.get("/cached")
    async def cached(request: Request):
        not_modified = conditional_get(request, 'W/"1:7"')
        return not_modified if not_modified is not None else {"id": "1"}

    return app


@pytest.fixture
def client():
    return TestClient(build_app())


def problem(response, status):
    assert_that(response.status_code).is_equal_to(status)
    assert_that(response.headers["content-type"]).is_equal_to(PROBLEM_MEDIA_TYPE)
    return response.json()


# --- page_params ------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ({}, 20),
        ({"pageSize": "7"}, 7),
        ({"pageSize": "1000"}, 50),
        ({"pageSize": "0"}, 20),
    ],
)
def test_page_size_is_clamped_never_rejected(client, query, expected):
    response = client.get("/items", params=query)
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()["size"]).is_equal_to(expected)


def test_a_page_token_is_decoded(client):
    token = encode_cursor("2026-01-01", "17")
    response = client.get("/items", params={"pageToken": token})
    assert_that(response.json()["cursor"]).is_equal_to(["2026-01-01", "17"])


def test_a_tampered_page_token_is_a_400_problem(client):
    body = problem(client.get("/items", params={"pageToken": "!!!"}), 400)
    assert_that(body["detail"]).is_equal_to("Malformed page token")


def test_the_page_size_parameter_carries_no_maximum():
    """A `le=` bound is a 422 in disguise; the cap is documented instead."""
    parameters = build_app().openapi()["paths"]["/items"]["get"]["parameters"]
    by_name = {parameter["name"]: parameter for parameter in parameters}
    assert_that(set(by_name)).is_equal_to({"pageSize", "pageToken"})
    assert_that(str(by_name["pageSize"]["schema"])).does_not_contain("maximum")
    assert_that(by_name["pageSize"]["description"]).contains("50")


# --- require_idempotency_key ------------------------------------------------


def test_a_missing_idempotency_key_is_a_400_problem(client):
    body = problem(client.post("/charges"), 400)
    assert_that(body["detail"]).is_equal_to("Idempotency-Key is required")


def test_an_idempotency_key_passes_through_unchanged(client):
    response = client.post("/charges", headers={"Idempotency-Key": "k-1"})
    assert_that(response.json()).is_equal_to({"key": "k-1"})


def test_the_idempotency_header_name_is_per_application(client):
    body = problem(client.post("/custom", headers={"Idempotency-Key": "k-1"}), 400)
    assert_that(body["detail"]).is_equal_to("X-Request-Key is required")
    response = client.post("/custom", headers={"X-Request-Key": "k-2"})
    assert_that(response.json()).is_equal_to({"key": "k-2"})


# --- require_if_match -------------------------------------------------------


def test_a_missing_if_match_is_a_428_problem(client):
    body = problem(client.patch("/things/1"), 428)
    assert_that(body["detail"]).is_equal_to(
        "This endpoint requires an If-Match precondition"
    )


def test_a_malformed_if_match_is_a_400_problem(client):
    body = problem(client.patch("/things/1", headers={"If-Match": '"7"'}), 400)
    assert_that(body["detail"]).is_equal_to('Malformed If-Match validator: "7"')


@pytest.mark.parametrize("value", ['W/"1:6"', "*"])
def test_a_valid_if_match_passes_through_unchanged(client, value):
    response = client.patch("/things/1", headers={"If-Match": value})
    assert_that(response.json()).is_equal_to({"ifMatch": value})


# --- conditional_get ---------------------------------------------------------


def test_a_matching_if_none_match_is_304(client):
    response = client.get("/cached", headers={"If-None-Match": 'W/"1:7"'})
    assert_that(response.status_code).is_equal_to(304)
    assert_that(response.headers["etag"]).is_equal_to('W/"1:7"')
    assert_that(response.content).is_equal_to(b"")


def test_a_mismatched_if_none_match_returns_the_representation(client):
    response = client.get("/cached", headers={"If-None-Match": 'W/"1:6"'})
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()).is_equal_to({"id": "1"})


def test_no_if_none_match_returns_the_representation(client):
    response = client.get("/cached")
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()).is_equal_to({"id": "1"})
