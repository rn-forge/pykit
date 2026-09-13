"""The Django-cache :class:`rn_forge.web.IdempotencyStore`, and its DRF seam.

The protocol, request hashing and reuse semantics are :mod:`rn_forge.web.idempotency`'s.
This module stores claims in the Django cache and lifts the key off a DRF
request; it decides nothing else.

**The claim is ``cache.add()``.** It is an atomic set-if-absent, which is what
gives the store the race property the protocol requires: two concurrent
first-sight requests, one claim. A ``get``-then-``set`` store lets both execute
and no ordinary test notices.

**Use a shared cache backend.** ``LocMemCache`` gives every worker process its
own dictionary, which makes this store a no-op under any real deployment.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any, Concatenate, Final, cast

from django.core.cache import caches
from django.http import StreamingHttpResponse
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.commons.exceptions import AppException
from rn_forge.web import (
    IdempotencyKeyRequired,
    IdempotencyKeyReuse,
    IdempotencyStore,
    StoredResponse,
    request_hash,
)

__all__ = ["CacheIdempotencyStore", "idempotent"]

DEFAULT_IDEMPOTENCY_HEADER: Final = "Idempotency-Key"
_SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class CacheIdempotencyStore:
    """``rn_forge.web.IdempotencyStore`` over the Django cache.

    Args:
        timeout: Seconds a claim and its stored response live. Defaults to 24h.
        cache_alias: The ``CACHES`` alias to store in.
    """

    def __init__(self, *, timeout: int = 86_400, cache_alias: str = "default") -> None:
        self._timeout = timeout
        self._cache_alias = cache_alias

    @staticmethod
    def cache_key(scope: str, key: str) -> str:
        """Return the cache key for *key* within *scope*.

        ``scope`` exists so two endpoints cannot collide on a client-chosen key:
        pass the route name, or a tenant id for a tenant-scoped API. The scope
        is length-prefixed, so a ``:`` in either part cannot make two
        ``(scope, key)`` pairs share an entry.
        """
        return f"idempotency:{len(scope)}:{scope}:{key}"

    def record_or_replay(
        self, *, scope: str, key: str, request_body: Any
    ) -> StoredResponse | None:
        """See :meth:`rn_forge.web.IdempotencyStore.record_or_replay`."""
        cache = caches[self._cache_alias]
        slot, digest = self.cache_key(scope, key), request_hash(request_body)
        if cache.add(slot, {"hash": digest, "response": None}, self._timeout):
            return None
        entry = cast(Mapping[str, Any] | None, cache.get(slot))
        if entry is None:  # expired between add and get
            return None
        if entry["hash"] != digest:
            raise IdempotencyKeyReuse(
                "Idempotency key {} was replayed with a different request body",
                key,
                error_code=409,
            )
        stored = cast(Mapping[str, Any] | None, entry["response"])
        if stored is None:  # claimed, still in flight
            return None
        return StoredResponse(
            status=int(stored["status"]), body=stored["body"], replayed=True
        )

    def complete(
        self, *, scope: str, key: str, status: int, response_body: Mapping[str, Any]
    ) -> None:
        """See :meth:`rn_forge.web.IdempotencyStore.complete`."""
        cache = caches[self._cache_alias]
        slot = self.cache_key(scope, key)
        entry = dict(
            cast(Mapping[str, Any] | None, cache.get(slot))
            or {"hash": None, "response": None}
        )
        entry["response"] = {"status": status, "body": dict(response_body)}
        cache.set(slot, entry, self._timeout)


def idempotent[V, **P](
    store: IdempotencyStore,
    *,
    scope: str,
    header: str = DEFAULT_IDEMPOTENCY_HEADER,
) -> Callable[
    [Callable[Concatenate[V, Request, P], Response]],
    Callable[Concatenate[V, Request, P], Response],
]:
    """Decorate a DRF handler method so an unsafe request executes once per key.

    A missing key on an unsafe method is :class:`rn_forge.web.IdempotencyKeyRequired`
    (400); a replay returns the stored status and body verbatim; the same key
    with a different body is :class:`rn_forge.web.IdempotencyKeyReuse` (409).
    Safe methods pass straight through.

    Example::

        class ChargeView(APIView):
            @idempotent(CacheIdempotencyStore(), scope="charges")
            def post(self, request): ...

    Raises:
        AppException: The handler returned a streaming response, which has no
            body to store.
    """

    def decorate(
        handler: Callable[Concatenate[V, Request, P], Response],
    ) -> Callable[Concatenate[V, Request, P], Response]:
        @functools.wraps(handler)
        def wrapper(
            view: V, request: Request, *args: P.args, **kwargs: P.kwargs
        ) -> Response:
            if request.method in _SAFE_METHODS:
                return handler(view, request, *args, **kwargs)
            key = cast(str | None, request.headers.get(header))
            if not key:
                raise IdempotencyKeyRequired("{} is required", header, error_code=400)
            body = cast(object, request.data)  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave data partially untyped
            stored = store.record_or_replay(scope=scope, key=key, request_body=body)
            if stored is not None:
                return Response(dict(stored.body), status=stored.status)
            response = handler(view, request, *args, **kwargs)
            AppException.check(
                not isinstance(response, StreamingHttpResponse),
                "Streaming responses cannot be stored against an idempotency key",
            )
            store.complete(
                scope=scope,
                key=key,
                status=response.status_code,
                response_body=cast(Mapping[str, Any], response.data),  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave data untyped
            )
            return response

        return wrapper

    return decorate
