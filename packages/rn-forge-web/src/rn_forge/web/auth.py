"""Framework-independent authentication wire contract.

Raw credentials, the ``Authorization`` header and the ``WWW-Authenticate``
challenge. Verification details must not be exposed in a 401 response.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

__all__ = [
    "AUTH_FAILED_DETAIL",
    "CSRF_FAILED_DETAIL",
    "BearerErrorCode",
    "Credentials",
    "challenge_header",
    "parse_authorization",
]

AUTH_FAILED_DETAIL: Final = "Authentication failed."
"""The non-sensitive detail returned for authentication failures."""

CSRF_FAILED_DETAIL: Final = "CSRF verification failed."
"""The detail returned for a CSRF rejection; it never names the check that failed."""

type BearerErrorCode = Literal["invalid_request", "invalid_token", "insufficient_scope"]
"""The ``error`` codes RFC 6750 §3 defines for a Bearer challenge."""


@dataclass(frozen=True)
class Credentials:
    """Raw credentials lifted off the request, before verification.

    ``scheme`` is the HTTP auth scheme as sent (``Bearer``, ``Basic``, ...) and
    ``token`` its parameter, verbatim. This is what a framework binding hands
    an authenticator; nothing here interprets it.
    """

    scheme: str
    token: str
    extras: Mapping[str, Any] = field(default_factory=dict[str, Any])


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


def parse_authorization(header: str | None, scheme: str) -> Credentials | None:
    """Return the *scheme* credentials in an ``Authorization`` header value.

    The scheme is matched case-insensitively (RFC 9110 §11.1) and the token
    is returned verbatim apart from surrounding whitespace — it may be empty.

    Args:
        header: The ``Authorization`` header value, or ``None`` when absent.
        scheme: The expected scheme, e.g. ``"Bearer"``.

    Returns:
        ``Credentials(scheme, token)``, or ``None`` when *header* is absent or
        names another scheme.
    """
    if not header:
        return None
    sent, _, token = header.partition(" ")
    if sent.lower() != scheme.lower():
        return None
    return Credentials(scheme, token.strip())


def _quote(value: str) -> str:
    """Escape a quoted-string parameter value (RFC 9110 §5.6.4)."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
