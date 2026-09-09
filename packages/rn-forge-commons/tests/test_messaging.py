"""Tests for rn_forge.commons.messaging."""

from __future__ import annotations

import pytest

from rn_forge.commons.messaging import (
    AsyncMessageBus,
    HandlerRegistry,
    InMemoryMessageBus,
    MessageBus,
)


class TestInMemoryMessageBus:
    def test_records_destination_and_event_in_order(self) -> None:
        bus = InMemoryMessageBus()
        bus.publish("orders", {"id": 1})
        bus.publish("orders", {"id": 2})
        assert bus.published == [("orders", {"id": 1}), ("orders", {"id": 2})]

    def test_clear_empties(self) -> None:
        bus = InMemoryMessageBus()
        bus.publish("orders", {"id": 1})
        bus.clear()
        assert bus.published == []

    def test_published_is_a_copy_not_the_live_list(self) -> None:
        bus = InMemoryMessageBus()
        bus.publish("orders", {"id": 1})
        snapshot = bus.published
        bus.publish("orders", {"id": 2})
        assert snapshot == [("orders", {"id": 1})]

    def test_satisfies_message_bus_protocol(self) -> None:
        # runtime_checkable Protocol isinstance checks only verify method
        # names exist, not sync-vs-async signatures — InMemoryMessageBus
        # structurally satisfies both protocols under isinstance.
        assert isinstance(InMemoryMessageBus(), MessageBus)
        assert isinstance(InMemoryMessageBus(), AsyncMessageBus)


class TestHandlerRegistry:
    def test_round_trip(self) -> None:
        registry = HandlerRegistry()
        handler = lambda event: None  # noqa: E731
        registry.register("order.created", handler)
        assert registry.handler_for("order.created") is handler

    def test_unknown_type_returns_none(self) -> None:
        registry = HandlerRegistry()
        assert registry.handler_for("unknown") is None

    def test_reregistering_same_type_raises(self) -> None:
        registry = HandlerRegistry()
        registry.register("order.created", lambda event: None)
        with pytest.raises(ValueError, match="already registered"):
            registry.register("order.created", lambda event: None)

    def test_register_returns_self_for_chaining(self) -> None:
        registry = HandlerRegistry()
        result = registry.register("a", lambda event: None)
        assert result is registry

    def test_two_registries_are_independent(self) -> None:
        r1 = HandlerRegistry()
        r2 = HandlerRegistry()
        r1.register("a", lambda event: None)
        assert r2.handler_for("a") is None
