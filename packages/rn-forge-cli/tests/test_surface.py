"""Tests for rn_forge.cli.surface and CliApp's declared-surface constructors."""

from __future__ import annotations

import sys

import pytest
import typer

from rn_forge.cli import CliApp, CliSurface, CommandSurface, ExitCode, LogLevel, run
from rn_forge.cli.surface import LIFECYCLE_VERBS
from rn_forge.commons.exceptions import AppException

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

    def test_a_minimal_surface_declares_no_commands(self):
        surface = CliSurface.load({"name": "demo"})
        assert surface.commands == ()
        assert surface.default_log_level is LogLevel.VERBOSE


class TestSurfaceValidation:
    def test_an_unnamed_cli_is_rejected(self):
        with pytest.raises(AppException):
            CliSurface(name="  ")

    def test_duplicate_command_names_are_rejected(self):
        with pytest.raises(AppException):
            CliSurface(
                name="demo",
                commands=(
                    CommandSurface(name="a", target=f"{HERE}:greet"),
                    CommandSurface(name="a", target=f"{HERE}:greet"),
                ),
            )


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
        with pytest.raises(AppException, match="broken"):
            CliApp.from_surface(
                CliSurface(
                    name="demo",
                    commands=(
                        CommandSurface(name="broken", target="no.such.module:thing"),
                    ),
                )
            )

    def test_a_target_that_is_neither_app_nor_callable_is_rejected(self):
        with pytest.raises(AppException):
            CliApp.from_surface(
                CliSurface(
                    name="demo",
                    commands=(CommandSurface(name="x", target=f"{HERE}:CONFIG"),),
                )
            )


PRODUCT = object()


def lifecycle_factory(product, verbs):
    """A stand-in for tooling's factory: one command per verb."""
    commands = typer.Typer()
    for verb in verbs:

        def verb_command(verb=verb) -> None:
            print(f"{verb} ran for {product is PRODUCT}")

        commands.command(name=verb)(verb_command)
    return commands


def not_a_typer(product, verbs):
    return "nope"


class TestLifecycle:
    def _surface(self, **lifecycle):
        return CliSurface.load(
            {
                "name": "demo",
                "lifecycle": {
                    "product": f"{HERE}:PRODUCT",
                    "target": f"{HERE}:lifecycle_factory",
                    **lifecycle,
                },
            }
        )

    def test_verbs_default_to_all_six(self):
        surface = self._surface()
        assert surface.lifecycle is not None
        assert surface.lifecycle.verbs == LIFECYCLE_VERBS

    def test_verbs_are_mounted_at_the_root_against_the_product(self, capsys):
        app = CliApp.from_surface(self._surface(verbs=["status", "doctor"]))
        assert run(app, ["doctor"]) == ExitCode.OK
        assert "doctor ran for True" in capsys.readouterr().out
        assert run(app, ["install"]) == ExitCode.USAGE

    def test_an_unknown_verb_is_rejected(self):
        with pytest.raises(AppException, match="Unknown lifecycle verb"):
            self._surface(verbs=["explode"])

    def test_a_verb_colliding_with_a_command_is_rejected(self):
        with pytest.raises(AppException, match="Duplicate"):
            CliSurface.load(
                {
                    "name": "demo",
                    "commands": [{"name": "status", "target": f"{HERE}:greet"}],
                    "lifecycle": {"product": "x:y", "target": "x:z"},
                }
            )

    def test_an_unimportable_product_is_reported(self):
        with pytest.raises(AppException, match="lifecycle product"):
            CliApp.from_surface(self._surface(product="no.such.module:PRODUCT"))

    def test_a_factory_not_returning_typer_is_rejected(self):
        with pytest.raises(AppException, match="not a Typer app"):
            CliApp.from_surface(self._surface(target=f"{HERE}:not_a_typer"))


class TestFromConfig:
    def test_loads_and_builds_in_one_call(self, tmp_path, capsys):
        path = tmp_path / "config.toml"
        path.write_text(CONFIG)
        assert CliApp.from_config(path).run(["greet", "world"]) == ExitCode.OK
        assert "hello world" in capsys.readouterr().out


def _commands():
    return {
        "commands": [
            {"name": "greet", "target": f"{HERE}:greet"},
            {"name": "sub", "target": f"{HERE}:nested"},
        ]
    }
