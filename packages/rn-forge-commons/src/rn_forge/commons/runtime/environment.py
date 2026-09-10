"""Typed environment-variable access, with fail-fast guards.

Provides :class:`Environment` — reading, writing and interpreting environment
variables, plus the ``require``/``forbid`` guards a process calls at startup so
that a misconfigured deployment fails at boot rather than at the first request.

All methods are static with no import-time side effects.
"""

from __future__ import annotations

import os
from typing import cast

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)

__all__ = ["Environment"]


class Environment:
    """Typed helpers for reading and writing environment variables.

    All methods are static.
    """

    @staticmethod
    def get_all() -> dict[str, str]:
        """Return a snapshot of all current environment variables."""
        return dict(os.environ)

    @staticmethod
    def get(name: str, default: str | None = None) -> str | None:
        """Return the value of *name*, or *default* if not set."""
        return os.environ.get(name, default)

    @staticmethod
    def set(name: str, value: str) -> str:
        """Set environment variable *name* to *value* and return *value*."""
        _LOGGER.info("Environment.set() | {} | {}", name, value)
        os.environ[name] = value
        return value

    @staticmethod
    def is_enabled(name: str, default: bool = False) -> bool:
        """Return ``True`` when env var *name* is a truthy string.

        Uses :func:`parse_bool` with ``strict=False``; unrecognised values
        fall back to *default*.
        """
        raw = os.environ.get(name)
        if raw is None:
            _LOGGER.trace(
                "Environment.is_enabled | name={} | raw=<unset> | using_default={}",
                name,
                default,
            )
            return default
        result = AppUtils.parse_bool(raw, strict=False)
        _LOGGER.trace(
            "Environment.is_enabled | name={} | parsed={} | used_default={}",
            name,
            result,
            result is None,
        )
        return result if result is not None else default

    @staticmethod
    def require(*names: str) -> dict[str, str]:
        """Return the values of *names*, raising if any is unset or blank.

        A set-but-empty/whitespace-only variable counts as missing, same as
        :meth:`AppUtils.is_empty`.

        Args:
            *names: Environment variable names that must all be present.

        Returns:
            A mapping of ``{name: value}`` for every requested variable.

        Raises:
            AppException: One or more variables are unset or empty. The
                message lists every missing name at once (not just the
                first), so a misconfigured deployment surfaces all problems
                in one run.

        Example::

            cfg = Environment.require("DB_URL", "SECRET_KEY")
        """
        values = {name: os.environ.get(name) for name in names}
        missing = sorted(
            name for name, value in values.items() if AppUtils.is_empty(value)
        )
        if missing:
            _LOGGER.warning("Environment.require | missing={}", missing)
            raise AppException(
                "Missing required environment variable(s): {}", ", ".join(missing)
            )
        return cast(dict[str, str], values)

    @staticmethod
    def forbid(name: str, *forbidden: str, message: str | None = None) -> None:
        """Raise if the value of *name* equals any of *forbidden*.

        Intended for "the insecure default is still in place" guards, e.g.
        ``Environment.forbid("SECRET_KEY", "change-me")``.

        Args:
            name: Environment variable to check.
            *forbidden: Values that must not be the current value of *name*.
            message: Custom exception message. Defaults to a generic one
                naming *name* and the matched value.

        Raises:
            AppException: The current value of *name* matches one of
                *forbidden*.
        """
        value = os.environ.get(name)
        if value in forbidden:
            _LOGGER.warning(
                "Environment.forbid | name={} | matched_forbidden_value=true", name
            )
            raise AppException(
                message or f"Environment variable {name!r} is set to a forbidden value"
            )
