"""Authorization for Django accounts: context provider and invalidation signals."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Final, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db.models import Model, Q
from django.db.models.signals import m2m_changed, post_delete, post_save
from rn_forge.auth import AuthorizationContext, AuthorizationContextCache

__all__ = [
    "BYPASS_ROLES",
    "DjangoAuthorizationContextProvider",
    "connect_authorization_signals",
    "permission_keys",
]

BYPASS_ROLES: Final = ("superuser", "staff")
"""Roles that grant every permission: ``superuser`` for ``is_superuser`` and
``staff`` for ``is_staff``."""

_MODEL_ACTIONS: Final[dict[str, tuple[str, ...]]] = {
    "add": ("create",),
    "change": ("update",),
    "delete": ("delete",),
    "view": ("read", "list"),
}


def permission_keys(permission: Permission) -> frozenset[str]:
    """The dotted permission keys that a Django *permission* grants.

    Django's default model permissions map to ``<app_label>.<model>.<action>``,
    lowercase: ``add`` to ``create``, ``change`` to ``update``, ``delete`` to
    ``delete`` and ``view`` to both ``read`` and ``list``. So
    ``inventory.change_stock`` is ``inventory.stock.update``. Any other
    permission, such as a custom ``inventory.adjust_stock``, keeps its
    ``<app_label>.<codename>`` as the key.
    """
    content_type = permission.content_type
    app_label = content_type.app_label
    verb, _, model = permission.codename.partition("_")
    if verb in _MODEL_ACTIONS and model == content_type.model:
        return frozenset(
            f"{app_label}.{model}.{a}".lower() for a in _MODEL_ACTIONS[verb]
        )
    return frozenset({f"{app_label}.{permission.codename}".lower()})


def _keys(permissions: Iterable[Permission]) -> frozenset[str]:
    return frozenset(
        key for permission in permissions for key in permission_keys(permission)
    )


class DjangoAuthorizationContextProvider:
    """An :class:`~rn_forge.auth.AuthorizationContextProvider` over Django's auth models.

    The account ID is the user's primary key as a string. An unknown user, or
    one with ``is_active`` false, resolves to an inactive context with no
    permissions. Roles are the names of the user's groups. Permissions are the
    keys (see :func:`permission_keys`) of the user's own permissions and those
    of their groups.

    A staff or superuser account additionally has the matching role from
    :data:`BYPASS_ROLES`, and holds the keys of every Django permission and of
    *catalog*, so the bypass shows in the context as a role and a full
    permission set.

    Args:
        catalog: Permission keys that exist outside Django's permission table,
            such as a viewset's ``orders.read``, which the bypass also grants.
        session_version: Returns a user's session version. Defaults to ``0``.
    """

    def __init__(
        self,
        *,
        catalog: Iterable[str] = (),
        session_version: Callable[[AbstractUser], int] = lambda _user: 0,
    ) -> None:
        self._catalog = frozenset(catalog)
        self._session_version = session_version

    def resolve(self, account_id: str) -> AuthorizationContext:
        """Return the current context of the user with primary key *account_id*."""
        user_model = cast(type[AbstractUser], get_user_model())
        user = user_model._default_manager.filter(pk=account_id).first()
        if user is None or not user.is_active:
            return AuthorizationContext(active=False, session_version=0)

        roles = set(user.groups.values_list("name", flat=True))
        if user.is_superuser:
            roles.add("superuser")
        if user.is_staff:
            roles.add("staff")

        if user.is_superuser or user.is_staff:
            granted = Permission.objects.select_related("content_type")
        else:
            granted = Permission.objects.filter(
                Q(user=user) | Q(group__user=user)
            ).select_related("content_type")
        permissions = _keys(granted)
        if user.is_superuser or user.is_staff:
            permissions |= self._catalog

        return AuthorizationContext(
            active=True,
            session_version=self._session_version(user),
            permissions=permissions,
            roles=frozenset(roles),
        )


def connect_authorization_signals(
    cache: AuthorizationContextCache,
) -> Callable[[], None]:
    """Invalidate *cache* when the Django models behind a context change.

    A change to a user, or to the groups or permissions assigned directly to
    them, invalidates that account. A change to a group or permission, or to
    which permissions a group holds, invalidates every account. These are the
    signals the ``User``, ``Group`` and ``Permission`` viewsets raise.

    Returns:
        A function that disconnects the receivers.
    """
    user_model = cast(type[Model], get_user_model())

    def account_changed(instance: Any, **_: Any) -> None:
        cache.invalidate(str(instance.pk))

    def everyone_changed(**_: Any) -> None:
        cache.invalidate_all()

    def user_membership_changed(
        instance: Any, action: str, reverse: bool, pk_set: set[Any] | None, **_: Any
    ) -> None:
        if not action.startswith("post_"):
            return
        if not reverse:
            cache.invalidate(str(instance.pk))
        elif pk_set is None:
            # A reverse clear does not say which users it touched.
            cache.invalidate_all()
        else:
            for pk in pk_set:
                cache.invalidate(str(pk))

    def group_permissions_changed(action: str, **_: Any) -> None:
        if action.startswith("post_"):
            cache.invalidate_all()

    uid = f"rn_forge_django_auth_{id(cache)}"
    user_groups = cast(Any, user_model).groups.through
    user_perms = cast(Any, user_model).user_permissions.through
    receivers: list[tuple[Any, Any, Any]] = [
        (post_save, account_changed, user_model),
        (post_delete, account_changed, user_model),
        (post_save, everyone_changed, Group),
        (post_delete, everyone_changed, Group),
        (post_save, everyone_changed, Permission),
        (post_delete, everyone_changed, Permission),
        (m2m_changed, user_membership_changed, user_groups),
        (m2m_changed, user_membership_changed, user_perms),
        (m2m_changed, group_permissions_changed, Group.permissions.through),
    ]
    for signal, receiver, sender in receivers:
        signal.connect(
            receiver,
            sender=sender,
            weak=False,
            dispatch_uid=f"{uid}_{receiver.__name__}_{sender.__name__}",
        )

    def disconnect() -> None:
        for signal, receiver, sender in receivers:
            signal.disconnect(
                receiver,
                sender=sender,
                dispatch_uid=f"{uid}_{receiver.__name__}_{sender.__name__}",
            )

    return disconnect
