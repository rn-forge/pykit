"""DRF-facing authorization permission for rn-forge-django auth."""

from __future__ import annotations

from typing import Any, Protocol, cast, override, runtime_checkable

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rn_forge.commons.logging import AppLogger
from rn_forge.django.drf import RequestUtils
from rn_forge.django.auth.credentials import BaseCredentials
from rn_forge.django.models import BaseModel

__all__ = ["AuthorizationPermission"]

_LOGGER = AppLogger.get_logger(__name__)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@runtime_checkable
class AuthorizationViewProtocol(Protocol):
    """View shape consumed by :class:`AuthorizationPermission`."""

    def is_request_authorized(self, request: Request) -> bool: ...

    def validate_permissions(self) -> bool: ...

    def should_validate_object_permissions(self, action: str) -> bool: ...

    def validate_object_permissions(
        self, obj: BaseModel | dict[str, Any]
    ) -> str | None: ...


class AuthorizationPermission(BasePermission):
    """Default DRF permission for rn-forge-django auth-enabled views."""

    @override
    def has_permission(self, request: Request, view: Any) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        if request.method in {"HEAD", "OPTIONS"}:
            return True

        if isinstance(view, AuthorizationViewProtocol) and view.is_request_authorized(
            request
        ):
            return True

        credentials = RequestUtils.get_request_auth(request)
        if not isinstance(credentials, BaseCredentials):
            user = RequestUtils.get_request_user(request)
            if user.is_authenticated:
                _LOGGER.error(
                    "Authorization misconfigured: method={} path={} auth={}",
                    request.method,
                    request.path,
                    type(credentials).__name__,
                )
                self.message = (
                    "rn-forge authentication is not configured for this endpoint"
                )
                self.code = "InvalidCredentials"
                return False
            _LOGGER.error(
                "Unauthenticated request: method={} path={}",
                request.method,
                request.path,
            )
            self.message = "User not authenticated"
            self.code = "UnauthenticatedRequest"
            return False

        if credentials.is_staff_user:
            return True

        if isinstance(view, AuthorizationViewProtocol):
            if view.validate_permissions():
                return True
            _LOGGER.warning(
                "Forbidden request: method={} path={}", request.method, request.path
            )
            self.message = "User does not have permission to access this resource"
            self.code = "ForbiddenRequest"
            return False

        return True

    @override
    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        if not isinstance(view, AuthorizationViewProtocol):
            return True

        action = str(getattr(view, "action", request.method.lower()))
        if not view.should_validate_object_permissions(action):
            return True

        error = view.validate_object_permissions(cast(BaseModel | dict[str, Any], obj))
        if error is None:
            return True

        self.message = error
        self.code = "ForbiddenRequest"
        return False
