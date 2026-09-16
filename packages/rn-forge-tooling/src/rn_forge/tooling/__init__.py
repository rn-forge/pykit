"""Public state, template, and installation APIs for developer tooling."""

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
