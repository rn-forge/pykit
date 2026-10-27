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
from rn_forge.auth import Principal, Requirement  # noqa: E402

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


def _entra(jwks_url):
    # A fresh subclass per test: authenticators are cached per class.
    class Entra(JWKSBearerAuthentication):
        issuer = ISSUER
        audience = "api://orders"
        realm = "orders"

    Entra.jwks_url = jwks_url
    return Entra


def _custom(jwks_url):
    class Custom(_entra(jwks_url)):
        def claims_to_principal(self, claims):
            return Principal(
                subject=f"custom:{claims['sub']}", scopes=frozenset({"orders.read"})
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
            "subject": "u1",
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
        assert body["subject"] == "custom:u1"

    def test_missing_scope_is_403(self, jwks_url) -> None:
        view = _view(
            _entra(jwks_url), Requirement(all_scopes=frozenset({"orders.admin"}))
        )
        response, _ = _get(view, _token())
        assert response.status_code == 403
        assert not response.has_header("WWW-Authenticate")
