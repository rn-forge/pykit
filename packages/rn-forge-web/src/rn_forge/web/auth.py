"""The authentication *contract*: who the caller is, and what a refusal looks like.

Token verification is not here. The concern splits across three layers, and
this is the middle one:

| Layer | Owns | Standards |
| --- | --- | --- |
| `rn-forge-commons` | Verification: JWKS fetch/cache/rotation, JWT signature and claims validation, OIDC discovery. No HTTP-server concept. | RFC 7519, 7517, 8414, OIDC Discovery 1.0 |
| **`rn-forge-web` (here)** | The contract: `Principal`, the authenticator/authorizer protocols, and the failure wire shape. | RFC 6750 §3, RFC 7617, RFC 9457 |
| `rn-forge-django` / `rn-forge-fastapi` | The binding only: a DRF `BaseAuthentication` / a FastAPI `Security` dependency, each producing the same `Principal`. | — |

The earlier reasoning — "OIDC/JWKS verification is framework-agnostic, so send
auth to commons" — is correct and incomplete: it covers *verifying a token* and
says nothing about *what a caller sees when verification fails*. A 401 body, the
``WWW-Authenticate`` challenge and the 401-vs-403 boundary are wire semantics in
exactly the sense the other modules are, and they are the part a UI cannot paper
over.

The failure contract, which is the reason this module exists
------------------------------------------------------------

- **401 vs 403 is not a judgement call.** No credentials, or credentials that
  fail verification → **401** with a ``WWW-Authenticate`` challenge. Valid
  credentials lacking the required scope or role → **403** with no challenge.
  RFC 6750 §3 is unambiguous.
- **The challenge is constructed, never hand-written.** :func:`challenge_header`
  builds both the Bearer (RFC 6750 §3) and Basic (RFC 7617) forms. A
  hand-assembled challenge string is how two services end up differing on a
  header a browser actually parses.
- **The problem body is the ordinary one.**
  :class:`~rn_forge.web.exceptions.AuthenticationFailed` → 401 slug
  ``unauthorized``, :class:`~rn_forge.web.exceptions.PermissionDenied` → 403
  slug ``forbidden``, both already in
  :func:`~rn_forge.web.problem.default_registry`. Nothing new on the wire
  beyond the header.
- **Never leak why verification failed.** The 401 detail says "authentication
  failed"; the reason — expired, bad signature, unknown ``kid`` — goes to the
  injected ``log``. Same policy as the 5xx rule in
  :mod:`rn_forge.web.problem`, and for the same reason.

What this module deliberately does not unify
--------------------------------------------

**SAML flows.** SAML 2.0 terminates in an assertion and a session, not a bearer
token, and the bindings, metadata and signature handling are the SP library's
job. Web defines only the assertion → :class:`Principal` mapping; each package
keeps its own flow. **Login endpoints, token issuance, refresh, session
cookies** are application concerns — pykit is not an authorization server.
**Basic auth** ships in both framework packages because local development and
simple internal deployments genuinely need it, and both must document it as
such and emit the identical 401 challenge.
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
"""The 401 ``detail``. It says nothing about *why*; see the module docstring."""

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

    ``subject`` is the only required field — it is ``sub`` for OIDC, the
    username for Basic, the ``NameID`` for SAML. Everything else is optional
    because no single mechanism supplies all of it.

    ``scopes`` and ``roles`` are **separate** and both are frozensets: OAuth
    issues scopes, enterprise directories issue roles or groups, and conflating
    them forces one to be encoded as the other.

    ``claims`` carries the raw verified claim set so an application can read
    something this library never modelled, without the dataclass growing a
    field per deployment. ``mechanism`` exists so a problem body and an audit
    log can say *how* the caller authenticated without each framework layer
    inventing its own vocabulary for it.
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
    """The async counterpart of :class:`Authenticator`.

    Both exist for the same reason the idempotency store has both: a
    JWKS-backed verifier does network I/O, and Django's authenticator is sync.
    """

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
    """The default :class:`Authorizer`: evaluates a :class:`Requirement` and nothing else.

    Args:
        log: Optional sink called as ``log(message, context)`` when access is
            refused. When ``None`` the authorizer stays silent — a library that
            logs where the consumer did not ask is worse than one that does not.
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

    RFC 6750 §3 defines the Bearer syntax and its ``error`` codes; RFC 7617
    defines the ``Basic realm="..."`` form. Parameters are emitted in the order
    the RFCs use in their own examples, and omitted entirely when ``None``.

    Args:
        scheme: ``Bearer`` or ``Basic``.
        realm: The protection space.
        error: One of RFC 6750's three codes. Bearer only.
        error_description: Human-readable text. **Never say why verification
            failed** — see the module docstring.
        scope: The scope required, for ``insufficient_scope``.

    Returns:
        A complete header value, e.g.
        ``Bearer realm="example", error="invalid_token", error_description="The access token expired"``.

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

    Shared so a Django service and a FastAPI service reading the same token
    produce the same principal. Claims are read as the common IdPs issue them:

    | Principal | Claim |
    | --- | --- |
    | `subject` | `sub` (required) |
    | `issuer` | `iss` |
    | `scopes` | `scope` (RFC 8693 §4.2, space-delimited) or `scp` (Entra; string or list) |
    | `roles` | `roles` (Entra app roles; a list) |
    | `tenant` | `tid` (Entra) |

    Anything else — Keycloak's nested ``realm_access.roles``, an Okta group
    claim — is a deployment's shape: override the mapping and read ``claims``.

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
