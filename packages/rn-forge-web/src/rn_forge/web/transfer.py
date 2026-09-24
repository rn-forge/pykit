"""Wire shapes for tabular export, import and bulk operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote

from rn_forge.web.problem import (
    VALIDATION_ERROR,
    ProblemRegistry,
    ProblemResponse,
    default_registry,
    field_error,
    render_problem,
)

__all__ = [
    "TABULAR_FORMATS",
    "RowError",
    "TabularFormat",
    "content_disposition",
    "export_cap_problem",
    "import_report_body",
    "negotiate_tabular_format",
    "row_errors_problem",
]


@dataclass(frozen=True)
class TabularFormat:
    """One tabular file format: its media type, extension and codec name."""

    media_type: str
    extension: str
    tablib_name: str


TABULAR_FORMATS: Final[Mapping[str, TabularFormat]] = {
    fmt.extension: fmt
    for fmt in (
        TabularFormat("text/csv", "csv", "csv"),
        TabularFormat("text/tab-separated-values", "tsv", "tsv"),
        TabularFormat(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
            "xlsx",
        ),
        TabularFormat("application/vnd.oasis.opendocument.spreadsheet", "ods", "ods"),
    )
}
"""The tabular formats, keyed by file extension (which is also the ``?format=`` value)."""


def negotiate_tabular_format(
    accept: str | None, format_param: str | None, allowed: Iterable[str]
) -> TabularFormat | None:
    """Choose the tabular format a GET should be answered in, if any.

    *format_param* wins over *accept*, as a link cannot set headers. Otherwise
    the allowed format with the highest ``q`` in *accept* is chosen, but only
    when it beats every explicitly listed non-tabular range; wildcards never
    select a tabular format, so a client that did not ask for one gets the
    JSON representation.

    Args:
        accept: The ``Accept`` header value.
        format_param: The ``format`` query parameter value.
        allowed: The extensions (keys of :data:`TABULAR_FORMATS`) the endpoint offers.

    Returns:
        The format, or ``None`` when the response should not be tabular,
        including when *format_param* names a format that is not allowed.
    """
    offered = [TABULAR_FORMATS[ext] for ext in allowed if ext in TABULAR_FORMATS]
    if format_param:
        return next((f for f in offered if f.extension == format_param.lower()), None)
    if not accept:
        return None
    by_media = {f.media_type: f for f in offered}
    best: tuple[float, TabularFormat] | None = None
    best_other = 0.0
    for media, q in _parse_accept(accept):
        fmt = by_media.get(media)
        if fmt is not None:
            if best is None or q > best[0]:
                best = (q, fmt)
        elif "*" not in media:
            best_other = max(best_other, q)
    if best is None or best[0] <= 0 or best[0] <= best_other:
        return None
    return best[1]


def _parse_accept(accept: str) -> list[tuple[str, float]]:
    """Return ``(lowercased media range, q)`` for each range in *accept*."""
    ranges: list[tuple[str, float]] = []
    for part in accept.split(","):
        media, *params = (p.strip() for p in part.split(";"))
        if not media:
            continue
        q = 1.0
        for param in params:
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        ranges.append((media.lower(), q))
    return ranges


def content_disposition(filename: str) -> str:
    """Return an ``attachment`` ``Content-Disposition`` value for *filename*.

    Carries both the RFC 6266 quoted ``filename`` (non-ASCII and control
    characters replaced by ``_``, path separators dropped) and the RFC 8187
    ``filename*`` in UTF-8, which clients that understand it prefer.

    Example::

        content_disposition("Orders 2026.csv")
        # 'attachment; filename="Orders 2026.csv"; filename*=UTF-8\\'\\'Orders%202026.csv'
    """
    name = filename.replace("/", "").replace("\\", "")
    fallback = "".join("_" if not (32 <= ord(c) < 127) else c for c in name).replace(
        '"', "'"
    )
    encoded = quote(name, safe="!#$&+-.^_`|~")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def import_report_body(
    *, created: int, updated: int, skipped: int, validate_only: bool
) -> dict[str, Any]:
    """Return the body of a successful import: counts, and whether nothing was persisted."""
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "validateOnly": validate_only,
    }


@dataclass(frozen=True)
class RowError:
    """One failed cell: the row's index, the column (or field), and the message.

    An empty *field* points at the whole row.
    """

    row: int
    field: str
    message: str


def row_errors_problem(
    errors: Iterable[RowError],
    *,
    instance: str,
    root: str = "rows",
    registry: ProblemRegistry | None = None,
) -> ProblemResponse:
    """Render row errors as a 422 ``application/problem+json`` response.

    Each error becomes an ``errors`` entry whose ``pointer`` is
    ``/<root>/<row>/<field>``, e.g. ``/rows/12/Quantity`` for an import and
    ``/requests/3/name`` for a batch create (``root="requests"``).

    Args:
        errors: The failed cells.
        instance: The ``instance`` member, in practice the request path.
        root: The first pointer segment.
        registry: The registry to render with; the default when omitted.
    """
    entries = [
        field_error((root, e.row, *([e.field] if e.field else [])), e.message)
        for e in errors
    ]
    return render_problem(
        registry or default_registry(),
        ValueError("Validation Error"),
        instance=instance,
        problem=VALIDATION_ERROR,
        detail="One or more rows are invalid.",
        extensions={"errors": entries},
    )


def export_cap_problem(
    cap: int, *, instance: str, registry: ProblemRegistry | None = None
) -> ProblemResponse:
    """Render "the export exceeds *cap* rows" as a 422 problem naming the cap."""
    return render_problem(
        registry or default_registry(),
        ValueError("Validation Error"),
        instance=instance,
        problem=VALIDATION_ERROR,
        detail=f"The export exceeds the limit of {cap} rows; narrow the filter.",
    )
