from __future__ import annotations

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from rest_framework.request import Request  # noqa: E402
from rest_framework.parsers import JSONParser  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.auth.credentials import BaseCredentials  # noqa: E402
from rn_forge.django.auth.basic.views import BasicLoginViewMixin  # noqa: E402
from rn_forge.django.auth.drf.authentication import (  # noqa: E402
    BaseLoginViewMixin,
)
from rn_forge.django.auth.drf.mixins import AuthorizationViewMixin  # noqa: E402
from rn_forge.django.auth.drf.permissions import (  # noqa: E402
    AuthorizationPermission,
)
from rn_forge.django.auth.payload import LoginPayload  # noqa: E402
from rn_forge.django.auth.drf.views import (  # noqa: E402
    AuthorizedAPIView,
    PermissionKeyViewMixin,
)
from rn_forge.django.drf.views import AuditFieldsViewMixin  # noqa: E402
from rn_forge.django.models import BaseModel  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeUser:
    def __init__(
        self,
        *,
        authenticated: bool = True,
        staff: bool = False,
        email: str = "user@example.com",
        permissions: set[str] | None = None,
    ) -> None:
        self.is_authenticated = authenticated
        self.is_staff = staff
        self.email = email
        self._permissions = permissions or set()

    def has_permission(self, permission: str) -> bool:
        return permission in self._permissions


class _FakeCredentials(BaseCredentials):
    pass


class _PermissionView(AuthorizationViewMixin):
    permission_key = "inventory.read"

    def __init__(self, user: _FakeUser, credentials: BaseCredentials) -> None:
        self.request = type("Request", (), {"user": user, "auth": credentials})()


class _ObjectPermissionView(AuthorizationViewMixin):
    def __init__(
        self,
        user: _FakeUser,
        credentials: BaseCredentials,
        action: str = "update",
    ) -> None:
        self.request = type("Request", (), {"user": user, "auth": credentials})()
        self.action = action

    def validate_object_permissions(
        self, obj: BaseModel | dict[str, object]
    ) -> str | None:
        return "denied"


class _PermissionKeyView(PermissionKeyViewMixin):
    permission_key = "inventory"

    def __init__(self, action: str, method: str = "GET") -> None:
        self.action = action
        self.request = APIRequestFactory().generic(method, "/")


class _AuditFieldsView(AuditFieldsViewMixin):
    def __init__(self, user: _FakeUser) -> None:
        self.request = type("Request", (), {"user": user})()


class _AuthorizedView(AuthorizedAPIView):
    permission_key = "inventory"

    def __init__(self, user: _FakeUser, credentials: BaseCredentials) -> None:
        self.request = APIRequestFactory().get("/")
        self.request.user = user
        self.request.auth = credentials


class _AuthView(BaseLoginViewMixin[_FakeUser]):
    def __init__(self, user: _FakeUser | None = None) -> None:
        self._user = user or _FakeUser()

    def build_login_payload(self, request: Request) -> LoginPayload:
        del request
        return LoginPayload(user=_FakeUser(email="user@example.com"))

    def build_login_response(self, login_payload: LoginPayload) -> dict[str, object]:
        user = login_payload.user
        return {"authenticated": True, "email": user.email}


class _BasicAuthView(BasicLoginViewMixin[_FakeUser]):
    pass


class TestBaseCredentials:
    def test_has_permission_uses_wrapped_user(self) -> None:
        credentials = _FakeCredentials(
            _FakeUser(permissions={"inventory.read"}),
            auth={"token": "x"},
        )

        assert credentials.has_permission("inventory.read") is True

    def test_has_any_permission_checks_sequence(self) -> None:
        credentials = _FakeCredentials(
            _FakeUser(permissions={"inventory.read"}),
            auth={"token": "x"},
        )

        assert (
            credentials.has_any_permission(["inventory.write", "inventory.read"])
            is True
        )


