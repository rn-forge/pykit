"""Tests for `current_principal`, `requires_permission` and `PolicyGuard`."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rn_forge.auth import (
    AuthorizationContext,
    PasswordIdentityProvider,
    Principal,
    Requirement,
)
from rn_forge.fastapi import (
    AuthRoutesConfig,
    PolicyGuard,
    SessionMiddleware,
    auth_router,
    bearer_auth,
    current_principal,
    register_problem_handlers,
    requires,
    requires_permission,
    sessions_for,
)
from rn_forge.web import AUTH_FAILED_DETAIL, AuthenticationFailed

pytestmark = pytest.mark.unit

ORIGIN = "https://testserver"
ISSUER = "idp"


class Accounts:
    def __init__(self) -> None:
        self.links = {(ISSUER, "tok-ada"): "acct-ada", (ISSUER, "tok-bob"): "acct-bob"}
        self.provisioned: list[Any] = []

    def resolve(self, identity: Any) -> str:
        return f"acct-{identity.subject}"

    def lookup(self, issuer: str, subject: str) -> str | None:
        return self.links.get((issuer, subject))


class Contexts:
    def __init__(self) -> None:
        self.inactive: set[str] = set()

    def resolve(self, account_id: str) -> AuthorizationContext:
        return AuthorizationContext(
            active=account_id not in self.inactive,
            session_version=1,
            permissions=frozenset({"orders.read", "orders.update"}),
            roles=frozenset({"staff"}),
            attributes={"tenant": "t-1"},
        )


class State:
    def set_active(self, account_id: str, active: bool) -> None:
        raise NotImplementedError

    def bump_session_version(self, account_id: str) -> int:
        return 1


class Tokens:
    """Verifies `good-*` tokens as the matching external subject."""

    def authenticate(self, *, credentials: Any) -> Principal:
        if credentials.token == "good-ada":
            return Principal(
                subject="tok-ada",
                issuer=ISSUER,
                scopes=frozenset({"orders:read"}),
                claims={"sub": "tok-ada"},
            )
        if credentials.token == "good-stranger":
            return Principal(subject="nobody", issuer=ISSUER)
        raise AuthenticationFailed("bad token")


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column()


class OwnerPolicy:
    def allows(self, principal: Principal, action: str, resource: Order) -> bool:
        return resource.owner == principal.subject

    def scope(self, principal: Principal, action: str, query: Any) -> Any:
        return query.where(Order.owner == principal.subject)


class World:
    def __init__(self, *, hides: bool = False, with_bearer: bool = True) -> None:
        self.verified: list[tuple[str, str]] = []

        def verify(username: str, password: str) -> str | None:
            self.verified.append((username, password))
            return username if password == "correct" and username == "ada" else None

        self.accounts = Accounts()
        self.contexts = Contexts()
        config = AuthRoutesConfig(
            providers={"password": PasswordIdentityProvider(verify)},
            accounts=self.accounts,
            contexts=self.contexts,
            account_state=State(),
            debug=True,
            problem_type_base="https://errors.example/",
        )
        engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all(
                [
                    Order(id=i, owner="acct-ada" if i % 3 else "acct-bob")
                    for i in range(1, 11)
                ]
            )
            db.commit()

        app = FastAPI()
        register_problem_handlers(app, realm="api")
        app.add_middleware(SessionMiddleware, sessions=sessions_for(config))
        app.include_router(auth_router(config))
        bearer = bearer_auth(
            authenticator=Tokens(),
            accounts=self.accounts,
            contexts=self.contexts,
            scope_map={"orders:read": frozenset({"orders.read"})},
        )
        who = current_principal(bearer=bearer if with_bearer else None)
        guard = PolicyGuard[Order, Any](OwnerPolicy(), hides_existence=hides)

        @app.get("/me")
        async def me(principal: Principal = Depends(who)) -> dict[str, Any]:
            return {
                "subject": principal.subject,
                "mechanism": principal.mechanism,
                "permissions": sorted(principal.permissions),
                "roles": sorted(principal.roles),
                "tenant": principal.tenant,
                "external": principal.external_subject,
                "amr": sorted(principal.amr),
                "auth_time": principal.auth_time is not None,
            }

        @app.get("/read")
        async def read(
            principal: Principal = Depends(
                requires_permission(who, "orders", "retrieve")
            ),
        ) -> dict[str, str]:
            return {"ok": principal.subject}

        @app.post("/update")
        async def update(
            principal: Principal = Depends(
                requires_permission(who, "orders", "partial_update")
            ),
        ) -> dict[str, str]:
            return {"ok": principal.subject}

        @app.delete("/delete")
        async def delete(
            principal: Principal = Depends(
                requires_permission(who, "orders", "destroy")
            ),
        ) -> dict[str, str]:
            return {"ok": principal.subject}

        @app.get("/requirement")
        async def requirement(
            principal: Principal = Depends(
                requires(who, Requirement(all_permissions=frozenset({"orders.admin"})))
            ),
        ) -> dict[str, str]:
            return {"ok": principal.subject}

        @app.get("/orders")
        def orders(
            limit: int = 3,
            offset: int = 0,
            principal: Principal = Depends(who),
        ) -> dict[str, Any]:
            query = guard.scope(principal, "list", select(Order.id))
            with Session(engine) as db:
                total = db.scalar(select(func.count()).select_from(query.subquery()))
                ids = db.scalars(query.order_by(Order.id).limit(limit).offset(offset))
                return {"total": total, "ids": list(ids)}

        @app.get("/orders/{order_id}")
        def order(order_id: int, principal: Principal = Depends(who)) -> dict[str, int]:
            with Session(engine) as db:
                found = db.get(Order, order_id)
                if found is None:
                    raise LookupError("Not found")
                return {"id": guard.check(principal, "read", found).id}

        self.client = TestClient(app, base_url=ORIGIN)

    def login(self) -> None:
        self.client.get("/auth/session")
        token = self.client.cookies.get("XSRF-TOKEN")
        response = self.client.post(
            "/auth/login/password",
            json={"username": "ada", "password": "correct"},
            headers={"Origin": ORIGIN, "X-XSRF-TOKEN": token or ""},
        )
        assert_that(response.status_code).is_equal_to(200)


GOOD = {"Authorization": "Bearer good-ada"}


def test_a_session_yields_a_session_principal_from_the_context() -> None:
    world = World()
    world.login()

    body = world.client.get("/me").json()

    assert_that(body["mechanism"]).is_equal_to("session")
    assert_that(body["subject"]).is_equal_to("acct-ada")
    assert_that(body["permissions"]).is_equal_to(["orders.read", "orders.update"])
    assert_that(body["roles"]).is_equal_to(["staff"])
    assert_that(body["tenant"]).is_equal_to("t-1")
    assert_that(body["external"]).is_equal_to("ada")


def test_no_credentials_with_bearer_is_a_401_with_the_bearer_challenge() -> None:
    response = World().client.get("/me")

    assert_that(response.status_code).is_equal_to(401)
    assert_that(response.headers["www-authenticate"]).is_equal_to('Bearer realm="api"')


def test_no_credentials_without_bearer_is_a_401_without_a_challenge() -> None:
    response = World(with_bearer=False).client.get("/me")

    assert_that(response.status_code).is_equal_to(401)
    assert_that("www-authenticate" in response.headers).is_false()


@pytest.mark.security_control("bearer-scope-ceiling")
def test_a_bearer_token_yields_the_linked_account_limited_by_scopes() -> None:
    world = World()

    body = world.client.get("/me", headers=GOOD).json()

    assert_that(body["mechanism"]).is_equal_to("bearer")
    assert_that(body["subject"]).is_equal_to("acct-ada")
    assert_that(body["external"]).is_equal_to("tok-ada")
    assert_that(body["permissions"]).is_equal_to(["orders.read"])
    assert_that(body["tenant"]).is_equal_to("t-1")


def test_an_unlinked_bearer_subject_is_a_401_and_is_never_provisioned() -> None:
    world = World()
    provisioned: list[Any] = []
    world.accounts.resolve = lambda identity: provisioned.append(identity) or "x"  # type: ignore[method-assign]

    response = world.client.get(
        "/me", headers={"Authorization": "Bearer good-stranger"}
    )

    assert_that(response.status_code).is_equal_to(401)
    assert_that(response.json()["detail"]).is_equal_to(AUTH_FAILED_DETAIL)
    assert_that(provisioned).is_empty()


def test_an_inactive_account_is_a_401() -> None:
    world = World()
    world.contexts.inactive.add("acct-ada")

    assert_that(world.client.get("/me", headers=GOOD).status_code).is_equal_to(401)


@pytest.mark.security_control("one-credential-per-request")
def test_an_invalid_bearer_is_a_401_even_with_a_valid_session_cookie() -> None:
    world = World()
    world.login()

    response = world.client.get("/me", headers={"Authorization": "Bearer forged"})

    assert_that(response.status_code).is_equal_to(401)
    assert_that(response.headers["www-authenticate"]).is_equal_to('Bearer realm="api"')


@pytest.mark.security_control("one-credential-per-request")
def test_an_authorization_header_without_bearer_auth_ignores_the_session() -> None:
    world = World(with_bearer=False)
    world.login()

    assert_that(world.client.get("/me", headers=GOOD).status_code).is_equal_to(401)


@pytest.mark.security_control("one-credential-per-request")
def test_a_valid_bearer_wins_over_the_session() -> None:
    world = World()
    world.login()

    body = world.client.get("/me", headers=GOOD).json()

    assert_that(body["mechanism"]).is_equal_to("bearer")


def test_the_permission_requirement_follows_the_http_method() -> None:
    world = World()
    world.login()

    assert_that(world.client.get("/read").status_code).is_equal_to(200)
    # `destroy` maps to `orders.delete`, which the context does not hold.
    denied = world.client.delete(
        "/delete",
        headers={"Origin": ORIGIN, "X-XSRF-TOKEN": world.client.cookies["XSRF-TOKEN"]},
    )
    assert_that(denied.status_code).is_equal_to(403)
    assert_that("www-authenticate" in denied.headers).is_false()


def test_a_named_action_is_mapped_to_its_permission_suffix() -> None:
    world = World()
    world.login()
    token = world.client.cookies["XSRF-TOKEN"]

    response = world.client.post(
        "/update", headers={"Origin": ORIGIN, "X-XSRF-TOKEN": token}
    )

    assert_that(response.status_code).is_equal_to(200)


@pytest.mark.security_control("bearer-scope-ceiling")
def test_a_bearer_scope_that_does_not_allow_the_permission_is_a_403() -> None:
    world = World()

    response = world.client.post("/update", headers=GOOD)

    assert_that(response.status_code).is_equal_to(403)


def test_requires_checks_a_requirement_against_the_current_principal() -> None:
    world = World()
    world.login()

    assert_that(world.client.get("/requirement").status_code).is_equal_to(403)


def test_list_scoping_narrows_rows_counts_and_pages() -> None:
    world = World()
    world.login()
    # ada owns every id that is not a multiple of 3: 1 2 4 5 7 8 10.
    first = world.client.get("/orders", params={"limit": 3, "offset": 0}).json()
    second = world.client.get("/orders", params={"limit": 3, "offset": 3}).json()
    third = world.client.get("/orders", params={"limit": 3, "offset": 6}).json()

    assert_that(first).is_equal_to({"total": 7, "ids": [1, 2, 4]})
    assert_that(second).is_equal_to({"total": 7, "ids": [5, 7, 8]})
    assert_that(third).is_equal_to({"total": 7, "ids": [10]})


def test_an_object_the_policy_allows_is_returned() -> None:
    world = World()
    world.login()

    assert_that(world.client.get("/orders/1").json()).is_equal_to({"id": 1})


def test_a_denied_object_is_a_403() -> None:
    world = World()
    world.login()

    assert_that(world.client.get("/orders/3").status_code).is_equal_to(403)


def test_a_denied_object_is_a_404_when_existence_is_sensitive() -> None:
    world = World(hides=True)
    world.login()

    denied = world.client.get("/orders/3")
    missing = world.client.get("/orders/99")

    assert_that(denied.status_code).is_equal_to(404)
    assert_that(missing.status_code).is_equal_to(404)
    assert_that(denied.json()["detail"]).is_equal_to(missing.json()["detail"])


def test_the_password_provider_uses_the_applications_verifier() -> None:
    world = World()
    world.client.get("/auth/session")
    token = world.client.cookies["XSRF-TOKEN"]

    response = world.client.post(
        "/auth/login/password",
        json={"username": "ada", "password": "wrong"},
        headers={"Origin": ORIGIN, "X-XSRF-TOKEN": token},
    )

    assert_that(response.status_code).is_equal_to(401)
    assert_that(world.verified).is_equal_to([("ada", "wrong")])


def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("audit event=")
    ]


@pytest.mark.security_control("audit-events")
def test_a_denied_permission_is_audited(caplog: pytest.LogCaptureFixture) -> None:
    world = World()
    world.login()
    caplog.set_level(logging.INFO)
    caplog.clear()

    world.client.delete("/delete", headers={"Origin": ORIGIN, **_csrf(world)})

    assert _events(caplog) == [
        "audit event=authorization.denied account_id='acct-ada' "
        "permission_key='orders' action='destroy'"
    ]


@pytest.mark.security_control("audit-events")
def test_a_denied_requirement_is_audited(caplog: pytest.LogCaptureFixture) -> None:
    world = World()
    world.login()
    caplog.set_level(logging.INFO)
    caplog.clear()

    world.client.get("/requirement")

    assert _events(caplog) == ["audit event=authorization.denied account_id='acct-ada'"]


@pytest.mark.security_control("audit-events")
@pytest.mark.parametrize(("hides", "status"), [(False, 403), (True, 404)])
def test_a_denied_object_is_audited(
    caplog: pytest.LogCaptureFixture, hides: bool, status: int
) -> None:
    world = World(hides=hides)
    world.login()
    caplog.set_level(logging.INFO)
    caplog.clear()

    response = world.client.get("/orders/3")

    assert_that(response.status_code).is_equal_to(status)
    assert _events(caplog) == [
        "audit event=authorization.denied account_id='acct-ada' action='read' "
        f"resource='Order' hidden={hides}"
    ]


@pytest.mark.security_control("audit-events")
def test_an_allowed_request_is_not_audited(caplog: pytest.LogCaptureFixture) -> None:
    world = World()
    world.login()
    caplog.set_level(logging.INFO)
    caplog.clear()

    world.client.get("/read")
    world.client.get("/orders/1")

    assert _events(caplog) == []


def _csrf(world: World) -> dict[str, str]:
    return {"X-XSRF-TOKEN": world.client.cookies["XSRF-TOKEN"]}
