"""SimpleJWT mixins layered on top of rn-forge-django DRF auth helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any, Generic, TypeVar, cast

from rest_framework import status
from rest_framework.request import Request
from django.http import HttpResponseBase
from rest_framework.response import Response
from rn_forge.commons.logging import AppLogger

from rn_forge.django.auth.drf.authentication import BaseLoginViewMixin
from rn_forge.django.auth.payload import LoginPayload
from rn_forge.django.auth.jwt.utils import JWTUtils

_UserT = TypeVar("_UserT")

__all__ = [
    "LoginExchangeViewMixin",
    "JWTAuthenticationViewMixin",
]

_LOGGER = AppLogger.get_logger(__name__)


class LoginExchangeViewMixin(
    BaseLoginViewMixin[_UserT],
    Generic[_UserT],
):
    """Login view mixin that returns a short-lived exchange JWT."""

    login_exchange_token_type = "login_exchange"
    login_exchange_lifetime = timedelta(minutes=5)

    def build_login_exchange_token(self, login_payload: LoginPayload) -> str:
        """Return the short-lived exchange token for the login handoff."""
        return JWTUtils.build_login_exchange_token(
            login_payload.user,
            token_type=self.login_exchange_token_type,
            lifetime=self.login_exchange_lifetime,
        )

    def build_login_response(self, login_payload: LoginPayload) -> dict[str, Any]:
        """Return the default login-exchange payload for *user*."""
        return {"exchange_token": self.build_login_exchange_token(login_payload)}

    def complete_login(
        self,
        request: Request,
        login_payload: LoginPayload,
    ) -> HttpResponseBase:
        """Return the exchange token without creating a Django session."""
        del request
        _LOGGER.success(
            "Login exchange completed: user={}",
            getattr(login_payload.user, "email", login_payload.user),
        )
        return Response(
            self.build_login_response(login_payload),
            status=status.HTTP_200_OK,
        )


class JWTAuthenticationViewMixin(
    BaseLoginViewMixin[_UserT],
    Generic[_UserT],
):
    """Authentication mixin that returns SimpleJWT access/refresh tokens."""

    def get_user_roles(self, login_payload: LoginPayload) -> tuple[str, ...]:
        """Return role names from the wrapped user when available."""
        groups = getattr(login_payload.user, "groups", None)
        values_list = getattr(groups, "values_list", None)
        if not callable(values_list):
            return ()

        try:
            role_names = values_list("name", flat=True)
        except Exception:  # pragma: no cover - role manager shape is app-specific
            return ()

        return tuple(
            sorted(str(role) for role in cast(Sequence[object], role_names) if role)
        )

    def get_user_permissions(self, login_payload: LoginPayload) -> tuple[str, ...]:
        """Return effective permission keys from the wrapped user when available."""
        get_all_permissions = getattr(login_payload.user, "get_all_permissions", None)
        if not callable(get_all_permissions):
            return ()

        return tuple(
            sorted(
                str(permission)
                for permission in cast(Sequence[object], get_all_permissions())
                if permission
            )
        )

    def build_jwt_claims(
        self,
        login_payload: LoginPayload,
    ) -> dict[str, object]:
        """Return flat JWT claims to apply to the refresh/access token pair."""
        claims: dict[str, object] = {}

        user = login_payload.user
        user_id = getattr(user, "id", getattr(user, "pk", None))
        if user_id not in {None, ""}:
            claims.setdefault("sub", str(user_id))

        get_full_name = getattr(user, "get_full_name", None)
        if callable(get_full_name):
            full_name = get_full_name()
            if full_name not in {None, ""}:
                claims.setdefault("name", str(full_name))

        if claims.get("name") in {None, ""}:
            first_name = getattr(user, "first_name", None)
            last_name = getattr(user, "last_name", None)
            if first_name not in {None, ""} or last_name not in {None, ""}:
                full_name = " ".join(
                    part
                    for part in (str(first_name or ""), str(last_name or ""))
                    if part
                ).strip()
                if full_name:
                    claims["name"] = full_name

        if claims.get("name") in {None, ""}:
            username = getattr(user, "username", None)
            if username not in {None, ""}:
                claims["name"] = str(username)

        first_name = getattr(user, "first_name", None)
        if first_name not in {None, ""}:
            claims.setdefault("given_name", str(first_name))

        last_name = getattr(user, "last_name", None)
        if last_name not in {None, ""}:
            claims.setdefault("family_name", str(last_name))

        email = getattr(user, "email", None)
        if email not in {None, ""}:
            claims.setdefault("email", str(email))

        email_verified = getattr(user, "email_verified", None)
        if email_verified is not None:
            claims.setdefault("email_verified", bool(email_verified))

        user_roles = self.get_user_roles(login_payload)
        if user_roles:
            claims["roles"] = user_roles
        else:
            roles = claims.get("roles")
            if isinstance(roles, Sequence) and not isinstance(roles, str):
                claims["roles"] = tuple(
                    str(role) for role in cast(Sequence[object], roles) if role
                )
            else:
                claims.setdefault("roles", ())

        user_permissions = self.get_user_permissions(login_payload)
        if user_permissions:
            claims["permissions"] = user_permissions
        else:
            permissions = claims.get("permissions")
            if isinstance(permissions, Sequence) and not isinstance(permissions, str):
                claims["permissions"] = tuple(
                    str(permission)
                    for permission in cast(Sequence[object], permissions)
                    if permission
                )
            else:
                claims.setdefault("permissions", ())
        return claims

    def build_login_response(self, login_payload: LoginPayload) -> dict[str, Any]:
        """Return the default JWT-based login payload for *user*."""
        payload: dict[str, Any] = {
            "authenticated": True,
            **JWTUtils.build_token_pair_with_claims(
                login_payload.user,
                **self.build_jwt_claims(login_payload),
            ),
        }
        return payload
