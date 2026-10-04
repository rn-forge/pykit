"""Wire shapes for tabular export, import and bulk operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, cast
from urllib.parse import quote

from rn_forge.web.exceptions import InvalidBatchGet, RowsInvalid
from rn_forge.web.merge_patch import JsonValue
from rn_forge.web.problem import (
    REQUIRED_FIELD_DETAIL,
    VALIDATION_ERROR,
    ProblemRegistry,
    ProblemResponse,
    default_registry,
    field_error,
    render_problem,
)

__all__ = [
    "DUPLICATE_ID_DETAIL",
    "NON_EMPTY_IDS_DETAIL",
    "NON_EMPTY_LIST_DETAIL",
    "TABULAR_FORMATS",
    "BatchUpdateItem",
    "ImportCounts",
    "RowError",
    "TabularFormat",
    "content_disposition",
    "export_cap_problem",
    "import_report_body",
    "negotiate_tabular_format",
    "batch_get_ids",
    "parse_batch_update",
    "parse_flag",
    "row_cap_problem",
    "row_errors_problem",
    "unreadable_file_detail",
    "unsupported_file_detail",
]

NON_EMPTY_LIST_DETAIL: Final = "A non-empty list is required."
"""The detail for a bulk member that is an empty list or not a list."""

NON_EMPTY_IDS_DETAIL: Final = "A non-empty ids parameter is required."
"""The detail for a ``:batchGet`` request with no usable ``ids`` value."""

DUPLICATE_ID_DETAIL: Final = "Duplicate id in batch."
"""The detail for a repeated id in a ``:batchUpdate`` request."""

_PATCH_DETAIL: Final = "A merge patch must be a JSON object."
_IF_MATCH_DETAIL: Final = "Not a valid string."


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


def row_cap_problem(
    kind: Literal["import", "batch"],
    cap: int,
    *,
    instance: str,
    registry: ProblemRegistry | None = None,
) -> ProblemResponse:
    """Render "the *kind* exceeds *cap* rows" as a 422 problem with no ``errors`` member.

    Args:
        kind: ``"import"`` or ``"batch"``.
        cap: The row limit.
        instance: The ``instance`` member, in practice the request path.
        registry: The registry to render with; the default when omitted.
    """
    return render_problem(
        registry or default_registry(),
        ValueError("Validation Error"),
        instance=instance,
        problem=VALIDATION_ERROR,
        detail=_cap_detail(kind, cap),
    )


def _cap_detail(kind: str, cap: int) -> str:
    return f"The {kind} exceeds the limit of {cap} rows."


def batch_get_ids(values: Iterable[str], *, cap: int | None) -> list[str]:
    """Return the ids of a ``:batchGet`` request, from its repeated ``ids`` values.

    Empty values are dropped; a value is never split, so a comma-joined value
    is one id.

    Args:
        values: The raw values of the repeated ``ids`` query parameter.
        cap: The most ids a request may name, or ``None`` for no limit.

    Raises:
        InvalidBatchGet: No value is non-empty, or there are more than *cap* ids.
    """
    ids = [value for value in values if value]
    if not ids:
        raise InvalidBatchGet(NON_EMPTY_IDS_DETAIL)
    if cap is not None and len(ids) > cap:
        raise InvalidBatchGet(_cap_detail("batch", cap))
    return ids


@dataclass(frozen=True)
class BatchUpdateItem:
    """One validated ``:batchUpdate`` item.

    *index* is the item's position in ``requests``, *patch* its JSON Merge Patch
    and *if_match* its ``ifMatch`` precondition, if any.
    """

    index: int
    id: str
    patch: dict[str, JsonValue]
    if_match: str | None


def parse_batch_update(
    body: object,
    *,
    cap: int | None,
    instance: str,
    registry: ProblemRegistry | None = None,
) -> list[BatchUpdateItem] | ProblemResponse:
    """Check a ``:batchUpdate`` body's list, its size, each item's shape and the ids.

    Args:
        body: The decoded JSON request body.
        cap: The most items a request may carry, or ``None`` for no limit.
        instance: The ``instance`` member, in practice the request path.
        registry: The registry to render with; the default when omitted.

    Returns:
        The items in request order, or the problem to render when ``requests``
        is missing, empty or not a list (422 at ``/requests``) or over *cap*
        (:func:`row_cap_problem`).

    Raises:
        RowsInvalid: An item has no ``id``, a ``patch`` that is not a JSON
            object or an ``ifMatch`` that is not a string, or repeats an
            earlier item's id. Every failing item is reported, with root
            ``requests``.
    """
    members = cast("dict[str, object]", body) if isinstance(body, dict) else {}
    raw = members.get("requests")
    if not isinstance(raw, list) or not raw:
        detail = (
            NON_EMPTY_LIST_DETAIL if "requests" in members else REQUIRED_FIELD_DETAIL
        )
        return render_problem(
            registry or default_registry(),
            ValueError("Validation Error"),
            instance=instance,
            problem=VALIDATION_ERROR,
            detail="Validation Error",
            extensions={"errors": [field_error(("requests",), detail)]},
        )
    entries = cast("list[object]", raw)
    if cap is not None and len(entries) > cap:
        return row_cap_problem("batch", cap, instance=instance, registry=registry)

    items: list[BatchUpdateItem] = []
    errors: list[RowError] = []
    for index, entry in enumerate(entries):
        fields = cast("dict[str, object]", entry) if isinstance(entry, dict) else {}
        item_id = fields.get("id")
        patch = fields.get("patch")
        if_match = fields.get("ifMatch")
        failed = False
        if isinstance(item_id, bool) or not isinstance(item_id, (str, int)):
            errors.append(RowError(index, "id", REQUIRED_FIELD_DETAIL))
            failed = True
        if not isinstance(patch, dict):
            errors.append(RowError(index, "patch", _PATCH_DETAIL))
            failed = True
        if if_match is not None and not isinstance(if_match, str):
            errors.append(RowError(index, "ifMatch", _IF_MATCH_DETAIL))
            failed = True
        if not failed:
            items.append(
                BatchUpdateItem(
                    index,
                    str(item_id),
                    cast("dict[str, JsonValue]", patch),
                    cast("str | None", if_match),
                )
            )
    if errors:
        raise RowsInvalid(errors, root="requests")

    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            errors.append(RowError(item.index, "id", DUPLICATE_ID_DETAIL))
        seen.add(item.id)
    if errors:
        raise RowsInvalid(errors, root="requests")
    return items


@dataclass(frozen=True)
class ImportCounts:
    """What an import did: rows *created*, rows *updated* and rows *skipped*."""

    created: int
    updated: int
    skipped: int


def parse_flag(value: str | None) -> bool:
    """Return whether *value* is ``"true"`` or ``"1"``, ignoring case.

    Anything else, including ``None``, is ``False``. It parses the
    ``validateOnly`` and ``prefill`` query parameters.
    """
    return value is not None and value.lower() in {"true", "1"}


def unsupported_file_detail(formats: Iterable[str]) -> str:
    """Return the detail for an upload whose type is not in *formats*.

    Example::

        unsupported_file_detail(("csv", "xlsx"))
        # 'Unsupported file type; use one of: csv, xlsx.'
    """
    return f"Unsupported file type; use one of: {', '.join(formats)}."


def unreadable_file_detail(extension: str) -> str:
    """Return the detail for an upload that could not be parsed as *extension*."""
    return f"The file could not be read as {extension}."
