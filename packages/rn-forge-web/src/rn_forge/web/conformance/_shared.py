"""Shared headers and problem expectations for HTTP conformance cases."""

from __future__ import annotations

from http import HTTPStatus
from typing import Final

from rn_forge.web.conformance.types import REDACTED
from rn_forge.web.pagination import encode_cursor
from rn_forge.web.problem import BLANK_TYPE, ProblemType

__all__ = [
    "PAGE_1_NEXT_TOKEN",
    "_BOOKS_GET",
    "_CSV_TYPE",
    "_CSV_TYPE_PATTERN",
    "_ITEMS_PATH",
    "_JSON",
    "_ORDERS_CSV",
    "_PROBLEM",
    "_problem_body",
]

_JSON: Final = {"Content-Type": "application/json"}

_PROBLEM: Final = {"Content-Type": "application/problem+json"}

_ITEMS_PATH: Final = "/conformance/items"

_CSV_TYPE: Final = "text/csv"

_CSV_TYPE_PATTERN: Final = r"text/csv(; charset=utf-8)?"

_ORDERS_CSV: Final = "id,name\r\n1,widget\r\n"

_BOOKS_GET: Final = "/conformance/books:batchGet"


def _problem_body(
    row: ProblemType, detail: str, **extensions: object
) -> dict[str, object]:
    """The problem body a driver must produce, already in redacted form.

    Every case here uses ``about:blank`` (no ``type_base`` configured), so per
    RFC 9457 §4.2.1 the title is the HTTP status phrase, not *row*'s
    kit-specific title.
    """
    return {
        "type": BLANK_TYPE,
        "title": HTTPStatus(row.status).phrase,
        "status": row.status,
        "detail": detail,
        "instance": REDACTED,
        "traceId": REDACTED,
        **extensions,
    }


PAGE_1_NEXT_TOKEN: Final = encode_cursor((), "2")
