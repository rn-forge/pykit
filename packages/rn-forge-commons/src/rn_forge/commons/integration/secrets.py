"""Secret-access protocols: fail fast on a missing secret, never on a silent default.

Missing keys raise :class:`SecretNotFound`; they never return ``None`` and risk
silently substituting an insecure default.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from rn_forge.commons.exceptions import AppException

__all__ = ["AsyncSecretStore", "EnvSecretStore", "SecretNotFound", "SecretStore"]


class SecretNotFound(AppException):
    """The named secret does not exist in the backing store."""


@runtime_checkable
class SecretStore(Protocol):
    """A synchronous secret-lookup protocol."""

    def get_secret(self, key: str) -> str:
        """Return the secret value for *key*.

        Raises:
            SecretNotFound: No secret exists for *key*.
        """
        ...


@runtime_checkable
class AsyncSecretStore(Protocol):
    """The async counterpart of :class:`SecretStore`."""

    async def get_secret(self, key: str) -> str:
        """Return the secret value for *key*.

        Raises:
            SecretNotFound: No secret exists for *key*.
        """
        ...


class EnvSecretStore:
    """Reads secrets from the process environment. The local/dev default.

    ``get_secret("db-password")`` reads ``DB_PASSWORD`` — the key is
    upper-cased, ``-`` is replaced with ``_``, and *prefix* (upper-cased, with
    a trailing ``_`` if not already present) is prepended.
    """

    def __init__(self, *, prefix: str = "") -> None:
        """Initialize :class:`EnvSecretStore`.

        Args:
            prefix: Prepended to every environment variable name looked up,
                e.g. ``prefix="myapp"`` maps ``get_secret("db-password")`` to
                ``MYAPP_DB_PASSWORD``.
        """
        prefix = prefix.upper().replace("-", "_")
        self._prefix = f"{prefix}_" if prefix and not prefix.endswith("_") else prefix

    def get_secret(self, key: str) -> str:
        """Return the environment variable value mapped from *key*.

        Raises:
            SecretNotFound: The mapped environment variable is unset or blank.
        """
        env_name = f"{self._prefix}{key.upper().replace('-', '_')}"
        value = os.environ.get(env_name)
        if not value or not value.strip():
            raise SecretNotFound(
                "No secret found for key {} (environment variable {})", key, env_name
            )
        return value
