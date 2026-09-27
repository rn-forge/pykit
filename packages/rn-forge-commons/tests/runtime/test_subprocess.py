"""Tests for rn_forge.commons.runtime.subprocess."""

import json
import shutil
import sys
from pathlib import Path

import pytest

import rn_forge.commons.runtime.subprocess as subprocess_module
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.runtime.subprocess import (
    Process,
    _coerce_process_output,
    _require_executable,
)


class TestRequireExecutable:
    def test_finds_python(self):
        # python3 (or python on Windows) should always be present in the test env
        result = _require_executable(sys.executable.split("/")[-1])
        assert result is not None

    def test_raises_for_missing(self):
        with pytest.raises(AppException, match="not found on PATH"):
            _require_executable("__no_such_executable_xyz__")


class TestCoerceProcessOutput:
    def test_none_returns_none(self):
        assert _coerce_process_output(None) is None

    def test_bytes_decode_to_string(self):
        assert _coerce_process_output(b"hello") == "hello"


class TestProcessDataclass:
    def _make(self, **overrides):
        defaults = {
            "name": "test",
            "args": ["echo", "hi"],
            "return_code": 0,
            "stdout": "hi\n",
            "stderr": "",
        }
        defaults.update(overrides)
        return Process(**defaults)

    def test_succeeded_true_on_zero(self):
        assert self._make(return_code=0).succeeded is True

    def test_succeeded_false_on_nonzero(self):
        assert self._make(return_code=1).succeeded is False

    def test_excluded_fields_not_in_as_dict(self):
        p = self._make(kwargs={"cwd": "/tmp"}, error=None, completed_process=None)
        d = p.as_dict()
        assert "kwargs" not in d
        assert "error" not in d
        assert "completed_process" not in d

    def test_core_fields_in_as_dict(self):
        p = self._make()
        d = p.as_dict()
        assert d["name"] == "test"
        assert d["return_code"] == 0
        assert d["stdout"] == "hi\n"

    def test_to_json_roundtrip(self):
        p = self._make()
        data = json.loads(p.to_json())
        assert data["name"] == "test"
        assert data["return_code"] == 0

    def test_frozen(self):
        p = self._make()
        with pytest.raises((AttributeError, TypeError)):
            p.return_code = 1


class TestProcessExecute:
    def _run_py(self, name: str, code: str, **kwargs):
        return Process.execute(name, sys.executable, "-c", code, **kwargs)

    def test_success(self):
        p = self._run_py("py-success", "print('hello')")
        assert p.succeeded
        assert p.return_code == 0
        assert p.name == "py-success"
        assert "hello" in (p.stdout or "")

    def test_captures_stdout(self):
        p = self._run_py("py-stdout", "print('captured')")
        assert p.stdout is not None
        assert "captured" in p.stdout

    def test_text_mode_output_is_preserved(self):
        p = self._run_py("py-text-mode", "print('text-mode')", text=True)
        assert p.succeeded
        assert p.stdout is not None
        assert "text-mode" in p.stdout

    def test_capture_output_false(self):
        p = self._run_py("py-no-capture", "print('x')", capture_output=False)
        assert p.stdout is None
        assert p.stderr is None

    def test_fail_on_error_raises(self):
        with pytest.raises(AppException, match="failed"):
            self._run_py("py-exit1", "import sys; sys.exit(1)")

    def test_fail_on_error_false_returns_process(self):
        p = self._run_py("py-exit2", "import sys; sys.exit(2)", fail_on_error=False)
        assert not p.succeeded
        assert p.return_code != 0

    def test_no_args_raises_app_exception(self):
        with pytest.raises(AppException, match="no command arguments"):
            Process.execute("empty")

    def test_empty_arg_raises_app_exception(self):
        with pytest.raises(AppException, match="empty argument"):
            Process.execute("bad", "echo", "")

    def test_args_stored_on_result(self):
        p = self._run_py("py-args", "print('hi')", fail_on_error=False)
        assert p.args[0] == sys.executable

    def test_nonexistent_command_captured_as_error(self):
        p = Process.execute("missing", "__no_such_cmd_xyz__", fail_on_error=False)
        assert not p.succeeded
        assert p.return_code == -1
        assert p.error is not None
        assert p.stderr is not None

    def test_stderr_captured_on_failure(self):
        p = self._run_py(
            "py-stderr",
            "import sys; sys.stderr.write('boom'); sys.exit(1)",
            fail_on_error=False,
        )
        assert not p.succeeded
        assert p.stderr  # non-empty


