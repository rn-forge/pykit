from __future__ import annotations

import pytest

pytest.importorskip("rest_framework_simplejwt")

from rest_framework.request import Request  # noqa: E402
from rest_framework.parsers import JSONParser  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from rest_framework.exceptions import ValidationError  # noqa: E402

from rn_forge.django.auth.jwt.authentication import (  # noqa: E402
    JWTAuthentication,
    _get_simplejwt_authentication_class,
)
from rn_forge.django.auth.jwt.credentials import JWTCredentials  # noqa: E402
from rn_forge.django.auth.jwt.mixins import (  # noqa: E402
    JWTAuthenticationViewMixin,
    LoginExchangeViewMixin,
)
from rn_forge.django.auth.payload import LoginPayload  # noqa: E402
from rn_forge.django.auth.jwt.views import UserTokenView  # noqa: E402
from rn_forge.django.auth.jwt.utils import JWTUtils  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeToken(dict):
    @property
    def access_token(self) -> str:
        return "access-token"

    def __str__(self) -> str:
        return "refresh-token"


class _FakeUser:
    email = "user@example.com"
    first_name = "Jane"
    last_name = "Doe"
    username = "jdoe"

    def __init__(self) -> None:
        self._groups = self._GroupManager()

    class _GroupManager:
        def values_list(self, *_args, **_kwargs):
            return ["inventory-admin"]

    @property
    def groups(self):
        return self._groups

    def get_all_permissions(self) -> set[str]:
        return {"inventory.read"}


class _JWTView(JWTAuthenticationViewMixin[_FakeUser]):
    def build_jwt_claims(self, login_payload: LoginPayload) -> dict[str, object]:
        claims = super().build_jwt_claims(login_payload)
        claims["email"] = login_payload.user.email
        return claims


class _JWTDefaultView(JWTAuthenticationViewMixin[_FakeUser]):
    pass


class _ExchangeView(LoginExchangeViewMixin[_FakeUser]):
    pass


class _UserTokenView(UserTokenView[_FakeUser]):
    def get_login_exchange_user(self, exchange_payload):
        del exchange_payload
        return _FakeUser()


class TestJWTUtils:
    def test_build_token_pair_with_claims(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FakeAccessToken(dict):
            def __str__(self) -> str:
                return "access-token"

        class _FakeToken(dict):
            def __init__(self) -> None:
                super().__init__()
                self._access_token = _FakeAccessToken()

            @property
            def access_token(self) -> _FakeAccessToken:
                return self._access_token

            def __str__(self) -> str:
                return "refresh-token"

        token = _FakeToken()
        monkeypatch.setattr(JWTUtils, "create_refresh_token", lambda _user: token)

        payload = JWTUtils.build_token_pair_with_claims(
            _FakeUser(),
            email="user@example.com",
        )

        assert payload == {"refresh": "refresh-token", "access": "access-token"}
        assert token["email"] == "user@example.com"
        assert token["rn_forge_token_type"] == "refresh"
        assert token.access_token["email"] == "user@example.com"
        assert token.access_token["rn_forge_token_type"] == "access"

    def test_validate_login_exchange_token_rejects_wrong_type(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import sys
        import types

        token_module = types.ModuleType("rest_framework_simplejwt.tokens")

        class _FakeRefreshToken(dict):
            def __init__(self, token: str) -> None:
                del token
                super().__init__()

            def get(self, key, default=None):
                del default
                if key == "rn_forge_token_type":
                    return "wrong-type"
                return None

            @property
            def payload(self):
                return {}

        token_module.RefreshToken = _FakeRefreshToken
        package_module = types.ModuleType("rest_framework_simplejwt")
        package_module.__path__ = []  # type: ignore[attr-defined]
        package_module.tokens = token_module
        monkeypatch.setitem(
            sys.modules,
            "rest_framework_simplejwt",
            package_module,
        )
        monkeypatch.setitem(
            sys.modules, "rest_framework_simplejwt.tokens", token_module
        )

        with pytest.raises(ValueError):
            JWTUtils.validate_login_exchange_token("exchange-token")

    def test_validate_login_exchange_token_rejects_invalid_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import sys
        import types

        token_module = types.ModuleType("rest_framework_simplejwt.tokens")

        class _InvalidRefreshToken:
            def __init__(self, token: str) -> None:
                del token
                raise RuntimeError("expired")

        token_module.RefreshToken = _InvalidRefreshToken
        package_module = types.ModuleType("rest_framework_simplejwt")
        package_module.__path__ = []  # type: ignore[attr-defined]
        package_module.tokens = token_module
        monkeypatch.setitem(
            sys.modules,
            "rest_framework_simplejwt",
            package_module,
        )
        monkeypatch.setitem(
            sys.modules, "rest_framework_simplejwt.tokens", token_module
        )

        with pytest.raises(ValueError):
            JWTUtils.validate_login_exchange_token("bad-token")


class TestLoginExchangeViewMixin:
    def test_build_login_response_returns_exchange_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            JWTUtils,
            "build_login_exchange_token",
            lambda _user, **_kwargs: "exchange-token",
        )

        payload = _ExchangeView().build_login_response(LoginPayload(user=_FakeUser()))

        assert payload == {"exchange_token": "exchange-token"}


class TestJWTAuthenticationViewMixin:
    def test_build_login_response_includes_tokens_and_user(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            JWTUtils,
            "build_token_pair_with_claims",
            lambda _user, **claims: {
                "refresh": "refresh-token",
                "access": "access-token",
                **claims,
            },
        )

        payload = _JWTView().build_login_response(LoginPayload(user=_FakeUser()))

        assert payload == {
            "authenticated": True,
            "refresh": "refresh-token",
            "access": "access-token",
            "email": "user@example.com",
            "name": "Jane Doe",
            "given_name": "Jane",
            "family_name": "Doe",
            "permissions": ("inventory.read",),
            "roles": ("inventory-admin",),
        }

    def test_build_login_response_uses_user_permissions_when_claims_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            JWTUtils,
            "build_token_pair_with_claims",
            lambda _user, **claims: {
                "refresh": "refresh-token",
                "access": "access-token",
                **claims,
            },
        )

        payload = _JWTDefaultView().build_login_response(LoginPayload(user=_FakeUser()))

        assert payload["email"] == "user@example.com"
        assert payload["name"] == "Jane Doe"
        assert payload["given_name"] == "Jane"
        assert payload["family_name"] == "Doe"
        assert payload["permissions"] == ("inventory.read",)
        assert payload["roles"] == ("inventory-admin",)


