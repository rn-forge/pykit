"""Admit a verified login to an account and session; the caller starts the session."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from rn_forge.auth.accounts import AccountRejected, AccountResolver
from rn_forge.auth.audit import audit
from rn_forge.auth.context import AuthorizationContextProvider
from rn_forge.auth.flow import CompletedLogin, LoginFailed
from rn_forge.auth.identity import SessionInfo
from rn_forge.auth.redirects import InvalidReturnTo, validate_return_to

__all__ = ["AdmittedLogin", "admit_login"]


@dataclass(frozen=True)
class AdmittedLogin:
    """The account, session content and destination for an admitted login.

    Attributes:
        account_id: The internal account ID.
        session: The identity content to use when starting the session.
        return_to: The validated destination after login.
    """

    account_id: str
    session: SessionInfo
    return_to: str


def admit_login(
    completed: CompletedLogin,
    *,
    provider_id: str,
    accounts: AccountResolver,
    contexts: AuthorizationContextProvider,
    now: datetime,
    absolute_timeout: timedelta,
    return_to_prefixes: Sequence[str],
    default_return_to: str,
) -> AdmittedLogin:
    """Resolve a verified login and build its session content.

    Emits ``account.rejected`` or ``account.disabled`` when admission is
    refused. It does not emit ``login.success`` or a log warning.

    Args:
        completed: The verified identity and requested destination.
        provider_id: The configured provider ID used by audit events.
        accounts: The resolver for external identities.
        contexts: The account context provider.
        now: The time the session starts.
        absolute_timeout: The session's absolute lifetime.
        return_to_prefixes: Path prefixes the destination may use.
        default_return_to: The destination used for an invalid path.

    Returns:
        The admitted account, session content and validated destination.

    Raises:
        LoginFailed: ``account_not_provisioned`` when the resolver rejects the
            identity, or ``access_denied`` when the account is inactive.
    """
    identity = completed.identity
    try:
        account_id = accounts.resolve(identity)
    except AccountRejected as exc:
        audit("account.rejected", provider=provider_id, reason=exc.reason)
        raise LoginFailed("account_not_provisioned", exc.reason) from exc

    context = contexts.resolve(account_id)
    if not context.active:
        audit("account.disabled", account_id=account_id, provider=provider_id)
        raise LoginFailed("access_denied", "account is not active")

    try:
        return_to = validate_return_to(completed.return_to, prefixes=return_to_prefixes)
    except InvalidReturnTo:
        return_to = default_return_to

    session = SessionInfo(
        account_id=account_id,
        session_version=context.session_version,
        provider=identity.provider,
        issuer=identity.issuer,
        external_subject=identity.subject,
        created_at=now,
        expires_at=now + absolute_timeout,
        auth_time=identity.auth_time,
        amr=identity.amr,
        session_ref=identity.session_ref,
        id_token=identity.id_token,
    )
    return AdmittedLogin(account_id, session, return_to)
