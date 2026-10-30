"""Authorization context contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["AuthorizationContext", "AuthorizationContextProvider"]


@dataclass(frozen=True)
class AuthorizationContext:
    """An account's current authorization data.

    Attributes:
        active: Whether the account may authenticate.
        session_version: The account's current session version.
        permissions: Permission keys the account holds.
        roles: Role names, as a display hint and provider input.
        attributes: Inputs to attribute-based rules, such as tenant, org units
            and locations.
    """

    active: bool
    session_version: int
    permissions: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    attributes: Mapping[str, Any] = field(default_factory=dict[str, Any])


@runtime_checkable
class AuthorizationContextProvider(Protocol):
    """Supplies the :class:`AuthorizationContext` of an account."""

    def resolve(self, account_id: str) -> AuthorizationContext:
        """Return the current context of *account_id*."""
        ...
