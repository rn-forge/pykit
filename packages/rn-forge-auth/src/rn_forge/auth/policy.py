"""Resource-level authorization contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rn_forge.auth.principal import Principal

__all__ = ["ResourcePolicy"]


@runtime_checkable
class ResourcePolicy[ResourceT, QueryT](Protocol):
    """Object-level and query-level checks beyond a route's requirement."""

    def allows(self, principal: Principal, action: str, resource: ResourceT) -> bool:
        """Return whether *principal* may perform *action* on *resource*."""
        ...

    def scope(self, principal: Principal, action: str, query: QueryT) -> QueryT:
        """Return *query* narrowed to what *principal* may *action*."""
        ...