class TestAuthorizationPermission:
    def test_allows_staff(self) -> None:
        request = APIRequestFactory().get("/")
        request.user = _FakeUser(staff=True)
        request.auth = _FakeCredentials(request.user, {})
        permission = AuthorizationPermission()

        assert permission.has_permission(request, object()) is True

    def test_denies_unauthenticated(self) -> None:
        request = APIRequestFactory().get("/")
        request.user = _FakeUser(authenticated=False)
        request.auth = None
        permission = AuthorizationPermission()

        assert permission.has_permission(request, object()) is False
        assert permission.code == "UnauthenticatedRequest"

    def test_uses_view_permission_key(self) -> None:
        request = APIRequestFactory().get("/")
        user = _FakeUser(permissions={"inventory.read"})
        credentials = _FakeCredentials(user, {})
        request.user = user
        request.auth = credentials
        view = _PermissionView(user, credentials)
        permission = AuthorizationPermission()

        assert permission.has_permission(request, view) is True

    def test_object_permission_uses_view_hook(self) -> None:
        request = APIRequestFactory().patch("/")
        user = _FakeUser()
        credentials = _FakeCredentials(user, {})
        request.user = user
        request.auth = credentials
        view = _ObjectPermissionView(user, credentials)
        permission = AuthorizationPermission()

        assert permission.has_object_permission(request, view, {}) is False
        assert permission.code == "ForbiddenRequest"

    def test_denies_authenticated_request_without_rn_forge_credentials(self) -> None:
        request = APIRequestFactory().get("/")
        request.user = _FakeUser()
        request.auth = {"token": "raw"}
        permission = AuthorizationPermission()

        assert permission.has_permission(request, object()) is False
        assert permission.code == "InvalidCredentials"


class TestPermissionKeyViewMixin:
    def test_list_action_maps_to_list_permission(self) -> None:
        view = _PermissionKeyView("list")
        assert view.get_permission_key() == "inventory.list"

    def test_partial_update_maps_to_update_permission(self) -> None:
        view = _PermissionKeyView("partial_update", method="PATCH")
        assert view.get_permission_key() == "inventory.update"

    def test_unknown_action_falls_back_to_base_permission(self) -> None:
        view = _PermissionKeyView("custom")
        assert view.get_permission_key() == "inventory"


class TestAuditFieldsViewMixin:
    def test_prepares_create_audit_fields(self) -> None:
        data: dict[str, object] = {}
        prepared = _AuditFieldsView(
            _FakeUser(email="auditor@example.com")
        ).prepare_create_data(data)

        assert prepared == {
            "created_by": "auditor@example.com",
            "updated_by": "auditor@example.com",
        }

    def test_prepares_update_audit_fields(self) -> None:
        data: dict[str, object] = {"created_by": "original@example.com"}
        prepared = _AuditFieldsView(
            _FakeUser(email="auditor@example.com")
        ).prepare_update_data(data)

        assert prepared == {"updated_by": "auditor@example.com"}


class TestAuthorizedAPIView:
    def test_permission_classes_default_to_authorization_permission(self) -> None:
        assert (
            AuthorizedAPIView.permission_classes[0].__name__
            == "AuthorizationPermission"
        )

    def test_inherits_permission_key_logic(self) -> None:
        user = _FakeUser()
        view = _AuthorizedView(user, _FakeCredentials(user, {}))
        view.action = "retrieve"
        assert view.get_permission_key() == "inventory.read"

    def test_exposes_credentials(self) -> None:
        user = _FakeUser()
        credentials = _FakeCredentials(user, {})
        view = _AuthorizedView(user, credentials)

        assert view.credentials is credentials


class TestBaseLoginViewMixin:
    def test_login_uses_lookup_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        request = Request(
            APIRequestFactory().post("/", {"email": "user@example.com"}, format="json"),
            parsers=[JSONParser()],
        )
        calls: list[str] = []

        monkeypatch.setattr(
            django.contrib.auth,
            "login",
            lambda _request, user: calls.append(user.email),
        )

        response = _AuthView().login(request)

        assert response.status_code == 200
        assert response.data == {"authenticated": True, "email": "user@example.com"}
        assert calls == ["user@example.com"]


class TestBasicLoginViewMixin:
    def test_login_uses_django_authenticate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        request = Request(
            APIRequestFactory().post(
                "/",
                {"username": "user", "password": "secret"},
                format="json",
            ),
            parsers=[JSONParser()],
        )
        calls: list[str] = []

        monkeypatch.setattr(
            django.contrib.auth,
            "authenticate",
            lambda _request, username, password: (
                _FakeUser(email=f"{username}@example.com")
                if password == "secret"
                else None
            ),
        )
        monkeypatch.setattr(
            "rn_forge.django.auth.jwt.mixins.JWTUtils.build_login_exchange_token",
            lambda _user, **_kwargs: "exchange-token",
        )
        monkeypatch.setattr(
            django.contrib.auth,
            "login",
            lambda _request, user: calls.append(user.email),
        )

        response = _BasicAuthView().login(request)

        assert response.status_code == 200
        assert response.data == {"exchange_token": "exchange-token"}
        assert calls == []
