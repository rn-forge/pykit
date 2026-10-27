"""The verified caller, the access requirement it is checked against, and the
default token-claims mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, cast

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.web.exceptions import AuthenticationFailed

__all__ = ["Mechanism", "Principal", "Requirement", "principal_from_claims"]

Mechanism = Literal["session", "bearer", "basic"]


@dataclass(frozen=True)
class Principal(DataclassMixin):
    """The verified caller.

    ``subject`` is the only required field.

    Attributes:
        subject: The internal account or service-account ID.
        issuer: The issuer of the external identity that authenticated, from
            the session metadata or the verified token.
        external_subject: The external identity's subject, from the same source.
        scopes: Delegated scopes from the verified token; empty for a session.
        permissions: Effective permissions: the authorization context's, limited
            by scopes for a bearer caller (see :func:`effective_permissions`).
        roles: Role names from the authorization context.
        tenant: The tenant, from the authorization context.
        attributes: Inputs to attribute-based rules, from the authorization
            context.
        claims: Verified token claims, retained for the application's own use;
            empty for a session.
        mechanism: How the caller authenticated, set by the authenticator.
        auth_time: When the caller authenticated, from the session metadata or
            the verified token.
        amr: Authentication methods used, from the same source.
    """

    subject: str
    issuer: str | None = None
    external_subject: str | None = None
    scopes: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    tenant: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict[str, Any])
    claims: Mapping[str, Any] = field(default_factory=dict[str, Any])
    mechanism: Mechanism = "bearer"
    auth_time: datetime | None = None
    amr: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Requirement:
    """A declarative access requirement.

    All four sets are ANDed together; within ``any_*`` the members are ORed.
    Permission clauses are checked against :attr:`Principal.permissions` and
    scope clauses against :attr:`Principal.scopes`; scope clauses can only
    narrow access further. An empty requirement is satisfied by any principal:
    it means "authenticated", not "denied".
    """

    any_scope: frozenset[str] = frozenset()
    all_scopes: frozenset[str] = frozenset()
    any_permission: frozenset[str] = frozenset()
    all_permissions: frozenset[str] = frozenset()

    def is_satisfied_by(self, principal: Principal) -> bool:
        """Return whether *principal* meets every clause of this requirement."""
        if self.any_scope and not (self.any_scope & principal.scopes):
            return False
        if not self.all_scopes <= principal.scopes:
            return False
        if self.any_permission and not (self.any_permission & principal.permissions):
            return False
        return self.all_permissions <= principal.permissions


def principal_from_claims(
    claims: Mapping[str, Any], *, mechanism: Mechanism = "bearer"
) -> Principal:
    """The default mapping from verified token claims to a :class:`Principal`.

    Claims are read as follows:

    | Principal | Claim |
    | --- | --- |
    | `subject` | `sub` (required) |
    | `issuer` | `iss` |
    | `scopes` | `scope` (RFC 8693 §4.2, space-delimited) or `scp` (string or list) |
    | `roles` | `roles` (a list) |
    | `tenant` | `tid` |

    Any other claim is left in :attr:`Principal.claims`, which retains every
    verified claim.

    Args:
        claims: Claims already verified by the caller.
        mechanism: Recorded on the principal.

    Raises:
        AuthenticationFailed: There is no ``sub``. The detail stays generic.
    """
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthenticationFailed("Token has no subject", error_code=401)
    issuer = claims.get("iss")
    tenant = claims.get("tid")
    return Principal(
        subject=subject,
        issuer=issuer if isinstance(issuer, str) else None,
        scopes=_string_set(claims.get("scope")) | _string_set(claims.get("scp")),
        roles=_string_set(claims.get("roles")),
        tenant=tenant if isinstance(tenant, str) else None,
        claims=dict(claims),
        mechanism=mechanism,
    )


def _string_set(value: object) -> frozenset[str]:
    """A space-delimited string or a list of strings, as a frozenset."""
    if isinstance(value, str):
        return frozenset(value.split())
    if isinstance(value, (list, tuple)):
        return frozenset(str(item) for item in cast("list[object]", value))
    return frozenset()
