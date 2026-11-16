"""The hand-registered and declared command paths share CLI behavior."""

from __future__ import annotations

import sys

import pytest
import typer
from rn_forge.cli import CliApp, CliOptions, CliSurface
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.runtime.console import console


def ok() -> None:
    pass


def fail() -> None:
    raise AppException("a diagnosed failure")


def crash() -> None:
    raise RuntimeError("a defect")


def stop() -> None:
    raise KeyboardInterrupt


def bail() -> None:
    raise typer.Exit(3)


def leave() -> None:
    raise SystemExit(4)


def strict(ctx: typer.Context) -> None:
    CliOptions.from_context(ctx, json_output=True).apply(ctx)


def show(ctx: typer.Context) -> None:
    options = CliOptions.from_context(ctx)
    print(f"quiet={options.quiet} json_output={options.json_output}")


sys.modules.setdefault("rn_forge_cli_test_command_paths", sys.modules[__name__])
_TARGET = "rn_forge_cli_test_command_paths"
_COMMANDS = (ok, fail, crash, stop, bail, leave, strict, show)


@pytest.fixture(params=["hand", "generated"], ids=["hand", "generated"])
def app(request):
    if request.param == "hand":
        application = CliApp("paths")
        for command in _COMMANDS:
            application.command()(command)
        return application
    return CliApp.from_surface(
        CliSurface.load(
            {
                "name": "paths",
                "commands": [
                    {
                        "name": command.__name__,
                        "target": f"{_TARGET}:{command.__name__}",
                    }
                    for command in _COMMANDS
                ],
            }
        )
    )


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["ok"], 0),
        (["fail"], 1),
        (["crash"], 1),
        (["stop"], 130),
        (["bail"], 3),
        (["leave"], 4),
        (["nope"], 2),
        ([], 2),
        (["--help"], 0),
        (["ok", "--help"], 0),
        (["--log-level", "bogus", "ok"], 2),
        (["ok", "--json"], 2),
    ],
)
def test_exit_codes(app, args, expected):
    assert app.run(args) == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--json", "show"], "quiet=False json_output=True"),
        (["--quiet", "show"], "quiet=True json_output=False"),
    ],
)
def test_inherited_options_reach_commands(app, args, expected, capsys):
    prior = console.mode
    assert app.run(args) == 0
    assert console.mode == prior
    assert expected in capsys.readouterr().out


@pytest.mark.parametrize("args", [["--quiet", "--json", "ok"], ["--quiet", "strict"]])
def test_inherited_option_conflicts_exit_usage_without_leaking_mode(app, args):
    prior = console.mode
    assert app.run(args) == 2
    assert console.mode == prior


def test_failure_output(app, capsys):
    assert app.run(["fail"]) == 1
    failure = capsys.readouterr()
    assert "a diagnosed failure" in failure.err
    assert "Traceback" not in failure.out + failure.err

    assert app.run(["crash"]) == 1
    failure = capsys.readouterr()
    assert "Unexpected error: a defect" in failure.err


def test_help_lists_standard_options_and_commands(app, capsys):
    assert app.run(["--help"]) == 0
    help_text = capsys.readouterr().out
    for option in ("--log-level", "--log-file", "--quiet", "--json"):
        assert option in help_text
    for command in ("ok", "fail", "crash", "stop", "bail", "leave", "strict", "show"):
        assert command in help_text
