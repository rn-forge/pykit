"""Tests for rn_forge.web.health."""

import asyncio
import threading
import time
from concurrent.futures import Future
from contextlib import contextmanager

import pytest
from assertpy import assert_that
from rn_forge.web import health
from rn_forge.web.exceptions import WebError
from rn_forge.web.health import CheckResult, run_checks, run_checks_sync

pytestmark = pytest.mark.unit


def ok() -> CheckResult:
    return CheckResult(status="pass")


def bad() -> CheckResult:
    return CheckResult(status="fail", reason="unreachable", remediation="start it")


def warned() -> CheckResult:
    return CheckResult(status="warn", reason="slow")


def skipped() -> CheckResult:
    return CheckResult(status="skipped", reason="not configured")


def boom() -> CheckResult:
    raise RuntimeError("kaboom")


async def aok() -> CheckResult:
    await asyncio.sleep(0)
    return CheckResult(status="pass")


@contextmanager
def _blocked_sync_run(count=1, timeout=0.05):
    release = threading.Event()
    started = threading.Semaphore(0)
    returned = threading.Event()
    outcome = Future()
    elapsed = []
    finished = threading.Semaphore(0)

    def blocked():
        started.release()
        try:
            release.wait()
            return True
        finally:
            finished.release()

    def run():
        before = time.monotonic()
        try:
            outcome.set_result(
                run_checks_sync(
                    {str(i): blocked for i in range(count)},
                    required=["0"],
                    timeout=timeout,
                )
            )
        except Exception as exc:  # noqa: BLE001 - surface helper-thread errors in the test
            outcome.set_exception(exc)
        finally:
            elapsed.append(time.monotonic() - before)
            returned.set()

    caller = threading.Thread(target=run)
    caller.start()
    try:
        for _ in range(count):
            assert started.acquire(timeout=5)
        yield release, returned, outcome, elapsed
    finally:
        release.set()
        caller.join(timeout=5)
        assert not caller.is_alive()
        for _ in range(count):
            assert finished.acquire(timeout=5)


def test_run_checks_sync_waits_for_a_blocked_check_after_timeout():
    with _blocked_sync_run() as (release, returned, outcome, elapsed):
        before_release = returned.wait(timeout=0.5)
        assert not release.is_set()
    assert outcome.result().checks["0"].status == "fail"
    assert before_release, f"call waited for release ({elapsed[0]:.3f}s)"


def test_run_checks_sync_gives_each_check_a_serial_deadline(monkeypatch):
    timeout = 0.3
    waits_finished = threading.Event()
    waits = []
    original_result = Future.result

    def observed_result(future, timeout=None):
        try:
            return original_result(future, timeout=timeout)
        finally:
            if timeout is not None:
                waits.append(time.monotonic())
                if len(waits) == 3:
                    waits_finished.set()

    monkeypatch.setattr(Future, "result", observed_result)
    with _blocked_sync_run(count=3, timeout=timeout) as (_, _, outcome, elapsed):
        assert waits_finished.wait(timeout=5)
    assert len(outcome.result().checks) == 3
    assert elapsed[0] < 2 * timeout, f"three waits took {elapsed[0]:.3f}s"


def test_run_checks_sync_reports_timeout_as_failed_check():
    with _blocked_sync_run() as (_, returned, outcome, elapsed):
        returned.wait(timeout=0.5)
    report = outcome.result()
    assert report.checks["0"].status == "fail"
    assert report.checks["0"].reason == "timed out after 0.05s"
    assert report.http_status == 503
    print(f"blocked sync call: {elapsed[0]:.3f}s (timeout=0.05s, release after 0.5s)")


@pytest.fixture
def fresh_pool(monkeypatch):
    pools = []

    def install(cap):
        pool = health._SyncCheckPool(cap)
        monkeypatch.setattr(health, "_sync_pool", pool)
        pools.append(pool)
        return pool

    yield install
    for pool in pools:
        if pool._executor is not None:
            pool._executor.shutdown(wait=True)


