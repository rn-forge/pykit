"""`OidcAuthenticator` driven through `bearer_auth()`. No test calls a real IdP.

The point of these cases is that this package writes no OIDC glue of its own:
the authenticator is `rn_forge.auth.oidc`'s, so the token accepted here is the
token `rn-forge-django`'s `JWKSBearerAuthentication` accepts.
"""

import time

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

from rn_forge.fastapi import (  # noqa: E402
    bearer_auth,
    register_problem_handlers,
    requires,
)
from rn_forge.auth import AuthorizationContext, Principal, Requirement  # noqa: E402
from rn_forge.web import (  # noqa: E402
    AUTH_FAILED_DETAIL,
)
from rn_forge.auth.oidc import OidcAuthenticator  # noqa: E402

pytestmark = pytest.mark.unit

ISSUER = "https://idp.example.com/tenant"
AUDIENCE = "api://orders"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FORGED = rsa.generate_private_key(public_exponent=65537, key_size=2048)


JWK = {**RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1"}


def _token(key=KEY, kid="k1", **claims):
    payload = {
        "sub": "u1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        "scp": "orders.read orders.write",
        "roles": ["Reader"],
        "tid": "t-1",
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


class Accounts:
    def resolve(self, identity):
        raise AssertionError("a bearer request must never provision")

    def lookup(self, issuer, subject):
        return "acct-1" if (issuer, subject) == (ISSUER, "u1") else None


class Contexts:
    def resolve(self, account_id):
        return AuthorizationContext(
            active=True,
            session_version=1,
            roles=frozenset({"Reader"}),
            attributes={"tenant": "t-1"},
        )


def build(jwks_url, requirement=Requirement()):
    authenticator = OidcAuthenticator.from_jwks_url(
        jwks_url, issuer=ISSUER, audience=AUDIENCE
    )
    app = FastAPI()
    register_problem_handlers(app, realm="orders")
    guarded = requires(
        bearer_auth(
            authenticator=authenticator, accounts=Accounts(), contexts=Contexts()
        ),
        requirement,
    )

    @app.get("/orders")
    def orders(principal: Principal = Depends(guarded)):
        return {
            "subject": principal.subject,
            "scopes": sorted(principal.scopes),
            "roles": sorted(principal.roles),
            "tenant": principal.tenant,
        }

    return TestClient(app)


def _get(client, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/orders", headers=headers)


@pytest.fixture
def jwks_url(serve_jwks):
    return serve_jwks([JWK])


class TestOidcThroughBearerAuth:
    def test_a_valid_token_yields_the_principal(self, jwks_url) -> None:
        response = _get(build(jwks_url), _token())

        assert_that(response.status_code).is_equal_to(200)
        assert_that(response.json()).is_equal_to(
            {
                "subject": "acct-1",
                "scopes": ["orders.read", "orders.write"],
                "roles": ["Reader"],
                "tenant": "t-1",
            }
        )

    @pytest.mark.parametrize(
        "token",
        [
            _token(exp=int(time.time()) - 60),
            _token(aud="api://other"),
            _token(iss="https://evil.example.com"),
            _token(key=FORGED),
            "not-a-jwt",
        ],
        ids=["expired", "audience", "issuer", "signature", "malformed"],
    )
    @pytest.mark.security_control("problem-responses")
    def test_verification_failures_are_a_generic_401(self, jwks_url, token) -> None:
        response = _get(build(jwks_url), token)

        assert_that(response.status_code).is_equal_to(401)
        assert_that(response.json()["detail"]).is_equal_to(AUTH_FAILED_DETAIL)
        assert_that(response.headers["WWW-Authenticate"]).is_equal_to(
            'Bearer realm="orders"'
        )

    @pytest.mark.security_control("problem-responses")
    def test_the_401_body_never_says_why_verification_failed(self, jwks_url) -> None:
        response = _get(build(jwks_url), _token(key=FORGED))

        assert_that(str(response.json())).does_not_contain("signature")

    def test_missing_scope_is_403_without_a_challenge(self, jwks_url) -> None:
        client = build(jwks_url, Requirement(all_scopes=frozenset({"orders.admin"})))

        response = _get(client, _token())

        assert_that(response.status_code).is_equal_to(403)
        assert_that(response.headers).does_not_contain_key("WWW-Authenticate")


@pytest.fixture
def idp():
    from rn_forge.auth.testing import FakeOidcProvider

    with FakeOidcProvider(user={"sub": "u1"}) as fake:
        yield fake


def _build_for(idp, *, cooldown=30.0, mode="rfc7519"):
    authenticator = OidcAuthenticator.from_issuer(
        idp.issuer, audience=AUDIENCE, cooldown_duration=cooldown, mode=mode
    )
    app = FastAPI()
    register_problem_handlers(app, realm="orders")

    class IdpAccounts(Accounts):
        def lookup(self, issuer, subject):
            return "acct-1" if (issuer, subject) == (idp.issuer, "u1") else None

    guarded = requires(
        bearer_auth(
            authenticator=authenticator, accounts=IdpAccounts(), contexts=Contexts()
        ),
        Requirement(),
    )

    @app.get("/orders")
    def orders(principal: Principal = Depends(guarded)):
        return {"subject": principal.subject}

    return TestClient(app)


class TestAgainstTheFakeProvider:
    @pytest.mark.security_control("token-profiles")
    def test_an_access_token_is_accepted(self, idp) -> None:
        response = _get(_build_for(idp), idp.access_token(profile="rfc7519"))

        assert_that(response.status_code).is_equal_to(200)

    @pytest.mark.security_control("token-profiles")
    def test_an_rfc9068_token_needs_rfc9068_mode(self, idp) -> None:
        token = idp.access_token(profile="rfc7519")

        response = _get(_build_for(idp, mode="rfc9068"), token)

        assert_that(response.status_code).is_equal_to(401)

    @pytest.mark.security_control("token-profiles")
    def test_a_logout_token_is_not_a_bearer_token(self, idp) -> None:
        response = _get(_build_for(idp), idp.logout_token(sub="u1", audience=AUDIENCE))

        assert_that(response.status_code).is_equal_to(401)

    @pytest.mark.security_control("token-profiles")
    def test_an_id_token_is_not_a_bearer_token(self, idp) -> None:
        token = idp.access_token(audience=AUDIENCE, nonce="n-0S6_WzA2Mj")

        response = _get(_build_for(idp), token)

        assert_that(response.status_code).is_equal_to(401)

    @pytest.mark.security_control("token-profiles")
    def test_an_unsigned_token_is_a_401(self, idp) -> None:
        now = int(time.time())
        token = idp.sign(
            {"sub": "u1", "iss": idp.issuer, "aud": AUDIENCE, "exp": now + 300},
            alg="none",
        )

        response = _get(_build_for(idp), token)

        assert_that(response.status_code).is_equal_to(401)
        assert_that(response.json()["detail"]).is_equal_to(AUTH_FAILED_DETAIL)

    @pytest.mark.security_control("jwks-rotation")
    def test_a_token_under_a_rotated_key_is_accepted_after_the_cooldown(
        self, idp
    ) -> None:
        client = _build_for(idp, cooldown=0.0)
        token = {"profile": "rfc7519"}
        assert_that(_get(client, idp.access_token(**token)).status_code).is_equal_to(
            200
        )

        idp.rotate_key()

        assert_that(_get(client, idp.access_token(**token)).status_code).is_equal_to(
            200
        )

    @pytest.mark.security_control("jwks-rotation")
    def test_an_unknown_kid_is_a_401_and_refetches_at_most_once_per_cooldown(
        self, idp
    ) -> None:
        client = _build_for(idp, cooldown=3600.0)
        _get(client, idp.access_token(profile="rfc7519"))
        fetched = idp.fetches("/keys")
        forged = idp.sign(
            {
                "sub": "u1",
                "iss": idp.issuer,
                "aud": AUDIENCE,
                "exp": int(time.time()) + 300,
            },
            kid="nope",
            key=idp.forged_key,
        )

        statuses = [_get(client, forged).status_code for _ in range(3)]

        assert_that(statuses).is_equal_to([401, 401, 401])
        assert_that(idp.fetches("/keys") - fetched).is_less_than_or_equal_to(1)
