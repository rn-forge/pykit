"""General-purpose utilities: environment access, base64, filesystem, and value helpers.

Provides:

- :class:`Environment` — typed env-var access with boolean interpretation.
- :class:`Base64` — encode/decode helpers that accept ``str`` or ``bytes``.
- :class:`PathUtils` — filesystem helpers (write, delete, temp dir) with
  automatic parent-directory creation.
- :class:`AppUtils` — value and import utilities: bool parsing, emptiness
  checks, dynamic imports, attribute access, and string joining.

All methods are static with no import-time side effects.
"""

from __future__ import annotations

import base64
import importlib
import numbers
import os
import shutil
import tempfile
from operator import attrgetter
from pathlib import Path
from collections.abc import Sized
from typing import Any, Callable, Sequence, cast

from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)

__all__ = [
    "AppUtils",
    "Base64",
    "Environment",
    "PathUtils",
]


# ---------------------------------------------------------------------------
# Environment — env-var access helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Base64 — encode / decode helpers
# ---------------------------------------------------------------------------


class Base64:
    """Base64 encode/decode utilities that accept ``str`` or ``bytes`` input.

    All methods are static.
    """

    @staticmethod
    def encode(value: str | bytes) -> str:
        """Return the base64-encoded string for *value*."""
        b = value if isinstance(value, bytes) else str(value).encode()
        return base64.b64encode(b).decode()

    @staticmethod
    def decode(value: str | bytes) -> bytes:
        """Return the raw bytes decoded from the base64 *value*."""
        b = value if isinstance(value, bytes) else str(value).encode()
        return base64.b64decode(b)

    @staticmethod
    def decode_to_string(value: str | bytes, encoding: str = "utf-8") -> str:
        """Decode the base64 *value* and return it as a string."""
        return Base64.decode(value).decode(encoding)


# ---------------------------------------------------------------------------
# PathUtils — filesystem helpers
# ---------------------------------------------------------------------------


