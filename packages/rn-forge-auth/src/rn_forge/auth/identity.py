"""Identity-provider contract and the values it exchanges.

A provider takes the framework's native request and returns an
:class:`ExternalIdentity`; everything on the far side of that result is
framework-neutral.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "ExternalIdentity",
    "IdentityProvider",
    "LoginRequest",
    "LoginStart",
    "LoginTransaction",
    "ProviderKind",
    "SessionInfo",
]

ProviderKind = Literal["oidc", "oauth2", "password", "development"]
"""The protocol family of an :class:`IdentityProvider`."""


@dataclass(frozen=True)
class ExternalIdentity:
    """A verified identity asserted by a login provider.

    Attributes:
        provider: Configured provider ID.
        issuer: The OIDC ``iss``, or ``"local"`` for a local login.
        subject: The OIDC ``sub``.
        email: The email address, if the provider released one.
        email_verified: Whether the provider verified ``email``.
        name: Display name.
        picture: Avatar URL.
        groups: Group names the provider asserted.
        attributes: Other mapped claims.
        auth_time: When the user authenticated.
        amr: How the user authenticated, such as ``pwd``, ``mfa`` or ``hwk``.
        session_ref: The OIDC ``sid``, used for logout.
        id_token: The raw ID token, set only when the provider has
            RP-initiated logout enabled.
    """

    provider: str
    issuer: str
    subject: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    picture: str | None = None
    groups: frozenset[str] = frozenset()
    attributes: Mapping[str, Any] = field(default_factory=dict[str, Any])
    auth_time: datetime | None = None
    amr: frozenset[str] = frozenset()
    session_ref: str | None = None
    id_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class LoginTransaction:
    """The state of one login in flight, persisted between begin and complete.

    Attributes:
        id: Opaque handle the transaction cookie carries.
        provider: ID of the provider that began the login.
        return_to: Validated path to send the user to after login.
        created_at: When the login began.
        state: The OAuth 2.0 ``state`` value.
        nonce: The OIDC ``nonce`` value.
        code_verifier: The PKCE code verifier.
        extra: Provider-specific values.
    """

    id: str
    provider: str
    return_to: str
    created_at: datetime
    state: str | None = None
    nonce: str | None = None
    code_verifier: str | None = None
    extra: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class LoginStart:
    """The result of :meth:`IdentityProvider.begin`.

    Attributes:
        transaction: The transaction to persist.
        redirect_url: Where to send the browser, or ``None`` when the provider
            takes a form instead, as password login does.
    """

    transaction: LoginTransaction
    redirect_url: str | None


@dataclass(frozen=True)
class SessionInfo:
    """The identity content of a login session; it holds no permissions.

    Attributes:
        account_id: The internal account ID.
        session_version: The account's session version at login.
        provider: ID of the provider that authenticated the session.
        issuer: The external identity's issuer.
        external_subject: The external identity's subject.
        auth_time: When the user authenticated.
        amr: How the user authenticated.
        session_ref: The OIDC ``sid``, used for logout.
        id_token: The ID token, kept only when RP-initiated logout is enabled.
        created_at: When the session started.
        expires_at: When the absolute timeout ends the session.
    """

    account_id: str
    session_version: int
    provider: str
    issuer: str
    external_subject: str
    created_at: datetime
    expires_at: datetime
    auth_time: datetime | None = None
    amr: frozenset[str] = frozenset()
    session_ref: str | None = None
    id_token: str | None = None


class LoginRequest(Protocol):
    """The part of a framework request that login providers read.

    A binding passes its native request when it has these two members, or a
    small adapter around it when it does not.

    Attributes:
        query: The URL query parameters; the provider's callback arrives here.
        form: The decoded form fields of a ``POST`` body, empty otherwise.
    """

    @property
    def query(self) -> Mapping[str, str]:
        """The URL query parameters."""
        ...

    @property
    def form(self) -> Mapping[str, str]:
        """The decoded form fields."""
        ...


@runtime_checkable
class IdentityProvider[RequestT](Protocol):
    """A login method, generic over the framework's native request type.

    Attributes:
        id: The configured provider ID.
        kind: The protocol family.
    """

    id: str
    kind: ProviderKind

    def begin(self, request: RequestT, *, return_to: str) -> LoginStart:
        """Return the redirect (or form) and the transaction to persist."""
        ...

    def complete(
        self, request: RequestT, transaction: LoginTransaction
    ) -> ExternalIdentity:
        """Validate the provider's response against *transaction*."""
        ...

    def logout_redirect(
        self, session: SessionInfo, *, post_logout_redirect: str
    ) -> str | None:
        """Return the provider's logout URL, or ``None`` for local logout only."""
        ...
