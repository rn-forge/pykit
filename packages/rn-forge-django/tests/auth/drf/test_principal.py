from __future__ import annotations

import json

import pytest

rest_framework = pytest.importorskip("rest_framework")

from django.test import override_settings  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from rn_forge.django.auth.drf.principal import (  # noqa: E402
    PrincipalBasicAuthentication,
    PrincipalBearerAuthentication,
    requires,
)
from rn_forge.web import (  # noqa: E402
    PROBLEM_MEDIA_TYPE,
    AuthenticationFailed,
    Principal,
    Requirement,
)

pytestmark = pytest.mark.unit

PROBLEM_HANDLER = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler"
}


class _Tokens:
    """Accepts `good-read` (scope read) and `good` (no scopes)."""

    def __init__(self) -> None:
        self.seen: list = []

    def authenticate(self, *, credentials):
        self.seen.append(credentials)
        if credentials.token == "good-read":
            return Principal(subject="u1", scopes=frozenset({"read"}))
        if credentials.token in ("good", "dTE6cHc="):
            return Principal(subject="u1", mechanism=credentials.scheme.lower())
        raise AuthenticationFailed("signature mismatch for kid k-7")


TOKENS = _Tokens()


class _Bearer(PrincipalBearerAuthentication):
    authenticator = TOKENS
    realm = "orders"


class _Basic(PrincipalBasicAuthentication):
    authenticator = TOKENS


class _PrivateView(APIView):
    authentication_classes = [_Bearer]
    permission_classes = [requires(Requirement(all_scopes=frozenset({"read"})))]

    def get(self, request):
        return Response(
            {"subject": request.user.subject, "type": type(request.user).__name__}
        )


class _BasicView(_PrivateView):
    authentication_classes = [_Basic]
    permission_classes = [requires(Requirement())]


def _get(view=_PrivateView, **headers):
    request = APIRequestFactory().get("/private", headers=headers)
    with override_settings(REST_FRAMEWORK=PROBLEM_HANDLER):
        response = view.as_view()(request)
        if hasattr(response, "render"):  # a problem body is a plain JsonResponse
            response.render()
    return response


class TestBearer:
    def test_valid_token_puts_the_principal_on_request_user(self) -> None:
        response = _get(Authorization="Bearer good-read")
        assert response.status_code == 200
        assert json.loads(response.content) == {"subject": "u1", "type": "Principal"}

    def test_missing_credentials_is_401_problem_with_rfc6750_challenge(self) -> None:
        response = _get()
        assert response.status_code == 401
        assert response["Content-Type"] == PROBLEM_MEDIA_TYPE
        assert response["WWW-Authenticate"] == 'Bearer realm="orders"'

    def test_invalid_token_is_401_without_the_reason(self) -> None:
        response = _get(Authorization="Bearer forged")
        body = json.loads(response.content)
        assert response.status_code == 401
        assert body["detail"] == "Authentication failed."
        assert "kid" not in response.content.decode()
        assert response["WWW-Authenticate"] == 'Bearer realm="orders"'

    def test_empty_token_is_401(self) -> None:
        assert _get(Authorization="Bearer ").status_code == 401

    def test_other_scheme_is_treated_as_no_credentials(self) -> None:
        assert _get(Authorization="Token good-read").status_code == 401

    def test_valid_token_without_scope_is_403_without_a_challenge(self) -> None:
        response = _get(Authorization="Bearer good")
        body = json.loads(response.content)
        assert response.status_code == 403
        assert not response.has_header("WWW-Authenticate")
        assert body["detail"] == "The authenticated principal lacks the required access"

    def test_does_not_inherit_drfs_default_challenge_or_body(self) -> None:
        response = _get()
        body = json.loads(response.content)
        assert set(body) >= {"type", "title", "status", "detail", "instance"}
        assert (
            "Authentication credentials were not provided."
            not in response.content.decode()
        )


class TestBasic:
    def test_basic_produces_the_same_principal_shape(self) -> None:
        response = _get(_BasicView, Authorization="Basic dTE6cHc=")
        assert response.status_code == 200
        assert json.loads(response.content)["type"] == "Principal"
        assert TOKENS.seen[-1].scheme == "Basic"
        assert TOKENS.seen[-1].token == "dTE6cHc="

    def test_basic_401_carries_a_basic_challenge(self) -> None:
        response = _get(_BasicView)
        assert response.status_code == 401
        assert response["WWW-Authenticate"] == "Basic"