class PathUtils:
    """Filesystem helpers with automatic parent-directory creation.

    All methods are static.
    """

    @staticmethod
    def temp_dir() -> Path:
        """Return the system's temporary directory as a :class:`~pathlib.Path`."""
        return Path(tempfile.gettempdir())

    @staticmethod
    def write_file(content: str | bytes, path: str | Path, **kwargs: Any) -> Path:
        """Write *content* to *path*, creating parent directories as needed.

        Args:
            content: Text or binary data to write.
            path: Destination file path.
            **kwargs: Forwarded to :meth:`~pathlib.Path.write_text` (e.g.
                ``encoding``).  Ignored for binary writes.

        Returns:
            The resolved :class:`~pathlib.Path` that was written.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        _LOGGER.verbose("Writing file: {}", p)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding=kwargs.get("encoding"))
        return p

    @staticmethod
    def delete(
        path: str | Path,
        *,
        ignore_missing: bool = True,
    ) -> None:
        """Delete a file or directory tree at *path*.

        Files and symlinks are removed with :meth:`~pathlib.Path.unlink`;
        directories are removed recursively with :func:`shutil.rmtree`.

        Args:
            path: Target file or directory to delete.
            ignore_missing: When ``True`` (default), silently return if *path*
                does not exist.  When ``False``, raise
                :exc:`FileNotFoundError`.

        Raises:
            FileNotFoundError: If *path* does not exist and
                ``ignore_missing=False``.
        """
        p = Path(path)
        if not p.exists():
            _LOGGER.verbose("Path does not exist: {}", p)
            if ignore_missing:
                return
            raise FileNotFoundError(f"Path does not exist: {p}")
        if p.is_file() or p.is_symlink():
            _LOGGER.warning("Removing file: {}", p)
            p.unlink()
        else:
            _LOGGER.warning("Removing directory: {}", p)
            shutil.rmtree(p)


# ---------------------------------------------------------------------------
# AppUtils — value and import helpers
# ---------------------------------------------------------------------------


class AppUtils:
    """General-purpose value and import utilities.

    All methods are static.
    """

    @staticmethod
    def parse_bool(value: Any, *, strict: bool = True) -> bool | None:
        """Convert a value to ``bool`` using common truthy/falsy string tokens.

        Recognises (case-insensitive):

        - Truthy: ``"true"``, ``"yes"``, ``"enabled"``
        - Falsy: ``"false"``, ``"no"``, ``"disabled"``, ``"none"``

        Args:
            value: The value to convert.  ``bool`` instances are returned
                unchanged without any string conversion.
            strict: When ``True`` (default), raise :exc:`ValueError` for
                unrecognised strings.  When ``False``, return ``None``
                instead.

        Returns:
            ``True``, ``False``, or ``None`` (only possible when
            ``strict=False``).

        Raises:
            ValueError: If *value* does not match any recognised token and
                ``strict=True``.

        Example::

            AppUtils.parse_bool("yes")      # True
            AppUtils.parse_bool("DISABLED") # False
            AppUtils.parse_bool("maybe", strict=False)  # None
        """
        if isinstance(value, bool):
            _LOGGER.trace("AppUtils.parse_bool | type=bool | result={}", value)
            return value

        text = str(value).strip().lower()
        if text in {"true", "yes", "enabled"}:
            _LOGGER.trace("AppUtils.parse_bool | token={} | result=True", text)
            return True
        if text in {"false", "no", "disabled", "none"}:
            _LOGGER.trace("AppUtils.parse_bool | token={} | result=False", text)
            return False

        if strict:
            _LOGGER.warning(
                "AppUtils.parse_bool | token={} | strict_failure=true", text
            )
            raise ValueError(f"Cannot parse {value!r} as bool")
        _LOGGER.trace("AppUtils.parse_bool | token={} | result=None", text)
        return None

    @staticmethod
    def is_empty(value: Any) -> bool:
        """Return ``True`` when *value* is considered empty.

        Rules:

        - ``None`` → ``True``
        - numbers and booleans → always ``False``
        - strings → ``True`` when blank (whitespace-only)
        - sequences and mappings → ``True`` when ``len == 0``
        - other objects → ``bool(value)`` inverted
        """
        if value is None:
            return True
        if isinstance(value, (numbers.Number, bool)):
            return False
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, Sized):
            return len(value) == 0
        return not bool(value)

    @staticmethod
    def get_or_default(value: Any, default: Any = None) -> Any:
        """Return *value* if it is not empty, otherwise *default*.

        Uses :meth:`is_empty` to test emptiness.
        """
        return default if AppUtils.is_empty(value) else value

    @staticmethod
    def import_string(qualname: str, package: str | None = None) -> Any:
        """Import and return an object by its fully-qualified dotted name.

        Args:
            qualname: Dotted path to the target, e.g. ``"os.path.join"`` or
                ``".submodule.MyClass"`` for relative imports.
            package: Required when *qualname* starts with ``"."`` (relative
                import).  Defaults to ``None``.

        Returns:
            The imported object (function, class, constant, etc.).

        Raises:
            ImportError: If *qualname* is malformed, the module cannot be
                imported, or the attribute does not exist on the module.

        Example::

            join = AppUtils.import_string("os.path.join")
            join("/tmp", "file.txt")  # "/tmp/file.txt"
        """
        if qualname.startswith(".") and package is None:
            _LOGGER.warning(
                "AppUtils.import_string | qualname={} | missing_package_for_relative_import=true",
                qualname,
            )
            raise ImportError(
                f"Package name is required for relative import: {qualname!r}"
            )
        _LOGGER.debug(
            "AppUtils.import_string | qualname={} | package={}",
            qualname,
            package,
        )
        try:
            module_path, attr_name = qualname.rsplit(".", 1)
        except ValueError as exc:
            _LOGGER.warning(
                "AppUtils.import_string | qualname={} | invalid_qualified_name=true",
                qualname,
            )
            raise ImportError(f"Invalid qualified name: {qualname!r}") from exc

        try:
            module = importlib.import_module(module_path, package)
        except Exception:
            _LOGGER.exception(
                "AppUtils.import_string failed | module_path={} | package={}",
                module_path,
                package,
            )
            raise
        try:
            return getattr(module, attr_name)
        except AttributeError as exc:
            _LOGGER.warning(
                "AppUtils.import_string | module_path={} | missing_attr={}",
                module_path,
                attr_name,
            )
            raise ImportError(
                f"Cannot import {attr_name!r} from module {module_path!r}"
            ) from exc

    @staticmethod
    def null_safe_attrgetter(*paths: str, default: Any = None) -> Callable[[Any], Any]:
        """Return a callable that safely retrieves one or more attributes.

        Wraps :func:`operator.attrgetter`, returning *default* instead of
        raising :exc:`AttributeError` when any attribute in the path is absent.

        Args:
            *paths: Attribute paths forwarded to :func:`operator.attrgetter`,
                e.g. ``"user.profile.email"``.
            default: Value returned when any attribute in any path is missing.
                Defaults to ``None``.

        Returns:
            A callable ``getter(obj)`` that returns the attribute value (or a
            list of values when multiple *paths* are given), or *default* on
            :exc:`AttributeError`.

        Example::

            get_email = AppUtils.null_safe_attrgetter("profile.email")
            get_email(user)  # "alice@example.com" or None
        """
        _getter = attrgetter(*paths)

        def getter(obj: Any) -> Any:
            try:
                result = _getter(obj)
                if len(paths) > 1:
                    return list(result)
                return result
            except AttributeError:
                _LOGGER.trace(
                    "AppUtils.null_safe_attrgetter | paths={} | used_default=true",
                    list(paths),
                )
                return default

        return getter

    @staticmethod
    def join_string(separator: str, *values: Any) -> str:
        """Join *values* into a string using *separator*.

        If a single non-string sequence is passed it is transparently unpacked,
        so both ``AppUtils.join_string(",", 1, 2, 3)`` and
        ``AppUtils.join_string(",", [1, 2, 3])`` produce the same output.

        Returns an empty string when no values are supplied.
        """
        if not values:
            return ""
        if (
            len(values) == 1
            and isinstance(values[0], Sequence)
            and not isinstance(values[0], str)
        ):
            items: list[Any] = list(cast(Sequence[Any], values[0]))
        else:
            items = list(values)
        return separator.join(str(v) for v in items)
