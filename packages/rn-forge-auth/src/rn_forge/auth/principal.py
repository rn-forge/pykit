"""The verified caller, the access requirement it is checked against, and the
default token-claims mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.web.exceptions import AuthenticationFailed

__all__ = ["Principal", "Requirement", "principal_from_claims"]


@dataclass(frozen=True)
class Principal(DataclassMixin):
    """The verified caller.

    ``subject`` is the only required field. ``claims`` retains verified values
    not represented by the common fields.
    """

    subject: str
    issuer: str | None = None
    scopes: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    tenant: str | None = None
    claims: Mapping[str, Any] = field(default_factory=dict[str, Any])
    mechanism: str = "bearer"


@dataclass(frozen=True)
class Requirement:
    """A declarative access requirement, evaluated identically by both frameworks.

    All four sets are ANDed together; within ``any_*`` the members are ORed.
    An empty requirement is satisfied by any principal — it means
    "authenticated", not "denied".
    """

    any_scope: frozenset[str] = frozenset()
    all_scopes: frozenset[str] = frozenset()
    any_role: frozenset[str] = frozenset()
    all_roles: frozenset[str] = frozenset()

    def is_satisfied_by(self, principal: Principal) -> bool:
        """Return whether *principal* meets every clause of this requirement."""
        if self.any_scope and not (self.any_scope & principal.scopes):
            return False
        if not self.all_scopes <= principal.scopes:
            return False
        if self.any_role and not (self.any_role & principal.roles):
            return False
        return self.all_roles <= principal.roles


def principal_from_claims(
    claims: Mapping[str, Any], *, mechanism: str = "bearer"
) -> Principal:
    """The default mapping from verified token claims to a :class:`Principal`.

    Claims are read as the common IdPs issue them:

    | Principal | Claim |
    | --- | --- |
    | `subject` | `sub` (required) |
    | `issuer` | `iss` |
    | `scopes` | `scope` (RFC 8693 §4.2, space-delimited) or `scp` (string or list) |
    | `roles` | `roles` (a list) |
    | `tenant` | `tid` |

    Any other shape — a nested ``realm_access.roles``, a custom group claim —
    is deployment-specific: override the mapping and read
    :attr:`Principal.claims`, which retains every verified claim.

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
