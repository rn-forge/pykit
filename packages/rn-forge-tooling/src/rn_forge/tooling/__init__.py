"""Public lifecycle and installation APIs for developer tools."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rn_forge.tooling.install import ToolHome, ToolProduct, extract_archive

__all__ = [
    "ToolHome",
    "ToolProduct",
    "extract_archive",
]

_INSTALL = "rn_forge.tooling.install"

_MODULES = {
    "ToolHome": _INSTALL,
    "ToolProduct": _INSTALL,
    "extract_archive": _INSTALL,
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
