"""Tests for rn_forge.fastapi.auth."""

import asyncio
import base64

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from rn_forge.fastapi import (
    basic_auth,
    bearer_auth,
    register_problem_handlers,
    requires,
)
from rn_forge.web import (
    AUTH_FAILED_DETAIL,
    PROBLEM_MEDIA_TYPE,
    AuthenticationFailed,
    Principal,
    Requirement,
)

pytestmark = pytest.mark.unit

ALICE = base64.b64encode(b"alice:secret").decode()


class Directory:
    """A sync authenticator standing in for a verifier over commons."""

    def __init__(self):
        self.seen = []

    def authenticate(self, *, credentials):
        self.seen.append(credentials)
        if credentials.token in ("good", ALICE):
            return Principal(
                subject="alice",
                scopes=frozenset({"read"}),
                mechanism=credentials.scheme.lower(),
            )
        if credentials.token == "narrow":
            return Principal(subject="bob")
        raise AuthenticationFailed("signature verification failed: unknown kid k-9")


class AsyncDirectory:
    async def authenticate(self, *, credentials):
        return Principal(subject="carol", scopes=frozenset({"read"}))


def build(authenticator, log=None):
    app = FastAPI()
    register_problem_handlers(app, realm="api")
    bearer = bearer_auth(authenticator=authenticator, log=log)
    reader = requires(bearer, Requirement(all_scopes=frozenset({"read"})))
    basic = basic_auth(authenticator=authenticator, log=log)

    def shape(principal):
        return {
            "subject": principal.subject,
            "scopes": sorted(principal.scopes),
            "mechanism": principal.mechanism,
        }

    @app.get("/me")
    async def me(principal: Principal = Depends(bearer)):
        return shape(principal)

    @app.get("/read")
    async def read(principal: Principal = Depends(reader)):
        return shape(principal)

    @app.get("/basic")
    async def basic_me(principal: Principal = Depends(basic)):
        return shape(principal)

    return TestClient(app)


def assert_401(response):
    assert_that(response.status_code).is_equal_to(401)
    assert_that(response.headers["content-type"]).is_equal_to(PROBLEM_MEDIA_TYPE)
    assert_that(response.headers["www-authenticate"]).is_equal_to('Bearer realm="api"')
    assert_that(response.json()["detail"]).is_equal_to(AUTH_FAILED_DETAIL)


def test_a_valid_bearer_token_yields_the_principal():
    response = build(Directory()).get("/me", headers={"Authorization": "Bearer good"})
    assert_that(response.json()).is_equal_to(
        {"subject": "alice", "scopes": ["read"], "mechanism": "bearer"}
    )


def test_a_sync_authenticator_runs_off_the_event_loop():
    loops = []

    class Probe(Directory):
        def authenticate(self, *, credentials):
            try:
                loops.append(asyncio.get_running_loop())
            except RuntimeError:
                loops.append(None)
            return super().authenticate(credentials=credentials)

    response = build(Probe()).get("/me", headers={"Authorization": "Bearer good"})
    assert_that(response.status_code).is_equal_to(200)
    assert_that(loops).is_equal_to([None])


def test_an_async_authenticator_is_awaited():
    response = build(AsyncDirectory()).get("/me", headers={"Authorization": "Bearer x"})
    assert_that(response.json()["subject"]).is_equal_to("carol")


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic abc"}])
def test_missing_bearer_credentials_are_a_401_with_the_rfc6750_challenge(headers):
    assert_401(build(Directory()).get("/me", headers=headers))


def test_an_invalid_token_logs_the_reason_and_never_returns_it():
    records = []
    response = build(
        Directory(), log=lambda event, context: records.append((event, context))
    ).get("/me", headers={"Authorization": "Bearer forged"})
    assert_401(response)
    assert_that(response.text).does_not_contain("kid")
    [(event, context)] = records
    assert_that(event).is_equal_to("authentication.failed")
    assert_that(context["reason"]).contains("unknown kid k-9")


def test_a_valid_token_without_the_scope_is_a_403_without_a_challenge():
    response = build(Directory()).get(
        "/read", headers={"Authorization": "Bearer narrow"}
    )
    assert_that(response.status_code).is_equal_to(403)
    assert_that(response.headers["content-type"]).is_equal_to(PROBLEM_MEDIA_TYPE)
    assert_that("www-authenticate" in response.headers).is_false()


def test_a_valid_token_with_the_scope_passes_the_requirement():
    response = build(Directory()).get("/read", headers={"Authorization": "Bearer good"})
    assert_that(response.status_code).is_equal_to(200)


def test_basic_auth_hands_over_the_parameter_verbatim_and_yields_the_same_shape():
    directory = Directory()
    response = build(directory).get(
        "/basic", headers={"Authorization": f"Basic {ALICE}"}
    )
    assert_that(response.json()).is_equal_to(
        {"subject": "alice", "scopes": ["read"], "mechanism": "basic"}
    )
    assert_that(directory.seen[-1].scheme).is_equal_to("Basic")
    assert_that(directory.seen[-1].token).is_equal_to(ALICE)


def test_missing_basic_credentials_are_the_same_401():
    assert_401(build(Directory()).get("/basic"))


def test_the_schema_declares_both_security_schemes():
    app = build(Directory()).app
    schemes = app.openapi()["components"]["securitySchemes"]
    assert_that(schemes).contains_key("HTTPBearer", "HTTPBasic")
