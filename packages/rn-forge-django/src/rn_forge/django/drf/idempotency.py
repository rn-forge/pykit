"""Django-cache idempotency storage and DRF integration."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any, Concatenate, cast

from django.core.cache import caches
from django.http import StreamingHttpResponse
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.commons.exceptions import AppException
from rn_forge.web import (
    IDEMPOTENCY_KEY_HEADER,
    IdempotencyKeyInFlight,
    IdempotencyKeyReuse,
    IdempotencyStore,
    StoredResponse,
    request_hash,
    run_idempotent,
)

__all__ = ["CacheIdempotencyStore", "idempotent"]


class CacheIdempotencyStore:
    """Implement ``rn_forge.web.IdempotencyStore`` over a shared Django cache.

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

        The length-prefixed scope prevents collisions between endpoint or tenant
        namespaces.
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
                error_code=422,
            )
        stored = cast(Mapping[str, Any] | None, entry["response"])
        if stored is None:
            raise IdempotencyKeyInFlight(
                "Idempotency key {} is still processing its original request",
                key,
                error_code=409,
            )
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
    header: str = IDEMPOTENCY_KEY_HEADER,
) -> Callable[
    [Callable[Concatenate[V, Request, P], Response]],
    Callable[Concatenate[V, Request, P], Response],
]:
    """Decorate a DRF handler method so an unsafe request executes once per key.

    Safe methods bypass the store. A missing key on an unsafe method raises
    :class:`rn_forge.web.IdempotencyKeyRequired` (400); a replay returns the
    stored status and body verbatim; the same key with a different body raises
    :class:`rn_forge.web.IdempotencyKeyReuse` (422); a duplicate while the
    original is still in flight raises
    :class:`rn_forge.web.IdempotencyKeyInFlight` (409).

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
            # The runner returns (status, body); the original Response object
            # — headers included — is kept here for the non-replayed case.
            executed: list[Response] = []

            def execute() -> tuple[int, Mapping[str, Any]]:
                response = handler(view, request, *args, **kwargs)
                AppException.check(
                    not isinstance(response, StreamingHttpResponse),
                    "Streaming responses cannot be stored against an idempotency key",
                )
                executed.append(response)
                return response.status_code, cast(Mapping[str, Any], response.data)  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave data untyped

            result = run_idempotent(
                store,
                scope=scope,
                key=cast(str | None, request.headers.get(header)),
                method=request.method or "",
                body=cast(object, request.data),  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave data partially untyped
                execute=execute,
                header=header,
            )
            if result.replayed:
                return Response(dict(result.body), status=result.status)
            return executed[0]

        return wrapper

    return decorate
