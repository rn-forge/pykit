"""Account resolution contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rn_forge.auth.identity import ExternalIdentity
from rn_forge.commons import AppException

__all__ = ["AccountRejected", "AccountResolver"]


class AccountRejected(AppException):
    """A login was refused by the :class:`AccountResolver`.

    The reason is for logs and is never shown to the user.

    Args:
        reason: A short description of why the login was refused.
    """

    def __init__(self, reason: str) -> None:
        super().__init__("Account rejected: {}", reason, reason=reason)
        self.reason = reason


@runtime_checkable
class AccountResolver(Protocol):
    """Maps an external identity to an internal account."""

    def resolve(self, identity: ExternalIdentity) -> str:
        """Link, provision or reject a login, and return the account ID.

        Raises:
            AccountRejected: The login may not proceed.
        """
        ...

    def lookup(self, issuer: str, subject: str) -> str | None:
        """Return the account ID linked to *issuer* and *subject*, if any.

        Never provisions.
        """
        ...
