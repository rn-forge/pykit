"""Permission keys: the action-to-key mapping and the scope limit on tokens."""

from __future__ import annotations

from collections.abc import Mapping

from rn_forge.auth.principal import Mechanism, Requirement

__all__ = ["DEFAULT_PERMISSION_ACTION_MAP", "effective_permissions", "requirement_for"]

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


def requirement_for(
    permission_key: str,
    action: str,
    *,
    action_map: Mapping[str, str] | None = None,
) -> Requirement:
    """The :class:`Requirement` for performing *action* on *permission_key*.

    The action is mapped to a permission suffix and joined to the key:
    ``requirement_for("orders", "partial_update")`` requires ``orders.update``.

    Args:
        permission_key: The resource's base permission key, such as ``orders``.
        action: The action name, such as a viewset action.
        action_map: Entries that override :data:`DEFAULT_PERMISSION_ACTION_MAP`;
            actions it does not name fall back to the default map. An action
            named by neither map is used as the suffix unchanged.

    Returns:
        A requirement of ``all_permissions={"<permission_key>.<suffix>"}``.
    """
    mapping = {**DEFAULT_PERMISSION_ACTION_MAP, **(action_map or {})}
    return Requirement(
        all_permissions=frozenset({f"{permission_key}.{mapping.get(action, action)}"})
    )


def effective_permissions(
    permissions: frozenset[str],
    *,
    mechanism: Mechanism,
    scopes: frozenset[str],
    scope_map: Mapping[str, frozenset[str]],
) -> frozenset[str]:
    """The permissions a caller may exercise, after the scope limit.

    A ``session`` or ``basic`` caller acts with its account's credentials, so
    *permissions* are returned unchanged. A ``bearer`` caller is limited to the
    permissions that its *scopes* allow through *scope_map*; a scope absent from
    the map allows nothing, and scopes never add permissions the account lacks.

    Args:
        permissions: The account's permissions.
        mechanism: How the caller authenticated.
        scopes: The scopes of the verified token.
        scope_map: The permissions each accepted scope allows.
    """
    if mechanism != "bearer":
        return permissions
    allowed: set[str] = set()
    for scope in scopes:
        allowed |= scope_map.get(scope, frozenset())
    return permissions & allowed
