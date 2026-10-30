"""DRF permission and resource-policy hooks over :mod:`rn_forge.auth`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, override

from django.db.models import QuerySet
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rn_forge.auth import Principal, ResourcePolicy, requirement_for
from rn_forge.auth.audit import audit
from rn_forge.django.drf import RequestUtils

__all__ = ["PermissionKeyPermission", "ResourcePolicyViewMixin"]


class PermissionKeyPermission(BasePermission):
    """Require the permission key a view's action maps to.

    The view declares ``permission_key`` and, optionally,
    ``permission_action_map``. The requirement is
    :func:`rn_forge.auth.requirement_for` of the key and the view's action (the
    HTTP method, lowercased, outside a viewset), checked against the request's
    :class:`~rn_forge.auth.Principal`. A view without a ``permission_key``
    requires only an authenticated principal. A request without a principal is
    denied.
    """

    @override
    def has_permission(self, request: Request, view: Any) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        principal = RequestUtils.get_request_user(request)
        if not isinstance(principal, Principal):
            return False
        key: str | None = getattr(view, "permission_key", None)
        if not key:
            return True
        action = str(getattr(view, "action", None) or request.method).lower()
        action_map: Mapping[str, str] | None = getattr(
            view, "permission_action_map", None
        )
        allowed = requirement_for(key, action, action_map=action_map).is_satisfied_by(
            principal
        )
        if not allowed:
            audit(
                "authorization.denied",
                account_id=principal.subject,
                permission_key=key,
                action=action,
            )
        return allowed


class ResourcePolicyViewMixin(GenericAPIView):
    """Apply a :class:`~rn_forge.auth.ResourcePolicy` to a generic view.

    :meth:`get_queryset` is narrowed by ``resource_policy.scope``, so list
    results, their counts and their pages contain only permitted rows, and a
    detail lookup of any other row is a ``404``. :meth:`get_object` then asks
    ``resource_policy.allows`` and raises ``403`` when it is denied, or ``404``
    when ``policy_hides_existence`` is true.

    Attributes:
        resource_policy: The policy. Required.
        policy_hides_existence: Report a denied object as ``404`` instead of
            ``403``.
    """

    resource_policy: ClassVar[ResourcePolicy[Any, QuerySet[Any]]]
    policy_hides_existence: ClassVar[bool] = False

    def _policy_principal(self) -> Principal:
        principal = RequestUtils.get_request_user(self.request)  # pyright: ignore[reportArgumentType]
        if not isinstance(principal, Principal):
            raise PermissionDenied
        return principal

    def _policy_action(self) -> str:
        return str(getattr(self, "action", None) or self.request.method).lower()

    @override
    def get_queryset(self) -> QuerySet[Any]:  # pyright: ignore[reportIncompatibleMethodOverride]  # DRF stubs type the base as returning Never
        return self.resource_policy.scope(
            self._policy_principal(), self._policy_action(), super().get_queryset()
        )

    @override
    def get_object(self) -> Any:
        obj = super().get_object()
        if not self.resource_policy.allows(
            self._policy_principal(), self._policy_action(), obj
        ):
            audit(
                "authorization.denied",
                account_id=self._policy_principal().subject,
                action=self._policy_action(),
                resource=type(obj).__name__,
                hidden=self.policy_hides_existence,
            )
            if self.policy_hides_existence:
                raise NotFound
            raise PermissionDenied
        return obj
