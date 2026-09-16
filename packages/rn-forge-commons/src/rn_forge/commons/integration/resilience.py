"""Async HTTP resilience with per-key circuit breakers, retry, and rate limiting.

Retries honor ``Retry-After`` and the token bucket clamps its quota from
``X-RateLimit-Remaining`` and ``X-RateLimit-Reset`` response headers. Circuits
are keyed independently so one failing upstream does not block another.

Requires the ``resilience`` extra (``purgatory``, ``stamina``, ``httpx``) and
must be imported directly.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import purgatory
import stamina
from purgatory.domain.model import OpenedState

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

__all__ = [
    "CircuitOpenError",
    "RateLimiter",
    "ResilientAsyncHttpClient",
    "parse_retry_after",
    "retryable",
]

_LOGGER = AppLogger.get_logger(__name__)

#: HTTP status codes treated as transient — worth retrying.
TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class CircuitOpenError(AppException):
    """A call was refused because its circuit is open."""


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value into seconds, or ``None`` if unparsable.

    Handles both forms RFC 9110 allows: delta-seconds (``"120"``) and an
    HTTP-date (``"Wed, 21 Oct 2026 07:28:00 GMT"``).
    """
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
    except TypeError, ValueError, IndexError:
        return None
    if target.tzinfo is None:
        return None
    from datetime import UTC, datetime

    return max(0.0, (target - datetime.now(UTC)).total_seconds())


