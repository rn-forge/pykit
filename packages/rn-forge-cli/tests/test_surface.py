"""Tests for rn_forge.cli.surface and CliApp's declared-surface constructors."""

from __future__ import annotations

import sys

import pytest
import typer
from rn_forge.cli import CliApp, CliSurface, CommandSurface, ExitCode, LogLevel, run
from rn_forge.commons.exceptions import AppException
from typer.testing import CliRunner

# Command implementations the declared surfaces below point at. They are
# ordinary functions and an ordinary Typer app: nothing here knows it is being
# declared rather than registered by hand.


def greet(name: str) -> None:
    """Greet someone."""
    print(f"hello {name}")


nested = typer.Typer()


@nested.command()
def inner() -> None:
    """A command in a namespace."""
    print("inner ran")


def bracketed() -> None:
    """Set the current repository's `[kiln] ref`, and [bold]bold[/bold] [project] name."""


def sectioned() -> None:
    """Sync the thing.

    Longer description here.

    Args:
        name: A name.

    Raises:
        AppException: `--archetype` is missing.
    """


sys.modules.setdefault("rn_forge_cli_test_commands", sys.modules[__name__])
HERE = "rn_forge_cli_test_commands"

CONFIG = f"""\
[cli]
name = "demo"
help = "A declared demo."

[[cli.commands]]
name = "greet"
target = "{HERE}:greet"

[[cli.commands]]
name = "sub"
help = "A namespace."
target = "{HERE}:nested"
"""


