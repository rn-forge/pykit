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
    def test_verification_failures_are_a_generic_401(self, jwks_url, token) -> None:
        response = _get(build(jwks_url), token)

        assert_that(response.status_code).is_equal_to(401)
        assert_that(response.json()["detail"]).is_equal_to(AUTH_FAILED_DETAIL)
        assert_that(response.headers["WWW-Authenticate"]).is_equal_to(
            'Bearer realm="orders"'
        )

    def test_the_401_body_never_says_why_verification_failed(self, jwks_url) -> None:
        response = _get(build(jwks_url), _token(key=FORGED))

        assert_that(str(response.json())).does_not_contain("signature")

    def test_missing_scope_is_403_without_a_challenge(self, jwks_url) -> None:
        client = build(jwks_url, Requirement(all_scopes=frozenset({"orders.admin"})))

        response = _get(client, _token())

        assert_that(response.status_code).is_equal_to(403)
        assert_that(response.headers).does_not_contain_key("WWW-Authenticate")
