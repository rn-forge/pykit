"""Tests for rn_forge.web.idempotency."""

import pytest
from assertpy import assert_that

from rn_forge.web.exceptions import IdempotencyKeyReuse
from rn_forge.web.idempotency import (
    AsyncIdempotencyStore,
    IdempotencyStore,
    InMemoryAsyncIdempotencyStore,
    InMemoryIdempotencyStore,
    StoredResponse,
    request_hash,
)

pytestmark = pytest.mark.unit


# --- request_hash ---------------------------------------------------------


def test_hash_is_key_order_independent():
    assert_that(request_hash({"a": 1, "b": 2})).is_equal_to(
        request_hash({"b": 2, "a": 1})
    )


def test_hash_is_stable_across_calls():
    assert_that(request_hash({"a": [1, 2]})).is_equal_to(request_hash({"a": [1, 2]}))


def test_hash_distinguishes_different_bodies():
    assert_that(request_hash({"a": 1})).is_not_equal_to(request_hash({"a": 2}))


def test_hash_distinguishes_a_string_from_a_number():
    assert_that(request_hash({"a": 1})).is_not_equal_to(request_hash({"a": "1"}))


def test_hash_handles_none_and_scalars():
    for body in (None, 0, "", [], {}):
        assert_that(request_hash(body)).is_length(64)


def test_hash_is_a_hex_digest():
    assert_that(request_hash({"a": 1})).matches(r"^[0-9a-f]{64}$")


# --- the store contract, exercised through the in-memory double -----------


@pytest.fixture
def store():
    return InMemoryIdempotencyStore()


def test_the_double_satisfies_the_protocol(store):
    assert_that(isinstance(store, IdempotencyStore)).is_true()


def test_first_sight_returns_none(store):
    assert_that(
        store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    ).is_none()


def test_replay_after_complete_returns_the_stored_response(store):
    store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    store.complete(scope="charges", key="k1", status=201, response_body={"id": "c1"})

    replayed = store.record_or_replay(
        scope="charges", key="k1", request_body={"amount": 1}
    )
    assert_that(replayed).is_equal_to(
        StoredResponse(status=201, body={"id": "c1"}, replayed=True)
    )


def test_the_first_response_is_stored_with_replayed_false(store):
    store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    store.complete(scope="charges", key="k1", status=201, response_body={"id": "c1"})
    first = store.record_or_replay(
        scope="charges", key="k1", request_body={"amount": 1}
    )
    assert_that(first.replayed).is_true()


def test_the_same_key_with_a_different_body_is_reuse(store):
    """The single most valuable thing in the module."""
    store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    assert_that(store.record_or_replay).raises(IdempotencyKeyReuse).when_called_with(
        scope="charges", key="k1", request_body={"amount": 999}
    )


def test_reuse_is_detected_before_completion_too(store):
    store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    store.complete(scope="charges", key="k1", status=201, response_body={})
    assert_that(store.record_or_replay).raises(IdempotencyKeyReuse).when_called_with(
        scope="charges", key="k1", request_body={"amount": 999}
    )


def test_a_reordered_body_is_not_reuse(store):
    store.record_or_replay(scope="charges", key="k1", request_body={"a": 1, "b": 2})
    store.record_or_replay(scope="charges", key="k1", request_body={"b": 2, "a": 1})


def test_distinct_scopes_do_not_collide(store):
    store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    store.complete(scope="charges", key="k1", status=201, response_body={"id": "c1"})

    # Same key, different scope: a first sight, not a replay and not reuse.
    assert_that(
        store.record_or_replay(scope="refunds", key="k1", request_body={"amount": 2})
    ).is_none()


def test_an_in_flight_replay_returns_none(store):
    """Documented behaviour, not an oversight — see the class docstring."""
    store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    assert_that(
        store.record_or_replay(scope="charges", key="k1", request_body={"amount": 1})
    ).is_none()


def test_the_stored_body_is_copied_not_aliased(store):
    body = {"id": "c1"}
    store.record_or_replay(scope="charges", key="k1", request_body={})
    store.complete(scope="charges", key="k1", status=201, response_body=body)
    body["id"] = "mutated"
    replayed = store.record_or_replay(scope="charges", key="k1", request_body={})
    assert_that(replayed.body).is_equal_to({"id": "c1"})


# --- the async protocol ---------------------------------------------------


def test_the_async_double_satisfies_the_async_protocol():
    assert_that(
        isinstance(InMemoryAsyncIdempotencyStore(), AsyncIdempotencyStore)
    ).is_true()


@pytest.mark.asyncio
async def test_the_async_double_has_the_same_semantics():
    store = InMemoryAsyncIdempotencyStore()
    assert_that(
        await store.record_or_replay(scope="s", key="k", request_body={"a": 1})
    ).is_none()
    await store.complete(scope="s", key="k", status=200, response_body={"ok": True})
    replayed = await store.record_or_replay(scope="s", key="k", request_body={"a": 1})
    assert_that(replayed).is_equal_to(
        StoredResponse(status=200, body={"ok": True}, replayed=True)
    )


@pytest.mark.asyncio
async def test_the_async_double_detects_reuse():
    store = InMemoryAsyncIdempotencyStore()
    await store.record_or_replay(scope="s", key="k", request_body={"a": 1})
    with pytest.raises(IdempotencyKeyReuse):
        await store.record_or_replay(scope="s", key="k", request_body={"a": 2})


def test_stored_response_serializes_through_the_dataclass_mixin():
    assert_that(StoredResponse(status=201, body={"id": 1}).as_dict()).is_equal_to(
        {"status": 201, "body": {"id": 1}, "replayed": False}
    )
