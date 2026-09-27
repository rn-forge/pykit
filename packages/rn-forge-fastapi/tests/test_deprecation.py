"""Tests for rn_forge.fastapi.deprecation."""

from datetime import UTC, datetime

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from rn_forge.fastapi import deprecated

pytestmark = pytest.mark.unit


def build_app():
    app = FastAPI()

    @app.get(
        "/legacy",
        deprecated=True,
        dependencies=[
            Depends(
                deprecated(
                    deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
                    sunset=datetime(2026, 7, 1, tzinfo=UTC),
                    link="https://example.com/deprecated",
                )
            )
        ],
    )
    async def legacy():
        return {}

    return app


@pytest.fixture
def client():
    return TestClient(build_app())


def test_the_response_carries_the_deprecation_headers(client):
    response = client.get("/legacy")
    assert_that(response.headers["deprecation"]).is_equal_to("@1767225600")
    assert_that(response.headers["sunset"]).is_equal_to("Wed, 01 Jul 2026 00:00:00 GMT")
    assert_that(response.headers["link"]).is_equal_to(
        '<https://example.com/deprecated>; rel="deprecation"'
    )


def test_the_openapi_operation_is_marked_deprecated():
    operation = build_app().openapi()["paths"]["/legacy"]["get"]
    assert_that(operation["deprecated"]).is_true()
