"""Shared type aliases and typed third-party integration boundaries."""

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
it untyped; callers of this alias must narrow values before using them.
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
