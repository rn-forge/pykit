"""Tests for rn_forge.fastapi.idempotency."""

import pytest
from assertpy import assert_that
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from rn_forge.fastapi.idempotency import idempotent
from rn_forge.fastapi.problem import register_problem_handlers
from rn_forge.web import InMemoryAsyncIdempotencyStore, PROBLEM_MEDIA_TYPE

pytestmark = pytest.mark.unit


def build_app(store):
    app = FastAPI()
    register_problem_handlers(app)
    calls = []

    @app.post("/charges", status_code=201)
    @idempotent(store, scope="charges")
    async def create_charge(request: Request) -> JSONResponse:
        calls.append(1)
        return JSONResponse({"charged": 1}, status_code=201, headers={"X-Made": "1"})

    @app.get("/charges")
    @idempotent(store, scope="charges")
    async def list_charges(request: Request) -> JSONResponse:
        calls.append(1)
        return JSONResponse({"items": []}, status_code=200)

    app.state.calls = calls
    return app


def problem(response, status):
    assert_that(response.status_code).is_equal_to(status)
    assert_that(response.headers["content-type"]).is_equal_to(PROBLEM_MEDIA_TYPE)
    return response.json()


def test_a_safe_method_bypasses_the_store():
    app = build_app(InMemoryAsyncIdempotencyStore())
    client = TestClient(app)
    client.get("/charges")
    client.get("/charges")
    assert_that(app.state.calls).is_length(2)


def test_a_missing_key_on_an_unsafe_method_is_a_400_problem():
    app = build_app(InMemoryAsyncIdempotencyStore())
    body = problem(TestClient(app).post("/charges"), 400)
    assert_that(body["detail"]).is_equal_to("Idempotency-Key is required")


def test_first_sight_executes_and_preserves_response_headers():
    app = build_app(InMemoryAsyncIdempotencyStore())
    response = TestClient(app).post("/charges", headers={"Idempotency-Key": "k1"})
    assert_that(response.status_code).is_equal_to(201)
    assert_that(response.json()).is_equal_to({"charged": 1})
    assert_that(response.headers["x-made"]).is_equal_to("1")


def test_a_replay_returns_the_stored_response_without_re_executing():
    app = build_app(InMemoryAsyncIdempotencyStore())
    client = TestClient(app)
    client.post("/charges", headers={"Idempotency-Key": "k1"})
    response = client.post("/charges", headers={"Idempotency-Key": "k1"})
    assert_that(response.status_code).is_equal_to(201)
    assert_that(response.json()).is_equal_to({"charged": 1})
    assert_that(app.state.calls).is_length(1)


def test_a_replayed_key_with_a_different_body_is_a_422_problem():
    app = build_app(InMemoryAsyncIdempotencyStore())
    client = TestClient(app)
    client.post("/charges", headers={"Idempotency-Key": "k1"}, json={"a": 1})
    body = problem(
        client.post("/charges", headers={"Idempotency-Key": "k1"}, json={"a": 2}), 422
    )
    assert_that(body["detail"]).contains("replayed with a different request body")