class TestProcessPythonShortcut:
    def test_runs_script(self, tmp_path: Path):
        script = tmp_path / "hello.py"
        script.write_text("print('from-script')")
        p = Process.python(script)
        assert p.succeeded
        assert "from-script" in (p.stdout or "")

    def test_passes_args_to_script(self, tmp_path: Path):
        script = tmp_path / "args.py"
        script.write_text("import sys; print(sys.argv[1])")
        p = Process.python(script, "myarg")
        assert "myarg" in (p.stdout or "")

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(AppException, match="not found"):
            Process.python(tmp_path / "missing.py")

    def test_default_name_uses_stem(self, tmp_path: Path):
        script = tmp_path / "myscript.py"
        script.write_text("")
        p = Process.python(script)
        assert "myscript" in p.name

    def test_custom_name(self, tmp_path: Path):
        script = tmp_path / "x.py"
        script.write_text("")
        p = Process.python(script, name="custom")
        assert p.name == "custom"

    def test_uses_active_interpreter(self, tmp_path: Path):
        script = tmp_path / "print_exec.py"
        script.write_text("import sys; print(sys.executable)")
        p = Process.python(script)
        assert p.succeeded
        assert p.args[0] == sys.executable
        assert (p.stdout or "").strip() == sys.executable


class TestProcessMvnShortcut:
    def test_missing_pom_raises(self, tmp_path: Path):
        with pytest.raises(AppException, match="POM file not found"):
            Process.mvn(tmp_path / "pom.xml", "clean")

    def test_default_name_without_args(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        pom = tmp_path / "pom.xml"
        pom.write_text("<project />")
        monkeypatch.setattr(subprocess_module, "_require_executable", lambda _: "mvn")
        monkeypatch.setattr(
            Process,
            "execute",
            classmethod(lambda cls, name, *args, **kwargs: {"name": name}),
        )
        result = Process.mvn(pom)
        assert result["name"] == f"mvn[{tmp_path.stem}][]"


class TestProcessNpmShortcut:
    def test_missing_package_json_raises(self, tmp_path: Path):
        with pytest.raises(AppException, match="package.json not found"):
            Process.npm(tmp_path)

    def test_default_name_without_args(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (tmp_path / "package.json").write_text("{}")
        monkeypatch.setattr(subprocess_module, "_require_executable", lambda _: "npm")
        monkeypatch.setattr(
            Process,
            "execute",
            classmethod(lambda cls, name, *args, **kwargs: {"name": name}),
        )
        result = Process.npm(tmp_path)
        assert result["name"] == f"npm[{tmp_path.stem}]"


class TestProcessAzShortcut:
    def test_empty_cmd_raises(self):
        with pytest.raises(AppException, match="cmd is required"):
            Process.az("")

    def test_default_name(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(subprocess_module, "_require_executable", lambda _: "az")
        monkeypatch.setattr(
            Process,
            "execute",
            classmethod(lambda cls, name, *args, **kwargs: {"name": name}),
        )
        result = Process.az("group list")
        assert result["name"] == "az[group list]"


class TestProcessPwshShortcut:
    def test_empty_cmd_raises(self):
        with pytest.raises(AppException, match="cmd_or_script is required"):
            Process.pwsh("")

    def test_file_mode_missing_script_raises(self, tmp_path: Path):
        with pytest.raises(AppException, match="not found"):
            Process.pwsh(tmp_path / "missing.ps1", mode="file")

    @pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
    def test_command_mode(self):
        p = Process.pwsh("Write-Output hello")
        assert p.succeeded

    def test_file_mode_executes_with_platform_python(self, tmp_path: Path, monkeypatch):
        script = tmp_path / "script.ps1"
        script.write_text("Write-Output 'hi'")

        captured: dict[str, list[str]] = {}

        def fake_require(_: str) -> str:
            return sys.executable

        def fake_run(args, capture_output=True, **kwargs):
            captured["args"] = list(args)

            class Result:
                returncode = 0
                stdout = b""
                stderr = b""

            return Result()

        monkeypatch.setattr(subprocess_module, "_require_executable", fake_require)
        monkeypatch.setattr(subprocess_module.subprocess, "run", fake_run)

        result = Process.pwsh(script, mode="file")

        assert result.succeeded
        assert captured["args"][0] == sys.executable
        assert captured["args"][1] == "-File"
        assert captured["args"][2] == script.as_posix()


# Coverage ROI notes:
# - Some subprocess branches are platform/tooling dependent (`mvn`, `npm`,
#   `az`, `pwsh`) and are covered through dispatch validation rather than
#   requiring those tools to be installed in CI.
