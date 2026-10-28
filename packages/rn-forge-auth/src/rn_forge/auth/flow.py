"""The login flow over a set of providers and a transaction store.

A framework binding mounts :class:`LoginFlow` at its login and callback routes:
it puts ``LoginStart.transaction.id`` in the transaction cookie after
:meth:`LoginFlow.begin`, and reads the cookie back for
:meth:`LoginFlow.complete`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

from rn_forge.auth.identity import ExternalIdentity, IdentityProvider, LoginStart
from rn_forge.auth.redirects import InvalidReturnTo, validate_return_to
from rn_forge.auth.session_body import CallbackError
from rn_forge.auth.stores import TransactionStore
from rn_forge.commons import AppException

__all__ = ["CompletedLogin", "LoginFailed", "LoginFlow"]

_logger = logging.getLogger(__name__)

DEFAULT_TRANSACTION_TTL = timedelta(seconds=600)


class LoginFailed(AppException):
    """A login did not complete.

    :attr:`reason` is for logs: it must not reach the user. :attr:`code` is what
    the error route receives.

    Args:
        code: The callback error code.
        reason: Why the login failed.

    Attributes:
        code: The callback error code.
        reason: Why the login failed.
    """

    def __init__(self, code: CallbackError, reason: str) -> None:
        super().__init__("Login failed ({}): {}", code, reason, code=code)
        self.code: CallbackError = code
        self.reason = reason


@dataclass(frozen=True)
class CompletedLogin:
    """A verified login and where to send the user next.

    Attributes:
        identity: The verified identity.
        return_to: The consumed transaction's ``return_to``, validated when the
            login began.
    """

    identity: ExternalIdentity
    return_to: str


class LoginFlow[RequestT]:
    """Begins and completes logins for the configured providers.

    Args:
        providers: The identity providers, by provider ID.
        transactions: Holds each login between its redirect and its callback.
        return_to_prefixes: Path prefixes a ``return_to`` may lie under.
        ttl: How long a login may take between its two legs.
    """

    def __init__(
        self,
        providers: Mapping[str, IdentityProvider[RequestT]],
        transactions: TransactionStore,
        *,
        return_to_prefixes: Sequence[str],
        ttl: timedelta = DEFAULT_TRANSACTION_TTL,
    ) -> None:
        self._providers = dict(providers)
        self._transactions = transactions
        self._prefixes = list(return_to_prefixes)
        self._ttl = ttl

    def begin(
        self, provider_id: str, request: RequestT, *, return_to: str
    ) -> LoginStart:
        """Start a login and save its transaction.

        Args:
            provider_id: The provider to log in with.
            request: The framework's native request.
            return_to: Where to send the user after login.

        Returns:
            The provider's redirect (or form) and the saved transaction; the
            caller carries ``transaction.id`` in the transaction cookie.

        Raises:
            LoginFailed: The provider is unknown, *return_to* is not an allowed
                path, or the provider could not begin.
        """
        provider = self._provider(provider_id)
        try:
            validate_return_to(return_to, prefixes=self._prefixes)
        except InvalidReturnTo as exc:
            raise self._fail("login_failed", provider_id, exc.reason) from exc
        try:
            start = provider.begin(request, return_to=return_to)
        except LoginFailed as exc:
            _logger.warning("Login with %s failed: %s", provider_id, exc.reason)
            raise
        except Exception as exc:
            raise self._unexpected(provider_id, "begin", exc) from exc
        self._transactions.save(start.transaction, ttl=self._ttl)
        return start

    def complete(
        self, provider_id: str, request: RequestT, *, transaction_id: str | None
    ) -> CompletedLogin:
        """Finish a login.

        The transaction is consumed whatever the outcome, so a callback works
        once.

        Args:
            provider_id: The provider the callback came to.
            request: The framework's native request.
            transaction_id: The ID from the browser's transaction cookie, or
                ``None`` when it sent none.

        Returns:
            The verified identity and the transaction's ``return_to``.

        Raises:
            LoginFailed: The transaction is missing, expired, already consumed
                or belongs to another provider, or the provider rejected the
                response.
        """
        provider = self._provider(provider_id)
        if not transaction_id:
            raise self._fail("login_failed", provider_id, "no transaction cookie")
        transaction = self._transactions.consume(transaction_id)
        if transaction is None:
            raise self._fail(
                "login_failed", provider_id, "transaction missing, expired or used"
            )
        if transaction.provider != provider_id:
            raise self._fail(
                "login_failed",
                provider_id,
                f"transaction belongs to provider {transaction.provider}",
            )
        try:
            identity = provider.complete(request, transaction)
        except LoginFailed as exc:
            _logger.warning("Login with %s failed: %s", provider_id, exc.reason)
            raise
        except Exception as exc:
            raise self._unexpected(provider_id, "complete", exc) from exc
        return CompletedLogin(identity, transaction.return_to)

    def _provider(self, provider_id: str) -> IdentityProvider[RequestT]:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise self._fail("login_failed", provider_id, "unknown provider")
        return provider

    @staticmethod
    def _fail(code: CallbackError, provider_id: str, reason: str) -> LoginFailed:
        _logger.warning("Login with %s failed: %s", provider_id, reason)
        return LoginFailed(code, reason)

    @staticmethod
    def _unexpected(provider_id: str, step: str, exc: Exception) -> LoginFailed:
        _logger.warning(
            "Login with %s failed at %s: %r", provider_id, step, exc, exc_info=exc
        )
        return LoginFailed("login_failed", f"provider error at {step}")