class TestCliSurfaceLoad:
    def test_reads_the_cli_table_from_a_document(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text(CONFIG)
        surface = CliSurface.load(path)
        assert surface.name == "demo"
        assert surface.help == "A declared demo."
        assert [c.name for c in surface.commands] == ["greet", "sub"]
        assert surface.commands[0].target == f"{HERE}:greet"

    def test_accepts_the_surface_table_directly(self):
        assert CliSurface.load({"name": "demo"}).name == "demo"

    def test_ignores_the_rest_of_the_document(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("[other]\nkey = 1\n\n" + CONFIG)
        assert CliSurface.load(path).name == "demo"

    def test_a_document_with_no_cli_table_is_rejected(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("[other]\nkey = 1\n")
        with pytest.raises(AppException):
            CliSurface.load(path)

    def test_an_unknown_top_level_key_is_refused(self):
        with pytest.raises(AppException, match="comands"):
            CliSurface.load({"name": "demo", "comands": []})

    def test_an_unknown_command_key_is_refused(self):
        data = {
            "name": "demo",
            "commands": [{"name": "a", "target": "m:f", "hlep": "x"}],
        }
        with pytest.raises(AppException, match=r"commands\.0\.hlep"):
            CliSurface.load(data)

    def test_an_unknown_key_in_a_file_is_refused(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('[cli]\nname = "demo"\ncolour = "red"\n')
        with pytest.raises(AppException, match="colour"):
            CliSurface.load(path)

    def test_a_minimal_surface_declares_no_commands(self):
        surface = CliSurface.load({"name": "demo"})
        assert surface.commands == ()
        assert surface.default_log_level is LogLevel.VERBOSE


class TestSurfaceValidation:
    def test_an_unnamed_cli_is_rejected(self):
        with pytest.raises(AppException):
            CliSurface(name="  ")

    def test_duplicate_command_names_are_rejected(self):
        commands = (
            CommandSurface(name="a", target=f"{HERE}:greet"),
            CommandSurface(name="a", target=f"{HERE}:greet"),
        )
        with pytest.raises(AppException):
            CliSurface(name="demo", commands=commands)


class TestSurfaceIsStrictlyTyped:
    """A [cli] table is written by hand, so a wrong type names the key rather
    than failing later as an attribute error (strict `from_dict`)."""

    def test_a_wrong_scalar_type_is_rejected_by_name(self):
        with pytest.raises(AppException, match="help"):
            CliSurface.load({"name": "demo", "help": 3})

    def test_a_wrong_type_inside_a_command_names_the_nested_field(self):
        with pytest.raises(AppException, match="commands.target"):
            CliSurface.load({"name": "demo", "commands": [{"name": "a", "target": 1}]})

    def test_an_undefined_enum_member_is_rejected(self):
        with pytest.raises(AppException, match="shouty"):
            CliSurface.load({"name": "demo", "default_log_level": "shouty"})


class TestSurfaceShapeErrors:
    def test_commands_string_is_rejected(self):
        with pytest.raises(
            AppException, match="commands must be an array of tables, not str"
        ):
            CliSurface.load({"name": "demo", "commands": "x"})

    def test_commands_entry_names_its_index(self):
        with pytest.raises(
            AppException, match=r"commands\[0\] must be a table, not int"
        ):
            CliSurface.load({"name": "demo", "commands": [1]})

    def test_commands_table_is_rejected(self):
        with pytest.raises(
            AppException, match="commands must be an array of tables, not dict"
        ):
            CliSurface.load(
                {"name": "demo", "commands": {"name": "a", "target": "m:f"}}
            )

    def test_missing_target_names_the_nested_field(self):
        with pytest.raises(AppException, match=r"commands\.target"):
            CliSurface.load({"name": "demo", "commands": [{"name": "a"}]})

    def test_target_list_names_the_nested_field(self):
        with pytest.raises(AppException, match=r"commands\.target"):
            CliSurface.load(
                {"name": "demo", "commands": [{"name": "a", "target": ["x"]}]}
            )


class TestFromSurface:
    def test_a_function_target_becomes_a_command(self, capsys):
        app = CliApp.from_surface(CliSurface.load({"name": "demo", **_commands()}))
        assert run(app, ["greet", "world"]) == ExitCode.OK
        assert "hello world" in capsys.readouterr().out

    def test_a_typer_target_becomes_a_namespace(self, capsys):
        app = CliApp.from_surface(CliSurface.load({"name": "demo", **_commands()}))
        assert run(app, ["sub", "inner"]) == ExitCode.OK
        assert "inner ran" in capsys.readouterr().out

    def test_the_standard_options_are_wired(self, capsys):
        app = CliApp.from_surface(CliSurface.load({"name": "demo", **_commands()}))
        assert run(app, ["--help"]) == ExitCode.OK
        help_text = capsys.readouterr().out
        assert "--log-level" in help_text
        assert "--json" in help_text

    def test_an_unimportable_target_is_reported_with_its_command(self):
        surface = CliSurface(
            name="demo",
            commands=(CommandSurface(name="broken", target="no.such.module:thing"),),
        )
        with pytest.raises(AppException, match="broken"):
            CliApp.from_surface(surface)

    def test_a_target_that_is_neither_app_nor_callable_is_rejected(self):
        surface = CliSurface(
            name="demo",
            commands=(CommandSurface(name="x", target=f"{HERE}:CONFIG"),),
        )
        with pytest.raises(AppException):
            CliApp.from_surface(surface)


class TestFromConfig:
    def test_loads_and_builds_in_one_call(self, tmp_path, capsys):
        path = tmp_path / "config.toml"
        path.write_text(CONFIG)
        assert CliApp.from_config(path).run(["greet", "world"]) == ExitCode.OK
        assert "hello world" in capsys.readouterr().out


class TestHelpText:
    @staticmethod
    def _help(tmp_path, monkeypatch, *args, entry_help="", target="bracketed"):
        monkeypatch.setenv("COLUMNS", "200")
        path = tmp_path / "config.toml"
        path.write_text(
            f'[cli]\nname = "demo"\n\n[[cli.commands]]\nname = "set"\n'
            f'{entry_help}target = "{HERE}:{target}"\n'
        )
        result = CliRunner().invoke(CliApp.from_config(path), [*args, "--help"])
        return result.output

    def test_brackets_show_in_the_command_help(self, tmp_path, monkeypatch):
        out = self._help(tmp_path, monkeypatch, "set")
        assert "`[kiln] ref`" in out
        assert "[project] name" in out

    def test_brackets_show_in_the_command_list(self, tmp_path, monkeypatch):
        assert "[kiln] ref" in self._help(tmp_path, monkeypatch)

    def test_rich_style_tags_still_style(self, tmp_path, monkeypatch):
        out = self._help(tmp_path, monkeypatch, "set")
        assert "bold" in out
        assert "[bold]" not in out

    def test_an_explicit_help_keeps_its_brackets(self, tmp_path, monkeypatch):
        out = self._help(
            tmp_path, monkeypatch, "set", entry_help='help = "Reads [project] name."\n'
        )
        assert "Reads [project] name." in out

    def test_help_ends_before_the_first_section(self, tmp_path, monkeypatch):
        out = self._help(tmp_path, monkeypatch, "set", target="sectioned")
        assert "Sync the thing." in out
        assert "Longer description here." in out
        assert "Args:" not in out
        assert "name: A name." not in out
        assert "Raises:" not in out

    def test_a_raises_section_shows_no_exception_name(self, tmp_path, monkeypatch):
        out = self._help(tmp_path, monkeypatch, "set", target="sectioned")
        assert "Raises:" not in out
        assert "AppException" not in out
        assert "--archetype" not in out

    def test_an_explicit_help_is_not_cut(self, tmp_path, monkeypatch):
        out = self._help(
            tmp_path,
            monkeypatch,
            "set",
            entry_help='help = "Kept.\\n\\nArgs:\\n    x: y."\n',
            target="sectioned",
        )
        assert "Args:" in out


def _commands():
    return {
        "commands": [
            {"name": "greet", "target": f"{HERE}:greet"},
            {"name": "sub", "target": f"{HERE}:nested"},
        ]
    }
