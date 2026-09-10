"""Value and import helpers, plus base64 encoding.

Provides:

- :class:`AppUtils` — bool parsing, emptiness checks, dynamic imports,
  null-safe attribute access, string joining and unified diffs.
- :class:`Base64` — encode/decode helpers that accept ``str`` or ``bytes``.

:class:`AppUtils` is an acknowledged grab bag rather than a designed surface;
it stays whole because splitting it would break a public class name for
tidiness. A new helper belongs in a named module unless it genuinely has no
other home.

All methods are static with no import-time side effects.
"""

from __future__ import annotations

import base64
import difflib
import importlib
import numbers
import pkgutil
from collections.abc import Sized
from operator import attrgetter
from typing import Any, Callable, Sequence, cast

from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)

__all__ = ["AppUtils", "Base64"]


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


class AppUtils:
    """General-purpose value and import utilities.

    All methods are static.
    """

    @staticmethod
    def parse_bool(value: Any, *, strict: bool = True) -> bool | None:
        """Convert a value to ``bool`` using common truthy/falsy string tokens.

        Recognises (case-insensitive):

        - Truthy: ``"true"``, ``"yes"``, ``"y"``, ``"on"``, ``"1"``, ``"enabled"``
        - Falsy: ``"false"``, ``"no"``, ``"n"``, ``"off"``, ``"0"``, ``"disabled"``, ``"none"``

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
        if text in {"true", "yes", "y", "on", "1", "enabled"}:
            _LOGGER.trace("AppUtils.parse_bool | token={} | result=True", text)
            return True
        if text in {"false", "no", "n", "off", "0", "disabled", "none"}:
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

        Delegates to :func:`pkgutil.resolve_name` for the absolute case, which
        also accepts ``pkg.mod:attr`` (colon-separated) as well as
        ``pkg.mod.attr`` — a superset of this function's original
        dot-only contract. Relative imports (a *qualname* starting with
        ``"."``) are not supported by :func:`~pkgutil.resolve_name`, so they
        are still handled via :func:`importlib.import_module`.

        Args:
            qualname: Dotted (or ``pkg.mod:attr``) path to the target, e.g.
                ``"os.path.join"`` or ``".submodule.MyClass"`` for relative
                imports.
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
        if qualname.startswith("."):
            if package is None:
                _LOGGER.warning(
                    "AppUtils.import_string | qualname={} | missing_package_for_relative_import=true",
                    qualname,
                )
                raise ImportError(
                    f"Package name is required for relative import: {qualname!r}"
                )
            return AppUtils._import_relative(qualname, package)

        _LOGGER.debug("AppUtils.import_string | qualname={}", qualname)
        try:
            return pkgutil.resolve_name(qualname)
        except AttributeError as exc:
            _LOGGER.warning(
                "AppUtils.import_string | qualname={} | missing_attr=true", qualname
            )
            raise ImportError(f"Cannot import {qualname!r}: {exc}") from exc
        except ImportError:
            _LOGGER.exception("AppUtils.import_string failed | qualname={}", qualname)
            raise

    @staticmethod
    def _import_relative(qualname: str, package: str) -> Any:
        """Resolve a relative ``.submodule.Attr`` *qualname* via ``importlib``."""
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

    @staticmethod
    def unified_diff(
        expected: str,
        actual: str,
        *,
        expected_name: str = "expected",
        actual_name: str = "actual",
    ) -> str:
        """Return a unified diff between *expected* and *actual*, or ``""`` if equal.

        The empty-string-for-equal-inputs contract is deliberate: callers use
        it to decide "did anything change" without a separate equality check.

        Args:
            expected: The baseline text.
            actual: The text being compared against *expected*.
            expected_name: Label for *expected* in the diff header.
            actual_name: Label for *actual* in the diff header.

        Returns:
            A conventional unified diff string, or ``""`` when *expected* and
            *actual* are identical.
        """
        if expected == actual:
            return ""
        diff = difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=expected_name,
            tofile=actual_name,
        )
        return "".join(diff)
