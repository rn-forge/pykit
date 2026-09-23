from __future__ import annotations

import pytest
from opentelemetry.instrumentation.propagators import (
    get_global_response_propagator,
    set_global_response_propagator,
)

from rn_forge.django.tracing import instrument

pytestmark = pytest.mark.unit


def test_instrument_is_idempotent() -> None:
    instrument()
    instrument()  # a second call must not raise


def test_instrument_sets_a_response_propagator_when_none_is_set() -> None:
    instrument()
    assert get_global_response_propagator() is not None


def test_instrument_leaves_an_existing_response_propagator_alone() -> None:
    sentinel = object()
    set_global_response_propagator(sentinel)
    try:
        instrument()
        assert get_global_response_propagator() is sentinel
    finally:
        set_global_response_propagator(None)
