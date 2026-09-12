"""Tests for rn_forge.cli.app."""

from __future__ import annotations

import pytest
import typer
from typer._click.exceptions import UsageError

from rn_forge.cli import CliApp, ExitCode, run
from rn_forge.commons.exceptions import AppException


class TestExitCodeForError:
    def test_usage_error_is_two(self):
        assert ExitCode.for_error(UsageError("bad")) is ExitCode.USAGE

    def test_interrupt_is_one_hundred_and_thirty(self):
        assert ExitCode.for_error(KeyboardInterrupt()) is ExitCode.INTERRUPTED

    def test_application_failure_is_one(self):
        assert ExitCode.for_error(AppException("nope")) is ExitCode.FAILURE

    def test_an_explicit_exit_keeps_its_own_code(self):
        assert ExitCode.for_error(typer.Exit(0)) == 0
        assert ExitCode.for_error(typer.Exit(3)) == 3


@pytest.fixture
def app():
    application = CliApp("demo", "A demo.")

    @application.command()
    def ok() -> None:
        pass

    @application.command()
    def fail() -> None:
        raise AppException("could not do the thing")

    @application.command()
    def crash() -> None:
        raise RuntimeError("a defect")

    @application.command()
    def stop() -> None:
        raise KeyboardInterrupt

    @application.command()
    def bail() -> None:
        raise typer.Exit(3)

    return application


class TestRun:
    def test_success_is_zero(self, app):
        assert run(app, ["ok"]) == ExitCode.OK

    def test_application_failure_is_reported_as_one(self, app, capsys):
        assert run(app, ["fail"]) == ExitCode.FAILURE
        assert "could not do the thing" in capsys.readouterr().err

    def test_an_unexpected_error_is_still_an_exit_code_not_a_traceback(self, app):
        assert run(app, ["crash"]) == ExitCode.FAILURE

    def test_interrupt_is_not_converted_into_a_generic_failure(self, app):
        assert run(app, ["stop"]) == ExitCode.INTERRUPTED

    def test_an_unknown_command_is_a_usage_error(self, app):
        assert run(app, ["nope"]) == ExitCode.USAGE

    def test_an_explicit_exit_code_survives(self, app):
        assert run(app, ["bail"]) == 3


class TestCallReturnsAnExitCode:
    """`sys.exit(app())` is what a generated console script runs, so calling a
    CliApp must return a code rather than raising — that is what lets a repo's
    `[project.scripts]` be the plain `pkg.cli:app` and still get the mapping."""

    def test_calling_the_app_returns_the_code(self, app):
        assert app(["ok"]) == ExitCode.OK
        assert app(["fail"]) == ExitCode.FAILURE
        assert app(["bail"]) == 3

    def test_the_run_method_matches_the_free_function(self, app):
        assert app.run(["ok"]) == run(app, ["ok"])

    def test_the_free_function_still_takes_a_plain_typer_app(self):
        plain = typer.Typer()

        @plain.command()
        def boom() -> None:
            raise AppException("from a hand-built app")

        @plain.command()
        def fine() -> None:
            pass

        assert run(plain, ["boom"]) == ExitCode.FAILURE
        assert run(plain, ["fine"]) == ExitCode.OK
