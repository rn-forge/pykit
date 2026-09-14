"""Public API for ``rn_forge.tooling``.

The file-owning half of the developer-tooling stack: local state, a strict
template engine, the generation engine, install mechanics and the
documentation checkers. A tool that writes into a repository takes these from
here rather than growing its own::

    from rn_forge.tooling import StateStore, TemplateEngine

Where :mod:`rn_forge.commons` is runtime-neutral and :mod:`rn_forge.cli` is the
command-line shape, this package is deliberately workstation-shaped: it assumes
a developer's filesystem and a tool that owns files in it. A ``python-app``
repository needs the first two and not this one; a ``python-tool`` repository
needs all three. A package that ships into a deployed runtime must not depend
on this one outside a ``codegen`` extra.

Two modules are deliberately absent from this curated surface and imported
directly: :mod:`rn_forge.tooling.docs`, whose checkers are a command's concern
rather than a library's, and :mod:`rn_forge.tooling.generation`, whose names
(``Artifact``, ``Action``, ``plan``, ``apply``) are too generic to hoist into a
package-level namespace.

Attributes are resolved lazily. :class:`~rn_forge.tooling.templates.TemplateEngine`
imports Jinja2, and a tool that only reads a state file should not pay for that
import — or fail on it — merely by importing this package.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rn_forge.tooling.install import ToolHome, ToolProduct, extract_archive
    from rn_forge.tooling.state import StateStore
    from rn_forge.tooling.templates import RenderError, TemplateEngine

__all__ = [
    "RenderError",
    "StateStore",
    "TemplateEngine",
    "ToolHome",
    "ToolProduct",
    "extract_archive",
]

_MODULES = {
    "RenderError": "rn_forge.tooling.templates",
    "StateStore": "rn_forge.tooling.state",
    "TemplateEngine": "rn_forge.tooling.templates",
    "ToolHome": "rn_forge.tooling.install",
    "ToolProduct": "rn_forge.tooling.install",
    "extract_archive": "rn_forge.tooling.install",
}


def __getattr__(name: str) -> Any:
    """Import and return a public symbol on first access."""
    module_name = _MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include the lazily-imported names in ``dir()``."""
    return sorted([*globals(), *__all__])
