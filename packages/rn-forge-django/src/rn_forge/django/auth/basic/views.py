"""Optional basic login views for rn-forge auth."""

from __future__ import annotations

from typing import Generic, TypeVar, cast

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rn_forge.commons.logging import AppLogger
from rn_forge.django._typing import DjangoAuthProtocol
from rn_forge.django.auth.drf.authentication import BaseLoginAPIView
from rn_forge.django.auth.jwt.mixins import LoginExchangeViewMixin
from rn_forge.django.auth.payload import LoginPayload
from rn_forge.django.drf import RequestUtils

from django.contrib import auth as django_auth

_UserT = TypeVar("_UserT")

__all__ = [
    "BasicLoginViewMixin",
    "BasicLoginAPIView",
]

_LOGGER = AppLogger.get_logger(__name__)
_DJANGO_AUTH = cast(DjangoAuthProtocol, django_auth)


class BasicLoginViewMixin(LoginExchangeViewMixin[_UserT], Generic[_UserT]):
    """Username/password login flow backed by Django authentication."""

    username_param = "username"
    password_param = "password"

    def get_basic_username(self, request: Request) -> str:
        """Return the incoming username from request data."""
        return str(RequestUtils.get_value(request, self.username_param) or "").strip()

    def get_basic_password(self, request: Request) -> str:
        """Return the incoming password from request data."""
        return str(RequestUtils.get_value(request, self.password_param) or "")

    def authenticate_basic_user(self, request: Request) -> _UserT:
        """Authenticate and return the target Django user."""
        username = self.get_basic_username(request)
        password = self.get_basic_password(request)
        user = cast(
            _UserT | None,
            _DJANGO_AUTH.authenticate(
                RequestUtils.get_django_request(request),
                username=username,
                password=password,
            ),
        )
        if user is None:
            raise AuthenticationFailed("Invalid username or password")
        return user

    def build_login_payload(self, request: Request) -> LoginPayload:
        """Return the normalized login payload for this request."""
        _LOGGER.notice(
            "Basic login started: username={}", self.get_basic_username(request)
        )
        return LoginPayload(user=self.authenticate_basic_user(request))


@_LOGGER.audit_class(include_inherited=True)
class BasicLoginAPIView(
    BasicLoginViewMixin[_UserT],
    BaseLoginAPIView,
    Generic[_UserT],
):
    """Username/password login API view that returns an exchange token."""
