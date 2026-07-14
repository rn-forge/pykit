"""Console utilities: argument parsing and logging configuration.

Provides:

- :class:`CLIArgumentParser` — an :class:`argparse.ArgumentParser`
  subclass that auto-adds ``--log-level`` and ``--log-file`` arguments and
  wires them into :meth:`AppLogger.initialize`.
- :class:`BooleanAction` — a clean ``argparse.Action`` for boolean flags that
  accepts ``true/false/yes/no/1/0`` values.
- :class:`KeyValueAction` — an ``argparse.Action`` for ``key=value`` pairs,
  collecting them into a dict on the namespace.
"""

from __future__ import annotations

import argparse
from typing import Any, Self, Sequence

from rn_forge.commons.logging import AppLogger

# Mapping from human-friendly level names (and single-letter shortcuts) to
# int values.  Includes all verboselogs levels plus TRACE.
_LOG_LEVELS: dict[str, int] = {
    "CRITICAL": AppLogger.CRITICAL,
    "FATAL": AppLogger.FATAL,
    "ERROR": AppLogger.ERROR,
    "SUCCESS": AppLogger.SUCCESS,
    "WARNING": AppLogger.WARNING,
    "NOTICE": AppLogger.NOTICE,
    "INFO": AppLogger.INFO,
    "VERBOSE": AppLogger.VERBOSE,
    "DEBUG": AppLogger.DEBUG,
    "SPAM": AppLogger.SPAM,
    "TRACE": AppLogger.TRACE,
    # Single-letter shortcuts
    "C": AppLogger.CRITICAL,
    "E": AppLogger.ERROR,
    "W": AppLogger.WARNING,
    "I": AppLogger.INFO,
    "V": AppLogger.VERBOSE,
    "D": AppLogger.DEBUG,
    "T": AppLogger.TRACE,
}


# ---------------------------------------------------------------------------
# BooleanAction — clean boolean flag parsing
# ---------------------------------------------------------------------------


class BooleanAction(argparse.Action):
    """Argparse action that parses boolean values from strings.

    Accepts: ``true``, ``false``, ``yes``, ``no``, ``1``, ``0``
    (case-insensitive).

    Usage::

        parser.add_argument("--dry-run", action=BooleanAction, default=False)
    """

    _TRUTHY = frozenset({"true", "yes", "1"})
    _FALSY = frozenset({"false", "no", "0"})

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        default: bool = False,
        required: bool = False,
        help: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs="?",
            const=True,
            default=default,
            type=None,
            choices=None,
            required=required,
            help=help,
            metavar="BOOL",
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        if values is None or values is self.const:
            setattr(namespace, self.dest, bool(self.const))
            return

        text = str(values).strip().lower()
        if text in self._TRUTHY:
            setattr(namespace, self.dest, True)
        elif text in self._FALSY:
            setattr(namespace, self.dest, False)
        else:
            raise argparse.ArgumentTypeError(
                f"Invalid boolean value '{values}' for {option_string}. "
                f"Expected: true/false, yes/no, 1/0"
            )


# ---------------------------------------------------------------------------
# KeyValueAction — collect key=value pairs into a dict
# ---------------------------------------------------------------------------


class KeyValueAction(argparse.Action):
    """Argparse action that collects ``key=value`` pairs into a dict.

    Usage::

        parser.add_argument("--config", action=KeyValueAction, help="key=value config")
        # CLI: --config timeout=30 --config retries=3
        # Result: args.config == {"timeout": "30", "retries": "3"}

        parser.add_argument("--env", action=KeyValueAction, nargs="*")
        # CLI: --env FOO=bar BAZ=qux
        # Result: args.env == {"FOO": "bar", "BAZ": "qux"}

    Values are always strings.  The application is responsible for type conversion.
    """

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: int | str | None = None,
        default: dict[str, str] | None = None,
        required: bool = False,
        help: str | None = None,  # noqa: A002
        metavar: str | None = "KEY=VALUE",
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            default=default if default is not None else {},
            type=None,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        dest_dict: dict[str, str] = getattr(namespace, self.dest, None) or {}

        items = [values] if isinstance(values, str) else (values or [])
        for item in items:
            text = str(item)
            if "=" not in text:
                raise argparse.ArgumentTypeError(
                    f"Invalid key=value pair '{text}' for {option_string}. "
                    f"Expected format: KEY=VALUE"
                )
            key, _, val = text.partition("=")
            dest_dict[key] = val

        setattr(namespace, self.dest, dest_dict)