class TestUserTokenView:
    def test_exchanges_token_for_final_jwt(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        request = Request(
            APIRequestFactory().post(
                "/", {"exchange_token": "exchange-token"}, format="json"
            ),
            parsers=[JSONParser()],
        )
        monkeypatch.setattr(
            JWTUtils,
            "validate_login_exchange_token",
            lambda token: (
                {
                    "rn_forge_token_type": "login_exchange",
                    "email": "user@example.com",
                    "permissions": ("inventory.read",),
                    "roles": ("inventory-admin",),
                }
                if token == "exchange-token"
                else {}
            ),
        )
        monkeypatch.setattr(
            JWTUtils,
            "build_token_pair_with_claims",
            lambda _user, **claims: {
                "refresh": "refresh-token",
                "access": "access-token",
                **claims,
            },
        )

        response = _UserTokenView().post(request)

        assert response.status_code == 200
        assert response.data == {
            "authenticated": True,
            "refresh": "refresh-token",
            "access": "access-token",
            "email": "user@example.com",
            "name": "Jane Doe",
            "given_name": "Jane",
            "family_name": "Doe",
            "permissions": ("inventory.read",),
            "roles": ("inventory-admin",),
        }

    def test_rejects_invalid_exchange_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        request = Request(
            APIRequestFactory().post(
                "/", {"exchange_token": "bad-token"}, format="json"
            ),
            parsers=[JSONParser()],
        )
        monkeypatch.setattr(
            JWTUtils,
            "validate_login_exchange_token",
            lambda _token: (_ for _ in ()).throw(
                ValueError("Invalid login exchange token")
            ),
        )

        with pytest.raises(ValidationError):
            _UserTokenView().post(request)


class TestJWTCredentials:
    def test_permissions_come_from_payload(self) -> None:
        credentials = JWTCredentials(
            _FakeUser(),
            {"permissions": ["inventory.read"], "email": "token@example.com"},
        )

        assert credentials.email == "token@example.com"
        assert credentials.has_permission("inventory.read") is True


class TestJWTAuthentication:
    def test_authenticate_wraps_validated_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        request = Request(APIRequestFactory().get("/"), parsers=[JSONParser()])
        user = _FakeUser()
        token = {"permissions": ["inventory.read"]}

        class _FakeSimpleJWTAuthentication:
            def authenticate(self, _request):
                return user, token

        monkeypatch.setattr(
            "rn_forge.django.auth.jwt.authentication._get_simplejwt_authentication_class",
            lambda: _FakeSimpleJWTAuthentication,
        )

        result = JWTAuthentication().authenticate(request)

        assert result is not None
        auth_user, credentials = result
        assert auth_user is user
        assert isinstance(credentials, JWTCredentials)
        assert credentials.has_permission("inventory.read") is True
