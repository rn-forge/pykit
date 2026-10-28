"""The default :class:`~rn_forge.auth.AccountResolver` on Django's user model."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, transaction
from django.db.models import F
from rn_forge.auth import AccountRejected, ExternalIdentity
from rn_forge.auth.audit import audit
from rn_forge.django.auth.models import AccountState, ExternalAccount

__all__ = [
    "DjangoAccountResolver",
    "DjangoAccountStateWriter",
    "ProviderPolicy",
    "account_session_version",
]


@dataclass(frozen=True)
class ProviderPolicy:
    """How logins from one provider are linked and provisioned.

    Attributes:
        provisioning: ``existing`` rejects a user with no account; ``jit``
            creates the account on first login.
        email_domains: With ``jit``, the email domains that may be provisioned.
            Empty allows any. A non-empty allowlist also requires a verified
            email.
        authoritative_domains: Email domains for which this provider is
            authoritative: a verified email in one links to the existing user
            with that address.
    """

    provisioning: Literal["existing", "jit"] = "existing"
    email_domains: frozenset[str] = frozenset()
    authoritative_domains: frozenset[str] = frozenset()


def account_session_version(user: AbstractUser) -> int:
    """The session version of *user*; ``0`` before the first bump."""
    return (
        AccountState.objects.filter(user=user)
        .values_list("session_version", flat=True)
        .first()
        or 0
    )


def _domain(email: str | None) -> str:
    return email.rpartition("@")[2].lower() if email else ""


class DjangoAccountResolver:
    """Links, provisions or rejects external identities as Django users.

    An identity already linked on ``(issuer, subject)`` resolves to its user.
    Otherwise a verified email in one of the provider's
    :attr:`~ProviderPolicy.authoritative_domains` links to the user with that
    address (case-insensitively, and only when exactly one matches). Otherwise
    the provider's ``jit`` policy provisions a user, and ``existing`` rejects.
    An unverified email never links and is never stored on a provisioned user.
    A provider with no policy is rejected.

    Args:
        policies: The policy of each provider, by provider ID.
        sync: Called with the user and the identity at every successful login,
            inside the transaction, to copy attributes onto the user. It must
            save what it changes.
    """

    def __init__(
        self,
        policies: Mapping[str, ProviderPolicy],
        *,
        sync: Callable[[AbstractUser, ExternalIdentity], None] | None = None,
    ) -> None:
        self._policies = policies
        self._sync = sync

    def resolve(self, identity: ExternalIdentity) -> str:
        """Return the account ID of *identity*.

        Raises:
            AccountRejected: The provider has no policy, or the policy refuses
                the identity.
        """
        policy = self._policies.get(identity.provider)
        if policy is None:
            raise AccountRejected(f"no policy for provider {identity.provider}")
        try:
            with transaction.atomic():
                user = self._user_for(identity, policy)
                if self._sync is not None:
                    self._sync(user, identity)
        except IntegrityError:
            # A concurrent first login created the link.
            user = self._linked(identity.issuer, identity.subject)
            if user is None:
                raise
        return str(user.pk)

    def lookup(self, issuer: str, subject: str) -> str | None:
        """Return the account ID linked to *issuer* and *subject*, if any."""
        user = self._linked(issuer, subject)
        return str(user.pk) if user is not None else None

    def link(
        self, issuer: str, subject: str, user: AbstractUser, *, provider: str = ""
    ) -> None:
        """Link *issuer* and *subject* to *user*, such as a service account.

        Raises:
            IntegrityError: The pair is already linked.
        """
        ExternalAccount.objects.create(
            issuer=issuer, subject=subject, user=user, provider=provider
        )

    def _user_for(
        self, identity: ExternalIdentity, policy: ProviderPolicy
    ) -> AbstractUser:
        user = self._linked(identity.issuer, identity.subject)
        if user is not None:
            return user
        domain = _domain(identity.email)
        verified = identity.email_verified and bool(domain)
        if verified and domain in policy.authoritative_domains:
            user = self._by_email(cast(str, identity.email))
        if user is None:
            if policy.provisioning != "jit":
                raise AccountRejected("no account for this identity")
            if policy.email_domains and not (
                verified and domain in policy.email_domains
            ):
                raise AccountRejected("email domain is not allowed")
            user = self._provision(identity, verified)
        self.link(identity.issuer, identity.subject, user, provider=identity.provider)
        return user

    @staticmethod
    def _linked(issuer: str, subject: str) -> AbstractUser | None:
        link = (
            ExternalAccount.objects.select_related("user")
            .filter(issuer=issuer, subject=subject)
            .first()
        )
        return cast(AbstractUser, link.user) if link is not None else None

    @staticmethod
    def _by_email(email: str) -> AbstractUser | None:
        users = list(
            _user_model()._default_manager.filter(email__iexact=email)[:2]
        )  # Django's documented manager access
        if len(users) > 1:
            raise AccountRejected("email matches more than one account")
        return users[0] if users else None

    @staticmethod
    def _provision(identity: ExternalIdentity, verified: bool) -> AbstractUser:
        user = _user_model()(
            **{_user_model().USERNAME_FIELD: uuid.uuid4().hex},
            email=identity.email if verified else "",
        )
        user.set_unusable_password()
        user.save()
        account_id, provider = str(user.pk), identity.provider
        # A first-login race rolls the loser back; only a committed account is audited.
        transaction.on_commit(
            lambda: audit(
                "account.provisioned", account_id=account_id, provider=provider
            )
        )
        return user


def _user_model() -> type[AbstractUser]:
    return cast(type[AbstractUser], get_user_model())


class DjangoAccountStateWriter:
    """The :class:`~rn_forge.auth.AccountStateWriter` for Django users."""

    def set_active(self, account_id: str, active: bool) -> None:
        """Store whether the user may authenticate."""
        _user_model()._default_manager.filter(pk=account_id).update(
            is_active=active
        )  # Django's documented manager access
        if not active:
            audit("account.disabled", account_id=account_id)

    def bump_session_version(self, account_id: str) -> int:
        """Increase the user's session version and return the new one."""
        with transaction.atomic():
            state, _ = AccountState.objects.get_or_create(user_id=account_id)
            AccountState.objects.filter(pk=state.pk).update(
                session_version=F("session_version") + 1
            )
            state.refresh_from_db()
        return state.session_version
