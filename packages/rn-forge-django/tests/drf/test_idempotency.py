from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

rest_framework = pytest.importorskip("rest_framework")

from django.http import StreamingHttpResponse  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from rn_forge.commons.exceptions import AppException  # noqa: E402
from rn_forge.django.drf.idempotency import (  # noqa: E402
    CacheIdempotencyStore,
    idempotent,
)
from rn_forge.web import (  # noqa: E402
    IdempotencyKeyInFlight,
    IdempotencyKeyRequired,
    IdempotencyKeyReuse,
    IdempotencyStore,
)

pytestmark = pytest.mark.unit


class TestCacheIdempotencyStore:
    def test_satisfies_the_web_protocol(self) -> None:
        assert isinstance(CacheIdempotencyStore(), IdempotencyStore)

    def test_first_sight_returns_none(self) -> None:
        store = CacheIdempotencyStore()
        assert store.record_or_replay(scope="s", key="k", request_body={"a": 1}) is None

    def test_replay_after_complete_returns_the_stored_response(self) -> None:
        store = CacheIdempotencyStore()
        store.record_or_replay(scope="s", key="k", request_body={"a": 1})
        store.complete(scope="s", key="k", status=201, response_body={"id": 7})
        stored = store.record_or_replay(scope="s", key="k", request_body={"a": 1})
        assert stored is not None
        assert (stored.status, dict(stored.body), stored.replayed) == (
            201,
            {"id": 7},
            True,
        )

    def test_a_duplicate_while_in_flight_raises(self) -> None:
        store = CacheIdempotencyStore()
        store.record_or_replay(scope="s", key="k", request_body={"a": 1})
        with pytest.raises(IdempotencyKeyInFlight):
            store.record_or_replay(scope="s", key="k", request_body={"a": 1})

    def test_same_key_different_body_raises_reuse(self) -> None:
        store = CacheIdempotencyStore()
        store.record_or_replay(scope="s", key="k", request_body={"a": 1})
        with pytest.raises(IdempotencyKeyReuse):
            store.record_or_replay(scope="s", key="k", request_body={"a": 2})

    def test_scopes_do_not_collide(self) -> None:
        store = CacheIdempotencyStore()
        store.record_or_replay(scope="orders", key="k", request_body={"a": 1})
        store.complete(scope="orders", key="k", status=201, response_body={})
        assert (
            store.record_or_replay(scope="charges", key="k", request_body={"b": 2})
            is None
        )

    def test_claim_is_cache_add_with_timeout_and_alias(self) -> None:
        cache = MagicMock()
        cache.add.return_value = True
        with patch("rn_forge.django.drf.idempotency.caches", {"other": cache}):
            store = CacheIdempotencyStore(timeout=30, cache_alias="other")
            assert store.record_or_replay(scope="s", key="k", request_body={}) is None
        cache.add.assert_called_once()
        assert cache.add.call_args.args[0] == "idempotency:1:s:k"
        assert cache.add.call_args.args[2] == 30
        cache.set.assert_not_called()
        cache.get.assert_not_called()

    def test_complete_honours_timeout(self) -> None:
        cache = MagicMock()
        cache.get.return_value = {"hash": "h", "response": None}
        with patch("rn_forge.django.drf.idempotency.caches", {"default": cache}):
            CacheIdempotencyStore(timeout=45).complete(
                scope="s", key="k", status=200, response_body={"ok": True}
            )
        slot, entry, timeout = cache.set.call_args.args
        assert (slot, timeout) == ("idempotency:1:s:k", 45)
        assert entry["response"] == {"status": 200, "body": {"ok": True}}

    def test_a_colon_cannot_move_a_key_across_scopes(self) -> None:
        assert CacheIdempotencyStore.cache_key(
            "tenant:orders", "x"
        ) != CacheIdempotencyStore.cache_key("tenant", "orders:x")


class _ChargeView(APIView):
    authentication_classes: list = []
    permission_classes: list = []
    calls = 0
    streaming = False

    @idempotent(CacheIdempotencyStore(), scope="charges")
    def post(self, request):
        type(self).calls += 1
        if self.streaming:
            return StreamingHttpResponse(iter([b"x"]))
        return Response({"charged": request.data["amount"]}, status=201)

    @idempotent(CacheIdempotencyStore(), scope="charges")
    def get(self, request):
        type(self).calls += 1
        return Response({"ok": True})


def _post(body, key: str | None = "k-1", view=_ChargeView):
    headers = {"Idempotency-Key": key} if key else {}
    request = APIRequestFactory().post("/charges", body, format="json", headers=headers)
    return view.as_view()(request)


class TestIdempotentDecorator:
    def setup_method(self) -> None:
        _ChargeView.calls = 0

    def test_missing_key_on_unsafe_method_raises(self) -> None:
        with pytest.raises(IdempotencyKeyRequired):
            _post({"amount": 1}, key=None)

    def test_safe_method_needs_no_key(self) -> None:
        response = _ChargeView.as_view()(APIRequestFactory().get("/charges"))
        assert response.status_code == 200

    def test_replay_executes_once_and_returns_the_stored_response(self) -> None:
        first = _post({"amount": 5})
        second = _post({"amount": 5})
        assert _ChargeView.calls == 1
        assert (second.status_code, second.data) == (201, first.data)

    def test_different_body_raises_reuse(self) -> None:
        _post({"amount": 5})
        with pytest.raises(IdempotencyKeyReuse):
            _post({"amount": 6})

    def test_streaming_response_is_refused(self) -> None:
        class Streaming(_ChargeView):
            streaming = True

        with pytest.raises(AppException):
            _post({"amount": 5}, key="k-stream", view=Streaming)
