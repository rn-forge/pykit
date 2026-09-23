"""Tests for rn_forge.fastapi.cors."""

import pytest
from assertpy import assert_that
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rn_forge.fastapi.cors import CorsPolicy, apply_cors
from rn_forge.web import DEFAULT_CORRELATION_HEADER, EXPOSED_HEADERS, WebError

pytestmark = pytest.mark.unit


def build_app(policy: CorsPolicy) -> FastAPI:
    app = FastAPI()
    apply_cors(app, policy)

    @app.get("/thing")
    async def thing() -> dict[str, str]:
        return {"id": "1"}

    return app


def test_a_simple_response_carries_the_allowed_origin_and_exposed_headers():
    app = build_app(CorsPolicy(allow_origins=("https://example.com",)))
    response = TestClient(app).get("/thing", headers={"Origin": "https://example.com"})
    assert_that(response.headers["access-control-allow-origin"]).is_equal_to(
        "https://example.com"
    )
    assert_that(response.headers["access-control-expose-headers"]).is_equal_to(
        ", ".join(EXPOSED_HEADERS)
    )


def test_a_preflight_returns_the_configured_methods_and_headers():
    app = build_app(CorsPolicy(allow_origins=("https://example.com",)))
    response = TestClient(app).options(
        "/thing",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert_that(response.headers["access-control-allow-methods"]).contains("GET")


def test_the_correlation_header_is_appended_without_duplication():
    app = FastAPI()
    apply_cors(
        app,
        CorsPolicy(allow_origins=("https://example.com",), expose_headers=("ETag",)),
        correlation_header=DEFAULT_CORRELATION_HEADER,
    )

    @app.get("/thing")
    async def thing() -> dict[str, str]:
        return {}

    response = TestClient(app).get("/thing", headers={"Origin": "https://example.com"})
    exposed = response.headers["access-control-expose-headers"].split(", ")
    assert_that(exposed).is_equal_to(["ETag", DEFAULT_CORRELATION_HEADER])


def test_credentials_with_a_wildcard_origin_is_rejected():
    assert_that(CorsPolicy).raises(WebError).when_called_with(
        allow_origins=("*",), allow_credentials=True
    )


def test_no_policy_means_no_cors_headers():
    app = FastAPI()

    @app.get("/thing")
    async def thing() -> dict[str, str]:
        return {}

    response = TestClient(app).get("/thing", headers={"Origin": "https://example.com"})
    assert_that(response.headers).does_not_contain_key("access-control-allow-origin")
