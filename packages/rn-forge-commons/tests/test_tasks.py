"""Tests for rn_forge.commons.tasks."""

import threading
import time
from types import MappingProxyType

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.tasks import Task, TaskPool


# ---------------------------------------------------------------------------
# Concrete Task implementations for testing
# ---------------------------------------------------------------------------


class SimpleTask(Task):
    """Records that run() was called."""

    def run(self) -> None:
        self._props["ran"] = True


class SlowTask(Task):
    """Sleeps for a configurable duration."""

    def run(self) -> None:
        time.sleep(self.get_prop("duration", 0.05))


class FailingTask(Task):
    """Always raises."""

    def run(self) -> None:
        raise ValueError(f"Task {self.name} intentionally failed")


class ThreadNameTask(Task):
    """Records the thread name at run time."""

    def run(self) -> None:
        self._props["thread_name"] = threading.current_thread().name


class ProducerTask(Task):
    """Writes a value into a shared list."""

    def run(self) -> None:
        self.get_prop("results").append(self.name)


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------


class TestTask:
    def test_name(self):
        t = SimpleTask("my-task")
        assert t.name == "my-task"

    def test_props_stored(self):
        t = SimpleTask("t", x=1, y="hello")
        assert t.props == {"x": 1, "y": "hello"}

    def test_get_prop(self):
        t = SimpleTask("t", key="value")
        assert t.get_prop("key") == "value"

    def test_get_prop_default(self):
        t = SimpleTask("t")
        assert t.get_prop("missing") is None
        assert t.get_prop("missing", 42) == 42

    def test_future_initially_none(self):
        assert SimpleTask("t").future is None

    def test_error_initially_none(self):
        assert SimpleTask("t").error is None

    def test_abstract_run_enforced(self):
        with pytest.raises(TypeError):
            Task("t")

    def test_start_sets_thread_name(self):
        t = ThreadNameTask("named-thread")
        t._start()
        assert t.props["thread_name"] == "named-thread"

    def test_start_captures_error(self):
        t = FailingTask("fail")
        with pytest.raises(ValueError):
            t._start()
        assert isinstance(t.error, ValueError)

    def test_start_reraises_error(self):
        t = FailingTask("fail")
        with pytest.raises(ValueError, match="intentionally failed"):
            t._start()

    def test_run_called_on_start(self):
        t = SimpleTask("t")
        t._start()
        assert t.props.get("ran") is True


# ---------------------------------------------------------------------------
# TaskPool tests
# ---------------------------------------------------------------------------


class TestTaskPoolBasic:
    def test_default_max_workers(self):
        pool = TaskPool()
        assert pool.max_workers == 10
        pool.shutdown(fail_on_error=False)

    def test_custom_max_workers(self):
        pool = TaskPool(max_workers=3)
        assert pool.max_workers == 3
        pool.shutdown(fail_on_error=False)

    def test_tasks_initially_empty(self):
        pool = TaskPool()
        assert len(pool.tasks) == 0
        pool.shutdown(fail_on_error=False)

    def test_tasks_returns_mapping_proxy(self):
        pool = TaskPool()
        assert isinstance(pool.tasks, MappingProxyType)
        pool.shutdown(fail_on_error=False)

    def test_tasks_read_only(self):
        pool = TaskPool()
        with pytest.raises(TypeError):
            pool.tasks["x"] = SimpleTask("x")
        pool.shutdown(fail_on_error=False)


class TestTaskPoolSubmit:
    def test_submit_returns_self(self):
        pool = TaskPool()
        result = pool.submit(SimpleTask("t"))
        assert result is pool
        pool.shutdown(fail_on_error=False)

    def test_submit_chaining(self):
        pool = TaskPool()
        pool.submit(SimpleTask("a")).submit(SimpleTask("b"))
        pool.shutdown(fail_on_error=False)
        assert "a" in pool.tasks
        assert "b" in pool.tasks

    def test_submit_multiple_at_once(self):
        pool = TaskPool()
        pool.submit(SimpleTask("x"), SimpleTask("y"), SimpleTask("z"))
        pool.shutdown(fail_on_error=False)
        assert set(pool.tasks) == {"x", "y", "z"}

    def test_future_assigned_after_submit(self):
        pool = TaskPool()
        t = SimpleTask("t")
        pool.submit(t)
        pool.shutdown(fail_on_error=False)
        assert t.future is not None

    def test_tasks_actually_run(self):
        results: list[str] = []
        pool = TaskPool()
        pool.submit(
            ProducerTask("a", results=results),
            ProducerTask("b", results=results),
            ProducerTask("c", results=results),
        )
        pool.shutdown(fail_on_error=False)
        assert sorted(results) == ["a", "b", "c"]

    def test_submit_rejects_duplicate_names_in_batch(self):
        pool = TaskPool()
        task_a = SimpleTask("dup")
        task_b = SimpleTask("dup")
        with pytest.raises(AppException, match="Duplicate task names"):
            pool.submit(task_a, task_b)
        pool.shutdown(fail_on_error=False)

    def test_submit_rejects_duplicate_name_from_prior_submit(self):
        pool = TaskPool()
        pool.submit(SimpleTask("dup"))
        second_task = SimpleTask("dup")
        with pytest.raises(AppException, match="already submitted"):
            pool.submit(second_task)
        pool.shutdown(fail_on_error=False)


