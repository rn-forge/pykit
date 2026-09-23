"""Tests for standard FastAPI application construction."""

from contextlib import asynccontextmanager
from typing import Any

import asyncio

import pytest
from assertpy import assert_that
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from rn_forge.fastapi import AppConfig, CorsPolicy, FastApiApp
from rn_forge.web import (
    API_CATALOG_PATH,
    DOCS_PATH,
    LINKSET_MEDIA_TYPE,
    OPENAPI_PATH,
    CheckResult,
    DomainConflict,
    ProblemType,
    default_registry,
)

pytestmark = pytest.mark.unit


def test_fastapi_app_installs_the_standard_adapters():
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
    app = FastApiApp(
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
    assert_that(isinstance(app, FastAPI)).is_true()


class OrderLocked(Exception):
    pass


def test_fastapi_app_is_a_fastapi_instance_with_its_config_attached():
    config = AppConfig()
    app = FastApiApp(config)
    assert_that(isinstance(app, FastAPI)).is_true()
    assert_that(app.config).is_same_as(config)


def test_fastapi_app_with_no_argument_uses_a_default_config():
    app = FastApiApp()
    assert_that(app.config).is_instance_of(AppConfig)
    assert_that(TestClient(app).get("/healthz").status_code).is_equal_to(200)


def test_generate_unique_id_function_is_overridable():
    def custom_operation_id(route: Any) -> str:
        return f"custom_{route.name}"

    app = FastApiApp(generate_unique_id_function=custom_operation_id)
    router = APIRouter()

    @router.get("/thing")
    async def thing() -> dict[str, str]:
        return {}

    app.include_router(router)
    schema = TestClient(app).get("/openapi.json").json()
    assert_that(schema["paths"]["/thing"]["get"]["operationId"]).is_equal_to(
        "custom_thing"
    )


def test_a_subclass_of_fastapi_app_constructs_and_serves():
    class MyApp(FastApiApp):
        pass

    app = MyApp(AppConfig(checks={"db": lambda: True}, required_checks=("db",)))
    assert_that(TestClient(app).get("/readyz").status_code).is_equal_to(200)


def test_required_check_timeout_and_optional_failure_keep_health_semantics():
    async def hung() -> None:
        await asyncio.Event().wait()

    app = FastApiApp(
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

    first = FastApiApp(
        AppConfig(checks={"db": lambda: False}, required_checks=("db",)),
        lifespan=lifespan,
    )
    second = FastApiApp(AppConfig(checks={"db": lambda: True}, required_checks=("db",)))

    with TestClient(first) as client:
        assert_that(client.get("/readyz").status_code).is_equal_to(503)
    assert_that(events).is_equal_to(["start", "stop"])
    assert_that(TestClient(second).get("/readyz").status_code).is_equal_to(200)


def test_openapi_and_docs_defaults_equal_the_web_constants():
    app = FastApiApp()
    assert_that(app.openapi_url).is_equal_to(OPENAPI_PATH)
    assert_that(app.docs_url).is_equal_to(DOCS_PATH)


def test_the_api_catalog_is_served_by_default():
    client = TestClient(FastApiApp())
    body = client.get(API_CATALOG_PATH).json()
    assert_that(body).is_equal_to(
        {
            "linkset": [
                {
                    "anchor": "/",
                    "service-desc": [{"href": OPENAPI_PATH}],
                    "service-doc": [{"href": DOCS_PATH}],
                    "status": [{"href": "/readyz"}],
                }
            ]
        }
    )
    assert_that(client.get(API_CATALOG_PATH).headers["content-type"]).is_equal_to(
        LINKSET_MEDIA_TYPE
    )
    assert_that(client.head(API_CATALOG_PATH).status_code).is_equal_to(200)


def test_the_api_catalog_is_excluded_from_the_openapi_document():
    schema = TestClient(FastApiApp()).get(OPENAPI_PATH).json()
    assert_that(schema["paths"]).does_not_contain_key(API_CATALOG_PATH)


def test_the_api_catalog_can_be_disabled():
    client = TestClient(FastApiApp(AppConfig(api_catalog=False)))
    assert_that(client.get(API_CATALOG_PATH).status_code).is_equal_to(404)


def test_security_headers_are_installed_by_default():
    response = TestClient(FastApiApp()).get("/healthz")
    assert_that(response.headers["cache-control"]).is_equal_to("no-store")
    assert_that(response.headers["content-security-policy"]).is_equal_to(
        "frame-ancestors 'none'"
    )
    assert_that(response.headers["x-content-type-options"]).is_equal_to("nosniff")
    assert_that(response.headers["x-frame-options"]).is_equal_to("DENY")
    assert_that(response.headers["referrer-policy"]).is_equal_to("no-referrer")
    assert_that(response.headers).does_not_contain_key("strict-transport-security")


def test_security_headers_can_be_disabled():
    response = TestClient(FastApiApp(AppConfig(security_headers=False))).get("/healthz")
    assert_that(response.headers).does_not_contain_key("cache-control")


def test_hsts_is_opt_in():
    response = TestClient(FastApiApp(AppConfig(hsts=True))).get("/healthz")
    assert_that(response.headers["strict-transport-security"]).is_equal_to(
        "max-age=31536000; includeSubDomains"
    )


def test_no_cors_policy_means_no_cors_middleware():
    response = TestClient(FastApiApp()).get(
        "/healthz", headers={"Origin": "https://example.com"}
    )
    assert_that(response.headers).does_not_contain_key("access-control-allow-origin")


def test_cors_is_applied_and_is_outermost():
    """The 404 problem response still carries CORS headers, proving the ordering."""
    app = FastApiApp(AppConfig(cors=CorsPolicy(allow_origins=("https://example.com",))))
    response = TestClient(app, raise_server_exceptions=False).get(
        "/nope", headers={"Origin": "https://example.com"}
    )
    assert_that(response.status_code).is_equal_to(404)
    assert_that(response.headers["access-control-allow-origin"]).is_equal_to(
        "https://example.com"
    )


def test_the_configured_log_sink_receives_request_complete_events():
    events = []
    app = FastApiApp(
        AppConfig(log=lambda event, ctx: events.append((event, dict(ctx))))
    )
    TestClient(app).get("/healthz")
    assert_that([event for event, _ in events]).contains("request.complete")
    fields = next(ctx for event, ctx in events if event == "request.complete")
    assert_that(fields["http.request.method"]).is_equal_to("GET")
    assert_that(fields["url.path"]).is_equal_to("/healthz")
    assert_that(fields["http.response.status_code"]).is_equal_to(200)


def test_a_subclass_can_extend_openapi_through_super():
    """R1.2's composition: extend the repair rather than patch an attribute."""

    class MyApp(FastApiApp):
        def openapi(self):
            schema = super().openapi()
            schema["info"]["x-extra"] = "yes"
            return schema

    app = MyApp()
    schema = TestClient(app).get("/openapi.json").json()
    assert_that(schema["info"]["x-extra"]).is_equal_to("yes")
    assert_that(schema["components"]["schemas"]).contains_key("ProblemDetail")
