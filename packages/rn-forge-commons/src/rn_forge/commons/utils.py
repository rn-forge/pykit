"""General-purpose utilities: environment access, base64, filesystem, and value helpers.

Provides:

- :class:`Environment` — typed env-var access with boolean interpretation.
- :class:`Base64` — encode/decode helpers that accept ``str`` or ``bytes``.
- :class:`PathUtils` — filesystem helpers (write, delete, temp dir) with
  automatic parent-directory creation.
- :class:`ContentHash` — content/file digests for detecting drift.
- :class:`AppUtils` — value and import utilities: bool parsing, emptiness
  checks, dynamic imports, attribute access, and string joining.

All methods are static with no import-time side effects.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import importlib
import numbers
import os
import pkgutil
import shutil
import tempfile
from operator import attrgetter
from pathlib import Path, PurePosixPath
from collections.abc import Sized
from typing import Any, Callable, Literal, Sequence, cast

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)

__all__ = [
    "AppUtils",
    "Base64",
    "ContentHash",
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
    def atomic_write(
        content: str | bytes,
        path: str | Path,
        *,
        mode: int | None = None,
        encoding: str = "utf-8",
    ) -> Path:
        """Atomically write *content* to *path*, never leaving a partial file visible.

        Writes to a ``.<name>.<random>.tmp`` temp file in *path*'s directory,
        ``fsync``s it, then publishes it over the target with
        :func:`os.replace` — the rename is atomic, so a reader never observes
        a partially-written file. The parent directory is then best-effort
        ``fsync``'d too: fsyncing only the file durably records its
        *contents*, but the rename that makes those contents visible under
        *path* lives in the parent directory's entry table, so a crash
        between the two can still lose the new name on some filesystems.
        Not every platform or filesystem permits opening a directory for this,
        hence best-effort — failure here is silently swallowed.

        Permissions: an explicit *mode* always wins; otherwise an existing
        file's mode is preserved across the replacement; otherwise (no
        existing file, no explicit mode) the temp file's default
        (restrictive) permissions are left as-is.

        A :class:`BaseException` (not just :class:`Exception`) during the
        write — including :exc:`KeyboardInterrupt`/:exc:`SystemExit` — still
        cleans up the temp file before propagating, so an interrupted write
        never leaves a stray temp file behind.

        Args:
            content: Text or binary data to write.
            path: Destination file path.
            mode: Optional explicit permission bits applied to the temp file
                before the atomic rename. Takes precedence over preserving an
                existing file's mode.
            encoding: Encoding used when *content* is ``str``. Ignored for
                binary writes.

        Returns:
            The resolved :class:`~pathlib.Path` that was written.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing_mode = p.stat().st_mode if p.exists() else None

        fd, tmp_name = tempfile.mkstemp(
            dir=p.parent, prefix=f".{p.name}.", suffix=".tmp"
        )
        try:
            if isinstance(content, bytes):
                with os.fdopen(fd, "wb") as binary_stream:
                    binary_stream.write(content)
                    binary_stream.flush()
                    os.fsync(binary_stream.fileno())
            else:
                with os.fdopen(fd, "w", encoding=encoding) as text_stream:
                    text_stream.write(content)
                    text_stream.flush()
                    os.fsync(text_stream.fileno())

            if mode is not None:
                os.chmod(tmp_name, mode)
            elif existing_mode is not None:
                os.chmod(tmp_name, existing_mode)

            os.replace(tmp_name, p)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

        try:
            dir_fd = os.open(p.parent, os.O_RDONLY)
        except OSError:
            return p
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)
        return p

    @staticmethod
    def find_root(
        start: str | Path | None = None,
        *,
        markers: Sequence[str | Path] = (".git",),
        fallback: Literal["start", "raise"] = "start",
    ) -> Path:
        """Walk up from *start* to the nearest ancestor containing any marker.

        *markers* are checked in order — every ancestor is checked against
        the first marker before the second marker is considered at all, so
        marker precedence outranks proximity to *start* (e.g. a ``.git``
        several levels up beats a ``pyproject.toml`` one level up, if
        ``markers=(".git", "pyproject.toml")``).

        Args:
            start: Directory (or file, whose parent is used) to search from.
                Defaults to the current working directory.
            markers: Ordered marker paths (relative to a candidate ancestor)
                whose existence identifies the root, e.g. ``(".git",)`` or
                ``("pyproject.toml", ".git")``.
            fallback: ``"start"`` (default) returns the resolved *start*
                directory when no marker matches anywhere up the tree.
                ``"raise"`` raises :class:`AppException` instead.

        Returns:
            The resolved root directory.

        Raises:
            AppException: No marker matched and ``fallback="raise"``.
        """
        current = (
            Path(start).expanduser().resolve() if start is not None else Path.cwd()
        )
        if current.is_file():
            current = current.parent
        candidates = [current, *current.parents]

        for marker in markers:
            for candidate in candidates:
                if (candidate / marker).exists():
                    return candidate

        if fallback == "raise":
            raise AppException(
                "No root found from {} for markers {}", current, list(markers)
            )
        return current

    @staticmethod
    def normalize_relative(raw: str) -> str:
        """Normalize *raw* to a POSIX relative path, rejecting escapes.

        Rejects absolute paths and any ``".."`` that would climb above the
        (implicit) root. ``"."`` means the root itself. Purely lexical — does
        not touch the filesystem or resolve symlinks; pair with
        :meth:`assert_within` when the path will actually be used.

        Args:
            raw: A path string, possibly using backslashes.

        Returns:
            The normalized POSIX relative path, or ``"."`` for the root.

        Raises:
            AppException: *raw* is empty/blank, absolute, or escapes the root.
        """
        if not raw.strip():
            raise AppException("Path must not be empty")

        candidate = PurePosixPath(raw.replace("\\", "/"))
        if candidate.is_absolute():
            raise AppException("Path must be relative: {!r}", raw)

        parts: list[str] = []
        for part in candidate.parts:
            if part in ("", "."):
                continue
            if part == "..":
                if not parts:
                    raise AppException("Path escapes root: {!r}", raw)
                parts.pop()
                continue
            parts.append(part)

        return "/".join(parts) if parts else "."

    @staticmethod
    def assert_within(root: str | Path, target: str | Path) -> Path:
        """Resolve *target* and raise unless it stays inside *root*.

        Covers both the lexical escape (a declared ``../../.ssh/config``) and
        the symlink-escape case (a symlink that *resolves* outside *root*) —
        :meth:`~pathlib.Path.resolve` collapses ``..`` segments and follows
        symlinks, so a single post-resolution containment check catches both.

        Args:
            root: The directory *target* must stay within.
            target: The path to check, resolved before comparison.

        Returns:
            The resolved, absolute *target* path.

        Raises:
            AppException: The resolved *target* is not *root* itself and is
                not inside it.
        """
        root_resolved = Path(root).resolve()
        target_resolved = Path(target).resolve()
        if (
            target_resolved != root_resolved
            and root_resolved not in target_resolved.parents
        ):
            raise AppException(
                "Path escapes root: {} is not within {}", target_resolved, root_resolved
            )
        return target_resolved

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

    @staticmethod
    def backup(
        path: str | Path,
        destination_root: str | Path,
        *,
        relative_to: Path | None = None,
    ) -> Path | None:
        """Copy *path* under *destination_root*, preserving its relative layout.

        Per-run timestamp policy (e.g. one backup directory per invocation) is
        deliberately not this method's concern — that is application policy,
        not a generic filesystem operation; a caller wanting timestamped
        backups builds *destination_root* accordingly before calling this.

        Args:
            path: The file to back up. A no-op (returns ``None``) if this is
                not an existing file.
            destination_root: Directory under which the backup is placed.
            relative_to: When given, *path* is stored under *destination_root*
                at its path relative to this directory. When *path* is not
                inside *relative_to* (or *relative_to* is omitted), it is
                stored at its path with the filesystem root stripped, e.g.
                ``/etc/app/config`` -> ``<destination_root>/etc/app/config``.

        Returns:
            The backup file's path, or ``None`` when *path* is not a file.
        """
        p = Path(path)
        if not p.is_file():
            return None
        resolved = p.expanduser().resolve()
        if relative_to is not None:
            try:
                rel = resolved.relative_to(Path(relative_to).expanduser().resolve())
            except ValueError:
                rel = Path(*resolved.parts[1:])
        else:
            rel = Path(*resolved.parts[1:])
        destination = Path(destination_root) / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, destination)
        return destination


# ---------------------------------------------------------------------------
# ContentHash — SHA-256 (or other) digests of content and files
# ---------------------------------------------------------------------------


class ContentHash:
    """Content-hashing helpers, for detecting drift between a recorded and current state.

    All methods are static.
    """

    @staticmethod
    def of(content: str | bytes, *, algorithm: str = "sha256") -> str:
        """Return a hex digest of *content* using *algorithm* (default ``sha256``)."""
        payload = content.encode() if isinstance(content, str) else content
        return hashlib.new(algorithm, payload).hexdigest()

    @staticmethod
    def of_file(path: str | Path, *, algorithm: str = "sha256") -> str | None:
        """Return a hex digest of the file at *path*, or ``None`` if it is not a file."""
        p = Path(path)
        return (
            ContentHash.of(p.read_bytes(), algorithm=algorithm) if p.is_file() else None
        )


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
