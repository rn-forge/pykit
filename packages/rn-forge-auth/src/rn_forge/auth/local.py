"""Local password and development login providers.

Both are :class:`~rn_forge.auth.identity.IdentityProvider` implementations
over :class:`~rn_forge.auth.identity.LoginRequest` and need no extra. A failed login
raises :class:`~rn_forge.auth.flow.LoginFailed` with code ``login_failed``.
"""

from __future__ import annotations

import html
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

from rn_forge.auth.flow import LoginFailed
from rn_forge.auth.identity import (
    ExternalIdentity,
    LoginRequest,
    LoginStart,
    LoginTransaction,
    ProviderKind,
    SessionInfo,
)

__all__ = [
    "DevelopmentAccount",
    "DevelopmentIdentityProvider",
    "DevelopmentModeRequired",
    "PasswordIdentityProvider",
    "PasswordVerifier",
]


class PasswordVerifier(Protocol):
    """Checks a username and password against the application's accounts."""

    def __call__(self, username: str, password: str) -> str | None:
        """Return the account's stable subject, or ``None`` when the account
        is unknown or the password is wrong."""
        ...


class DevelopmentModeRequired(RuntimeError):
    """The development provider was constructed without declaring debug mode."""


INVALID_CREDENTIALS = "invalid credentials"


def _start(provider: str, return_to: str) -> LoginStart:
    transaction = LoginTransaction(
        id=secrets.token_urlsafe(32),
        provider=provider,
        return_to=return_to,
        created_at=datetime.now(UTC),
    )
    return LoginStart(transaction=transaction, redirect_url=None)


class PasswordIdentityProvider:
    """Username and password login against an application-supplied verifier.

    The login is a form, so :meth:`begin` returns no redirect. Rate limiting
    belongs to the framework binding. The password is never logged or kept.

    Attributes:
        id: The configured provider ID.
        kind: Always ``"password"``.
    """

    kind: ProviderKind = "password"

    def __init__(self, verifier: PasswordVerifier, *, id: str = "password") -> None:
        self.id = id
        self._verifier = verifier

    def begin(self, request: LoginRequest, *, return_to: str) -> LoginStart:
        """Return a transaction with no redirect."""
        return _start(self.id, return_to)

    def complete(
        self, request: LoginRequest, transaction: LoginTransaction
    ) -> ExternalIdentity:
        """Verify the ``username`` and ``password`` form fields.

        Returns:
            An identity with issuer ``"local"`` and ``amr`` of ``{"pwd"}``.

        Raises:
            LoginFailed: The fields are missing, the account is unknown or the
                password is wrong.
        """
        username = request.form.get("username")
        password = request.form.get("password")
        subject = (
            self._verifier(username, password)
            if username is not None and password is not None
            else None
        )
        if not subject:
            raise LoginFailed("login_failed", INVALID_CREDENTIALS)
        return ExternalIdentity(
            provider=self.id,
            issuer="local",
            subject=subject,
            auth_time=datetime.now(UTC),
            amr=frozenset({"pwd"}),
        )

    def logout_redirect(
        self, session: SessionInfo, *, post_logout_redirect: str
    ) -> str | None:
        """Return ``None``; logout is local only."""
        return None


@dataclass(frozen=True)
class DevelopmentAccount:
    """A fixture account the development provider offers.

    Attributes:
        subject: The stable subject; also the value of the ``account``
            parameter that selects the account.
        email: Email address.
        name: Display name, also the link text when set.
        groups: Group names.
        attributes: Other mapped claims.
    """

    subject: str
    email: str | None = None
    name: str | None = None
    groups: frozenset[str] = frozenset()
    attributes: Mapping[str, Any] = field(default_factory=dict[str, Any])


class DevelopmentIdentityProvider:
    """Sign in as a fixture account; for local development only.

    Construction fails unless ``debug`` is true. :meth:`render_accounts`
    produces this markup, with every value HTML-escaped::

        <ul data-rn-forge-dev-accounts>
        <li><a href="LOGIN_URL?account=SUBJECT" data-account="SUBJECT">LABEL</a></li>
        </ul>

    ``?`` becomes ``&`` when ``LOGIN_URL`` already has a query string.
    ``LABEL`` is the account's name, or its subject when it has none. The
    identity carries issuer ``"development"`` and ``amr`` of ``{"dev"}``.
    :meth:`complete` reads the ``account`` form field, falling back to the
    ``account`` query parameter.

    Attributes:
        id: The configured provider ID.
        kind: Always ``"development"``.

    Raises:
        DevelopmentModeRequired: ``debug`` is not true.
    """

    kind: ProviderKind = "development"

    def __init__(
        self,
        accounts: Iterable[DevelopmentAccount],
        *,
        debug: bool,
        id: str = "development",
    ) -> None:
        if debug is not True:
            raise DevelopmentModeRequired(
                "the development provider requires debug mode"
            )
        self.id = id
        self._accounts = {account.subject: account for account in accounts}

    def render_accounts(self, *, login_url: str) -> str:
        """Return the account list, each link pointing at *login_url*."""
        separator = "&" if "?" in login_url else "?"
        items = "\n".join(
            f'<li><a href="{html.escape(login_url + separator)}account='
            f'{html.escape(quote(account.subject, safe=""))}" '
            f'data-account="{html.escape(account.subject)}">'
            f"{html.escape(account.name or account.subject)}</a></li>"
            for account in self._accounts.values()
        )
        return f"<ul data-rn-forge-dev-accounts>\n{items}\n</ul>"

    def begin(self, request: LoginRequest, *, return_to: str) -> LoginStart:
        """Return a transaction with no redirect."""
        return _start(self.id, return_to)

    def complete(
        self, request: LoginRequest, transaction: LoginTransaction
    ) -> ExternalIdentity:
        """Sign in as the account named by the ``account`` parameter.

        Raises:
            LoginFailed: The parameter is missing or names no fixture account.
        """
        subject = request.form.get("account") or request.query.get("account")
        account = self._accounts.get(subject) if subject else None
        if account is None:
            raise LoginFailed("login_failed", INVALID_CREDENTIALS)
        return ExternalIdentity(
            provider=self.id,
            issuer="development",
            subject=account.subject,
            email=account.email,
            name=account.name,
            groups=account.groups,
            attributes=account.attributes,
            auth_time=datetime.now(UTC),
            amr=frozenset({"dev"}),
        )

    def logout_redirect(
        self, session: SessionInfo, *, post_logout_redirect: str
    ) -> str | None:
        """Return ``None``; logout is local only."""
        return None
