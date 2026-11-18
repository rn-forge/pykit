"""Content digests for detecting drift from a recorded state."""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["ContentHash"]


class ContentHash:
    """Content-hashing helpers for strings, bytes, and files."""

    @staticmethod
    def of(content: str | bytes, *, algorithm: str = "sha256") -> str:
        """Return a hex digest of *content* using *algorithm* (default ``sha256``)."""
        payload = content.encode() if isinstance(content, str) else content
        return hashlib.new(algorithm, payload).hexdigest()

    @staticmethod
    def of_file(path: str | Path, *, algorithm: str = "sha256") -> str | None:
        """Return a hex digest of the file at *path*, or ``None`` if it is not a file."""
        p = Path(path)
        if not p.is_file():
            return None
        with p.open("rb") as handle:
            return hashlib.file_digest(handle, algorithm).hexdigest()
