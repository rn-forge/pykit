"""Shared type aliases and typed third-party integration boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import verboselogs

__all__ = [
    "JsonValue",
    "VerboseLoggerBase",
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