def test_overlapping_blocked_calls_share_a_bounded_pool(fresh_pool):
    fresh_pool(4)
    release = threading.Event()
    started = []
    outcomes = [Future() for _ in range(6)]

    def blocked():
        started.append(threading.current_thread())
        release.wait()
        return True

    def run(outcome):
        try:
            outcome.set_result(run_checks_sync({"db": blocked}, timeout=0.05))
        except Exception as exc:  # noqa: BLE001 - surface caller-thread errors
            outcome.set_exception(exc)

    baseline = threading.active_count()
    callers = [threading.Thread(target=run, args=(outcome,)) for outcome in outcomes]
    try:
        for caller in callers:
            caller.start()
        for caller in callers:
            caller.join(timeout=0.5)
        assert len(started) <= 4
        assert threading.active_count() <= baseline + 4 + len(callers)
        assert all(outcome.done() for outcome in outcomes)
        assert (
            sum(
                outcome.result().checks["db"].reason
                == "not run: health check capacity exhausted"
                for outcome in outcomes
            )
            == 2
        )
        assert not release.is_set()
    finally:
        release.set()
        for caller in callers:
            caller.join(timeout=5)
            assert not caller.is_alive()


def test_a_full_pool_fails_the_check_without_queueing(fresh_pool):
    fresh_pool(1)
    ran = threading.Event()
    with _blocked_sync_run() as (_, _, _, _):
        before = time.monotonic()
        report = run_checks_sync({"cache": lambda: ran.set() or True}, timeout=1)
        assert time.monotonic() - before < 0.5
        assert not ran.is_set()
        assert report.checks["cache"] == CheckResult(
            status="fail", reason="not run: health check capacity exhausted"
        )


def test_a_released_slot_is_reused(fresh_pool):
    pool = fresh_pool(1)
    with _blocked_sync_run() as (_, returned, _, _):
        returned.wait(timeout=0.5)
    assert pool._executor is not None
    pool._executor.submit(lambda: None).result(timeout=5)
    assert run_checks_sync({"cache": ok}).checks["cache"].status == "pass"


@pytest.mark.asyncio
async def test_run_checks_async_leaves_the_worker_running_after_timeout():
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    workers = []

    def blocked():
        workers.append(threading.current_thread())
        started.set()
        try:
            release.wait()
            return True
        finally:
            finished.set()

    before = time.monotonic()
    try:
        report = await asyncio.wait_for(run_checks({"db": blocked}, timeout=0.05), 2)
        elapsed = time.monotonic() - before
        assert started.is_set()
        assert elapsed < 1
        assert report.checks["db"].status == "fail"
        assert report.checks["db"].reason == "timed out after 0.05s"
        assert not finished.is_set()
        assert workers[0].is_alive()
        print(f"async call: {elapsed:.3f}s; worker still running")
    finally:
        release.set()
        assert finished.wait(timeout=5)


# --- the sync runner ------------------------------------------------------


def test_all_pass_is_200():
    report = run_checks_sync({"db": ok, "queue": ok})
    assert_that(report.status).is_equal_to("pass")
    assert_that(report.http_status).is_equal_to(200)


def test_a_required_failure_is_503():
    report = run_checks_sync({"db": bad, "queue": ok}, required=["db"])
    assert_that(report.status).is_equal_to("fail")
    assert_that(report.http_status).is_equal_to(503)


def test_a_non_required_failure_is_200_but_degraded():
    report = run_checks_sync({"db": ok, "queue": bad}, required=["db"])
    assert_that(report.status).is_equal_to("fail")
    assert_that(report.http_status).is_equal_to(200)


def test_a_warning_never_changes_the_http_status():
    report = run_checks_sync({"db": warned}, required=["db"])
    assert_that(report.status).is_equal_to("warn")
    assert_that(report.http_status).is_equal_to(200)


