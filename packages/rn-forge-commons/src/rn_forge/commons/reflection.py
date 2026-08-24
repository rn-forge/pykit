"""Reflection helpers for fully-qualified names, error messages, and argument inspection.

Provides:
    ReflectUtils: Static utilities for inspecting callables, resolving fully-qualified
        names, formatting error messages, and reading variable values from stack frames.

Typical usage::

    from rn_forge.commons.reflection import ReflectUtils

    fqn = ReflectUtils.get_fully_qualified_name(MyClass)
    # "mypackage.module.MyClass"
"""

from __future__ import annotations

import inspect
from operator import attrgetter
from types import FrameType
from typing import Any, Callable, cast

__all__ = ["ReflectUtils"]


def _logger():
    from rn_forge.commons.logging import AppLogger

    return AppLogger.get_logger(__name__)


class ReflectUtils:
    """Reflection and introspection utilities.

    All methods are static.  Useful for logging, error formatting, and audit
    tooling that needs human-readable names for arbitrary Python objects.

    Example::

        from rn_forge.commons.reflection import ReflectUtils

        fqn = ReflectUtils.get_fully_qualified_name(ValueError("oops"))
        # "builtins.ValueError"
    """

    @staticmethod
    def get_fully_qualified_name(target: Any) -> str:
        """Return the fully-qualified ``module.qualname`` for a type, function, instance, or frame.

        For a :class:`types.FrameType` the result is
        ``<module>.<co_qualname>``.  For all other objects the containing
        module and ``__qualname__`` of the type (or the object itself, if it
        is a class or function) are joined with a ``"."``.

        Args:
            target: A class, function, object instance, or :class:`types.FrameType`.

        Returns:
            A dotted string of the form ``"module.QualifiedName"``.

        Example::

            ReflectUtils.get_fully_qualified_name(int)
            # "builtins.int"
        """
        if isinstance(target, FrameType):
            return f"{target.f_globals.get('__name__')}.{target.f_code.co_qualname}"

        target_type = (  # pyright: ignore[reportUnknownVariableType]
            target
            if (inspect.isclass(target) or inspect.isfunction(target))
            else type(target)
        )
        return f"{target_type.__module__}.{target_type.__qualname__}"

    @staticmethod
    def get_error_message(error: Exception) -> str:
        """Return a formatted error string of the form ``"<FQN> -> <str(error)>"``.

        Args:
            error: The exception instance to format.

        Returns:
            A string combining the fully-qualified class name and the exception
            message, separated by `` -> ``.

        Example::

            ReflectUtils.get_error_message(ValueError("bad input"))
            # "builtins.ValueError -> bad input"
        """
        return f"{ReflectUtils.get_fully_qualified_name(error)} -> {error}"

    @staticmethod
    def inspect_method_arguments(
        method: Callable[..., Any],
        method_args: tuple[Any, ...],
        method_kwargs: dict[str, Any],
        exclude: list[str] | None = None,
        include: list[str] | None = None,
    ) -> list[str]:
        """Return ``["param=value", ...]`` for the arguments bound to *method*.

        ``self`` and ``cls`` are excluded by default unless listed in *include*.
        Intended for audit logging and debug output — do not use to drive
        program logic.

        Args:
            method: The callable whose signature is used for binding.
            method_args: Positional arguments to bind.
            method_kwargs: Keyword arguments to bind.
            exclude: Additional parameter names to suppress from output.
            include: When provided, only these parameter names are included,
                overriding the default ``self``/``cls`` exclusion.

        Returns:
            A list of ``"name=value"`` strings for each included bound argument.

        Example::

            def greet(self, name: str, greeting: str = "Hello") -> str: ...

            ReflectUtils.inspect_method_arguments(
                greet, (obj, "World"), {}, exclude=["greeting"]
            )
            # ["name='World'"]
        """
        _include = include or []
        _exclude = [e for e in (exclude or []) + ["self", "cls"] if e not in _include]
        bound = inspect.signature(cast(Any, method)).bind(*method_args, **method_kwargs)
        bound.apply_defaults()
        return [f"{k}={v}" for k, v in bound.arguments.items() if k not in _exclude]

    @staticmethod
    def inspect_variables(
        var_names: str,
        source_frame: FrameType | None = None,
    ) -> list[str]:
        """Return ``["name=value", ...]`` for comma-separated *var_names* resolved in a frame.

        Dot-notation is supported for attribute access (e.g. ``"obj.attr"``).
        When a dotted path ends in a callable attribute, it is called with no
        arguments and the return value is used.

        Args:
            var_names: Comma-separated variable names, optionally with
                dot-notation for attribute traversal (e.g. ``"req.method"``).
            source_frame: The stack frame whose locals are searched. Defaults
                to the immediate caller's frame when ``None``.

        Returns:
            A list of ``"name=value"`` strings.  Returns an empty list when no
            frame can be resolved.

        Example::

            x = 42
            ReflectUtils.inspect_variables("x")
            # ["x=42"]

            ReflectUtils.inspect_variables("request.method, user.email")
        """
        frame = source_frame
        if frame is None:
            current = inspect.currentframe()
            frame = current.f_back if current is not None else None
        if frame is None:
            _logger().trace(
                "ReflectUtils.inspect_variables: no frame | var_names={}",
                var_names,
            )
            return []

        values = [
            ReflectUtils._resolve_variable(var, frame)
            for var in var_names.replace(" ", "").split(",")
        ]

        _logger().trace(
            "ReflectUtils.inspect_variables: resolved_count={} | var_names={}",
            len(values),
            var_names,
        )
        return values

    @staticmethod
    def _resolve_variable(var: str, frame: FrameType) -> str:
        """Resolve one ``"name=value"`` entry for `inspect_variables`."""
        if "." in var:
            return ReflectUtils._resolve_dotted_variable(var, frame)

        if var not in frame.f_locals:
            _logger().debug(
                "ReflectUtils.inspect_variables: missing variable | var={}",
                var,
            )
            return f"{var}=<undefined>"
        return f"{var}={frame.f_locals[var]}"

    @staticmethod
    def _resolve_dotted_variable(var: str, frame: FrameType) -> str:
        """Resolve a dot-notation ``"obj.attr"`` entry for `inspect_variables`."""
        parts = var.split(".")
        if parts[0] not in frame.f_locals:
            _logger().debug(
                "ReflectUtils.inspect_variables: missing root variable | var={}",
                parts[0],
            )
            return f"{var}=<undefined>"
        val = attrgetter(".".join(parts[1:]))(frame.f_locals[parts[0]])
        return f"{var}={val() if callable(val) else val}"
