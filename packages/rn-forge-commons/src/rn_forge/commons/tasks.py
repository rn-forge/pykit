"""Parallel task execution via a managed thread pool.

Provides:
    Task: Abstract base class for units of concurrent work.  Subclass and
        implement :meth:`Task.run`.
    TaskPool: Thread pool that submits :class:`Task` instances, tracks their
        futures, and reports failures on shutdown.

Typical usage::

    from rn_forge.commons.tasks import Task, TaskPool

    class FetchTask(Task):
        def run(self) -> None:
            url = self.get_prop("url")
            ...  # perform work

    with TaskPool(max_workers=4) as pool:
        pool.submit(
            FetchTask("fetch-a", url="https://example.com/a"),
            FetchTask("fetch-b", url="https://example.com/b"),
        )
    # all tasks have completed (or AppException is raised on failure)
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from abc import ABC, abstractmethod
from types import MappingProxyType, TracebackType
from typing import Any, Self

from concurrent.futures import CancelledError

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

__all__ = ["Task", "TaskPool"]

_LOGGER = AppLogger.get_logger(__name__)



class Task(ABC):
    """Abstract base for units of work executed inside a :class:`TaskPool`.

    Subclass and implement :meth:`run`.  Pass keyword arguments as *props*;
    retrieve them later with :meth:`get_prop`.

    Example::

        class DownloadTask(Task):
            def run(self):
                url = self.get_prop("url")
                ...

        pool = TaskPool()
        pool.submit(DownloadTask("fetch-data", url="https://example.com"))
        pool.shutdown()
    """

    def __init__(self, name: str, **props: Any) -> None:
        """Initialize a :class:`Task`.

        Args:
            name: Unique human-readable identifier for this task.  Used as the
                thread name while the task is executing and as the key in
                :attr:`TaskPool.tasks`.
            **props: Arbitrary keyword arguments stored as task properties and
                retrievable via :meth:`get_prop`.
        """
        self._name = name
        self._props: dict[str, Any] = props
        self._future: concurrent.futures.Future[Any] | None = None
        self._error: Exception | None = None

    @property
    def name(self) -> str:
        """Unique identifier for this task.

        Returns:
            The name string supplied at construction time.
        """
        return self._name

    @property
    def props(self) -> dict[str, Any]:
        """Dictionary of properties supplied at construction time.

        Returns:
            A mutable dict of all keyword arguments passed to ``__init__``.
        """
        return self._props

    @property
    def future(self) -> concurrent.futures.Future[Any] | None:
        """The :class:`~concurrent.futures.Future` for this task's execution.

        Returns:
            The ``Future`` assigned by :meth:`TaskPool.submit`, or ``None``
            before the task has been submitted.
        """
        return self._future

    @property
    def error(self) -> Exception | None:
        """The exception raised during :meth:`run`, if any.

        Returns:
            The caught exception, or ``None`` when the task succeeded or has
            not yet been run.
        """
        return self._error

    def get_prop(self, key: str, default: Any = None) -> Any:
        """Return the prop value for *key*, or *default* if absent.

        Args:
            key: The property name to look up.
            default: Value returned when *key* is not present. Defaults to
                ``None``.

        Returns:
            The stored property value, or *default*.
        """
        return self._props.get(key, default)

    def _set_future(self, future: concurrent.futures.Future[Any]) -> None:
        self._future = future

    def _start(self) -> None:
        """Entry point called by the thread pool. Do not override."""
        _LOGGER.info("Task.start | name={} | props={}", self._name, self._props)
        threading.current_thread().name = self._name
        try:
            self.run()
        except Exception as exc:
            self._error = exc
            _LOGGER.exception("Task.error | name={}", self._name)
            raise
        _LOGGER.verbose("Task.complete | name={} | props={}", self._name, self._props)

    @abstractmethod
    def run(self) -> None:
        """Execute the task's work.

        Subclasses must implement this method.  It is called by the thread
        pool via :meth:`_start`; do not call it directly.  Any exception
        raised here is captured in :attr:`error` and re-raised so the
        :class:`~concurrent.futures.Future` records it.
        """


class TaskPool[_TaskType: Task]:
    """Thread pool that submits :class:`Task` instances and tracks their results.

    The type parameter ``_TaskType`` bounds the pool to a specific
    :class:`Task` subclass, enabling type-safe access to task-specific
    properties after completion.

    Can be used as a context manager — :meth:`__exit__` calls
    ``executor.shutdown(wait=True)`` so all tasks finish before the ``with``
    block exits::

        with TaskPool(max_workers=4) as pool:
            pool.submit(task_a, task_b, task_c)
        # all tasks complete here

    Note:
        Using the context manager does **not** automatically raise on task
        failures.  Call :meth:`shutdown` explicitly if you need
        ``fail_on_error`` behaviour inside the context.

    Example::

        pool = TaskPool(max_workers=4)
        failed = pool.submit(task_a, task_b).shutdown(fail_on_error=False)
        if failed:
            ...
    """

    def __init__(self, max_workers: int = 10) -> None:
        """Initialize a :class:`TaskPool`.

        Args:
            max_workers: Maximum number of concurrent worker threads.
                Defaults to ``10``.
        """
        self._max_workers = max_workers
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, _TaskType] = {}
        self._shutdown: bool = False

    @property
    def max_workers(self) -> int:
        """Maximum number of concurrent worker threads configured at construction.

        Returns:
            The integer value passed as *max_workers* to ``__init__``.
        """
        return self._max_workers

    @property
    def executor(self) -> concurrent.futures.ThreadPoolExecutor:
        """The underlying :class:`~concurrent.futures.ThreadPoolExecutor`.

        Returns:
            The executor instance managing the thread pool.
        """
        return self._executor

    @property
    def tasks(self) -> MappingProxyType[str, _TaskType]:
        """Read-only view of submitted tasks keyed by name."""
        return MappingProxyType(self._tasks)

    def submit(self, *tasks: _TaskType) -> Self:
        """Submit one or more tasks for execution and return *self* for chaining.

        Args:
            *tasks: :class:`Task` instances to enqueue.

        Raises:
            AppException: If the pool has already been shut down.
        """
        if self._shutdown:
            raise AppException(
                "Cannot submit tasks: TaskPool has already been shut down"
            )
        task_names = [task.name for task in tasks]
        duplicate_names = sorted(
            {name for name in task_names if task_names.count(name) > 1}
        )
        if duplicate_names:
            _LOGGER.warning(
                "TaskPool.submit | duplicate_names={}",
                duplicate_names,
            )
            raise AppException("Duplicate task names in submit(): {}", duplicate_names)

        _LOGGER.debug("TaskPool.submit | task_count={}", len(tasks))
        for task in tasks:
            if task.name in self._tasks:
                _LOGGER.warning(
                    "TaskPool.submit | already_submitted_name={}",
                    task.name,
                )
                raise AppException("Task name already submitted: {}", task.name)
            future = self._executor.submit(task._start)  # pyright: ignore[reportPrivateUsage]
            task._set_future(future)  # pyright: ignore[reportPrivateUsage]
            self._tasks[task.name] = task
            _LOGGER.debug("Submitted task | name={}", task.name)
        return self

    def shutdown(
        self,
        wait: bool = True,
        cancel_futures: bool = False,
        timeout: float | None = None,
        fail_on_error: bool = True,
    ) -> list[_TaskType]:
        """Wait for all tasks to finish and shut down the pool.

        Args:
            wait: Block until all running futures complete (default ``True``).
            cancel_futures: Cancel pending (not-yet-started) futures.
            timeout: Per-task timeout in seconds when checking for exceptions.
            fail_on_error: Raise :exc:`~rn_forge.commons.AppException` if any tasks failed.

        Returns:
            List of failed :class:`Task` instances (empty if all succeeded).

        Example::

            failed = pool.shutdown(timeout=5, fail_on_error=False)
            for task in failed:
                print(task.name, task.error)
        """
        _LOGGER.notice(
            "shutdown.initiated | tasks={} | wait={} | cancel_futures={} | timeout={} | fail_on_error={}",
            len(self._tasks),
            wait,
            cancel_futures,
            timeout,
            fail_on_error,
        )
        self._shutdown = True
        start = time.perf_counter()
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        elapsed = time.perf_counter() - start

        _LOGGER.success(
            "shutdown.complete: tasks={} | time={:.6f} seconds",
            len(self._tasks),
            elapsed,
        )

        failed: list[_TaskType] = []
        for task in self._tasks.values():
            future = task.future
            if future is None:
                continue
            try:
                exc = future.exception(timeout=timeout)
            except CancelledError as err:
                exc = err
                task._error = err  # pyright: ignore[reportPrivateUsage]
            if exc:
                failed.append(task)

        if failed and fail_on_error:
            _LOGGER.warning(
                "TaskPool.shutdown | failed_tasks={}",
                [task.name for task in failed],
            )
            raise AppException(
                "TaskPool: {} task(s) failed",
                len(failed),
                error_code=len(failed),
                **{t.name: t.error for t in failed},
            )

        return failed

    def __enter__(self) -> Self:
        """Enter the context manager.

        Returns:
            This :class:`TaskPool` instance.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager, waiting for all running tasks to finish.

        Calls ``executor.shutdown(wait=True)``.  Task exceptions are stored
        on the individual :class:`Task` instances but are **not** re-raised
        here — inspect :attr:`Task.error` or call :meth:`shutdown` with
        ``fail_on_error=True`` if you need failure propagation.

        Args:
            exc_type: Exception type, if any.
            exc_val: Exception value, if any.
            exc_tb: Exception traceback, if any.
        """
        _LOGGER.trace(
            "TaskPool.__exit__ | task_count={} | fail_on_error_propagation=false",
            len(self._tasks),
        )
        self._shutdown = True
        self._executor.shutdown(wait=True)
