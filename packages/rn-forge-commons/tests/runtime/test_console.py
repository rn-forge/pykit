"""Tests for rn_forge.commons.runtime.console."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from rich.console import Console

from rn_forge.commons.runtime.console import AppConsole, OutputMode


def _console(mode: OutputMode = OutputMode.RICH) -> tuple[AppConsole, StringIO]:
    """Build an AppConsole writing to an in-memory, colour-free buffer with a fixed width.

    Colour is always off here regardless of *mode* so tests can assert on
    literal substrings without ANSI codes splitting them; mode dispatch
    (RICH vs PLAIN) is otherwise unaffected by colour.
    """
    ac = AppConsole(mode=mode)
    buf = StringIO()
    ac._out = Console(
        file=buf, width=80, no_color=True, force_terminal=True, highlight=False
    )
    return ac, buf


# -- mode dispatch matrix ---------------------------------------------------


class TestPrint:
    def test_rich_mode_prints(self) -> None:
        ac, buf = _console(OutputMode.RICH)
        ac.print("hello {}", "world")
        assert "hello world" in buf.getvalue()

    def test_plain_mode_prints_unstyled(self) -> None:
        ac, buf = _console(OutputMode.PLAIN)
        ac.print("hello")
        assert "hello" in buf.getvalue()
        assert "\x1b[" not in buf.getvalue()

    def test_quiet_mode_suppresses(self) -> None:
        ac, buf = _console(OutputMode.QUIET)
        ac.print("hello")
        assert buf.getvalue() == ""

    def test_json_mode_suppresses(self) -> None:
        ac, buf = _console(OutputMode.JSON)
        ac.print("hello")
        assert buf.getvalue() == ""


class TestSemanticMethods:
    @pytest.mark.parametrize("method", ["success", "info", "detail"])
    def test_stdout_methods_no_op_in_quiet_and_json(self, method: str) -> None:
        for mode in (OutputMode.QUIET, OutputMode.JSON):
            ac, buf = _console(mode)
            getattr(ac, method)("msg")
            assert buf.getvalue() == ""

    @pytest.mark.parametrize("method", ["success", "info", "detail"])
    def test_stdout_methods_format_and_print(self, method: str) -> None:
        ac, buf = _console(OutputMode.RICH)
        getattr(ac, method)("value={}", 42)
        assert "value=42" in buf.getvalue()

    @pytest.mark.parametrize("method", ["warning", "error"])
    def test_stderr_methods_go_to_stderr(self, method: str) -> None:
        ac = AppConsole(mode=OutputMode.RICH)
        err_buf = StringIO()
        ac._err = Console(
            file=err_buf, width=80, no_color=True, force_terminal=True, highlight=False
        )
        getattr(ac, method)("oops {}", 1)
        assert "oops 1" in err_buf.getvalue()

    @pytest.mark.parametrize("method", ["warning", "error"])
    def test_stderr_methods_no_op_in_quiet_and_json(self, method: str) -> None:
        for mode in (OutputMode.QUIET, OutputMode.JSON):
            ac = AppConsole(mode=mode)
            err_buf = StringIO()
            ac._err = Console(file=err_buf, width=80)
            getattr(ac, method)("oops")
            assert err_buf.getvalue() == ""

    def test_fail_raises_system_exit_with_code_and_writes_stderr(self) -> None:
        ac = AppConsole(mode=OutputMode.RICH)
        err_buf = StringIO()
        ac._err = Console(
            file=err_buf, width=80, no_color=True, force_terminal=True, highlight=False
        )
        with pytest.raises(SystemExit) as exc_info:
            ac.fail("bad thing: {}", "oops", code=3)
        assert exc_info.value.code == 3
        assert "bad thing: oops" in err_buf.getvalue()


class TestEmit:
    def test_emit_json_mode_serializes(self) -> None:
        ac, buf = _console(OutputMode.JSON)
        ac.emit({"a": 1})
        assert json.loads(buf.getvalue()) == {"a": 1}

    def test_emit_quiet_with_quiet_text(self) -> None:
        ac, buf = _console(OutputMode.QUIET)
        ac.emit({"a": 1}, quiet_text="done")
        assert buf.getvalue().strip() == "done"

    def test_emit_quiet_without_quiet_text_emits_nothing(self) -> None:
        ac, buf = _console(OutputMode.QUIET)
        ac.emit({"a": 1})
        assert buf.getvalue() == ""

    def test_emit_rich_mode_prints_value(self) -> None:
        ac, buf = _console(OutputMode.RICH)
        ac.emit("a renderable string")
        assert "a renderable string" in buf.getvalue()


class TestJson:
    def test_json_always_emits_even_in_quiet(self) -> None:
        ac, buf = _console(OutputMode.QUIET)
        ac.json({"a": 1})
        assert json.loads(buf.getvalue()) == {"a": 1}

    def test_json_handles_path(self) -> None:
        from pathlib import Path

        ac, buf = _console(OutputMode.RICH)
        ac.json({"p": Path("/tmp/x")})
        assert json.loads(buf.getvalue()) == {"p": "/tmp/x"}

    def test_json_handles_enum(self) -> None:
        from enum import Enum

        class Color(Enum):
            RED = "red"

        ac, buf = _console(OutputMode.RICH)
        ac.json({"c": Color.RED})
        assert json.loads(buf.getvalue()) == {"c": "red"}

    def test_json_handles_datetime(self) -> None:
        from datetime import datetime

        ac, buf = _console(OutputMode.RICH)
        dt = datetime(2026, 1, 1, 12, 0, 0)
        ac.json({"dt": dt})
        assert json.loads(buf.getvalue()) == {"dt": dt.isoformat()}

    def test_json_handles_set(self) -> None:
        ac, buf = _console(OutputMode.RICH)
        ac.json({"s": {3, 1, 2}})
        assert json.loads(buf.getvalue()) == {"s": [1, 2, 3]}

    def test_json_handles_decimal(self) -> None:
        from decimal import Decimal

        ac, buf = _console(OutputMode.RICH)
        ac.json({"d": Decimal("1.5")})
        assert json.loads(buf.getvalue()) == {"d": 1.5}

    def test_json_handles_nested_dataclass(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class Inner:
            value: int

        @dataclass
        class Outer:
            inner: Inner

        ac, buf = _console(OutputMode.RICH)
        ac.json(Outer(Inner(5)))
        assert json.loads(buf.getvalue()) == {"inner": {"value": 5}}


class TestTable:
    def test_table_json_mode_emits_array_of_objects(self) -> None:
        ac, buf = _console(OutputMode.JSON)
        ac.table("name", "status", rows=[("alpha", "ok"), ("beta", "failed")])
        assert json.loads(buf.getvalue()) == [
            {"name": "alpha", "status": "ok"},
            {"name": "beta", "status": "failed"},
        ]

    def test_table_quiet_mode_no_op(self) -> None:
        ac, buf = _console(OutputMode.QUIET)
        ac.table("name", rows=[("alpha",)])
        assert buf.getvalue() == ""

    def test_table_rich_mode_renders(self) -> None:
        ac, buf = _console(OutputMode.RICH)
        ac.table("name", "status", rows=[("alpha", "ok")])
        out = buf.getvalue()
        assert "name" in out
        assert "alpha" in out

    def test_table_cell_markup_not_styled(self) -> None:
        ac, buf = _console(OutputMode.RICH)
        ac.table("name", rows=[("[red]not styled[/red]",)])
        assert "[red]not styled[/red]" in buf.getvalue()


class TestDiff:
    def test_diff_markup_not_interpreted(self) -> None:
        ac, buf = _console(OutputMode.RICH)
        ac.diff("[red]literal[/red]\n")
        assert "[red]literal[/red]" in buf.getvalue()

    def test_diff_no_op_in_quiet_and_json(self) -> None:
        for mode in (OutputMode.QUIET, OutputMode.JSON):
            ac, buf = _console(mode)
            ac.diff("some diff text")
            assert buf.getvalue() == ""


class TestModeAndEscapeHatch:
    def test_default_mode_from_terminal_detection(self) -> None:
        ac = AppConsole()
        assert ac.mode in (OutputMode.RICH, OutputMode.PLAIN)

    def test_set_mode_returns_self_for_chaining(self) -> None:
        ac = AppConsole()
        result = ac.set_mode(OutputMode.QUIET)
        assert result is ac
        assert ac.mode is OutputMode.QUIET

    def test_rich_property_is_escape_hatch(self) -> None:
        ac = AppConsole()
        assert isinstance(ac.rich, Console)


class TestJsonIsNotReflowed:
    def test_long_json_stays_parseable_in_a_narrow_terminal(self) -> None:
        ac, buf = _console(OutputMode.JSON)
        ac.emit({"path": "a" * 200})
        assert json.loads(buf.getvalue()) == {"path": "a" * 200}