# ---------------------------------------------------------------------------
# CLIArgumentParser
# ---------------------------------------------------------------------------


class CLIArgumentParser(argparse.ArgumentParser):
    """ArgumentParser with built-in ``--log-level`` and ``--log-file`` support.

    Extends :class:`argparse.ArgumentParser` with:

    - ``--log-level`` / ``-ll``: set the logging level (accepts full names
      like ``INFO`` or single-letter shortcuts like ``I``).
    - ``--log-file`` / ``-lf``: path to a log file.
    - :meth:`configure_logging`: one-call bridge from parsed args to
      :meth:`AppLogger.initialize`.
    - :meth:`add_boolean_argument`: convenience for boolean flags.
    - :meth:`add_key_value_argument`: convenience for ``key=value`` pair
      collection.

    Usage::

        parser = CLIArgumentParser(prog="my-tool")
        parser.add_argument("--input", required=True)
        parser.add_key_value_argument("--env", help="Environment overrides")
        args = parser.parse_args()
        logger = parser.configure_logging(args)
    """

    def __init__(
        self,
        prog: str,
        *,
        add_log_args: bool = True,
        default_log_level: str = "VERBOSE",
        **kwargs: Any,
    ) -> None:
        super().__init__(prog=prog, **kwargs)
        self._default_log_level = default_log_level
        if add_log_args:
            self._add_log_arguments()

    def _add_log_arguments(self) -> None:
        """Add ``--log-level`` and ``--log-file`` arguments."""
        group = self.add_argument_group("logging")
        group.add_argument(
            "-ll",
            "--log-level",
            dest="log_level",
            type=str.upper,
            choices=_LOG_LEVELS,
            default=self._default_log_level,
            help="Logging level (default: %(default)s)",
        )
        group.add_argument(
            "-lf",
            "--log-file",
            dest="log_file",
            default=None,
            help="Path to log file",
        )

    def add_boolean_argument(
        self,
        *args: str,
        default: bool = False,
        **kwargs: Any,
    ) -> Self:
        """Add a boolean flag argument.

        Accepts ``true/false/yes/no/1/0``.  Returns *self* for chaining.
        """
        kwargs["action"] = BooleanAction
        kwargs["default"] = default
        self.add_argument(*args, **kwargs)
        return self

    def add_key_value_argument(
        self,
        *args: str,
        multi: bool = True,
        **kwargs: Any,
    ) -> Self:
        """Add a ``key=value`` pair argument that collects into a dict.

        Args:
            *args: Option strings (e.g. ``"--config"``, ``"-c"``).
            multi: When ``True`` (default), accepts multiple values per invocation
                (``--config a=1 b=2``).  When ``False``, accepts one value per
                invocation (``--config a=1 --config b=2``).  Both modes accumulate
                into the same dict.
            **kwargs: Additional keyword arguments passed to ``add_argument``.

        Returns:
            ``self`` for chaining.
        """
        kwargs["action"] = KeyValueAction
        if multi:
            kwargs.setdefault("nargs", "*")
        self.add_argument(*args, **kwargs)
        return self

    def configure_logging(
        self,
        args: argparse.Namespace,
        *,
        root_logger_name: str | None = None,
        **kwargs: Any,
    ) -> AppLogger:
        """Configure logging from parsed arguments.

        Reads ``args.log_level`` and ``args.log_file`` from the namespace
        and delegates to :meth:`AppLogger.initialize`.

        Args:
            args: The parsed namespace (from ``parse_args()``).
            root_logger_name: Override the root logger name.
                Defaults to the parser's ``prog`` (spaces replaced with ``_``,
                lowercased).
            **kwargs: Additional keyword arguments forwarded to
                :meth:`AppLogger.initialize`.

        Returns:
            The configured :class:`AppLogger`.
        """
        level_name = getattr(args, "log_level", self._default_log_level)
        level = _LOG_LEVELS.get(level_name, AppLogger.VERBOSE)
        log_file = getattr(args, "log_file", None)

        return AppLogger.initialize(
            root_logger_name=root_logger_name or self.prog.replace(" ", "_").lower(),
            level=level,
            file=log_file,
            **kwargs,
        )


__all__ = [
    "CLIArgumentParser",
    "BooleanAction",
    "KeyValueAction",
]
