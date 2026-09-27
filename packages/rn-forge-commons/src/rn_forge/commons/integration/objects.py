"""Object-storage protocols: put/get/delete/exists plus a pre-signed URL.

``url_for`` returns a time-limited pre-signed URL (a SAS URL on Azure, a
presigned URL on S3) so a client downloads directly instead of streaming
bytes through the application. ``expires_in`` is required, not defaulted — a
pre-signed URL with a forgotten expiry is a leak with a long tail.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol, runtime_checkable

from rn_forge.commons.exceptions import AppException

__all__ = ["AsyncObjectStore", "InMemoryObjectStore", "ObjectNotFound", "ObjectStore"]


class ObjectNotFound(AppException):
    """No object exists at the given key."""


@runtime_checkable
class ObjectStore(Protocol):
    """A synchronous object-storage protocol."""

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        """Store *data* at *key*, overwriting any existing object."""
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes stored at *key*.

        Raises:
            ObjectNotFound: No object exists at *key*.
        """
        ...

    def delete(self, key: str) -> None:
        """Delete the object at *key*. A no-op when *key* does not exist."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether an object exists at *key*."""
        ...

    def url_for(self, key: str, *, expires_in: timedelta) -> str:
        """Return a time-limited pre-signed URL for *key*, valid for *expires_in*."""
        ...


@runtime_checkable
class AsyncObjectStore(Protocol):
    """The async counterpart of :class:`ObjectStore`."""

    async def put(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None:
        """Store *data* at *key*, overwriting any existing object."""
        ...

    async def get(self, key: str) -> bytes:
        """Return the bytes stored at *key*.

        Raises:
            ObjectNotFound: No object exists at *key*.
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete the object at *key*. A no-op when *key* does not exist."""
        ...

    async def exists(self, key: str) -> bool:
        """Return whether an object exists at *key*."""
        ...

    async def url_for(self, key: str, *, expires_in: timedelta) -> str:
        """Return a time-limited pre-signed URL for *key*, valid for *expires_in*."""
        ...


class InMemoryObjectStore:
    """Dict-backed store for tests. ``url_for`` raises ``NotImplementedError``."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        """Store *data* at *key*, overwriting any existing object. *content_type* is ignored."""
        self._objects[key] = data

    def get(self, key: str) -> bytes:
        """Return the bytes stored at *key*.

        Raises:
            ObjectNotFound: No object exists at *key*.
        """
        try:
            return self._objects[key]
        except KeyError:
            raise ObjectNotFound("No object found at key {}", key) from None

    def delete(self, key: str) -> None:
        """Delete the object at *key*. A no-op when *key* does not exist."""
        self._objects.pop(key, None)

    def exists(self, key: str) -> bool:
        """Return whether an object exists at *key*."""
        return key in self._objects

    def url_for(self, key: str, *, expires_in: timedelta) -> str:
        """Not supported by the in-memory store — always raises.

        Raises:
            NotImplementedError: Always — a fabricated URL would prove nothing.
        """
        raise NotImplementedError("InMemoryObjectStore does not support url_for")
