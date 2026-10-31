"""Single-owner thread actor.

Provides:
    ThreadActor: Owns one resource on a dedicated thread.  The resource is
        created, used and closed on that thread, and callers reach it through
        queued calls that return a :class:`~concurrent.futures.Future` or an
        awaitable.

Typical usage::

    from rn_forge.commons.runtime.actor import ThreadActor

    actor = ThreadActor(
        lambda: sqlite3.connect("app.db"),
        on_close=lambda conn: conn.close(),
    )
    try:
        row = await actor.run(lambda conn: conn.execute("SELECT 1").fetchone())
    finally:
        actor.close()
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

__all__ = ["ThreadActor"]

_LOGGER = AppLogger.get_logger(__name__)


class ThreadActor[R]:
    """Runs every call against one resource on a single dedicated thread.

    The thread is a daemon, named after *name*.  Calls run one at a time in
    the order they were queued.

    Example::

        actor = ThreadActor(Connection, name="db", on_close=Connection.close)
        future = actor.submit(lambda conn: conn.query("..."))
        actor.close()
    """

    def __init__(
        self,
        factory: Callable[[], R],
        *,
        name: str = "actor",
        startup_timeout: float = 30.0,
        close_timeout: float = 10.0,
        on_close: Callable[[R], None] | None = None,
    ) -> None:
        """Start the owner thread and wait for *factory* to return.

        Args:
            factory: Builds the resource.  Runs on the owner thread.
            name: Name of the owner thread.
            startup_timeout: Seconds to wait for *factory* to return.
            close_timeout: Seconds :meth:`close` waits for the owner thread
                to finish.
            on_close: Called with the resource on the owner thread after the
                last queued call.  If it raises, the error is logged.  It is
                not called when *factory* raises.  If *factory* returns after
                *startup_timeout*, the resource is passed to it at once.

        Raises:
            AppException: If *factory* raises, with the original exception as
                ``__cause__``, or if it does not return within
                *startup_timeout*.
        """
        self._factory = factory
        self._name = name
        self._close_timeout = close_timeout
        self._on_close = on_close
        self._queue: queue.SimpleQueue[
            tuple[Callable[[R], Any], Future[Any]] | None
        ] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._closed = False
        self._abandoned = False
        self._started = False
        self._startup_error: BaseException | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._main, name=name, daemon=True)
        self._thread.start()

        self._ready.wait(startup_timeout)
        with self._lock:
            # Decided under the lock the owner thread also takes, so a factory
            # finishing at the deadline is either served or closed.
            if not self._started and self._startup_error is None:
                self._abandoned = True
                self._closed = True
                raise AppException(
                    "ThreadActor {}: factory did not return within {} seconds",
                    name,
                    startup_timeout,
                )
        if self._startup_error is not None:
            raise AppException(
                "ThreadActor {}: factory failed", name
            ) from self._startup_error

    def submit[T](self, fn: Callable[[R], T]) -> Future[T]:
        """Queue ``fn(resource)`` to run on the owner thread.

        A cancelled future is skipped.  An exception, including
        ``BaseException``, raised by *fn* is set on the returned future.

        Args:
            fn: Called with the resource.

        Returns:
            A future holding the result of *fn*.

        Raises:
            AppException: If the actor has been closed.
        """
        future: Future[T] = Future()
        with self._lock:
            if self._closed:
                raise AppException("ThreadActor {} is closed", self._name)
            self._queue.put((fn, future))
        return future

    async def run[T](self, fn: Callable[[R], T]) -> T:
        """Queue ``fn(resource)`` and await its result without blocking the loop.

        Args:
            fn: Called with the resource.

        Returns:
            The result of *fn*.

        Raises:
            AppException: If the actor has been closed.
        """
        return await asyncio.wrap_future(self.submit(fn))

    def close(self) -> None:
        """Run the queued calls, then close the resource and stop the thread.

        Waits for the owner thread for at most *close_timeout* seconds; on
        timeout a warning is logged and the thread keeps draining in the
        background.  Called from the owner thread, it does not wait.  Calling
        it again is a no-op.
        """
        with self._lock:
            if not self._closed:
                self._closed = True
                self._queue.put(None)
        if threading.current_thread() is self._thread:
            return
        self._thread.join(self._close_timeout)
        if self._thread.is_alive():
            _LOGGER.warning(  # noqa: PLE1205  # brace-style log format
                "ThreadActor.close.timeout | name={} | close_timeout={}",
                self._name,
                self._close_timeout,
            )

    def _main(self) -> None:
        try:
            resource = self._factory()
        except BaseException as exc:  # noqa: BLE001  # raised from the constructor
            with self._lock:
                self._startup_error = exc
            self._ready.set()
            return
        with self._lock:
            abandoned = self._abandoned
            self._started = not abandoned
        self._ready.set()
        if abandoned:
            self._release(resource)
            return
        try:
            self._serve(resource)
        finally:
            self._release(resource)

    def _serve(self, resource: R) -> None:
        while (job := self._queue.get()) is not None:
            fn, future = job
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = fn(resource)
            except BaseException as exc:  # noqa: BLE001  # delivered to the future
                future.set_exception(exc)
            else:
                future.set_result(result)

    def _release(self, resource: R) -> None:
        if self._on_close is None:
            return
        try:
            self._on_close(resource)
        except Exception:
            _LOGGER.exception(  # noqa: PLE1205  # brace-style log format
                "ThreadActor.on_close.error | name={}", self._name
            )
