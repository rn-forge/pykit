"""Console output: a Rich-based, quiet/JSON-aware output facade.

Human-readable logs use stderr; :meth:`AppConsole.emit` writes command output
to stdout so machine-readable output remains separate.

Typical usage::

    from rn_forge.commons import console, OutputMode

    console.info("Starting {}", "job")
    console.table("name", "status", rows=[("alpha", "ok"), ("beta", "failed")])
    console.set_mode(OutputMode.JSON)
    console.emit({"status": "ok"})
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager, nullcontext
from enum import StrEnum
from typing import Any, Iterable, NoReturn, Self, Sequence, cast

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from rn_forge.commons.fs.documents import JsonUtils

__all__ = ["AppConsole", "OutputMode", "console"]


class OutputMode(StrEnum):
    """Output mode for :class:`AppConsole`."""

    RICH = "rich"
    """Default: styled output, tables, colour."""
    PLAIN = "plain"
    """No styling (explicit override; also what a non-TTY gets)."""
    QUIET = "quiet"
    """Suppress everything except explicit ``quiet_text``."""
    JSON = "json"
    """Machine-readable output only."""


def _format(msg: Any, args: tuple[Any, ...]) -> Any:
    """``{}``-format *msg* with *args* when both are present, matching the AppLogger idiom."""
    if args and isinstance(msg, str):
        return msg.format(*args)
    return msg


class AppConsole:
    """Facade over :class:`rich.console.Console` with quiet and JSON modes.

    Access :attr:`rich` for unsupported Rich features such as progress bars,
    live displays, and custom renderables.
    """

    def __init__(
        self,
        *,
        mode: OutputMode | None = None,
        stderr: bool = False,
        theme: Theme | None = None,
    ) -> None:
        """Initialize :class:`AppConsole`.

        Args:
            mode: Initial output mode. Defaults to :attr:`OutputMode.RICH`
                when stdout is a TTY, else :attr:`OutputMode.PLAIN`.
            stderr: When ``True``, the primary console (and therefore
                :attr:`rich`) writes to stderr instead of stdout.
            theme: A Rich theme applied to the underlying console(s).
        """
        self._theme = theme
        # highlight=False: this facade prints curated messages, not values for
        # interactive inspection — Rich's automatic ReprHighlighter would bold
        # numbers/strings/brackets in ordinary log-style text even with colour
        # disabled (bold is not a colour), which looks like a rendering bug.
        self._out = Console(stderr=stderr, theme=theme, highlight=False)
        self._err: Console | None = self._out if stderr else None
        self._mode = mode if mode is not None else self._default_mode()
        self._sync_no_color()

    def _default_mode(self) -> OutputMode:
        return OutputMode.RICH if self._out.is_terminal else OutputMode.PLAIN

    def _sync_no_color(self) -> None:
        no_color = self._mode is not OutputMode.RICH
        self._out.no_color = no_color
        if self._err is not None:
            self._err.no_color = no_color

    @property
    def _stderr(self) -> Console:
        if self._err is None:
            self._err = Console(stderr=True, theme=self._theme, highlight=False)
            self._err.no_color = self._mode is not OutputMode.RICH
        return self._err

    # -- mode ---------------------------------------------------------------

    @property
    def mode(self) -> OutputMode:
        """The current :class:`OutputMode`."""
        return self._mode

    def set_mode(self, mode: OutputMode) -> Self:
        """Set the output mode. Returns ``self`` for chaining."""
        self._mode = mode
        self._sync_no_color()
        return self

    @property
    def rich(self) -> Console:
        """The underlying :class:`rich.console.Console`."""
        return self._out

    # -- core -----------------------------------------------------------

    def print(
        self, msg: Any = "", *args: Any, style: str | None = None, markup: bool = True
    ) -> None:
        """Print *msg*, ``{}``-formatted with *args*. No-op in ``QUIET``/``JSON``."""
        if self._mode in (OutputMode.QUIET, OutputMode.JSON):
            return
        self._out.print(_format(msg, args), style=style, markup=markup)

    def emit(self, value: Any, *, quiet_text: str | None = None) -> None:
        """Emit *value* according to the current mode.

        - ``JSON`` -> :meth:`json`.
        - ``QUIET`` -> print *quiet_text* unstyled if given, else nothing.
        - else -> ``self.rich.print(value)`` (renders ``Table``/``Panel``/``str``/renderables).
        """
        if self._mode is OutputMode.JSON:
            self.json(value)
        elif self._mode is OutputMode.QUIET:
            if quiet_text is not None:
                self._out.print(quiet_text, markup=False)
        else:
            self._out.print(value)

    def json(self, value: Any) -> None:
        """Serialize *value* via :meth:`JsonUtils.serialize` and print it. Always emits, even in ``QUIET``.

        Printed with ``soft_wrap`` so Rich neither wraps nor crops it: a
        machine-readable payload that the console reflowed at terminal width
        is no longer parseable, and the consumer is a pipe, not a reader.
        """
        self._out.print(JsonUtils.serialize(value), markup=False, soft_wrap=True)

    # -- semantic (all {}-formatting, all no-op in QUIET/JSON) --------------

    def success(self, msg: str, *args: Any) -> None:
        """Print *msg* in green. No-op in ``QUIET``/``JSON``."""
        self.print(msg, *args, style="bold green")

    def info(self, msg: str, *args: Any) -> None:
        """Print *msg* unstyled. No-op in ``QUIET``/``JSON``."""
        self.print(msg, *args)

    def detail(self, msg: str, *args: Any) -> None:
        """Print *msg* dimmed. No-op in ``QUIET``/``JSON``."""
        self.print(msg, *args, style="dim")

    def warning(self, msg: str, *args: Any) -> None:
        """Print *msg* in yellow to stderr. No-op in ``QUIET``/``JSON``."""
        if self._mode in (OutputMode.QUIET, OutputMode.JSON):
            return
        self._stderr.print(_format(msg, args), style="yellow")

    def error(self, msg: str, *args: Any) -> None:
        """Print *msg* in red to stderr. No-op in ``QUIET``/``JSON``."""
        if self._mode in (OutputMode.QUIET, OutputMode.JSON):
            return
        self._stderr.print(_format(msg, args), style="bold red")

    def fail(self, msg: str, *args: Any, code: int = 1) -> NoReturn:
        """Call :meth:`error`, then raise :exc:`SystemExit` with *code*.

        Raises ``SystemExit`` rather than ``typer.Exit`` — this module has no
        Typer dependency; Typer/Click both handle a bare ``SystemExit`` fine.
        """
        self.error(msg, *args)
        raise SystemExit(code)

    # -- structures -----------------------------------------------------

    def table(
        self,
        *columns: str,
        rows: Iterable[Sequence[Any]],
        title: str | None = None,
        **table_kwargs: Any,
    ) -> None:
        """Build and print a table in one call. No-op in ``QUIET``.

        Non-``str`` cells go through ``str()``. Cell content is never
        interpreted as markup — data values are untrusted. In ``JSON`` mode,
        emits ``[{column: cell, ...}, ...]`` instead of a table.
        """
        if self._mode is OutputMode.QUIET:
            return
        rows = list(rows)
        if self._mode is OutputMode.JSON:
            self.json([dict(zip(columns, row, strict=False)) for row in rows])
            return
        tbl = Table(*columns, title=title, **table_kwargs)
        for row in rows:
            tbl.add_row(*(Text(str(cell)) for cell in row))
        self._out.print(tbl)

    def diff(self, text: str, *, title: str | None = None) -> None:
        """Print *text* as a syntax-highlighted unified diff. No-op in ``QUIET``/``JSON``.

        *text* is rendered via :class:`rich.syntax.Syntax`, which never
        interprets markup — diff text is untrusted.
        """
        if self._mode in (OutputMode.QUIET, OutputMode.JSON):
            return
        if title:
            self._out.rule(title)
        self._out.print(Syntax(text, "diff"))

    def rule(self, title: str = "") -> None:
        """Print a horizontal rule. No-op in ``QUIET``/``JSON``."""
        if self._mode in (OutputMode.QUIET, OutputMode.JSON):
            return
        self._out.rule(title)

    # -- interaction (always uses the real stdin/stdout, ignores QUIET) -----

    def confirm(self, msg: str, *, default: bool = False) -> bool:
        """Prompt for a yes/no confirmation. Ignores the current output mode."""
        return Confirm.ask(msg, default=default, console=self._out)

    def prompt(
        self, msg: str, *, default: str | None = None, password: bool = False
    ) -> str:
        """Prompt for a line of input. Ignores the current output mode."""
        return cast(
            str, Prompt.ask(msg, default=default, password=password, console=self._out)
        )

    def status(self, msg: str) -> AbstractContextManager[None]:
        """Return a spinner context manager in ``RICH`` mode, a no-op otherwise."""
        if self._mode is not OutputMode.RICH:
            return nullcontext()
        return self._status_context(msg)

    @contextmanager
    def _status_context(self, msg: str):
        with self._out.status(msg):
            yield


console: AppConsole = AppConsole()
