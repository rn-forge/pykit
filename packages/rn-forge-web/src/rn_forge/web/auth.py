"""Framework-independent authentication and authorization contracts.

Missing or invalid credentials produce a 401 challenge; an authenticated
principal without sufficient access produces 403. Verification details must
not be exposed in the 401 response.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol, cast, runtime_checkable

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.web.exceptions import AuthenticationFailed, PermissionDenied

__all__ = [
    "AUTH_FAILED_DETAIL",
    "AsyncAuthenticator",
    "Authenticator",
    "Authorizer",
    "BearerErrorCode",
    "Credentials",
    "Principal",
    "Requirement",
    "ScopeAuthorizer",
    "challenge_header",
    "principal_from_claims",
]

AUTH_FAILED_DETAIL: Final = "Authentication failed."
"""The non-sensitive detail returned for authentication failures."""

type BearerErrorCode = Literal["invalid_request", "invalid_token", "insufficient_scope"]
"""The ``error`` codes RFC 6750 §3 defines for a Bearer challenge."""


@dataclass(frozen=True)
class Credentials:
    """Raw credentials lifted off the request, before verification.

    ``scheme`` is the HTTP auth scheme as sent (``Bearer``, ``Basic``, ...) and
    ``token`` its parameter, verbatim. This is what a framework binding hands
    an :class:`Authenticator`; nothing here interprets it.
    """

    scheme: str
    token: str
    extras: Mapping[str, Any] = field(default_factory=dict[str, Any])


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


@runtime_checkable
class Authenticator(Protocol):
    """Turns raw credentials into a verified :class:`Principal`."""

    def authenticate(self, *, credentials: Credentials) -> Principal:
        """Verify *credentials*.

        Raises:
            AuthenticationFailed: The credentials are absent, malformed or
                invalid. The message must not say which.
        """
        ...


@runtime_checkable
class AsyncAuthenticator(Protocol):
    """Asynchronous counterpart of :class:`Authenticator`."""

    async def authenticate(self, *, credentials: Credentials) -> Principal:
        """See :meth:`Authenticator.authenticate`."""
        ...


@runtime_checkable
class Authorizer(Protocol):
    """Decides whether a verified principal may proceed."""

    def authorize(self, principal: Principal, *, requires: Requirement) -> None:
        """Permit the request, or refuse it.

        Raises:
            PermissionDenied: The principal lacks the required access. Never
                :class:`~rn_forge.web.exceptions.AuthenticationFailed` — the
                caller is authenticated; that is the 401/403 boundary.
        """
        ...


class ScopeAuthorizer:
    """An :class:`Authorizer` that evaluates a :class:`Requirement`.

    Args:
        log: Optional sink called as ``log(message, context)`` when access is
            refused. ``None`` disables logging.
    """

    def __init__(
        self, *, log: Callable[[str, Mapping[str, Any]], None] | None = None
    ) -> None:
        self._log = log

    def authorize(self, principal: Principal, *, requires: Requirement) -> None:
        """See :meth:`Authorizer.authorize`."""
        if requires.is_satisfied_by(principal):
            return
        if self._log is not None:
            self._log(
                "authorization.denied",
                {
                    "subject": principal.subject,
                    "mechanism": principal.mechanism,
                    "required": requires,
                },
            )
        raise PermissionDenied(
            "The authenticated principal lacks the required access", error_code=403
        )


def challenge_header(
    *,
    scheme: str = "Bearer",
    realm: str | None = None,
    error: BearerErrorCode | None = None,
    error_description: str | None = None,
    scope: str | None = None,
) -> str:
    """Build a ``WWW-Authenticate`` challenge.

    Parameters follow RFC 6750 for Bearer and RFC 7617 for Basic. ``None``
    values are omitted.

    Args:
        scheme: ``Bearer`` or ``Basic``.
        realm: The protection space.
        error: One of RFC 6750's three codes. Bearer only.
        error_description: Non-sensitive human-readable text.
        scope: The scope required, for ``insufficient_scope``.

    Returns:
        A complete challenge header value.

    Example::

        challenge_header(realm="example")
        # 'Bearer realm="example"'
        challenge_header(realm="example", error="insufficient_scope", scope="read")
        # 'Bearer realm="example", error="insufficient_scope", scope="read"'
    """
    params: list[tuple[str, str]] = []
    if realm is not None:
        params.append(("realm", realm))
    if error is not None:
        params.append(("error", error))
    if error_description is not None:
        params.append(("error_description", error_description))
    if scope is not None:
        params.append(("scope", scope))
    if not params:
        return scheme
    rendered = ", ".join(f'{k}="{_quote(v)}"' for k, v in params)
    return f"{scheme} {rendered}"


def _quote(value: str) -> str:
    """Escape a quoted-string parameter value (RFC 9110 §5.6.4)."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


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
