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
from rn_forge.web import Principal, Requirement  # noqa: E402

pytestmark = pytest.mark.unit

ISSUER = "https://login.example.com/tenant/v2.0"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FORGED = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PROBLEM_HANDLER = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler"
}


class _IdP:
    def __init__(self):
        self.calls = 0

    def __call__(self, url):
        self.calls += 1
        jwk = {**RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1"}
        return {"keys": [jwk]}


IDP = _IdP()


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


class _Entra(JWKSBearerAuthentication):
    jwks_url = "https://login.example.com/tenant/discovery/v2.0/keys"
    issuer = ISSUER
    audience = "api://orders"
    realm = "orders"
    fetch = staticmethod(IDP)


class _Custom(_Entra):
    def claims_to_principal(self, claims):
        return Principal(
            subject=f"custom:{claims['sub']}", scopes=frozenset({"orders.read"})
        )


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


class TestJWKSBearerAuthentication:
    def test_valid_token_lands_a_principal_on_request_user(self) -> None:
        response, body = _get(_view(_Entra), _token())
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
    def test_verification_failures_are_a_generic_401(self, token) -> None:
        response, body = _get(_view(_Entra), token)
        assert response.status_code == 401
        assert body["detail"] == "Authentication failed."
        assert response["WWW-Authenticate"] == 'Bearer realm="orders"'

    def test_missing_header_is_401(self) -> None:
        response, _ = _get(_view(_Entra))
        assert response.status_code == 401

    def test_key_set_is_cached_across_requests(self) -> None:
        before = IDP.calls
        for _ in range(3):
            _get(_view(_Entra), _token())
        assert IDP.calls - before <= 1

    def test_claims_to_principal_override_is_used(self) -> None:
        response, body = _get(_view(_Custom), _token())
        assert response.status_code == 200
        assert body["subject"] == "custom:u1"

    def test_missing_scope_is_403(self) -> None:
        view = _view(_Entra, Requirement(all_scopes=frozenset({"orders.admin"})))
        response, _ = _get(view, _token())
        assert response.status_code == 403
        assert not response.has_header("WWW-Authenticate")
