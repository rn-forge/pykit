"""Tests for rn_forge.commons.console."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pytest

from rn_forge.commons.console import (
    CLIArgumentParser,
    BooleanAction,
    KeyValueAction,
    _LOG_LEVELS,
)


@pytest.fixture(autouse=True)
def reset_logger_state():
    from rn_forge.commons.logging import AppLogger

    AppLogger._configured = False
    yield
    AppLogger._configured = False
    logging.getLogger().handlers.clear()


# -- BooleanAction ---------------------------------------------------------


class TestBooleanAction:
    def _parser(self) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser()
        p.add_argument("--flag", action=BooleanAction, default=False)
        return p

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "yes", "Yes", "1"])
    def test_truthy_values(self, value: str) -> None:
        args = self._parser().parse_args(["--flag", value])
        assert args.flag is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "no", "No", "0"])
    def test_falsy_values(self, value: str) -> None:
        args = self._parser().parse_args(["--flag", value])
        assert args.flag is False

    def test_bare_flag_is_true(self) -> None:
        args = self._parser().parse_args(["--flag"])
        assert args.flag is True

    def test_omitted_flag_uses_default(self) -> None:
        args = self._parser().parse_args([])
        assert args.flag is False

    def test_invalid_value_raises(self) -> None:
        parser = self._parser()
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid boolean value"):
            parser.parse_args(["--flag", "maybe"])


# -- KeyValueAction --------------------------------------------------------


class TestKeyValueAction:
    def test_single_pair(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction)
        args = p.parse_args(["--config", "key=value"])
        assert args.config == {"key": "value"}

    def test_multiple_pairs_nargs_star(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction, nargs="*")
        args = p.parse_args(["--config", "a=1", "b=2"])
        assert args.config == {"a": "1", "b": "2"}

    def test_repeated_flag_accumulates(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction)
        args = p.parse_args(["--config", "a=1", "--config", "b=2"])
        assert args.config == {"a": "1", "b": "2"}

    def test_value_with_equals(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction)
        args = p.parse_args(["--config", "url=https://host?a=1"])
        assert args.config == {"url": "https://host?a=1"}

    def test_empty_value(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction)
        args = p.parse_args(["--config", "key="])
        assert args.config == {"key": ""}

    def test_missing_equals_raises(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction)
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid key=value"):
            p.parse_args(["--config", "no_equals"])

    def test_default_empty_dict(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction)
        args = p.parse_args([])
        assert args.config == {}

    def test_overwrite_same_key(self) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--config", action=KeyValueAction)
        args = p.parse_args(["--config", "a=1", "--config", "a=2"])
        assert args.config == {"a": "2"}


# -- CLIArgumentParser: log arguments --------------------------------


class TestLogArguments:
    def test_default_log_level(self) -> None:
        parser = CLIArgumentParser(prog="test")
        args = parser.parse_args([])
        assert args.log_level == "VERBOSE"

    def test_custom_default_log_level(self) -> None:
        parser = CLIArgumentParser(prog="test", default_log_level="DEBUG")
        args = parser.parse_args([])
        assert args.log_level == "DEBUG"

    def test_log_level_short_flag(self) -> None:
        parser = CLIArgumentParser(prog="test")
        args = parser.parse_args(["-ll", "info"])
        assert args.log_level == "INFO"

    def test_log_level_long_flag(self) -> None:
        parser = CLIArgumentParser(prog="test")
        args = parser.parse_args(["--log-level", "debug"])
        assert args.log_level == "DEBUG"

    def test_single_letter_shortcut(self) -> None:
        parser = CLIArgumentParser(prog="test")
        args = parser.parse_args(["-ll", "d"])
        assert args.log_level == "D"

    def test_log_file_default_none(self) -> None:
        parser = CLIArgumentParser(prog="test")
        args = parser.parse_args([])
        assert args.log_file is None

    def test_log_file_flag(self, tmp_path: Path) -> None:
        log_file = str(tmp_path / "test.log")
        parser = CLIArgumentParser(prog="test")
        args = parser.parse_args(["--log-file", log_file])
        assert args.log_file == log_file

    def test_no_log_args(self) -> None:
        parser = CLIArgumentParser(prog="test", add_log_args=False)
        args = parser.parse_args([])
        assert not hasattr(args, "log_level")

    def test_invalid_level_rejected(self) -> None:
        parser = CLIArgumentParser(prog="test")
        with pytest.raises(SystemExit):
            parser.parse_args(["--log-level", "INVALID"])


# -- CLIArgumentParser: add_boolean_argument -------------------------


class TestAddBooleanArgument:
    def test_chaining(self) -> None:
        parser = CLIArgumentParser(prog="test")
        result = parser.add_boolean_argument("--dry-run")
        assert result is parser

    def test_boolean_arg_works(self) -> None:
        parser = CLIArgumentParser(prog="test")
        parser.add_boolean_argument("--dry-run")
        args = parser.parse_args(["--dry-run", "true"])
        assert args.dry_run is True

    def test_boolean_arg_default(self) -> None:
        parser = CLIArgumentParser(prog="test")
        parser.add_boolean_argument("--dry-run")
        args = parser.parse_args([])
        assert args.dry_run is False


# -- CLIArgumentParser: add_key_value_argument -----------------------


class TestAddKeyValueArgument:
    def test_chaining(self) -> None:
        parser = CLIArgumentParser(prog="test")
        result = parser.add_key_value_argument("--env")
        assert result is parser

    def test_multi_mode_default(self) -> None:
        parser = CLIArgumentParser(prog="test")
        parser.add_key_value_argument("--env")
        args = parser.parse_args(["--env", "A=1", "B=2"])
        assert args.env == {"A": "1", "B": "2"}

    def test_single_mode(self) -> None:
        parser = CLIArgumentParser(prog="test")
        parser.add_key_value_argument("--env", multi=False)
        args = parser.parse_args(["--env", "A=1", "--env", "B=2"])
        assert args.env == {"A": "1", "B": "2"}


# -- CLIArgumentParser: configure_logging ----------------------------


class TestConfigureLogging:
    def test_configure_logging_returns_logger(self) -> None:
        from rn_forge.commons.logging import AppLogger

        AppLogger._configured = False
        parser = CLIArgumentParser(prog="test-app")
        args = parser.parse_args(["-ll", "info"])
        logger = parser.configure_logging(args)
        assert isinstance(logger, AppLogger)
        AppLogger._configured = False

    def test_configure_logging_with_shortcut(self) -> None:
        from rn_forge.commons.logging import AppLogger

        AppLogger._configured = False
        parser = CLIArgumentParser(prog="test-app")
        args = parser.parse_args(["-ll", "d"])
        logger = parser.configure_logging(args)
        assert isinstance(logger, AppLogger)
        AppLogger._configured = False

    def test_configure_logging_custom_root_name(self) -> None:
        from rn_forge.commons.logging import AppLogger

        AppLogger._configured = False
        parser = CLIArgumentParser(prog="test-app")
        args = parser.parse_args([])
        logger = parser.configure_logging(args, root_logger_name="custom")
        assert logger.name == "custom"
        AppLogger._configured = False

    def test_prog_name_used_as_root_logger(self) -> None:
        from rn_forge.commons.logging import AppLogger

        AppLogger._configured = False
        parser = CLIArgumentParser(prog="My App")
        args = parser.parse_args([])
        logger = parser.configure_logging(args)
        assert logger.name == "my_app"
        AppLogger._configured = False


# -- _LOG_LEVELS constant ---------------------------------------------------


class TestLogLevels:
    def test_contains_standard_levels(self) -> None:
        for name in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
            assert name in _LOG_LEVELS

    def test_contains_custom_levels(self) -> None:
        for name in ("VERBOSE", "NOTICE", "SPAM", "TRACE", "SUCCESS"):
            assert name in _LOG_LEVELS

    def test_contains_single_letter_shortcuts(self) -> None:
        for letter in ("C", "E", "W", "I", "V", "D", "T"):
            assert letter in _LOG_LEVELS

    def test_shortcut_matches_full_name(self) -> None:
        assert _LOG_LEVELS["D"] == _LOG_LEVELS["DEBUG"]
        assert _LOG_LEVELS["I"] == _LOG_LEVELS["INFO"]
        assert _LOG_LEVELS["W"] == _LOG_LEVELS["WARNING"]
        assert _LOG_LEVELS["E"] == _LOG_LEVELS["ERROR"]
        assert _LOG_LEVELS["C"] == _LOG_LEVELS["CRITICAL"]
        assert _LOG_LEVELS["V"] == _LOG_LEVELS["VERBOSE"]
        assert _LOG_LEVELS["T"] == _LOG_LEVELS["TRACE"]

    def test_all_values_are_ints(self) -> None:
        for name, value in _LOG_LEVELS.items():
            assert isinstance(value, int), f"{name} is not an int"
