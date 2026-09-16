"""Tests for rn_forge.fastapi.health."""

import asyncio

import pytest
from assertpy import assert_that
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rn_forge.fastapi import health_router
from rn_forge.web import CheckResult

pytestmark = pytest.mark.unit


def client_for(checks, *, required=(), prefix=""):
    app = FastAPI()
    app.include_router(health_router(checks=checks, required=required, prefix=prefix))
    return TestClient(app)


def test_all_checks_pass_is_200():
    response = client_for({"db": lambda: True}, required=["db"]).get("/readyz")
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.headers["content-type"]).is_equal_to("application/json")
    assert_that(response.json()["status"]).is_equal_to("pass")


def test_a_failing_required_check_is_503_naming_it():
    checks = {
        "db": lambda: CheckResult(status="fail", reason="unreachable"),
        "queue": lambda: True,
    }
    response = client_for(checks, required=["db"]).get("/readyz")
    assert_that(response.status_code).is_equal_to(503)
    assert_that(response.headers["content-type"]).is_equal_to("application/json")
    assert_that(response.json()["checks"]["db"]).contains_entry(
        {"reason": "unreachable"}
    )


def test_a_failing_optional_check_is_200_and_reported():
    response = client_for(
        {"db": lambda: True, "queue": lambda: False}, required=["db"]
    ).get("/readyz")
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()["status"]).is_equal_to("fail")
    assert_that(response.json()["checks"]["queue"]["status"]).is_equal_to("fail")


def test_a_raising_check_is_reported_rather_than_propagated():
    def explode():
        raise ConnectionError("refused")

    response = client_for({"db": explode}, required=["db"]).get("/readyz")
    assert_that(response.status_code).is_equal_to(503)
    assert_that(response.json()["checks"]["db"]).contains_entry(
        {"status": "fail"}, {"reason": "refused"}
    )


def test_sync_and_async_checks_both_work():
    async def cache():
        await asyncio.sleep(0)
        return CheckResult(status="warn", reason="slow")

    response = client_for({"db": lambda: True, "cache": cache}).get("/readyz")
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()["checks"]["cache"]["status"]).is_equal_to("warn")


def test_liveness_runs_no_checks():
    calls = []
    response = client_for(
        {"db": lambda: calls.append("db") or False}, required=["db"]
    ).get("/healthz")
    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.json()).is_equal_to({"status": "pass"})
    assert_that(calls).is_empty()


def test_the_prefix_is_applied_to_both_paths():
    client = client_for({}, prefix="/ops")
    assert_that(client.get("/ops/healthz").status_code).is_equal_to(200)
    assert_that(client.get("/ops/readyz").status_code).is_equal_to(200)


def test_a_hung_required_check_times_out_as_503():
    async def hung():
        await asyncio.Event().wait()

    app = FastAPI()
    app.include_router(
        health_router(checks={"db": hung}, required=["db"], timeout=0.05)
    )
    response = TestClient(app).get("/readyz")
    assert_that(response.status_code).is_equal_to(503)
    assert_that(response.json()["checks"]["db"]).contains_entry(
        {"status": "fail"}, {"reason": "timed out after 0.05s"}
    )


def test_two_routers_do_not_share_checks():
    first = client_for({"db": lambda: False}, required=["db"])
    second = client_for({"db": lambda: True}, required=["db"])
    assert_that(first.get("/readyz").status_code).is_equal_to(503)
    assert_that(second.get("/readyz").status_code).is_equal_to(200)
