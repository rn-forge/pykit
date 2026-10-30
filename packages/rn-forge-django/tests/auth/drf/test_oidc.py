from __future__ import annotations

import json
import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("rest_framework")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from django.test import override_settings  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from rn_forge.django.auth.drf.oidc import JWKSBearerAuthentication  # noqa: E402
from rn_forge.django.auth.drf.principal import requires  # noqa: E402
from rn_forge.auth import AuthorizationContext, Principal, Requirement  # noqa: E402

pytestmark = pytest.mark.unit

ISSUER = "https://login.example.com/tenant/v2.0"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FORGED = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PROBLEM_HANDLER = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler"
}


JWK = {**RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1"}


def _token(key=KEY, kid="k1", **claims):
    payload = {
        "sub": "u1",
        "iss": ISSUER,
        "aud": "api://orders",
        "exp": int(time.time()) + 300,
        "scp": "orders.read orders.write",
        "roles": ["Reader"],
        "tid": "t-1",
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


class _Accounts:
    def lookup(self, issuer, subject):
        return "acct-1" if subject == "u1" else None


class _Contexts:
    def resolve(self, account_id):
        return AuthorizationContext(
            active=True,
            session_version=0,
            roles=frozenset({"Reader"}),
            attributes={"tenant": "t-1"},
        )


def _entra(jwks_url):
    # A fresh subclass per test: authenticators are cached per class.
    class Entra(JWKSBearerAuthentication):
        issuer = ISSUER
        audience = "api://orders"
        realm = "orders"
        accounts = _Accounts()
        contexts = _Contexts()

    Entra.jwks_url = jwks_url
    return Entra


def _custom(jwks_url):
    class Custom(_entra(jwks_url)):
        def claims_to_principal(self, claims):
            return Principal(
                subject=claims["sub"],
                issuer=claims["iss"],
                scopes=frozenset({"orders.read"}),
            )

    return Custom


def _view(auth_class, requirement=Requirement()):
    class View(APIView):
        authentication_classes = [auth_class]
        permission_classes = [requires(requirement)]

        def get(self, request):
            user = request.user
            return Response(
                {
                    "type": type(user).__name__,
                    "subject": user.subject,
                    "scopes": sorted(user.scopes),
                    "roles": sorted(user.roles),
                    "tenant": user.tenant,
                }
            )

    return View


def _get(view, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with override_settings(REST_FRAMEWORK=PROBLEM_HANDLER):
        response = view.as_view()(APIRequestFactory().get("/orders", headers=headers))
        if hasattr(response, "render"):
            response.render()
    return response, json.loads(response.content)


@pytest.fixture
def jwks_url(serve_jwks):
    return serve_jwks([JWK])


class TestJWKSBearerAuthentication:
    def test_valid_token_lands_a_principal_on_request_user(self, jwks_url) -> None:
        response, body = _get(_view(_entra(jwks_url)), _token())
        assert response.status_code == 200
        assert body == {
            "type": "Principal",
            "subject": "acct-1",
            "scopes": ["orders.read", "orders.write"],
            "roles": ["Reader"],
            "tenant": "t-1",
        }

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
        response, body = _get(_view(_entra(jwks_url)), token)
        assert response.status_code == 401
        assert body["detail"] == "Authentication failed."
        assert response["WWW-Authenticate"] == 'Bearer realm="orders"'

    def test_missing_header_is_401(self, jwks_url) -> None:
        response, _ = _get(_view(_entra(jwks_url)))
        assert response.status_code == 401

    def test_claims_to_principal_override_is_used(self, jwks_url) -> None:
        response, body = _get(_view(_custom(jwks_url)), _token())
        assert response.status_code == 200
        assert body["subject"] == "acct-1"

    def test_missing_scope_is_403(self, jwks_url) -> None:
        view = _view(
            _entra(jwks_url), Requirement(all_scopes=frozenset({"orders.admin"}))
        )
        response, _ = _get(view, _token())
        assert response.status_code == 403
        assert not response.has_header("WWW-Authenticate")


class TestUnlinkedSubject:
    def test_token_without_a_linked_account_is_401(self, jwks_url) -> None:
        response, body = _get(_view(_entra(jwks_url)), _token(sub="stranger"))
        assert response.status_code == 401
        assert body["detail"] == "Authentication failed."


@pytest.fixture
def idp():
    from rn_forge.auth.testing import FakeOidcProvider

    with FakeOidcProvider(user={"sub": "u1"}) as fake:
        yield fake


def _for(idp, *, cooldown=30.0):
    class Fake(_entra(idp.jwks_url)):
        issuer = idp.issuer
        cooldown_duration = cooldown

    return _view(Fake)


class TestAgainstTheFakeProvider:
    @pytest.mark.security_control("token-profiles")
    def test_an_access_token_is_accepted(self, idp) -> None:
        response, _ = _get(
            _for(idp), idp.access_token(audience="api://orders", profile="rfc7519")
        )

        assert response.status_code == 200

    @pytest.mark.security_control("token-profiles")
    def test_a_logout_token_is_not_a_bearer_token(self, idp) -> None:
        response, _ = _get(
            _for(idp), idp.logout_token(sub="u1", audience="api://orders")
        )

        assert response.status_code == 401

    @pytest.mark.security_control("token-profiles")
    def test_an_id_token_is_not_a_bearer_token(self, idp) -> None:
        token = idp.access_token(audience="api://orders", nonce="n-0S6_WzA2Mj")

        response, _ = _get(_for(idp), token)

        assert response.status_code == 401

    @pytest.mark.security_control("token-profiles")
    def test_an_unsigned_token_is_a_401(self, idp) -> None:
        token = idp.sign(
            {
                "sub": "u1",
                "iss": idp.issuer,
                "aud": "api://orders",
                "exp": int(time.time()) + 300,
            },
            alg="none",
        )

        response, body = _get(_for(idp), token)

        assert response.status_code == 401
        assert body["detail"] == "Authentication failed."

    @pytest.mark.security_control("jwks-rotation")
    def test_a_token_under_a_rotated_key_is_accepted_after_the_cooldown(
        self, idp
    ) -> None:
        view = _for(idp, cooldown=0.0)
        mint = lambda: idp.access_token(audience="api://orders", profile="rfc7519")  # noqa: E731
        assert _get(view, mint())[0].status_code == 200

        idp.rotate_key()

        assert _get(view, mint())[0].status_code == 200

    @pytest.mark.security_control("jwks-rotation")
    def test_an_unknown_kid_is_a_401_and_refetches_at_most_once_per_cooldown(
        self, idp
    ) -> None:
        view = _for(idp, cooldown=3600.0)
        _get(view, idp.access_token(audience="api://orders", profile="rfc7519"))
        fetched = idp.fetches("/keys")
        forged = idp.sign(
            {
                "sub": "u1",
                "iss": idp.issuer,
                "aud": "api://orders",
                "exp": int(time.time()) + 300,
            },
            kid="nope",
            key=idp.forged_key,
        )

        statuses = [_get(view, forged)[0].status_code for _ in range(3)]

        assert statuses == [401, 401, 401]
        assert idp.fetches("/keys") - fetched <= 1
