"""A strict Jinja2 render engine for generated config files and documents.

Provides :class:`TemplateEngine`, a thin wrapper over `jinja2.Environment`
with strict-undefined-by-default rendering (a silently-empty variable in a
generated config file is a bug that surfaces far from its cause), support for
either a filesystem directory or a package resource directory as the
template source, and a ``validate()`` that compiles every visible template so
a ``doctor``-style command can catch a broken template before a user hits it.

Requires the ``templates`` extra (``jinja2``) — this module is not imported
by ``rn_forge.commons``'s curated ``__init__.py``, so ``import
rn_forge.commons`` never requires it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jinja2

from rn_forge.commons.documents import ConfigFormat, DocumentUtils
from rn_forge.commons.exceptions import AppException

__all__ = ["RenderError", "TemplateEngine"]


class RenderError(AppException):
    """A template could not be loaded, compiled, or rendered."""


class TemplateEngine:
    """Render templates from a directory or a package, with strict undefined handling."""

    def __init__(
        self,
        *,
        directory: str | None = None,
        package: str | None = None,
        package_path: str = "templates",
        strict: bool = True,
        **environment_kwargs: Any,
    ) -> None:
        """Initialize :class:`TemplateEngine`.

        Exactly one of *directory* or *package* must be given.

        Args:
            directory: A filesystem directory of templates
                (``jinja2.FileSystemLoader``).
            package: A Python package name whose ``package_path`` subdirectory
                holds templates (``jinja2.PackageLoader``) — the resource
                loads even when the package is installed as a zipped wheel.
            package_path: Subdirectory within *package* holding templates.
                Only meaningful with *package*.
            strict: Use ``jinja2.StrictUndefined`` (default) so referencing an
                undefined variable raises instead of rendering empty.
            **environment_kwargs: Forwarded to the ``jinja2.Environment``
                constructor (e.g. ``trim_blocks``, ``lstrip_blocks``).
                ``keep_trailing_newline=True`` is the default unless
                overridden here.

        Raises:
            ValueError: Both or neither of *directory*/*package* are given.
        """
        if (directory is None) == (package is None):
            raise ValueError("Exactly one of directory or package must be given")

        loader: jinja2.BaseLoader = (
            jinja2.FileSystemLoader(directory)
            if directory is not None
            else jinja2.PackageLoader(package, package_path)  # type: ignore[arg-type]
        )
        environment_kwargs.setdefault("keep_trailing_newline", True)
        self._environment = jinja2.Environment(
            loader=loader,
            undefined=jinja2.StrictUndefined if strict else jinja2.Undefined,
            autoescape=False,
            **environment_kwargs,
        )

        def to_toml(value: Mapping[str, Any]) -> str:
            return DocumentUtils.dumps(value, ConfigFormat.TOML)

        def to_yaml(value: Mapping[str, Any]) -> str:
            return DocumentUtils.dumps(value, ConfigFormat.YAML)

        self._environment.filters["to_toml"] = to_toml
        self._environment.filters["to_yaml"] = to_yaml

    @property
    def environment(self) -> jinja2.Environment:
        """The underlying ``jinja2.Environment`` — the escape hatch."""
        return self._environment

    def render_string(self, template: str, context: Mapping[str, Any]) -> str:
        """Render an inline template string.

        Raises:
            RenderError: The template cannot be compiled or evaluated.
        """
        try:
            return self._environment.from_string(template).render(**context)
        except jinja2.TemplateError as exc:
            raise RenderError(str(exc)) from exc

    def render(self, name: str, context: Mapping[str, Any]) -> str:
        """Render a named template from the configured directory or package.

        Raises:
            RenderError: The template cannot be loaded, compiled, or evaluated.
        """
        try:
            return self._environment.get_template(name).render(**context)
        except jinja2.TemplateError as exc:
            raise RenderError(str(exc)) from exc

    def validate(self) -> list[str]:
        """Compile every template visible to the loader; return error messages.

        Returns ``[]`` (rather than raising ``TypeError``) for an environment
        whose loader does not support listing templates.
        """
        errors: list[str] = []
        try:
            names = self._environment.list_templates()
        except TypeError:
            return errors
        for name in names:
            try:
                self._environment.get_template(name)
            except jinja2.TemplateError as exc:
                errors.append(f"{name}: {exc}")
        return errors
