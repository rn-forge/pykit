"""Shared type aliases and typing helpers for third-party integration boundaries.

Several of this package's optional dependencies ship no type information
(``verboselogs``) or have incomplete stubs (``pandas``). This
module is the single place where those gaps are absorbed, so a dependency
upgrade has one file to revisit rather than scattered ``# pyright: ignore``
comments.

It also holds :data:`JsonValue`, the one recursive JSON alias the package
uses, so "arbitrary JSON metadata" has a single spelling.

The third-party helpers come in two shapes:

- **Base-class aliases** declared under ``TYPE_CHECKING`` with a plain runtime
  fallback, for subclassing an untyped third-party class.
- **Thin typed wrappers** that contain the cast once so call sites stay clean.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import verboselogs

__all__ = [
    "JsonValue",
    "VerboseLoggerBase",
    "series_columns",
    "series_value",
]


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

type JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
"""Any value :func:`json.dumps` accepts, recursively.

Annotating "arbitrary JSON metadata" as ``dict[str, Any]`` makes every read of
it untyped; this alias keeps the recursion explicit so a caller has to narrow
before using a value. Several modules had grown their own copy of it.
"""


# ---------------------------------------------------------------------------
# verboselogs
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    import logging

    class VerboseLoggerBase(logging.Logger):
        """Typed stand-in for the untyped :class:`verboselogs.VerboseLogger`.

        Declares only the extra levels verboselogs adds on top of
        :class:`logging.Logger`, so ``super()`` calls to them type-check.
        """

        def success(self, msg: Any, *args: Any, **kwargs: Any) -> None: ...

        def notice(self, msg: Any, *args: Any, **kwargs: Any) -> None: ...

        def verbose(self, msg: Any, *args: Any, **kwargs: Any) -> None: ...

        def spam(self, msg: Any, *args: Any, **kwargs: Any) -> None: ...

else:
    VerboseLoggerBase = verboselogs.VerboseLogger


# ---------------------------------------------------------------------------
# pandas
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    import pandas

    type SeriesRow = pandas.Series
else:
    SeriesRow = Any


def series_value(row: SeriesRow, field_name: str) -> Any:
    """Return ``row[field_name]``, normalized to ``Any``.

    ``Series.__getitem__`` has a wide overload set; pinning the result to
    ``Any`` here keeps the variation out of every call site.
    """
    return row[field_name]


def series_columns(row: SeriesRow) -> list[Any]:
    """Return the index labels of *row* as a plain list."""
    return row.index.tolist()