def retryable(exc: BaseException) -> bool | float:
    """Stamina backoff hook for transient httpx failures.

    Returns:
        ``True`` for a connection/timeout error or a transient status code
        with no usable ``Retry-After``; a ``float`` (seconds) when
        ``Retry-After`` is present and parsable; ``False`` for anything else
        (a non-transient 4xx is not retried — the case most likely to be got
        wrong).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        if response.status_code not in TRANSIENT_STATUS_CODES:
            return False
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        return retry_after if retry_after is not None else True
    return isinstance(
        exc, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError)
    )


class RateLimiter:
    """A token bucket clamped from rate-limit response headers.

    "Never optimistic": :meth:`update_from_headers` only ever lowers the
    known remaining quota to match what the server reports, never raises it
    back up except at a reset boundary. A limiter that trusted a stale
    higher count would keep sending requests a server has already decided to
    reject.
    """

    def __init__(self, *, capacity: int = 100) -> None:
        """Initialize :class:`RateLimiter` with an assumed starting *capacity*."""
        self._capacity = capacity
        self._remaining = capacity
        self._reset_at: float | None = None

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        """Clamp the known remaining quota from ``X-RateLimit-Remaining``/``-Reset``.

        ``X-RateLimit-Reset`` is read as a Unix epoch timestamp in seconds, so
        :meth:`acquire` compares it against a wall clock.
        """
        remaining = headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                self._remaining = min(self._remaining, int(remaining))
            except ValueError:
                pass
        reset = headers.get("X-RateLimit-Reset")
        if reset is not None:
            try:
                self._reset_at = float(reset)
            except ValueError:
                pass

    async def acquire(
        self,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        """Wait, if necessary, until quota is available, then consume one unit.

        Args:
            clock: Injectable wall-clock time source (epoch seconds, the unit
                of ``X-RateLimit-Reset``), for deterministic tests.
            sleep: Injectable async sleep, for deterministic tests.
        """
        if self._remaining <= 0 and self._reset_at is not None:
            wait = self._reset_at - clock()
            if wait > 0:
                await sleep(wait)
            self._remaining = self._capacity
            self._reset_at = None
        self._remaining -= 1


class ResilientAsyncHttpClient:
    """An ``httpx.AsyncClient`` wrapped in a per-key circuit breaker, retry, and rate limiting.

    Breakers use the request *key*, falling back to the client *name*, so one
    instance can protect independent upstreams separately.
    """

    def __init__(
        self,
        base_url: str,
        *,
        name: str,
        stop_after_attempt: int = 3,
        wait_initial: float = 0.5,
        wait_max: float = 8.0,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        on_state_change: Callable[[str, str, str], None] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        **httpx_kwargs: Any,
    ) -> None:
        """Initialize :class:`ResilientAsyncHttpClient`.

        Args:
            base_url: Forwarded to ``httpx.AsyncClient``.
            name: Default circuit/breaker key when :meth:`request` is not
                given an explicit *key*.
            stop_after_attempt: Maximum attempts per logical call (initial +
                retries).
            wait_initial: Minimum backoff before the first retry, in seconds.
            wait_max: Maximum backoff between retries, in seconds.
            fail_max: Consecutive failures before a circuit opens. A
                non-transient status (a 404, a 422) is the caller's error, not
                the upstream's, and does not count.
            reset_timeout: Seconds an open circuit stays open before allowing
                a trial request.
            on_state_change: ``(key, old_state, new_state)`` called on every
                circuit transition. Defaults to an ``AppLogger`` warning —
                this is the metrics seam; wire it to your own backend rather
                than importing OpenTelemetry here.
            clock: Injectable wall-clock time source (epoch seconds) used by
                the rate limiter, for deterministic tests.
            sleep: Injectable async sleep used by the rate limiter. Defaults
                to ``asyncio.sleep``.
            **httpx_kwargs: Forwarded to ``httpx.AsyncClient``.
        """
        self._client = httpx.AsyncClient(base_url=base_url, **httpx_kwargs)
        self._name = name
        self._stop_after_attempt = stop_after_attempt
        self._wait_initial = wait_initial
        self._wait_max = wait_max
        self._clock = clock
        self._sleep = sleep or _default_sleep()
        self._rate_limiter = RateLimiter()
        self._breakers = purgatory.AsyncCircuitBreakerFactory(
            default_threshold=fail_max,
            default_ttl=reset_timeout,
            exclude=[(httpx.HTTPStatusError, _is_client_error)],
        )
        self._breakers_initialized = False
        self._last_state: dict[str, str] = {}
        self._on_state_change = on_state_change or self._log_state_change
        self._breakers.add_listener(self._handle_event)

    @property
    def client(self) -> httpx.AsyncClient:
        """The underlying ``httpx.AsyncClient``."""
        return self._client

    async def request(
        self, method: str, url: str, *, key: str | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Issue one logical request: rate-limited, retried, and circuit-broken.

        Args:
            method: HTTP method.
            url: Request URL (joined with ``base_url`` per ``httpx`` rules).
            key: Circuit/breaker key. Defaults to the client's *name*.
            **kwargs: Forwarded to ``httpx.AsyncClient.request``.

        Raises:
            CircuitOpenError: The circuit for *key* is open; the call was
                never attempted.
            httpx.HTTPError: The final retry attempt still failed.
        """
        if not self._breakers_initialized:
            await self._breakers.initialize()
            self._breakers_initialized = True

        circuit_key = key or self._name
        try:
            breaker = await self._breakers.get_breaker(circuit_key)
            async with breaker:
                response: httpx.Response | None = None
                async for attempt in stamina.retry_context(
                    on=retryable,
                    attempts=self._stop_after_attempt,
                    wait_initial=self._wait_initial,
                    wait_max=self._wait_max,
                ):
                    with attempt:
                        await self._rate_limiter.acquire(
                            clock=self._clock, sleep=self._sleep
                        )
                        response = await self._client.request(method, url, **kwargs)
                        self._rate_limiter.update_from_headers(response.headers)
                        response.raise_for_status()
                assert response is not None  # noqa: S101 - stamina guarantees this on success
                return response
        except OpenedState as exc:
            raise CircuitOpenError(f"Circuit {circuit_key!r} is open") from exc

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """``GET`` via :meth:`request`."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """``POST`` via :meth:`request`."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """``PUT`` via :meth:`request`."""
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """``PATCH`` via :meth:`request`."""
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """``DELETE`` via :meth:`request`."""
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        """Close the underlying ``httpx.AsyncClient``."""
        await self._client.aclose()

    async def __aenter__(self) -> ResilientAsyncHttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def _handle_event(self, name: str, kind: str, event: Any) -> None:
        if kind != "state_changed":
            return
        old_state = self._last_state.get(name, "closed")
        new_state = event.state
        self._last_state[name] = new_state
        self._on_state_change(name, old_state, new_state)

    def _log_state_change(self, name: str, old_state: str, new_state: str) -> None:
        _LOGGER.warning(
            "ResilientAsyncHttpClient circuit state change | name={} | {} -> {}",
            name,
            old_state,
            new_state,
        )


def _is_client_error(exc: BaseException) -> bool:
    """Whether *exc* is a non-transient status — excluded from breaker failures."""
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code not in TRANSIENT_STATUS_CODES
    )


def _default_sleep() -> Callable[[float], Awaitable[None]]:
    import asyncio

    return asyncio.sleep