def test_skipped_is_recorded_and_ignored_for_the_aggregate():
    report = run_checks_sync({"db": ok, "saml": skipped})
    assert_that(report.status).is_equal_to("pass")
    assert_that(report.checks["saml"].status).is_equal_to("skipped")
    assert_that(report.checks["saml"].reason).is_equal_to("not configured")


def test_a_skipped_required_check_does_not_503():
    """ "Not configured" is not "broken"."""
    report = run_checks_sync({"db": skipped}, required=["db"])
    assert_that(report.http_status).is_equal_to(200)


def test_a_raising_check_becomes_a_failure_carrying_its_message():
    report = run_checks_sync({"db": boom}, required=["db"])
    assert_that(report.checks["db"].status).is_equal_to("fail")
    assert_that(report.checks["db"].reason).is_equal_to("kaboom")
    assert_that(report.http_status).is_equal_to(503)


def test_a_raising_check_with_no_message_names_its_type():
    report = run_checks_sync({"db": lambda: (_ for _ in ()).throw(RuntimeError())})
    assert_that(report.checks["db"].reason).is_equal_to("RuntimeError")


@pytest.mark.parametrize(("value", "expected"), [(True, "pass"), (False, "fail")])
def test_a_bool_is_coerced(value, expected):
    report = run_checks_sync({"db": lambda: value})
    assert_that(report.checks["db"].status).is_equal_to(expected)


def test_an_empty_map_is_200():
    report = run_checks_sync({})
    assert_that(report.status).is_equal_to("pass")
    assert_that(report.http_status).is_equal_to(200)


def test_a_required_name_that_is_not_a_check_is_ignored():
    report = run_checks_sync({"db": ok}, required=["db", "nonexistent"])
    assert_that(report.http_status).is_equal_to(200)


def test_the_sync_runner_refuses_an_async_check():
    """Otherwise a coroutine object is reported as truthy and therefore passing."""
    assert_that(run_checks_sync).raises(WebError).when_called_with({"db": aok})


def test_the_worst_status_wins():
    report = run_checks_sync({"a": ok, "b": warned, "c": bad, "d": skipped})
    assert_that(report.status).is_equal_to("fail")


def test_warn_beats_pass_and_skipped():
    report = run_checks_sync({"a": ok, "b": warned, "c": skipped})
    assert_that(report.status).is_equal_to("warn")


def test_the_report_body_omits_the_transport_status():
    report = run_checks_sync({"db": ok})
    assert_that(report.as_body()).is_equal_to(
        {
            "status": "pass",
            "checks": {
                "db": {
                    "status": "pass",
                    "reason": None,
                    "remediation": None,
                    "details": {},
                }
            },
        }
    )


# --- the async runner -----------------------------------------------------


@pytest.mark.asyncio
async def test_async_and_sync_checks_mix_freely():
    report = await run_checks({"sync": ok, "async": aok, "bool": lambda: True})
    assert_that(report.status).is_equal_to("pass")
    assert_that(report.checks).is_length(3)


@pytest.mark.asyncio
async def test_an_async_check_that_raises_is_captured():
    async def afail() -> CheckResult:
        raise RuntimeError("kaboom")

    report = await run_checks({"db": afail}, required=["db"])
    assert_that(report.checks["db"].reason).is_equal_to("kaboom")
    assert_that(report.http_status).is_equal_to(503)


@pytest.mark.asyncio
async def test_an_async_required_failure_is_503():
    async def afail() -> CheckResult:
        return CheckResult(status="fail", reason="down")

    report = await run_checks({"db": afail, "q": aok}, required=["db"])
    assert_that(report.http_status).is_equal_to(503)


