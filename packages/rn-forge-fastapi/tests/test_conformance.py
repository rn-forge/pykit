"""The FastAPI conformance driver: every case in `rn_forge.web.conformance.CASES`.

The fixture application is wired from this package's adapters and nothing
hand-written: if a case needs more than a line or two over them, the adapter is
missing. Assertions are against the table, never against Django's output — two
stacks agreeing on the wrong thing is not conformance.

There is no `pytest.skip` in this file, and there must never be one. A case
this stack cannot satisfy is a finding: either an adapter is missing here, or
the case encodes a decision FastAPI cannot honour and belongs in the web plan.
"""

import re

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from rn_forge.fastapi import (
    Page,
    WireModel,
    bearer_auth,
    health_router,
    page_params,
    register_problem_handlers,
    require_idempotency_key,
    require_if_match,
    requires,
)
from rn_forge.web import (
    CheckResult,
    CorrelationIdMiddleware,
    DomainConflict,
    EntityVersionETagCodec,
    InMemoryIdempotencyStore,
    Principal,
    Requirement,
    check_precondition,
    encode_cursor,
)
from rn_forge.web.conformance import CASES, VARIABLE_MEMBERS, case_by_id, redact

pytestmark = pytest.mark.unit

ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
ITEM_VERSION = 7
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
CASING_EXEMPT = {"correlation_id"} | set(VARIABLE_MEMBERS)


class AnyToken:
    """Verifies every token as a principal with no scopes."""

    def authenticate(self, *, credentials):
        return Principal(subject="u1")


class Charge(WireModel):
    amount: int


class Named(WireModel):
    name: str


def build_app(*, failing: str | None) -> FastAPI:
    """A fresh application: the idempotency store must not carry over between cases."""
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)
    register_problem_handlers(app, realm="conformance")
    store = InMemoryIdempotencyStore()
    private = requires(
        bearer_auth(authenticator=AnyToken()),
        Requirement(all_scopes=frozenset({"read"})),
    )

    def check(name):
        return lambda: CheckResult(
            status="fail" if name == failing else "pass",
            reason="unreachable" if name == failing else None,
        )

    app.include_router(
        health_router(
            checks={"db": check("db"), "queue": check("queue")},
            required=["db"],
            prefix="/conformance",
        )
    )

    @app.get("/conformance/boom")
    async def boom():
        raise RuntimeError("connection to db-primary.internal failed: password=hunter2")

    @app.get("/conformance/conflict")
    async def conflict():
        raise DomainConflict("Order already dispatched")

    @app.post("/conformance/validate")
    async def validate(body: Named):
        return {"name": body.name}

    @app.patch("/conformance/items/{pk}")
    async def patch_item(pk: str, if_match: str = Depends(require_if_match())):
        check_precondition(
            if_match, current_version=ITEM_VERSION, entity_id=pk, required=True
        )
        etag = EntityVersionETagCodec().format(entity_id=pk, version=ITEM_VERSION)
        return JSONResponse({"id": pk, "version": ITEM_VERSION}, headers={"ETag": etag})

    @app.get("/conformance/items")
    async def list_items(
        params=Depends(page_params(cap=2, default=2)),
    ) -> Page[dict[str, str]]:
        size, cursor = params
        start = (
            next(i + 1 for i, row in enumerate(ROWS) if row["id"] == cursor.entity_id)
            if cursor
            else 0
        )
        window = ROWS[start : start + size]
        more = start + size < len(ROWS)
        token = encode_cursor(window[-1]["id"], window[-1]["id"]) if more else None
        return Page[dict[str, str]](items=window, next_page_token=token)

    @app.post("/conformance/charges", status_code=201)
    async def create_charge(
        body: Charge, key: str = Depends(require_idempotency_key())
    ):
        payload = body.model_dump()
        stored = store.record_or_replay(scope="charges", key=key, request_body=payload)
        if stored is not None:
            return JSONResponse(
                {**stored.body, "replayed": True}, status_code=stored.status
            )
        result = {"charged": body.amount}
        store.complete(scope="charges", key=key, status=201, response_body=result)
        return JSONResponse({**result, "replayed": False}, status_code=201)

    @app.get("/conformance/private")
    async def private_route(principal: Principal = Depends(private)):
        return {"subject": principal.subject}

    @app.get("/conformance/echo")
    async def echo():
        return {}

    return app


def issue(client, case):
    spec = case.request
    return client.request(
        spec.method,
        spec.path,
        headers=dict(spec.headers),
        params=dict(spec.query),
        json=spec.body,
    )


def casing_violations(node, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key not in CASING_EXEMPT and not CAMEL_CASE.match(key):
                found.append(key)
            casing_violations(value, found)
    elif isinstance(node, list):
        for item in node:
            casing_violations(item, found)
    return found


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_fastapi_conforms(case):
    client = TestClient(
        build_app(failing=case.request.query.get("fail")),
        raise_server_exceptions=False,
    )
    for prerequisite in case.depends_on:
        issue(client, case_by_id(prerequisite))

    response = issue(client, case)

    assert_that(response.status_code).described_as("status").is_equal_to(
        case.expect_status
    )
    for name, value in case.expect_headers.items():
        assert_that(response.headers.get(name)).described_as(name).is_equal_to(value)
    for name in case.expect_absent_headers:
        assert_that(name in response.headers).described_as(name).is_false()
    body = response.json()
    assert_that(redact(body)).is_equal_to(dict(case.expect_body))
    assert_that(casing_violations(body)).described_as("camelCase").is_empty()


def test_the_fixture_serves_every_path_the_table_uses():
    """A case added for an endpoint this driver does not serve must fail here."""
    paths = build_app(failing=None).openapi()["paths"]
    served = {path.replace("{pk}", "1") for path in paths}
    used = {case.request.path for case in CASES}
    assert_that(used - served - {"/conformance/missing"}).is_empty()
