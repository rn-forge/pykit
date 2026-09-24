"""Keyset pagination over :mod:`rn_forge.web`'s opaque page token.

``sqlakeyset`` is not adopted (checked 2026-09-23): its bookmark is its own
marker tuple, so adopting it would mean translating the token both ways to
replace a predicate of about ten lines.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, or_

from rn_forge.web import (
    Cursor,
    InvalidCursor,
    OrderField,
    check_cursor_order,
    encode_cursor,
    format_order_by,
)

__all__ = ["keyset", "next_page_token"]


def keyset[T: Select[Any]](
    stmt: T,
    *,
    columns: Mapping[str, ColumnElement[Any]],
    terms: Sequence[OrderField],
    cursor: Cursor | None,
    id_column: ColumnElement[Any],
) -> T:
    """Order *stmt* by the first ``orderBy`` term and resume after *cursor*.

    Rows are ordered by the first term's column, then *id_column*, both in that
    term's direction. Later terms do not order the rows, because the token holds
    one sort value, so the first term's column must be unique per row apart from
    the id tiebreak, and non-null. With no terms the order is *id_column*
    ascending and the token's sort key is the id.

    Fetch ``page_size + 1`` rows from the result to learn whether another page
    exists.

    Args:
        stmt: The query to order and filter.
        columns: Each allowed wire field name mapped to its column.
        terms: The parsed ``orderBy``; pass the request's terms, empty when the
            request gave none.
        cursor: The decoded page token, or ``None`` for the first page.
        id_column: The unique tiebreaker column.

    Raises:
        InvalidCursor: The token was issued for a different ``orderBy``, or its
            values do not fit the columns.
    """
    sort = columns[terms[0].field] if terms else id_column
    descending = terms[0].descending if terms else False
    if cursor is not None:
        check_cursor_order(cursor, terms)
        after_id = _from_wire(id_column, cursor.entity_id)
        if not terms:
            stmt = stmt.where(id_column > after_id)
        else:
            after = _from_wire(sort, cursor.sort_key)
            beyond = sort < after if descending else sort > after
            tie = id_column < after_id if descending else id_column > after_id
            stmt = stmt.where(or_(beyond, and_(sort == after, tie)))
    if not terms:
        return stmt.order_by(id_column)
    ordered = (sort.desc(), id_column.desc()) if descending else (sort, id_column)
    return stmt.order_by(*ordered)


def next_page_token(
    sort_value: object, entity_id: object, terms: Sequence[OrderField]
) -> str:
    """Encode the token that resumes after the row with these values.

    *sort_value* is the last row's value in the first term's column (its id
    when *terms* is empty). Pass the same *terms* given to :func:`keyset`.
    """
    return encode_cursor(
        _to_wire(sort_value), _to_wire(entity_id), format_order_by(terms)
    )


def _to_wire(value: object) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _from_wire(column: ColumnElement[Any], raw: str) -> Any:
    python_type: Any = column.type.python_type
    try:
        return (
            datetime.fromisoformat(raw) if python_type is datetime else python_type(raw)
        )
    except (ValueError, TypeError) as exc:
        raise InvalidCursor("Malformed page token", error_code=400) from exc
