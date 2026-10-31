"""Tests for rn_forge.commons.runtime.actor."""

import asyncio
import threading
from concurrent.futures import Future

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.runtime.actor import ThreadActor


class _Resource:
    def __init__(self) -> None:
        self.thread = threading.current_thread()


def test_calls_run_on_the_factory_thread() -> None:
    actor = ThreadActor(_Resource, name="owner-test")
    try:
        threads = [
            f.result(timeout=5)
            for f in [
                actor.submit(lambda _: threading.current_thread()) for _ in range(5)
            ]
        ]
        resource_thread = actor.submit(lambda r: r.thread).result(timeout=5)
    finally:
        actor.close()
    assert len({t.ident for t in threads}) == 1
    assert threads[0] is resource_thread
    assert threads[0] is not threading.current_thread()
    assert threads[0].name == "owner-test"
    assert threads[0].daemon


def test_per_producer_order_with_concurrent_producers() -> None:
    seen: list[tuple[int, int]] = []
    actor = ThreadActor(list)
    futures: list[Future[None]] = []
    futures_lock = threading.Lock()

    def produce(pid: int) -> None:
        for i in range(50):
            fut = actor.submit(lambda _, p=pid, n=i: seen.append((p, n)))
            with futures_lock:
                futures.append(fut)

    producers = [threading.Thread(target=produce, args=(p,)) for p in range(4)]
    for t in producers:
        t.start()
    for t in producers:
        t.join()
    actor.close()
    for f in futures:
        f.result(timeout=5)
    assert len(seen) == 200
    for pid in range(4):
        assert [n for p, n in seen if p == pid] == list(range(50))


def test_exception_in_fn_only_reaches_its_future() -> None:
    actor = ThreadActor(_Resource)

    def boom(_: _Resource) -> None:
        raise ValueError("boom")

    def stop(_: _Resource) -> None:
        raise KeyboardInterrupt

    try:
        bad = actor.submit(boom)
        base = actor.submit(stop)
        good = actor.submit(lambda _: 42)
        assert good.result(timeout=5) == 42
    finally:
        actor.close()
    with pytest.raises(ValueError, match="boom"):
        bad.result(timeout=5)
    with pytest.raises(KeyboardInterrupt):
        base.result(timeout=5)


def test_factory_failure_raises_with_cause_and_skips_on_close() -> None:
    closed: list[object] = []

    def factory() -> object:
        raise RuntimeError("no resource")

    with pytest.raises(AppException) as info:
        ThreadActor(factory, on_close=closed.append)
    assert isinstance(info.value.__cause__, RuntimeError)
    assert closed == []


def test_slow_factory_times_out_and_resource_reaches_on_close() -> None:
    release = threading.Event()
    closed = threading.Event()
    closed_on: list[threading.Thread] = []
    holder: list[threading.Thread] = []

    def factory() -> object:
        holder.append(threading.current_thread())
        release.wait(timeout=5)
        return object()

    def on_close(_: object) -> None:
        closed_on.append(threading.current_thread())
        closed.set()

    with pytest.raises(AppException):
        ThreadActor(factory, startup_timeout=0.05, on_close=on_close)
    release.set()
    assert closed.wait(timeout=5)
    holder[0].join(timeout=5)
    assert not holder[0].is_alive()
    assert closed_on == holder


@pytest.mark.asyncio
async def test_run_does_not_block_the_event_loop() -> None:
    started = threading.Event()
    gate = threading.Event()
    actor = ThreadActor(_Resource)

    def work(_: _Resource) -> str:
        started.set()
        gate.wait(timeout=5)
        return "done"

    try:
        task = asyncio.create_task(actor.run(work))
        while not started.is_set():
            await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
        gate.set()
        assert await task == "done"
    finally:
        gate.set()
        actor.close()


def test_close_drains_calls_closes_on_owner_thread_and_is_idempotent() -> None:
    closed_on: list[threading.Thread] = []
    gate = threading.Event()
    ran: list[int] = []

    actor = ThreadActor(
        _Resource, on_close=lambda r: closed_on.append(threading.current_thread())
    )
    owner = actor.submit(lambda r: r.thread)
    actor.submit(lambda _: gate.wait(timeout=5))
    queued = [actor.submit(lambda _, n=n: ran.append(n)) for n in range(3)]
    gate.set()
    actor.close()
    actor.close()

    assert ran == [0, 1, 2]
    assert all(f.done() for f in queued)
    assert closed_on == [owner.result(timeout=5)]
    with pytest.raises(AppException):
        actor.submit(lambda _: None)


def test_cancelled_future_is_skipped() -> None:
    gate = threading.Event()
    ran: list[int] = []
    actor = ThreadActor(_Resource)
    try:
        actor.submit(lambda _: gate.wait(timeout=5))
        cancelled = actor.submit(lambda _: ran.append(1))
        kept = actor.submit(lambda _: ran.append(2))
        assert cancelled.cancel()
        gate.set()
        kept.result(timeout=5)
    finally:
        gate.set()
        actor.close()
    assert ran == [2]


def test_close_from_the_owner_thread_does_not_deadlock() -> None:
    closed = threading.Event()
    actor = ThreadActor(_Resource, on_close=lambda _: closed.set())

    actor.submit(lambda _: actor.close()).result(timeout=5)

    assert closed.wait(timeout=5)
    with pytest.raises(AppException):
        actor.submit(lambda _: None)


def test_on_close_failure_does_not_reach_the_caller() -> None:
    def on_close(_: _Resource) -> None:
        raise RuntimeError("close failed")

    actor = ThreadActor(_Resource, on_close=on_close)

    actor.close()


def test_startup_errors_name_the_actor() -> None:
    def factory() -> object:
        raise RuntimeError("no resource")

    with pytest.raises(AppException, match="db"):
        ThreadActor(factory, name="db")
