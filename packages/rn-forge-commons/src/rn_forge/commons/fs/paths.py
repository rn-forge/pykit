"""Filesystem helpers: atomic writes, backups, temp dirs and containment guards.

Includes atomic publish-by-rename, repository-root discovery, and
:meth:`~PathUtils.assert_within` containment checks.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Sequence

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)

__all__ = ["PathUtils"]


class PathUtils:
    """Filesystem helpers with automatic parent-directory creation."""

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
