"""Projection from authenticated identities to authorization principals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from rn_forge.auth.accounts import AccountResolver
from rn_forge.auth.context import AuthorizationContext, AuthorizationContextProvider
from rn_forge.auth.identity import SessionInfo
from rn_forge.auth.permissions import effective_permissions
from rn_forge.auth.principal import Principal

__all__ = ["PrincipalLinkError", "link_bearer_principal", "session_principal"]


class PrincipalLinkError(Exception):
    """An authenticated identity cannot be linked to an active account.

    Args:
        reason: The reason linking failed; also the exception message.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def link_bearer_principal(
    principal: Principal,
    *,
    accounts: AccountResolver,
    contexts: AuthorizationContextProvider,
    scope_map: Mapping[str, frozenset[str]],
) -> Principal:
    """Link a verified bearer principal to its active account and permissions.

    Raises:
        PrincipalLinkError: The issuer is absent, no account is linked, or the
            linked account is inactive.
    """
    if not principal.issuer:
        raise PrincipalLinkError("No account is linked to the token subject")
    account_id = accounts.lookup(principal.issuer, principal.subject)
    if account_id is None:
        raise PrincipalLinkError("No account is linked to the token subject")
    context = contexts.resolve(account_id)
    if not context.active:
        raise PrincipalLinkError("The account is not active")
    return replace(
        principal,
        subject=account_id,
        external_subject=principal.subject,
        permissions=effective_permissions(
            context.permissions,
            mechanism="bearer",
            scopes=principal.scopes,
            scope_map=scope_map,
        ),
        roles=context.roles,
        tenant=_tenant(context),
        attributes=context.attributes,
    )


def session_principal(info: SessionInfo, context: AuthorizationContext) -> Principal:
    """Build a session principal from its stored identity and current context."""
    return Principal(
        subject=info.account_id,
        issuer=info.issuer,
        external_subject=info.external_subject,
        permissions=context.permissions,
        roles=context.roles,
        tenant=_tenant(context),
        attributes=context.attributes,
        mechanism="session",
        auth_time=info.auth_time,
        amr=info.amr,
    )


def _tenant(context: AuthorizationContext) -> str | None:
    tenant = context.attributes.get("tenant")
    return tenant if isinstance(tenant, str) else None
