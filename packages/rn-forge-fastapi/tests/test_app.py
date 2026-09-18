"""Tests for standard FastAPI application construction."""

from contextlib import asynccontextmanager

import asyncio

import pytest
from assertpy import assert_that
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from rn_forge.fastapi import AppConfig, create_app
from rn_forge.web import CheckResult, DomainConflict, ProblemType, default_registry

pytestmark = pytest.mark.unit


def test_create_app_installs_the_standard_adapters():
    router = APIRouter()

    @router.get("/orders")
    async def orders() -> dict[str, str]:
        return {"id": "1"}

    @router.get("/locked")
    async def locked() -> None:
        raise OrderLocked()

    registry = default_registry().register(
        OrderLocked, ProblemType("order-locked", 423, "Locked")
    )
    app = create_app(
        AppConfig(
            registry=registry,
            checks={"db": lambda: True},
            required_checks=("db",),
        ),
        routers=(router,),
        title="Orders",
    )

    client = TestClient(app, raise_server_exceptions=False)
    assert_that(client.get("/healthz").json()).is_equal_to({"status": "pass"})
    assert_that(client.get("/readyz").status_code).is_equal_to(200)
    assert_that(client.get("/orders").json()).is_equal_to({"id": "1"})
    assert_that(client.get("/locked").status_code).is_equal_to(423)
    schema = client.get("/openapi.json").json()
    assert_that(schema["openapi"]).is_equal_to("3.1.0")
    assert_that(schema["components"]["schemas"]).contains_key("ProblemDetail")


class OrderLocked(Exception):
    pass


def test_required_check_timeout_and_optional_failure_keep_health_semantics():
    async def hung() -> None:
        await asyncio.Event().wait()

    app = create_app(
        AppConfig(
            checks={"db": hung, "queue": lambda: CheckResult(status="fail")},
            required_checks=("db",),
            check_timeout=0.01,
        )
    )
    response = TestClient(app).get("/readyz")
    assert_that(response.status_code).is_equal_to(503)
    assert_that(response.json()["checks"]["queue"]["status"]).is_equal_to("fail")


def test_lifespan_and_each_configuration_stay_with_its_own_app():
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        events.append("start")
        yield
        events.append("stop")

    first = create_app(
        AppConfig(checks={"db": lambda: False}, required_checks=("db",)),
        lifespan=lifespan,
    )
    second = create_app(AppConfig(checks={"db": lambda: True}, required_checks=("db",)))

    with TestClient(first) as client:
        assert_that(client.get("/readyz").status_code).is_equal_to(503)
    assert_that(events).is_equal_to(["start", "stop"])
    assert_that(TestClient(second).get("/readyz").status_code).is_equal_to(200)
