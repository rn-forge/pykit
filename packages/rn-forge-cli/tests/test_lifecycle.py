"""Same-process console and logging lifecycle tests."""

from __future__ import annotations

import logging

import pytest
import typer
from rn_forge.cli import CliApp, CliOptions
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.runtime.console import OutputMode, console


@pytest.fixture
def app():
    prior = console.mode
    root = logging.getLogger()
    AppLogger._configured = False
    root.handlers.clear()
    application = CliApp("lifecycle")
    application.modes = []

    @application.command()
    def show() -> None:
        console.print("hello")

    @application.command()
    def boom() -> None:
        raise AppException("command failed")

    @application.command()
    def say(text: str) -> None:
        AppLogger.get_logger("lifecycle.cmd").warning(text)

    @application.command()
    def nested() -> None:
        application.modes.append(console.mode)
        assert application.run(["--quiet", "show"]) == 0
        application.modes.append(console.mode)

    @application.command()
    def strict(ctx: typer.Context) -> None:
        CliOptions.from_context(ctx, json_output=True).apply(ctx)

    yield application

    AppLogger._configured = False
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    console.set_mode(prior)


def test_json_then_plain_prints_plain_output(app, capsys):
    assert app.run(["--json", "show"]) == 0
    assert capsys.readouterr().out == ""
    assert app.run(["show"]) == 0
    assert "hello" in capsys.readouterr().out


def test_quiet_then_plain_prints_plain_output(app, capsys):
    assert app.run(["--quiet", "show"]) == 0
    assert capsys.readouterr().out == ""
    assert app.run(["show"]) == 0
    assert "hello" in capsys.readouterr().out


def test_failed_json_then_plain(app, capsys):
    assert app.run(["--json", "boom"]) == 1
    assert capsys.readouterr().out == ""
    assert app.run(["show"]) == 0
    assert "hello" in capsys.readouterr().out


@pytest.mark.parametrize(
    "args", [["--json", "show"], ["--quiet", "show"], ["--json", "boom"]]
)
def test_mode_after_run_equals_mode_before(app, args, capsys):
    prior = console.mode
    assert app.run(args) == (1 if args[-1] == "boom" else 0)
    assert console.mode == prior


def test_conflict_at_root_does_not_leak(app, capsys):
    prior = console.mode
    assert app.run(["--quiet", "--json", "show"]) == 2
    assert console.mode == prior


def test_conflict_at_command_level_does_not_leak(app, capsys):
    prior = console.mode
    assert app.run(["--quiet", "strict"]) == 2
    assert console.mode == prior
    capsys.readouterr()
    assert app.run(["show"]) == 0
    assert "hello" in capsys.readouterr().out


def test_nested_run_restores_outer_mode(app, capsys):
    prior = console.mode
    assert app.run(["--json", "nested"]) == 0
    assert app.modes == [OutputMode.JSON, OutputMode.JSON]
    assert console.mode == prior


def test_log_level_follows_each_invocation(app, capsys):
    assert app.run(["--log-level", "info", "show"]) == 0
    assert logging.getLogger().level == logging.INFO
    assert app.run(["--log-level", "debug", "show"]) == 0
    assert logging.getLogger().level == logging.DEBUG
    assert app.run(["show"]) == 0
    assert logging.getLogger().level == logging.DEBUG


def test_host_logging_survives_invocation_without_log_options(app, capsys):
    AppLogger.initialize(root_logger_name="host", level=AppLogger.WARNING)
    marker = logging.NullHandler()
    root = logging.getLogger()
    root.addHandler(marker)
    assert app.run(["show"]) == 0
    assert root.level == logging.WARNING
    assert marker in root.handlers


def test_log_file_follows_each_invocation(app, capsys, tmp_path):
    first = tmp_path / "a.log"
    second = tmp_path / "b.log"
    assert app.run(["--log-file", str(first), "say", "one"]) == 0
    assert app.run(["--log-file", str(second), "say", "two"]) == 0
    assert "one" in first.read_text()
    assert "two" not in first.read_text()
    assert "two" in second.read_text()
    assert all(
        not isinstance(handler, logging.FileHandler)
        or handler.baseFilename != str(first)
        for handler in logging.getLogger().handlers
    )
