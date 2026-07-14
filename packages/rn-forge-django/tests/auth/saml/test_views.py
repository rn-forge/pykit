from __future__ import annotations

import pytest

pytest.importorskip("onelogin.saml2.auth")

from rest_framework.parsers import JSONParser  # noqa: E402
from rest_framework.request import Request  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from django.http import HttpResponseRedirect  # noqa: E402

from rn_forge.django.auth.saml.views import SAMLLoginViewMixin  # noqa: E402
from rn_forge.django.auth.jwt.utils import JWTUtils  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeUser:
    email = "user@example.com"


class _FakeSAMLAuth:
    last_return_to = None

    def __init__(self) -> None:
        self.return_to = None

    def login(self, return_to=None):
        self.return_to = return_to
        type(self).last_return_to = return_to
        return "/saml/provider"

    def process_response(self) -> None:
        return None

    def get_errors(self) -> list[str]:
        return []

    def is_authenticated(self) -> bool:
        return True


class _SAMLView(SAMLLoginViewMixin[_FakeUser]):
    def build_saml_request_data(self, request):
        del request
        return {"https": "on"}

    def get_saml_user_lookup(self, request, auth):
        del request, auth
        return {"email": "user@example.com"}

    def get_user(self, user_lookup: dict[str, str]) -> _FakeUser:
        assert user_lookup["email"] == "user@example.com"
        return _FakeUser()

    def create_user_for_login(self, request, user_lookup):
        del request, user_lookup
        raise AssertionError("create_user_for_login should not be called")

    def get_saml_auth(self, request):
        del request
        return _FakeSAMLAuth()

    def get_saml_login_auth(self, request):
        del request
        return _FakeSAMLAuth()


class _RedirectSAMLView(_SAMLView):
    def build_saml_login_response(self, request, auth):
        del request, auth
        return HttpResponseRedirect("/saml/provider")


class TestSAMLLoginViewMixin:
    def test_get_redirects_to_provider(
        self,
    ) -> None:
        request = Request(
            APIRequestFactory().get("/?return_to=/dashboard"),
            parsers=[JSONParser()],
        )

        response = _SAMLView().get(request)

        assert response.status_code == 302
        assert response["Location"] == "/saml/provider"
        assert _FakeSAMLAuth.last_return_to == "/dashboard"

    def test_get_can_be_overridden_to_redirect(
        self,
    ) -> None:
        request = Request(APIRequestFactory().get("/"), parsers=[JSONParser()])

        response = _RedirectSAMLView().get(request)

        assert response.status_code == 302
        assert response["Location"] == "/saml/provider"

    def test_login_uses_processed_saml_user(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        request = Request(
            APIRequestFactory().get("/?return_to=/dashboard"),
            parsers=[JSONParser()],
        )
        calls: list[str] = []

        monkeypatch.setattr(
            "django.contrib.auth.login",
            lambda _request, user: calls.append(user.email),
        )
        monkeypatch.setattr(
            JWTUtils,
            "build_login_exchange_token",
            lambda _user, **_kwargs: "exchange-token",
        )

        response = _SAMLView().login(request)

        assert response.status_code == 302
        assert response["Location"] == "/dashboard#exchange_token=exchange-token"
        assert calls == []