@pytest.mark.asyncio
async def test_checks_run_concurrently_not_serially():
    started: list[str] = []
    release = asyncio.Event()

    async def gated(name: str) -> CheckResult:
        started.append(name)
        # Both checks must have started before either is allowed to finish;
        # under a serial runner the second never starts and this deadlocks.
        if len(started) == 2:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=1)
        return CheckResult(status="pass")

    report = await asyncio.wait_for(
        run_checks({"a": lambda: gated("a"), "b": lambda: gated("b")}), timeout=2
    )
    assert_that(report.status).is_equal_to("pass")
    assert_that(started).contains("a", "b")


@pytest.mark.asyncio
async def test_sync_checks_run_off_the_event_loop():
    # Each check blocks until both checks are running (the barrier) and the
    # loop has run other work (loop_ran). On the loop, or serially, neither can
    # happen, so the checks time out and fail. The timeouts only bound the
    # failure path; a passing run never waits on them.
    both_running = threading.Barrier(2)
    loop_ran = threading.Event()

    def blocking() -> CheckResult:
        both_running.wait(timeout=5)
        if not loop_ran.wait(timeout=5):
            return CheckResult(status="fail", reason="event loop was blocked")
        return CheckResult(status="pass")

    async def tick() -> None:
        await asyncio.sleep(0)
        loop_ran.set()

    ticker = asyncio.create_task(tick())
    report = await run_checks({"a": blocking, "b": blocking})
    await ticker
    assert_that(report.status).is_equal_to("pass")


@pytest.mark.asyncio
async def test_the_async_runner_preserves_check_names():
    report = await run_checks({"db": aok, "queue": ok})
    assert_that(list(report.checks)).is_equal_to(["db", "queue"])


@pytest.mark.asyncio
async def test_an_empty_map_is_200_async():
    report = await run_checks({})
    assert_that(report.http_status).is_equal_to(200)


@pytest.mark.asyncio
async def test_a_hung_async_check_times_out_as_a_failure():
    async def hung() -> CheckResult:
        await asyncio.Event().wait()
        return CheckResult(status="pass")

    report = await asyncio.wait_for(
        run_checks({"db": hung, "queue": aok}, required=["db"], timeout=0.05),
        timeout=2,
    )
    assert_that(report.checks["db"].status).is_equal_to("fail")
    assert_that(report.checks["db"].reason).is_equal_to("timed out after 0.05s")
    assert_that(report.checks["queue"].status).is_equal_to("pass")
    assert_that(report.http_status).is_equal_to(503)


@pytest.mark.asyncio
async def test_a_hung_sync_check_times_out_without_blocking_the_run():
    release = threading.Event()

    def hung() -> bool:
        return release.wait(timeout=2)

    try:
        report = await asyncio.wait_for(
            run_checks({"db": hung}, timeout=0.05), timeout=1
        )
    finally:
        release.set()
    assert_that(report.checks["db"].status).is_equal_to("fail")
    assert_that(report.checks["db"].reason).contains("timed out")


@pytest.mark.asyncio
async def test_a_check_inside_the_timeout_is_unaffected():
    report = await run_checks({"db": aok, "sync": ok}, timeout=1)
    assert_that(report.status).is_equal_to("pass")


# --- the wire body --------------------------------------------------------


def test_as_body_omits_http_status():
    """It is the status line, not body content — and the only snake_case name here."""
    report = run_checks_sync({"db": ok})
    assert_that(report.as_body()).does_not_contain_key("http_status")


def test_as_body_matches_the_conformance_table():
    report = run_checks_sync({"db": ok, "queue": bad}, required=["db"])
    assert_that(report.as_body()).is_equal_to(
        {
            "status": "fail",
            "checks": {
                "db": {
                    "status": "pass",
                    "reason": None,
                    "remediation": None,
                    "details": {},
                },
                "queue": {
                    "status": "fail",
                    "reason": "unreachable",
                    "remediation": "start it",
                    "details": {},
                },
            },
        }
    )


def test_as_body_keys_are_all_camel_case():

    report = run_checks_sync({"db": ok})
    for key in report.as_body()["checks"]["db"]:
        assert_that(key).matches(r"^[a-z][a-zA-Z0-9]*$")
