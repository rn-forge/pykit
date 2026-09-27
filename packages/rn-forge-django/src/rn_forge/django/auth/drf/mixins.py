"""Auth-aware DRF view mixins."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, cast

from rest_framework.request import Request
from rn_forge.django.auth.drf.permissions import AuthorizationPermission
from rn_forge.django.auth.credentials import BaseCredentials
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.django.drf import PermissionAwareUser, RequestUtils
from rn_forge.django.drf.views.mixins import RequestAccessViewMixin
from rn_forge.django.models import BaseModel
from rn_forge.django.settings import rn_forge_django_settings

__all__ = [
    "AuthorizationViewMixin",
    "PermissionKeyViewMixin",
]

_LOGGER = AppLogger.get_logger(__name__)
DEFAULT_PERMISSION_ACTION_MAP: Mapping[str, str] = {
    "list": "list",
    "retrieve": "read",
    "create": "create",
    "update": "update",
    "partial_update": "update",
    "destroy": "delete",
    "batch_create": "create",
    "batch_delete": "delete",
    "import_items": "upload",
    "import_template": "upload",
}


def _get_permission_action_map(view_map: Mapping[str, str]) -> Mapping[str, str]:
    """Return default, settings, and view-level permission action mappings."""
    return {
        **dict(DEFAULT_PERMISSION_ACTION_MAP),
        **dict(rn_forge_django_settings.drf.views.permission_action_map),
        **dict(view_map),
    }


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class AuthorizationViewMixin(RequestAccessViewMixin):
    """View contract consumed by auth-aware DRF permissions."""

    permission_classes = [AuthorizationPermission]
    permission_key: str | None = None
    permission_action_map: ClassVar[Mapping[str, str]] = {}

    @property
    def credentials(self) -> BaseCredentials:
        """Return the rn-forge credentials attached to the current request."""

        credentials = RequestUtils.get_request_auth(self.drf_request)
        if not isinstance(credentials, BaseCredentials):
            raise TypeError(
                f"{type(self).__name__} requires rn-forge credentials on request.auth"
            )

        return credentials

    @property
    def user(self) -> PermissionAwareUser:
        return cast(
            PermissionAwareUser, RequestUtils.get_request_user(self.drf_request)
        )

    def is_request_authorized(self, request: Request) -> bool:
        """Return ``True`` to bypass standard permission checks."""
        del request
        return False

    def get_permission_key(self) -> str | None:
        """Return the permission key required for this view."""

        base_key = self.permission_key
        if not base_key:
            return None

        request_method = getattr(self.drf_request, "method", "GET")
        action = str(getattr(self, "action", request_method)).lower()
        action_map = _get_permission_action_map(self.permission_action_map)
        suffix = action_map.get(action)
        resolved = (
            base_key if not suffix else AppUtils.join_string(".", base_key, suffix)
        )

        _LOGGER.debug(
            "Resolved permission key: action={} base={} resolved={}",
            action,
            base_key,
            resolved,
        )
        return resolved

    def validate_permissions(self) -> bool:
        """Return whether the current request user passes view-level authorization."""

        permission_key = self.get_permission_key()
        if not permission_key:
            return True

        allowed = self.credentials.has_permission(permission_key)
        if not allowed:
            _LOGGER.warning(
                "Forbidden request: method={} path={} permission={}",
                self.drf_request.method,
                self.drf_request.path,
                permission_key,
            )

        return allowed

    def should_validate_object_permissions(self, action: str) -> bool:
        """Return whether object-level permissions should run for *action*."""

        return action in {"update", "partial_update", "destroy"}

    def validate_object_permissions(
        self, obj: BaseModel | dict[str, Any]
    ) -> str | None:
        """Return an error string to deny access, or ``None`` to allow it."""
        del obj
        return None


class PermissionKeyViewMixin:
    """Derive permission keys from a base permission key and view action."""

    permission_key: str | None = None
    permission_action_map: ClassVar[Mapping[str, str]] = {}

    @property
    def drf_request(self) -> Request:
        """Return ``self.request`` narrowed to a DRF request."""
        return cast(Request, getattr(self, "request"))

    def get_permission_key(self) -> str | None:
        base_key = self.permission_key
        if not base_key:
            return None

        action = getattr(self, "action", None)
        if action is None:
            action = getattr(self.drf_request, "method", "GET")

        action = str(action).lower()
        action_map = _get_permission_action_map(self.permission_action_map)
        suffix = action_map.get(action, "")
        if not suffix:
            return base_key

        resolved = AppUtils.join_string(".", base_key, suffix)
        _LOGGER.debug(
            "Resolved permission key: action={} base={} resolved={}",
            action,
            base_key,
            resolved,
        )

        return resolved
