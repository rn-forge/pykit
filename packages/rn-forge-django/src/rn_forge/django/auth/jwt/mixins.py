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

    def _claim_sub(self, user: object) -> str | None:
        """Return the ``sub`` claim value derived from the user's id/pk."""
        user_id = getattr(user, "id", getattr(user, "pk", None))
        return str(user_id) if user_id not in {None, ""} else None

    def _claim_name(self, user: object) -> str | None:
        """Return the ``name`` claim, falling back through several sources."""
        get_full_name = getattr(user, "get_full_name", None)
        if callable(get_full_name):
            full_name = get_full_name()
            if full_name not in {None, ""}:
                return str(full_name)

        first_name = getattr(user, "first_name", None)
        last_name = getattr(user, "last_name", None)
        if first_name not in {None, ""} or last_name not in {None, ""}:
            full_name = " ".join(
                part for part in (str(first_name or ""), str(last_name or "")) if part
            ).strip()
            if full_name:
                return full_name

        username = getattr(user, "username", None)
        return str(username) if username not in {None, ""} else None

    def _claim_given_family_names(self, user: object) -> tuple[str | None, str | None]:
        """Return the ``given_name``/``family_name`` claim values."""
        first_name = getattr(user, "first_name", None)
        last_name = getattr(user, "last_name", None)
        given_name = str(first_name) if first_name not in {None, ""} else None
        family_name = str(last_name) if last_name not in {None, ""} else None
        return given_name, family_name

    def _claim_email(self, user: object) -> str | None:
        """Return the ``email`` claim value."""
        email = getattr(user, "email", None)
        return str(email) if email not in {None, ""} else None

    def _claim_email_verified(self, user: object) -> bool | None:
        """Return the ``email_verified`` claim value."""
        email_verified = getattr(user, "email_verified", None)
        return bool(email_verified) if email_verified is not None else None

    def _resolve_sequence_claim(
        self, resolved: tuple[str, ...], existing: object
    ) -> tuple[str, ...]:
        """Return *resolved* values, or a normalized *existing* claim as fallback."""
        if resolved:
            return resolved
        if isinstance(existing, Sequence) and not isinstance(existing, str):
            return tuple(
                str(value) for value in cast(Sequence[object], existing) if value
            )
        return ()

    def build_jwt_claims(
        self,
        login_payload: LoginPayload,
    ) -> dict[str, object]:
        """Return flat JWT claims to apply to the refresh/access token pair."""
        claims: dict[str, object] = {}
        user = login_payload.user

        sub = self._claim_sub(user)
        if sub is not None:
            claims["sub"] = sub

        name = self._claim_name(user)
        if name is not None:
            claims["name"] = name

        given_name, family_name = self._claim_given_family_names(user)
        if given_name is not None:
            claims["given_name"] = given_name
        if family_name is not None:
            claims["family_name"] = family_name

        email = self._claim_email(user)
        if email is not None:
            claims["email"] = email

        email_verified = self._claim_email_verified(user)
        if email_verified is not None:
            claims["email_verified"] = email_verified

        claims["roles"] = self._resolve_sequence_claim(
            self.get_user_roles(login_payload), claims.get("roles")
        )
        claims["permissions"] = self._resolve_sequence_claim(
            self.get_user_permissions(login_payload), claims.get("permissions")
        )
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
