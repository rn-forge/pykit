"""Typed helpers for working with Django REST Framework request objects."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast, runtime_checkable

from rest_framework.request import Request
from rest_framework.exceptions import ValidationError

from django.http import HttpRequest
from django.core.files.uploadedfile import UploadedFile
from rn_forge.django.drf._typing import RequestProtocol

__all__ = [
    "AuthenticatedRequestUser",
    "DRFUtils",
    "PermissionAwareUser",
    "RequestUtils",
]


# ---------------------------------------------------------------------------
# Request/User Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class AuthenticatedRequestUser(Protocol):
    """Minimum user shape expected by DRF-facing library helpers."""

    is_authenticated: bool
    is_staff: bool
    email: str


@runtime_checkable
class PermissionAwareUser(AuthenticatedRequestUser, Protocol):
    """User shape required by permission-aware DRF helpers."""

    def has_permission(self, permission: str) -> bool: ...


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


class RequestUtils:
    """Typed boundary helpers for DRF request objects.

    These helpers centralize the narrow Pyright workarounds needed around DRF's
    request, user, and auth attributes so view and auth modules can use a small
    stable API instead of scattering casts and ignores.
    """

    @staticmethod
    def get_django_request(request: Request) -> HttpRequest:
        """Return the underlying Django request from a DRF request."""
        return cast(RequestProtocol, request)._request  # pyright: ignore[reportPrivateUsage]

    @staticmethod
    def get_param(request: Request, key: str, default: str | None = None) -> str | None:
        """Return a query-parameter value from the request."""
        if not hasattr(request, "query_params"):
            query_params = cast(Any, cast(HttpRequest, request).GET)
            value = query_params.get(key, default)
            return cast(str | None, value)
        return cast(
            str | None, cast(RequestProtocol, request).query_params.get(key, default)
        )

    @staticmethod
    def get_data(request: Request) -> dict[str, Any]:
        """Return request data normalized to a plain ``dict[str, Any]``."""
        if not hasattr(request, "data"):
            django_request = cast(HttpRequest, request)
            if django_request.POST:
                return cast(dict[str, Any], django_request.POST.dict())
            body = cast(bytes, getattr(django_request, "body", b""))
            if not body:
                return {}
            return cast(dict[str, Any], json.loads(body.decode()))
        return cast(dict[str, Any], cast(RequestProtocol, request).data)

    @staticmethod
    def get_value(request: Request, key: str, default: Any = None) -> Any:
        """Return a value from request data."""
        if not hasattr(request, "data"):
            return RequestUtils.get_data(request).get(key, default)
        data = cast(RequestProtocol, request).data
        if not isinstance(data, dict):
            return default
        request_data = cast(dict[str, Any], data)
        return request_data.get(key, default)

    @staticmethod
    def get_string(
        request: Request, key: str, default: str | None = None
    ) -> str | None:
        """Return a query/body value converted to ``str`` when present."""
        value = RequestUtils.get_param(request, key)
        if value is None:
            value = RequestUtils.get_value(request, key)
        if value is None:
            return default
        return str(value)

    @staticmethod
    def get_uploaded_file(request: Request, key: str = "file") -> UploadedFile:
        """Return an uploaded file or raise a DRF validation error."""
        files = cast(RequestProtocol, request).FILES
        file = files.get(key) if hasattr(files, "get") else None
        if isinstance(file, UploadedFile):
            return file
        data_file = RequestUtils.get_value(request, key)
        if isinstance(data_file, UploadedFile):
            return data_file
        raise ValidationError(f"Missing uploaded file field: {key}")

    @staticmethod
    def get_request_param(
        request: Request, key: str, default: str | None = None
    ) -> str | None:
        """Compatibility alias for :meth:`get_param`."""
        return RequestUtils.get_param(request, key, default)

    @staticmethod
    def get_request_data(request: Request) -> dict[str, Any]:
        """Compatibility alias for :meth:`get_data`."""
        return RequestUtils.get_data(request)

    @staticmethod
    def get_request_value(request: Request, key: str, default: Any = None) -> Any:
        """Compatibility alias for :meth:`get_value`."""
        return RequestUtils.get_value(request, key, default)

    @staticmethod
    def get_request_user(request: Request) -> AuthenticatedRequestUser:
        """Return the current request user with a stable typed protocol."""
        return cast(AuthenticatedRequestUser, cast(RequestProtocol, request).user)

    @staticmethod
    def get_request_auth(request: Request) -> Any:
        """Return the current request auth payload."""
        return cast(RequestProtocol, request).auth


DRFUtils = RequestUtils
