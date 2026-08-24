"""DRF-facing authentication helpers and login views for rn-forge auth."""

from __future__ import annotations

from typing import Any, cast

from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.commons.logging import AppLogger
from rn_forge.django._typing import DjangoAuthProtocol
from rn_forge.django.drf import RequestUtils
from rn_forge.django.drf.views.base import BaseAPIView
from rn_forge.django.auth.payload import LoginPayload

from django.contrib import auth as django_auth
from django.http import HttpResponseBase

__all__ = [
    "BaseLoginAPIView",
    "BaseLoginViewMixin",
    "LogoutAPIView",
]

_LOGGER = AppLogger.get_logger(__name__)
_DJANGO_AUTH = cast(DjangoAuthProtocol, django_auth)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class BaseLoginViewMixin[_UserT]:
    """Session-oriented login/logout helpers for DRF views.

    This mixin is intentionally token-agnostic. Subclasses can override
    :meth:`build_login_response` to add JWTs or provider-specific metadata.
    """

    auto_create_user = False
    user_lookup_param = "email"
    user_lookup_field = "email"

    def build_login_response(self, login_payload: LoginPayload) -> dict[str, Any]:
        """Return the response payload for a successful login."""
        raise NotImplementedError(
            f"build_login_response not implemented: {type(self).__name__}"
        )

    def build_login_payload(self, request: Request) -> LoginPayload:
        """Return the normalized login payload for this login request."""
        raise NotImplementedError(
            f"build_login_payload not implemented: {type(self).__name__}"
        )

    def complete_login(
        self,
        request: Request,
        login_payload: LoginPayload,
    ) -> HttpResponseBase:
        """Persist the Django session and return the final login response."""
        _DJANGO_AUTH.login(
            RequestUtils.get_django_request(request),
            cast(Any, login_payload.user),
        )
        _LOGGER.success(
            "Login completed: user={}",
            getattr(login_payload.user, "email", login_payload.user),
        )
        return Response(
            self.build_login_response(login_payload),
            status=status.HTTP_200_OK,
        )

    def login(self, request: Request) -> HttpResponseBase:
        """Authenticate a user into the Django session and return an HTTP response."""
        _LOGGER.notice("Login started: view={}", type(self).__name__)
        login_payload = self.build_login_payload(request)
        return self.complete_login(request, login_payload)

    @staticmethod
    def logout(request: Request) -> Response:
        """Log out the current session user."""
        _DJANGO_AUTH.logout(RequestUtils.get_django_request(request))
        return Response({"authenticated": False}, status=status.HTTP_200_OK)


class BaseLoginAPIView(BaseAPIView):
    """Common API view base for login/logout endpoints."""

    authentication_classes: list[type[BaseAuthentication]] = []
    permission_classes = [AllowAny]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponseBase:
        """Dispatch ``POST`` requests to :meth:`login`."""
        del args, kwargs
        login = getattr(self, "login")
        return login(request)


@_LOGGER.audit_class()
class LogoutAPIView(BaseAPIView):
    """Common API view for logging out the current session."""

    authentication_classes: list[type[BaseAuthentication]] = []
    permission_classes = [AllowAny]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Dispatch ``POST`` logout requests."""
        del args, kwargs
        return BaseLoginViewMixin.logout(request)
