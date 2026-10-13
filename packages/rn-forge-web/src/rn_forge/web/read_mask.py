"""The ``readMask`` query parameter: partial responses (AIP-157)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

from rn_forge.web.exceptions import InvalidReadMask

__all__ = [
    "READ_MASK_PARAM",
    "FieldTree",
    "ReadMask",
    "parse_read_mask",
]

READ_MASK_PARAM: Final = "readMask"
"""The name of the query parameter that carries the mask."""

type FieldTree = Mapping[str, FieldTree | None]
"""The declared shape of a representation, by wire field name.

A declared object, or a list of declared objects, maps to a subtree. Every
other field maps to ``None``, including a free-form JSON value.
"""

type _MaskTree = Mapping[str, _MaskTree | None]

_WHOLE: Final = "*"


@dataclass(frozen=True)
class ReadMask:
    """A validated, merged set of field paths.

    *tree* maps each selected wire field name to a subtree of selected
    sub-fields, or to ``None`` when the whole value is selected.
    """

    tree: _MaskTree

    def apply(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Return a copy of *body* holding only the selected fields.

        A path through a list applies to every element. A selected field that
        *body* lacks is not added.
        """
        return _prune(body, self.tree)


def parse_read_mask(raw: str | None, *, fields: FieldTree) -> ReadMask | None:
    """Parse a ``readMask`` value against the declared fields of a representation.

    Paths are comma-separated and joined by ``.``; whitespace around a path is
    ignored. Overlapping paths merge, so ``address`` and
    ``address.city`` select the whole ``address``.

    Args:
        raw: The raw query value.
        fields: The declared shape of the representation.

    Returns:
        ``None`` when *raw* is absent, blank or ``*``: the whole representation.

    Raises:
        InvalidReadMask: ``*`` is combined with other paths, or a path is empty
            or names no declared field, including one that goes inside a scalar
            or free-form field.
    """
    if not raw or not raw.strip():
        return None
    paths = [part.strip() for part in raw.split(",")]
    if _WHOLE in paths:
        if len(paths) > 1:
            raise InvalidReadMask("readMask '*' cannot be combined with other paths")
        return None
    tree: dict[str, Any] = {}
    for path in paths:
        _add(tree, path, fields)
    return ReadMask(tree)


def _add(tree: dict[str, Any], path: str, fields: FieldTree) -> None:
    """Merge *path* into *tree*, raising if it names no declared field."""
    node: dict[str, Any] | None = tree
    declared: FieldTree | None = fields
    segments = path.split(".")
    for position, segment in enumerate(segments):
        if declared is None or segment not in declared:
            raise InvalidReadMask(f"Unknown readMask path '{path}'")
        declared = declared[segment]
        if node is None:
            continue
        if position == len(segments) - 1:
            node[segment] = None
        else:
            node = node.setdefault(segment, {})


def _prune(body: Mapping[str, Any], tree: _MaskTree) -> dict[str, Any]:
    """Keep the members of *body* that *tree* selects."""
    kept: dict[str, Any] = {}
    for name, value in body.items():
        if name not in tree:
            continue
        subtree = tree[name]
        if subtree is None:
            kept[name] = value
        elif isinstance(value, Mapping):
            kept[name] = _prune(cast("Mapping[str, Any]", value), subtree)
        elif isinstance(value, list):
            kept[name] = [
                _prune(cast("Mapping[str, Any]", item), subtree)
                if isinstance(item, Mapping)
                else item
                for item in cast("list[Any]", value)
            ]
        else:
            kept[name] = value
    return kept
