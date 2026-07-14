"""JWT authentication classes for rn-forge auth."""

from __future__ import annotations

from typing import Any, cast

from rest_framework.request import Request
from rn_forge.django.auth.jwt.credentials import JWTCredentials

__all__ = ["JWTAuthentication"]


def _get_simplejwt_authentication_class():
    """Return the SimpleJWT authentication class lazily."""
    from rest_framework_simplejwt.authentication import (
        JWTAuthentication as SimpleJWTAuthentication,
    )

    return SimpleJWTAuthentication


class JWTAuthentication:
    """
    SimpleJWT authentication that wraps validated tokens as rn-forge credentials.
    This should be registered in the DRF settings['DEFAULT_AUTHENTICATION_CLASSES].
    """

    def authenticate(self, request: Request):
        """Return the authenticated user plus :class:`JWTCredentials`."""
        result = cast(
            Any,
            _get_simplejwt_authentication_class()(),
        ).authenticate(request)

        if result is None:
            return None

        user, validated_token = result
        return user, JWTCredentials(user, validated_token)
