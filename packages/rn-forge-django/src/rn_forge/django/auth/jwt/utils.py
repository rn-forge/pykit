"""SimpleJWT helpers for rn-forge-django."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast

__all__ = ["JWTUtils"]


# ---------------------------------------------------------------------------
# Token Helpers
# ---------------------------------------------------------------------------


class JWTUtils:
    """Static helpers for minting and inspecting SimpleJWT tokens."""

    @staticmethod
    def create_refresh_token(user: object):
        """Create and return a refresh token for *user*."""
        from rest_framework_simplejwt.tokens import RefreshToken

        return RefreshToken.for_user(cast(Any, user))

    @staticmethod
    def create_access_token(user: object) -> str:
        """Create and return an access token string for *user*."""
        refresh = JWTUtils.create_refresh_token(user)
        access = refresh.access_token
        access["rn_forge_token_type"] = "access"
        return str(access)

    @staticmethod
    def build_token_pair(user: object) -> dict[str, str]:
        """Return ``refresh`` and ``access`` token strings for *user*."""
        refresh = JWTUtils.create_refresh_token(user)
        refresh["rn_forge_token_type"] = "refresh"
        access = refresh.access_token
        access["rn_forge_token_type"] = "access"
        return {
            "refresh": str(refresh),
            "access": str(access),
        }

    @staticmethod
    def add_claims(token: Any, **claims: object) -> Any:
        """Add custom claims to a mutable SimpleJWT token and return it."""
        for key, value in claims.items():
            token[key] = value
        return token

    @staticmethod
    def build_token_pair_with_claims(
        user: object,
        **claims: object,
    ) -> dict[str, str]:
        """Return refresh/access tokens after applying custom claims."""
        refresh = JWTUtils.create_refresh_token(user)
        JWTUtils.add_claims(refresh, **claims)
        refresh["rn_forge_token_type"] = "refresh"
        access = refresh.access_token
        JWTUtils.add_claims(access, **claims)
        access["rn_forge_token_type"] = "access"
        return {
            "refresh": str(refresh),
            "access": str(access),
        }

    @staticmethod
    def build_login_exchange_token(
        user: object,
        *,
        token_type: str = "login_exchange",
        lifetime: timedelta = timedelta(minutes=5),
    ) -> str:
        """Return a short-lived JWT for the login-exchange handoff."""
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(cast(Any, user))
        token.set_exp(lifetime=lifetime)
        token["rn_forge_token_type"] = token_type
        return str(token)

    @staticmethod
    def validate_login_exchange_token(token: str) -> Mapping[str, object]:
        """Return a decoded login-exchange token payload."""
        from rest_framework_simplejwt.tokens import RefreshToken

        try:
            exchange_token = RefreshToken(cast(Any, token))
        except (
            Exception
        ) as exc:  # pragma: no cover - SimpleJWT raises token-specific errors
            raise ValueError("Invalid login exchange token") from exc
        if exchange_token.get("rn_forge_token_type") != "login_exchange":
            raise ValueError("Invalid login exchange token")
        return cast(Mapping[str, object], exchange_token.payload)