class TestTaskPoolShutdown:
    def test_shutdown_returns_empty_on_success(self):
        pool = TaskPool()
        pool.submit(SimpleTask("ok"))
        failed = pool.shutdown(fail_on_error=False)
        assert failed == []

    def test_shutdown_returns_failed_tasks(self):
        pool = TaskPool()
        pool.submit(FailingTask("bad"))
        failed = pool.shutdown(fail_on_error=False)
        assert len(failed) == 1
        assert failed[0].name == "bad"

    def test_shutdown_fail_on_error_raises(self):
        pool = TaskPool()
        pool.submit(FailingTask("bad"))
        with pytest.raises(AppException, match="1 task"):
            pool.shutdown(fail_on_error=True)

    def test_shutdown_fail_on_error_attaches_error_data(self):
        pool = TaskPool()
        pool.submit(FailingTask("bad1"), FailingTask("bad2"))
        with pytest.raises(AppException) as exc_info:
            pool.shutdown(fail_on_error=True)
        exc = exc_info.value
        assert "bad1" in exc.error_data
        assert "bad2" in exc.error_data
        assert exc.error_code == 2

    def test_partial_failure_isolates_bad_tasks(self):
        pool = TaskPool()
        pool.submit(SimpleTask("ok"), FailingTask("bad"))
        failed = pool.shutdown(fail_on_error=False)
        assert len(failed) == 1
        assert failed[0].name == "bad"


class TestTaskPoolContextManager:
    def test_context_manager_runs_tasks(self):
        results: list[str] = []
        with TaskPool() as pool:
            pool.submit(ProducerTask("t", results=results))
        assert "t" in results

    def test_context_manager_shuts_down_on_exit(self):
        with TaskPool() as pool:
            pool.submit(SimpleTask("t"))
        # executor should be shut down — submitting again should raise
        with pytest.raises(RuntimeError):
            pool.executor.submit(lambda: None)

    def test_context_manager_propagates_exceptions(self):
        # NOSONAR: intentionally wraps the whole `with TaskPool()` block —
        # this verifies that an exception raised inside the context manager's
        # body propagates out through TaskPool.__exit__, not just that the
        # final `raise` throws.
        with pytest.raises(ValueError, match="outer"):
            with TaskPool() as pool:
                pool.submit(SimpleTask("t"))
                raise ValueError("outer")


class TestTaskPoolConcurrency:
    def test_tasks_run_concurrently(self):
        release = threading.Event()
        started_a = threading.Event()
        started_b = threading.Event()

        class BlockingTask(Task):
            def run(self) -> None:
                self.get_prop("started").set()
                release.wait(timeout=1)

        pool = TaskPool(max_workers=2)
        pool.submit(
            BlockingTask("a", started=started_a),
            BlockingTask("b", started=started_b),
        )

        assert started_a.wait(timeout=1)
        assert started_b.wait(timeout=1)

        release.set()
        pool.shutdown(fail_on_error=False)

        assert started_a.is_set() and started_b.is_set()


class TestTaskPoolAdvancedShutdown:
    def test_shutdown_timeout_argument(self):
        pool = TaskPool()
        pool.submit(SimpleTask("instant"))
        failed = pool.shutdown(timeout=0, fail_on_error=False)
        assert failed == []

    def test_shutdown_cancel_futures(self):
        release = threading.Event()

        class BlockingTask(Task):
            def run(self) -> None:
                release.wait(timeout=1)

        pool = TaskPool(max_workers=1)
        running = BlockingTask("running")
        queued = BlockingTask("queued")
        pool.submit(running, queued)

        pool.shutdown(wait=False, cancel_futures=True, fail_on_error=False)

        release.set()
        assert running.future is not None
        running.future.result(timeout=1)
        assert queued.future is not None
        assert queued.future.cancelled()

    def test_shutdown_ignores_task_without_future(self):
        pool = TaskPool()
        pool._tasks["orphan"] = SimpleTask("orphan")
        assert pool.shutdown(fail_on_error=False) == []
