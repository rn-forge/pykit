"""Validation of the post-login ``return_to`` target."""

from __future__ import annotations

import re
from collections.abc import Sequence

from rn_forge.commons import AppException

__all__ = ["InvalidReturnTo", "validate_return_to"]

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_ENCODED_UNSAFE = re.compile(r"%(?:2f|5c|2e)", re.IGNORECASE)


class InvalidReturnTo(AppException):
    """A ``return_to`` value is not an allowed relative path.

    Callers catch it and fall back to a default target.

    Args:
        reason: A short description of the rule the value broke.
    """

    def __init__(self, reason: str) -> None:
        super().__init__("Invalid return_to: {}", reason, reason=reason)
        self.reason = reason


def validate_return_to(value: str, *, prefixes: Sequence[str]) -> str:
    """Return *value* when it is a relative path under one of *prefixes*.

    A prefix matches whole path segments: ``/app`` allows ``/app`` and
    ``/app/x`` but not ``/apple``, and ``/`` allows every path. A query string
    or fragment may follow the path.

    Args:
        value: The candidate target.
        prefixes: Allowed path prefixes, each starting with ``/``.

    Returns:
        *value*, unchanged.

    Raises:
        InvalidReturnTo: *value* is empty, is not a path starting with a single
            ``/``, contains a backslash or a control character, has a percent-
            encoded slash, backslash or dot in its path, has a ``..`` segment,
            or lies outside every prefix.
    """
    if not value:
        raise InvalidReturnTo("empty")
    if not value.startswith("/") or value.startswith("//"):
        raise InvalidReturnTo("not a relative path")
    if "\\" in value or _CONTROL.search(value):
        raise InvalidReturnTo("backslash or control character")
    path = value.split("?", 1)[0].split("#", 1)[0]
    if _ENCODED_UNSAFE.search(path):
        raise InvalidReturnTo("encoded slash, backslash or dot")
    if ".." in path.split("/"):
        raise InvalidReturnTo("path traversal")
    if not any(_under(path, prefix) for prefix in prefixes):
        raise InvalidReturnTo("outside the allowed prefixes")
    return value


def _under(path: str, prefix: str) -> bool:
    base = prefix.rstrip("/")
    return path == base or path.startswith(base + "/")
