"""Secret redaction for structured log values.

:func:`redact` returns a copy of a value with secrets replaced by
:data:`REDACTED`. A :class:`RedactionPolicy` selects what counts as a secret:

- **Keys.** A value stored under a key matching ``field_pattern`` is replaced
  wholesale, whatever its type, except ``None`` and ``""``, which are kept.
  :meth:`RedactionPolicy.default` matches a key whose final segment is
  ``authorization``, ``cookie``, ``password``, ``secret`` or ``token`` (plural
  allowed), case-insensitively. Segments split on ``_``, ``-``, ``.`` and a
  camelCase boundary, so ``access_token`` and ``accessToken`` match while
  ``token_count`` does not.
- **Values.** Any string, under any key, has the credential in
  ``Bearer <token>`` and ``Basic <credential>`` replaced when
  ``scrub_credentials`` is set, and the password in ``scheme://user:password@host``
  replaced when ``scrub_url_passwords`` is set. A credential must contain a
  digit, a symbol or an inner capital; a plain word after the scheme is kept.

Dicts, lists and tuples are rebuilt, at any depth; the input is never mutated.
Exception tracebacks are not inspected.
"""

# Exemption to design principle 1 (ADR-0001): no maintained library redacts
# structured values without a heavy dependency, so this is hand-rolled.

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

__all__ = ["REDACTED", "RedactionPolicy", "redact"]

REDACTED: Final = "[redacted]"
"""The replacement for a redacted value."""

_DEFAULT_FIELD_PATTERN: Final = re.compile(
    r"(?:^|[_.-]|(?-i:(?<=[a-z])(?=[A-Z])))"
    r"(?:authorization|cookie|password|secret|token)s?$",
    re.IGNORECASE,
)
# A credential must hold a digit, a symbol or an inner capital; a plain word after
# the scheme is prose ("bearer token expired", "basic authentication failed").
_CREDENTIAL: Final = re.compile(
    r"\b((?:Bearer|Basic)\s+)(?=\S*(?:[0-9+/_=~-]|(?-i:[a-z][A-Z])))\S+",
    re.IGNORECASE,
)
_URL_PASSWORD: Final = re.compile(
    r"(\b[A-Za-z][A-Za-z0-9+.-]*://[^\s:/@]*:)[^\s@/]+(?=@)"
)


@dataclass(frozen=True)
class RedactionPolicy:
    """What :func:`redact` treats as a secret.

    Attributes:
        field_pattern: Searched against a key; a match redacts the key's value.
        scrub_credentials: Replace the credential in ``Bearer <token>`` and
            ``Basic <credential>`` inside string values.
        scrub_url_passwords: Replace the password in
            ``scheme://user:password@host`` inside string values.
    """

    field_pattern: re.Pattern[str]
    scrub_credentials: bool = True
    scrub_url_passwords: bool = True

    @classmethod
    def default(cls) -> RedactionPolicy:
        """Return the policy described in the module docstring."""
        return cls(field_pattern=_DEFAULT_FIELD_PATTERN)

    def scrub(self, text: str) -> str:
        """Return *text* with credentials and URL passwords replaced."""
        if self.scrub_credentials:
            text = _CREDENTIAL.sub(lambda m: m.group(1) + REDACTED, text)
        if self.scrub_url_passwords:
            text = _URL_PASSWORD.sub(lambda m: m.group(1) + REDACTED, text)
        return text


def redact(value: Any, *, policy: RedactionPolicy | None = None, key: str = "") -> Any:
    """Return a copy of *value* with secrets replaced by :data:`REDACTED`.

    Args:
        value: A scalar, or a dict, list or tuple nested to any depth. Other
            types are returned unchanged.
        policy: What to redact. Defaults to :meth:`RedactionPolicy.default`.
        key: The key *value* is stored under, if any.

    Returns:
        *value* unchanged when *key* does not match, otherwise a redacted copy.
        A value under a matching *key* becomes :data:`REDACTED` unless it is
        ``None`` or ``""``.

    Example::

        redact({"user": "ann", "password": "hunter2"})
        # {'user': 'ann', 'password': '[redacted]'}
    """
    return _redact(value, policy or RedactionPolicy.default(), key)


def _redact(value: Any, policy: RedactionPolicy, key: str) -> Any:
    if key and policy.field_pattern.search(key):
        return value if value is None or value == "" else REDACTED
    if isinstance(value, str):
        return policy.scrub(value)
    if isinstance(value, Mapping):
        return {
            k: _redact(v, policy, k if isinstance(k, str) else str(k))
            for k, v in cast("Mapping[Any, Any]", value).items()
        }
    if isinstance(value, list):
        return [_redact(v, policy, "") for v in cast("list[Any]", value)]
    if isinstance(value, tuple):
        return tuple(_redact(v, policy, "") for v in cast("tuple[Any, ...]", value))
    return value
