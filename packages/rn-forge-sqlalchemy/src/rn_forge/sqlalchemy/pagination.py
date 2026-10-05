"""Keyset pagination over :mod:`rn_forge.web`'s opaque page token.

``sqlakeyset`` is not adopted (checked 2026-09-23): its bookmark is its own
marker tuple, so adopting it would mean translating the token both ways to
replace a short predicate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, and_, or_

from rn_forge.web import (
    Cursor,
    InvalidCursor,
    OrderField,
    SortValue,
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
    """Order *stmt* by every ``orderBy`` term and resume after *cursor*.

    Rows are ordered by each term's column in turn, then by *id_column* in the
    last term's direction (ascending with no terms), unless *id_column* is
    already a term. Rows whose value is ``NULL`` come after those that have one,
    in both directions, on every database. Term columns need not be unique and
    may be nullable; *id_column* must not be.

    Fetch ``page_size + 1`` rows from the result to learn whether another page
    exists.

    Args:
        stmt: The query to order and filter.
        columns: Each allowed wire field name mapped to its column.
        terms: The parsed ``orderBy``; pass the request's terms, empty when the
            request gave none.
        cursor: The decoded page token, or ``None`` for the first page.
        id_column: The unique, non-null tiebreaker column.

    Raises:
        InvalidCursor: The token was issued for a different ``orderBy``, or its
            values do not fit the columns.
    """
    keys = [(columns[t.field], t.descending) for t in terms]
    if not any(column is id_column for column, _ in keys):
        keys.append((id_column, keys[-1][1] if keys else False))
    if cursor is not None:
        check_cursor_order(cursor, terms)
        raw = [*cursor.sort_keys]
        if len(raw) < len(keys):
            raw.append(cursor.entity_id)
        after = [_from_wire(column, value) for (column, _), value in zip(keys, raw)]
        stmt = stmt.where(_after(keys, after, id_column))
    ordered: list[ColumnElement[Any]] = []
    for column, descending in keys:
        if column is not id_column:
            ordered.append(column.is_(None))
        ordered.append(column.desc() if descending else column)
    return stmt.order_by(*ordered)


def _after(
    keys: Sequence[tuple[ColumnElement[Any], bool]],
    values: Sequence[Any],
    id_column: ColumnElement[Any],
) -> ColumnElement[bool]:
    """The rows past *values*: for some term, every earlier one equal and it beyond."""
    arms: list[ColumnElement[bool]] = []
    for i, ((column, descending), value) in enumerate(zip(keys, values)):
        if value is None:
            if column is id_column:
                raise InvalidCursor("Malformed page token", error_code=400)
            continue  # nothing follows inside the nulls
        beyond = column < value if descending else column > value
        if column is not id_column:
            beyond = or_(beyond, column.is_(None))
        equal = [
            c.is_(None) if v is None else c == v
            for (c, _), v in zip(keys[:i], values[:i])
        ]
        arms.append(and_(*equal, beyond))
    return or_(*arms)


def next_page_token(
    row_values: Sequence[object], entity_id: object, terms: Sequence[OrderField]
) -> str:
    """Encode the token that resumes after the row with these values.

    *row_values* is the last row's value in each term's column, one per term
    (empty when *terms* is empty). Pass the same *terms* given to :func:`keyset`.
    """
    return encode_cursor(
        tuple(_to_wire(v) for v in row_values),
        str(entity_id),
        format_order_by(terms),
    )


def _to_wire(value: object) -> SortValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return value.isoformat() if isinstance(value, date) else str(value)


def _from_wire(column: ColumnElement[Any], raw: SortValue) -> Any:
    if raw is None:
        return None
    python_type: Any = column.type.python_type
    try:
        if python_type is datetime:
            return datetime.fromisoformat(cast(str, raw))
        if python_type is date:
            return date.fromisoformat(cast(str, raw))
        if isinstance(raw, bool) != (python_type is bool) or (
            isinstance(raw, float) and python_type is int
        ):
            raise TypeError(raw)
        return python_type(raw)
    except (ValueError, TypeError) as exc:
        raise InvalidCursor("Malformed page token", error_code=400) from exc
