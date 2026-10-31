"""Filesystem helpers: atomic writes, backups, temp dirs and containment guards.

Includes atomic publish-by-rename, repository-root discovery, and
:meth:`~PathUtils.assert_within` containment checks.
"""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)

__all__ = ["PathUtils"]


def _fsync_path(path: Path) -> None:
    """``fsync`` the file at *path*, opened by name."""
    # Windows' fsync needs a writable descriptor; on POSIX a copy of a
    # read-only file cannot be opened for writing.
    fd = os.open(path, os.O_RDWR if os.name == "nt" else os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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
        with PathUtils.atomic_replace(p, copy=False, mode=mode) as tmp:
            if isinstance(content, bytes):
                tmp.write_bytes(content)
            else:
                tmp.write_text(content, encoding=encoding)
        return p

    @staticmethod
    @contextmanager
    def atomic_replace(
        path: str | Path, *, copy: bool = True, mode: int | None = None
    ) -> Generator[Path]:
        """Edit a temporary sibling of *path* and publish it over *path* atomically.

        Yields a ``.<name>.<random>.tmp`` path in *path*'s directory. When
        *copy* is true it starts as a :func:`shutil.copy2` copy of *path*; the
        caller edits it with any tool, including one that replaces it by
        rename. On a clean exit the temporary is ``fsync``'d, given its
        permissions, published over *path* with :func:`os.replace`, and the
        parent directory is best-effort ``fsync``'d.

        Permissions: an explicit *mode* wins; otherwise an existing *path*'s
        mode is kept; otherwise the temporary's default (restrictive)
        permissions are left as-is.

        On any :class:`BaseException`, including :exc:`KeyboardInterrupt`,
        the temporary is removed and *path* is left untouched.

        Args:
            path: The file to replace. Its directory must exist.
            copy: Pre-fill the temporary with a copy of *path*. When false the
                temporary starts empty and *path* may not exist yet.
            mode: Optional explicit permission bits for the published file.

        Yields:
            The temporary path to edit.

        Raises:
            FileNotFoundError: *copy* is true and *path* does not exist.
        """
        p = Path(path)
        existing_mode = p.stat().st_mode if p.exists() else None

        fd, tmp_name = tempfile.mkstemp(
            dir=p.parent, prefix=f".{p.name}.", suffix=".tmp"
        )
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            if copy:
                shutil.copy2(p, tmp)
            yield tmp

            # Reopen by name: the caller's tool may have swapped the file by
            # rename, so the mkstemp descriptor could point at the old inode.
            _fsync_path(tmp)

            if mode is not None:
                os.chmod(tmp, mode)
            elif existing_mode is not None:
                os.chmod(tmp, existing_mode)

            os.replace(tmp, p)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

        try:
            dir_fd = os.open(p.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

    @staticmethod
    def move_no_clobber(source: str | Path, destination: str | Path) -> Path:
        """Move *source* to *destination*, never overwriting an existing file.

        Creates *destination*'s parent directories, then publishes with
        :func:`os.link` and unlinks *source*. The link fails atomically when
        *destination* exists, so a file that appears there during the call is
        never replaced. Across filesystems, *source* is copied with
        :func:`shutil.copy2` to a temporary beside *destination*, ``fsync``'d,
        linked to *destination* and removed, then *source* is removed.

        Args:
            source: The file to move.
            destination: The path to move it to.

        Returns:
            *destination*, as a :class:`~pathlib.Path`.

        Raises:
            FileExistsError: *destination* exists. Both files are left as
                they were.
            FileNotFoundError: *source* does not exist.
            OSError: Any other failure, including a filesystem without hard
                links. Parent directories already created are kept.
        """
        src = Path(source)
        dst = Path(destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            fd, tmp_name = tempfile.mkstemp(
                dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp"
            )
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                shutil.copy2(src, tmp)
                _fsync_path(tmp)
                os.link(tmp, dst)
            finally:
                tmp.unlink(missing_ok=True)
        src.unlink()
        return dst

    @staticmethod
    def prune_empty_parents(start: str | Path, stop: str | Path) -> None:
        """Remove *start* and its empty ancestors, up to but excluding *stop*.

        Both paths are resolved first. Starting at *start*, each directory is
        removed with :meth:`~pathlib.Path.rmdir` and the walk moves to its
        parent, ending at the first directory that is not empty. Only
        directories strictly inside *stop* are touched: nothing happens when
        the resolved *start* is *stop* or lies outside it. A directory that
        no longer exists is skipped.

        Args:
            start: The directory to remove first.
            stop: The directory that bounds the walk; it is never removed.

        Raises:
            NotADirectoryError: *start* is a file.
            OSError: ``rmdir`` failed for a reason other than the directory
                being non-empty or missing, e.g. :exc:`PermissionError`.
        """
        stop_resolved = Path(stop).resolve()
        current = Path(start).resolve()
        while current != stop_resolved and current.is_relative_to(stop_resolved):
            try:
                current.rmdir()
            except FileNotFoundError:
                pass
            except OSError as exc:
                if exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
                    return
                raise
            current = current.parent

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
            _LOGGER.warning("Removing file: {}", p)  # noqa: PLE1205  # brace-style log format
            p.unlink()
        else:
            _LOGGER.warning("Removing directory: {}", p)  # noqa: PLE1205  # brace-style log format
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
