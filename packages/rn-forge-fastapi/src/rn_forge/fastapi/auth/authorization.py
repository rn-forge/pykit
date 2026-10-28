"""Object and query checks from a :class:`~rn_forge.auth.ResourcePolicy`."""

from __future__ import annotations

from typing import Any

from rn_forge.auth import Principal, ResourcePolicy
from rn_forge.web import PermissionDenied

__all__ = ["PolicyGuard"]


class PolicyGuard[ResourceT, QueryT]:
    """Apply a :class:`~rn_forge.auth.ResourcePolicy` to queries and objects.

    The guard is independent of the query type: *QueryT* is whatever the policy
    narrows, such as a SQLAlchemy ``Select``.

    Args:
        policy: The policy.
        hides_existence: Report a denied object as 404 instead of 403.

    Example:
        ``rows = guard.scope(principal, "list", select(Order))`` narrows a list
        query, so its rows, counts and pages hold only permitted rows;
        ``guard.check(principal, "read", order)`` then returns *order* or raises.
    """

    def __init__(
        self,
        policy: ResourcePolicy[ResourceT, QueryT],
        *,
        hides_existence: bool = False,
    ) -> None:
        self._policy: ResourcePolicy[Any, Any] = policy
        self._hides_existence = hides_existence

    def scope(self, principal: Principal, action: str, query: QueryT) -> QueryT:
        """Return *query* narrowed to what *principal* may *action*."""
        return self._policy.scope(principal, action, query)

    def check(
        self, principal: Principal, action: str, resource: ResourceT
    ) -> ResourceT:
        """Return *resource* if *principal* may *action* it.

        Raises:
            LookupError: The policy denies it and ``hides_existence`` is true (404).
            PermissionDenied: The policy denies it (403).
        """
        if self._policy.allows(principal, action, resource):
            return resource
        if self._hides_existence:
            raise LookupError("Not found")
        raise PermissionDenied("The policy denies the action")
