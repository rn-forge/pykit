"""Subprocess execution with structured result capture.

Typical usage::

    from rn_forge.commons.runtime.subprocess import Process

    result = Process.execute("list-files", "ls", "-la", "/tmp")
    if result.succeeded:
        print(result.stdout)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self, cast

from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.reflection import ReflectUtils
from rn_forge.commons.logging import AppLogger

_LOGGER = AppLogger.get_logger(__name__)

__all__ = ["Process"]


def _require_executable(name: str) -> str:
    """Return the full path to *name* or raise :exc:`~rn_forge.commons.AppException` if not on PATH."""
    path = shutil.which(name)
    if path is None:
        _LOGGER.warning("Executable not found on PATH: {}", name)
        raise AppException("Executable not found on PATH: {}", name)
    return path


def _coerce_process_output(value: str | bytes | None) -> str | None:
    """Normalize subprocess output to text regardless of text/binary mode."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    return value


@dataclass(frozen=True)
class Process(DataclassMixin):
    """Immutable record of a subprocess execution.

    Construct via :meth:`execute` or the named shortcuts (:meth:`python`,
    :meth:`mvn`, :meth:`npm`, :meth:`az`, :meth:`pwsh`).  Instances are
    frozen dataclasses, so all fields are set at construction time.

    Fields ``kwargs``, ``error``, and ``completed_process`` are excluded
    from serialisation (they carry ``metadata={"exclude": True}``).

    Attributes:
        name: Human-readable label for the process used in log messages and
            :exc:`~rn_forge.commons.AppException` messages.
        args: The exact argument list forwarded to :func:`subprocess.run`.
        return_code: Exit code of the process (``-1`` when execution raised
            an exception before the process could return).
        stdout: Decoded standard output, or ``None`` when ``capture_output``
            was ``False``.
        stderr: Decoded standard error, or ``None`` when ``capture_output``
            was ``False``.
        kwargs: Extra keyword arguments that were passed to
            :func:`subprocess.run`. Excluded from serialisation.
        error: The exception raised during execution, if any. Excluded from
            serialisation.
        completed_process: The raw :class:`subprocess.CompletedProcess` result.
            Excluded from serialisation and equality comparison.

    Example::

        result = Process.execute("ping", "ping", "-c", "1", "localhost")
        assert result.succeeded
        assert "localhost" in (result.stdout or "")

        Process.python("scripts/build_report.py", "--date", "2026-04-23")
    """

    #: Human-readable label for this process.
    name: str
    #: The argument list passed to :func:`subprocess.run`.
    args: list[str]
    #: Exit code (``0`` means success, ``-1`` means execution error).
    return_code: int
    #: Decoded stdout, or ``None`` when output was not captured.
    stdout: str | None
    #: Decoded stderr, or ``None`` when output was not captured.
    stderr: str | None
    kwargs: dict[str, Any] = field(
        default_factory=dict[str, Any], metadata={"exclude": True}
    )
    error: Exception | None = field(default=None, metadata={"exclude": True})
    completed_process: subprocess.CompletedProcess[Any] | None = field(
        default=None, compare=False, metadata={"exclude": True}
    )

    @property
    def succeeded(self) -> bool:
        """Whether the process exited successfully.

        Returns:
            ``True`` when :attr:`return_code` is zero, ``False`` otherwise.
        """
        return self.return_code == 0

    @classmethod
    def execute(
        cls,
        name: str,
        *args: str,
        fail_on_error: bool = True,
        capture_output: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Run a subprocess and return an immutable :class:`Process` result.

        Args:
            name: Human-readable label for this process (used in log messages
                and exception messages).
            *args: Command and arguments forwarded to :func:`subprocess.run`.
                The first element must be the executable.
            fail_on_error: When ``True`` (default), raise
                :exc:`~rn_forge.commons.AppException` if the process exits
                with a non-zero return code.
            capture_output: When ``True`` (default), capture stdout and stderr
                as UTF-8 strings (with ``"ignore"`` error handling).
            **kwargs: Additional keyword arguments forwarded verbatim to
                :func:`subprocess.run` (e.g. ``cwd``, ``env``, ``timeout``).

        Returns:
            A :class:`Process` instance populated with the exit code, stdout,
            stderr, and the raw :class:`subprocess.CompletedProcess`.

        Example::

            result = Process.execute(
                "list-files",
                "ls",
                "-la",
                cwd=".",
                fail_on_error=False,
            )

        Raises:
            AppException: If *args* is empty or contains an empty string.
            AppException: If ``fail_on_error=True`` and the process exits
                with a non-zero return code.
        """
        if not args:
            raise AppException("Process '{}': no command arguments provided", name)
        if any(not arg for arg in args):
            raise AppException("Process '{}': empty argument in {}", name, args)

        stdout = stderr = None
        error: Exception | None = None
        completed: subprocess.CompletedProcess[Any] | None = None
        _LOGGER.info(
            "Process.execute | name={} | args={} | cwd={}",
            name,
            args,
            kwargs.get("cwd"),
        )

        try:
            completed = cast(
                subprocess.CompletedProcess[Any],
                subprocess.run(args, capture_output=capture_output, **kwargs),
            )
            return_code = completed.returncode
            if capture_output:
                stdout = _coerce_process_output(completed.stdout)
                stderr = _coerce_process_output(completed.stderr)
        except Exception as exc:
            return_code = -1
            stderr = ReflectUtils.get_error_message(exc)
            error = exc

        process = cls(
            name=name,
            args=list(args),
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
            kwargs=kwargs,
            error=error,
            completed_process=completed,
        )

        if return_code != 0 and fail_on_error:
            _LOGGER.error(
                "Process failed | name={} exit={} stderr={}",
                name,
                return_code,
                stderr,
            )
            raise AppException(
                "Process '{}' failed (exit {}): {}",
                name,
                return_code,
                stderr,
                error_code=return_code,
                process=process,
            )

        if return_code != 0:
            _LOGGER.warning(
                "Process completed with non-zero exit | name={} exit={} stderr={}",
                name,
                return_code,
                stderr,
            )
        elif completed is None:
            _LOGGER.warning("Process not executed: {}", name)
        else:
            _LOGGER.verbose("Process completed successfully: {}[{}]", name, return_code)

        return process

    # ------------------------------------------------------------------
    # Named shortcuts
    # ------------------------------------------------------------------

    @classmethod
    def python(cls, file: str | Path, *args: str, **kwargs: Any) -> Self:
        """Run a Python script using the active Python interpreter.

        Args:
            file: Path to the ``.py`` script to execute.
            *args: Additional arguments passed to the script.
            **kwargs: Forwarded to :meth:`execute` (e.g. ``cwd``, ``timeout``).
                Pass ``name=...`` to override the default process label.

        Returns:
            A :class:`Process` result from :meth:`execute`.

        Example::

            Process.python("scripts/build_report.py", "--date", "2026-04-23")

        Raises:
            AppException: If *file* does not exist.
        """
        path = Path(file)
        if not path.is_file():
            _LOGGER.warning("Python script not found: {}", path)
            raise AppException("Python script not found: {}", path)
        _LOGGER.debug("Process.python | path={} | args={}", path, args)
        return cls.execute(
            kwargs.pop("name", f"python[{path.stem}]"),
            sys.executable,
            path.as_posix(),
            *args,
            **kwargs,
        )

    @classmethod
    def mvn(cls, pom: str | Path, *args: str, **kwargs: Any) -> Self:
        """Run a Maven command against a POM file.

        Args:
            pom: Path to the ``pom.xml`` file.
            *args: Maven goals and arguments (e.g. ``"clean"``, ``"install"``).
            **kwargs: Forwarded to :meth:`execute`.  Pass ``name=...`` to
                override the default process label.

        Returns:
            A :class:`Process` result from :meth:`execute`.

        Raises:
            AppException: If *pom* does not exist or ``mvn`` is not on PATH.
        """
        path = Path(pom)
        if not path.is_file():
            _LOGGER.warning("POM file not found: {}", path)
            raise AppException("POM file not found: {}", path)
        goal = args[-1] if args else ""
        _LOGGER.debug("Process.mvn | pom={} | args={}", path, args)
        return cls.execute(
            kwargs.pop("name", f"mvn[{path.parent.stem}][{goal}]"),
            _require_executable("mvn"),
            "-f",
            path.as_posix(),
            *args,
            **kwargs,
        )

    @classmethod
    def npm(cls, project: str | Path, *args: str, **kwargs: Any) -> Self:
        """Run an npm command in *project* directory.

        Args:
            project: Path to the directory containing ``package.json``.
            *args: npm arguments (e.g. ``"install"``, ``"run"``, ``"build"``).
            **kwargs: Forwarded to :meth:`execute`.  Pass ``name=...`` to
                override the default process label.

        Returns:
            A :class:`Process` result from :meth:`execute`.

        Raises:
            AppException: If ``package.json`` is not found in *project* or
                ``npm`` is not on PATH.
        """
        project_path = Path(project)
        package_json = project_path / "package.json"
        if not package_json.is_file():
            _LOGGER.warning("package.json not found: {}", package_json)
            raise AppException("package.json not found: {}", package_json)
        _LOGGER.debug("Process.npm | project={} | args={}", project_path, args)
        return cls.execute(
            kwargs.pop("name", f"npm[{project_path.stem}]"),
            _require_executable("npm"),
            "--prefix",
            project_path.as_posix(),
            *args,
            **kwargs,
        )

    @classmethod
    def az(cls, cmd: str, *args: str, **kwargs: Any) -> Self:
        """Run an Azure CLI (``az``) command.

        Args:
            cmd: The ``az`` subcommand string (e.g. ``"login"``,
                ``"account list"``).
            *args: Additional arguments appended after *cmd*.
            **kwargs: Forwarded to :meth:`execute`.  Pass ``name=...`` to
                override the default process label.

        Returns:
            A :class:`Process` result from :meth:`execute`.

        Raises:
            AppException: If *cmd* is empty or ``az`` is not on PATH.
        """
        if not cmd:
            _LOGGER.warning("az: cmd is required")
            raise AppException("az: cmd is required")
        _LOGGER.debug("Process.az | cmd={} | args={}", cmd, args)
        cmd_parts = cmd.split()
        return cls.execute(
            kwargs.pop("name", f"az[{cmd}]"),
            _require_executable("az"),
            *cmd_parts,
            *args,
            **kwargs,
        )

    @classmethod
    def pwsh(
        cls,
        cmd_or_script: str | Path,
        *args: str,
        mode: str = "command",
        **kwargs: Any,
    ) -> Self:
        """Run a PowerShell (``pwsh``) command or script.

        Args:
            cmd_or_script: A PowerShell command string or a path to a ``.ps1``
                script file.
            *args: Additional arguments appended to the ``pwsh`` invocation.
            mode: ``"command"`` (default) executes *cmd_or_script* as an
                inline command (``-Command``).  ``"file"`` treats it as a
                script path (``-File``).
            **kwargs: Forwarded to :meth:`execute`.  Pass ``name=...`` to
                override the default process label.

        Returns:
            A :class:`Process` result from :meth:`execute`.

        Raises:
            AppException: If *cmd_or_script* is empty, ``mode="file"`` is used
                and the script path does not exist, or ``pwsh`` is not on PATH.
        """
        if not cmd_or_script:
            _LOGGER.warning("pwsh: cmd_or_script is required")
            raise AppException("pwsh: cmd_or_script is required")
        path = Path(cmd_or_script)
        if mode == "file" and not path.is_file():
            _LOGGER.warning("PowerShell script not found: {}", path)
            raise AppException("PowerShell script not found: {}", path)
        _LOGGER.debug(
            "Process.pwsh | mode={} | target={} | args={}",
            mode,
            cmd_or_script,
            args,
        )
        return cls.execute(
            kwargs.pop("name", f"pwsh[{path.stem}]"),
            _require_executable("pwsh"),
            f"-{mode.capitalize()}",
            path.as_posix(),
            *args,
            **kwargs,
        )
