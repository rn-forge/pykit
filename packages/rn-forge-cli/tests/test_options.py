"""Tests for rn_forge.cli."""

from __future__ import annotations

import json
import logging

import pytest
import typer
from typer.testing import CliRunner

from rn_forge.cli.console import console
from rn_forge.cli.errors import run
from rn_forge.commons.logging import AppLogger

from rn_forge.cli import (
    CliOptions,
    DryRunOption,
    JsonOption,
    LogLevel,
    build_app,
    command_options,
    options,
    parse_key_values,
    parse_overrides,
    YesOption,
)
from rn_forge.cli.console import OutputMode, console
from rn_forge.commons.logging import AppLogger

runner = CliRunner()


@pytest.fixture(autouse=True)
def reset_logger_state():
    AppLogger._configured = False
    console.set_mode(OutputMode.RICH)
    yield
    AppLogger._configured = False
    logging.getLogger().handlers.clear()
    console.set_mode(OutputMode.RICH)


# -- LogLevel ----------------------------------------------------------------


class TestLogLevel:
    @pytest.mark.parametrize("level", list(LogLevel))
    def test_to_int_maps_every_member(self, level: LogLevel) -> None:
        expected = {
            LogLevel.CRITICAL: AppLogger.CRITICAL,
            LogLevel.ERROR: AppLogger.ERROR,
            LogLevel.SUCCESS: AppLogger.SUCCESS,
            LogLevel.WARNING: AppLogger.WARNING,
            LogLevel.NOTICE: AppLogger.NOTICE,
            LogLevel.INFO: AppLogger.INFO,
            LogLevel.VERBOSE: AppLogger.VERBOSE,
            LogLevel.DEBUG: AppLogger.DEBUG,
            LogLevel.SPAM: AppLogger.SPAM,
            LogLevel.TRACE: AppLogger.TRACE,
        }[level]
        assert level.to_int() == expected


# -- build_app -----------------------------------------------------------


class TestBuildApp:
    def test_help_lists_log_and_output_options(self) -> None:
        app = build_app("testapp")

        @app.command()
        def hello() -> None:
            print("hi")

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--log-level" in result.output
        assert "--log-file" in result.output
        assert "--quiet" in result.output
        assert "--json" in result.output

    def test_add_log_options_false_omits_them(self) -> None:
        app = build_app("testapp", add_log_options=False)

        @app.command()
        def hello() -> None:
            print("hi")

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--log-level" not in result.output
        assert "--log-file" not in result.output

    def test_add_output_options_false_omits_them(self) -> None:
        app = build_app("testapp", add_output_options=False)

        @app.command()
        def hello() -> None:
            print("hi")

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--quiet" not in result.output
        assert "--json" not in result.output

    def test_quiet_and_json_together_is_a_usage_error(self) -> None:
        app = build_app("testapp")

        @app.command()
        def hello() -> None:
            print("hi")

        result = runner.invoke(app, ["--quiet", "--json", "hello"])
        assert result.exit_code != 0

    def test_log_level_sets_root_logger_level(self) -> None:
        app = build_app("testapp")

        @app.command()
        def hello() -> None:
            print("hi")

        result = runner.invoke(app, ["--log-level", "debug", "hello"])
        assert result.exit_code == 0
        assert logging.getLogger().level == logging.DEBUG

    def test_options_seen_before_subcommand_name(self) -> None:
        app = build_app("testapp")
        seen: dict[str, CliOptions] = {}

        @app.command()
        def hello(ctx: typer.Context) -> None:
            seen["opts"] = options(ctx)

        result = runner.invoke(app, ["--quiet", "hello"])
        assert result.exit_code == 0
        assert seen["opts"] == CliOptions(quiet=True, json_output=False)

    def test_json_mode_keeps_log_output_off_stdout(self) -> None:
        app = build_app("testapp")

        @app.command()
        def emit(ctx: typer.Context) -> None:
            console.json({"ok": True})

        result = runner.invoke(app, ["--json", "emit"])
        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"ok": True}

    def test_explicit_log_level_is_honoured_even_with_json(self) -> None:
        app = build_app("testapp")

        @app.command()
        def emit(ctx: typer.Context) -> None:
            pass

        result = runner.invoke(app, ["--json", "--log-level", "debug", "emit"])
        assert result.exit_code == 0
        assert logging.getLogger().level == logging.DEBUG

    def test_dry_run_and_yes_are_command_level_and_merge(self) -> None:
        app = build_app("testapp")
        seen: dict[str, CliOptions] = {}

        @app.command()
        def apply_(
            ctx: typer.Context,
            dry_run: DryRunOption = False,
            yes: YesOption = False,
        ) -> None:
            seen["opts"] = command_options(ctx, dry_run=dry_run, yes=yes)

        result = runner.invoke(app, ["apply-", "--dry-run", "-y"])
        assert result.exit_code == 0
        assert seen["opts"] == CliOptions(dry_run=True, yes=True)

    def test_dry_run_defaults_to_false(self) -> None:
        app = build_app("testapp")
        seen: dict[str, CliOptions] = {}

        @app.command()
        def apply_(ctx: typer.Context, dry_run: DryRunOption = False) -> None:
            seen["opts"] = command_options(ctx, dry_run=dry_run)

        result = runner.invoke(app, ["apply-"])
        assert result.exit_code == 0
        assert seen["opts"] == CliOptions()

    def test_options_seen_after_subcommand_name_via_command_options(self) -> None:
        app = build_app("testapp")
        seen: dict[str, CliOptions] = {}

        @app.command()
        def hello(
            ctx: typer.Context,
            quiet: bool = typer.Option(False, "--quiet"),
        ) -> None:
            seen["opts"] = command_options(ctx, quiet=quiet)

        result = runner.invoke(app, ["hello", "--quiet"])
        assert result.exit_code == 0
        assert seen["opts"] == CliOptions(quiet=True, json_output=False)


