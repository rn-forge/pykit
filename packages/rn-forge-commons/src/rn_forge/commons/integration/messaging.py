"""Messaging protocols: a transport-agnostic publish interface.

Provides:

- :class:`MessageBus` / :class:`AsyncMessageBus` — a minimal publish protocol,
  satisfied structurally by any sync/async message-bus client (Azure Service
  Bus, SQS, an in-process event dispatcher, ...).
- :class:`InMemoryMessageBus` — records published events; the test double and
  the local/dev default.
- :class:`HandlerRegistry` — maps a message type to its handler. Instantiable,
  not a module-level registry, so two registries can coexist and a test can
  start from a clean one.

No delivery guarantees are implied. ``publish`` is fire-and-forget from the
protocol's point of view — retries, at-least-once delivery, and transactional
outbox semantics are the caller's responsibility, not this module's.

This module has no optional dependency — it is protocols, a dict, and a list.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol, Self, Sequence, runtime_checkable

__all__ = [
    "AsyncMessageBus",
    "HandlerRegistry",
    "InMemoryMessageBus",
    "MessageBus",
]


@runtime_checkable
class MessageBus(Protocol):
    """A synchronous publish target for a named destination."""

    def publish(self, destination: str, event: Mapping[str, Any]) -> None:
        """Publish *event* to *destination*. Fire-and-forget; no delivery guarantee."""
        ...


@runtime_checkable
class AsyncMessageBus(Protocol):
    """The async counterpart of :class:`MessageBus`."""

    async def publish(self, destination: str, event: Mapping[str, Any]) -> None:
        """Publish *event* to *destination*. Fire-and-forget; no delivery guarantee."""
        ...


class InMemoryMessageBus:
    """Records published events in memory. The test double, and the local default."""

    def __init__(self) -> None:
        self._published: list[tuple[str, Mapping[str, Any]]] = []

    def publish(self, destination: str, event: Mapping[str, Any]) -> None:
        """Record ``(destination, event)`` in publish order."""
        self._published.append((destination, event))

    @property
    def published(self) -> Sequence[tuple[str, Mapping[str, Any]]]:
        """A snapshot of every ``(destination, event)`` pair published so far, in order."""
        return list(self._published)

    def clear(self) -> None:
        """Discard every recorded publish."""
        self._published.clear()


class HandlerRegistry:
    """Maps a message type to its handler. Instantiable — no module-level registry."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[Mapping[str, Any]], None]] = {}

    def register(
        self, message_type: str, handler: Callable[[Mapping[str, Any]], None]
    ) -> Self:
        """Register *handler* for *message_type*. Returns ``self`` for chaining.

        Raises:
            ValueError: *message_type* is already registered.
        """
        if message_type in self._handlers:
            raise ValueError(
                f"Handler already registered for message type: {message_type!r}"
            )
        self._handlers[message_type] = handler
        return self

    def handler_for(
        self, message_type: str
    ) -> Callable[[Mapping[str, Any]], None] | None:
        """Return the handler registered for *message_type*, or ``None``."""
        return self._handlers.get(message_type)