# -- parse_key_values ------------------------------------------------------


class TestParseKeyValues:
    def test_happy_path(self) -> None:
        assert parse_key_values(["a=1", "b=2"]) == {"a": "1", "b": "2"}

    def test_empty_input(self) -> None:
        assert parse_key_values(None) == {}
        assert parse_key_values([]) == {}

    def test_missing_equals_raises(self) -> None:
        with pytest.raises(typer.BadParameter):
            parse_key_values(["no_equals"])


# -- parse_overrides ---------------------------------------------------------


class TestParseOverrides:
    def test_dotted_path_nesting(self) -> None:
        assert parse_overrides(["a.b=1"]) == {"a": {"b": 1}}

    def test_json_scalar(self) -> None:
        assert parse_overrides(["a=[1,2]"]) == {"a": [1, 2]}
        assert parse_overrides(["a=true"]) == {"a": True}

    def test_toml_fallback_scalar(self) -> None:
        assert parse_overrides(["a=2026-01-01"]) is not None

    def test_raw_string_fallback(self) -> None:
        assert parse_overrides(["a=not valid json or toml scalar!!"]) == {
            "a": "not valid json or toml scalar!!"
        }

    def test_missing_equals_raises(self) -> None:
        with pytest.raises(typer.BadParameter):
            parse_overrides(["no_equals"])

    def test_empty_key_raises(self) -> None:
        with pytest.raises(typer.BadParameter):
            parse_overrides(["=value"])

    def test_collision_with_scalar_raises(self) -> None:
        with pytest.raises(typer.BadParameter):
            parse_overrides(["a=1", "a.b=2"])

    def test_empty_input(self) -> None:
        assert parse_overrides(None) == {}


class TestJsonStaysParseable:
    """F10: diagnostics go to stderr, so `--json` stdout is a payload."""

    @pytest.fixture
    def app(self):
        application = build_app("json-demo", "Demo.")
        logger = AppLogger.get_logger("json_demo.command")

        @application.command()
        def report(ctx: typer.Context, json_output: JsonOption = False) -> None:
            command_options(ctx, json_output=json_output)
            logger.info("a diagnostic that must not land on stdout")
            console.emit({"status": "ok"})

        return application

    @pytest.mark.parametrize(
        "args",
        [
            ["--json", "report"],
            ["report", "--json"],
        ],
        ids=["flag-at-the-root", "flag-on-the-command"],
    )
    def test_stdout_is_parseable_wherever_the_flag_sits(self, app, args, capsys):
        assert run(app, args) == 0
        assert json.loads(capsys.readouterr().out) == {"status": "ok"}
