"""AIP-158 cursor pagination and legacy page-number pagination for DRF."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, cast, override

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q, QuerySet
from django.db.models.expressions import OrderBy
from rest_framework import filters as drf_filters
from rest_framework import pagination as drf_pagination
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.django import settings as rnf_settings
from rn_forge.django.drf.casing import camelize_key, underscore_key
from rn_forge.web import (
    DEFAULT_PAGE_TOKEN_PARAM,
    ORDER_BY_PARAM,
    Cursor,
    InvalidCursor,
    OrderField,
    Page,
    SortValue,
    check_cursor_order,
    clamp_page_size,
    decode_cursor,
    encode_cursor,
    format_order_by,
    parse_order_by,
)

__all__ = ["CursorPagination", "LegacyPageNumberPagination", "OrderByFilter"]


def _page_size(
    request: Request, *, page_size: int | None, max_page_size: int | None
) -> int:
    """Resolve the page size from the query string, clamped and never rejected."""
    conf = rnf_settings.rn_forge_django_settings.drf.pagination
    raw = request.query_params.get(conf.page_size_query_param)
    requested = int(raw) if raw is not None and raw.lstrip("-").isdigit() else None
    return clamp_page_size(
        requested,
        default=page_size if page_size is not None else conf.page_size,
        cap=max_page_size if max_page_size is not None else conf.max_page_size,
    )


class OrderByFilter(drf_filters.OrderingFilter):
    """AIP-132 ``orderBy`` (``displayName desc``) over the view's ``ordering_fields``.

    List it in the view's ``filter_backends``; :class:`CursorPagination`
    then pages in that order. ``ordering_fields`` holds the model's
    ``snake_case`` names, and may be nullable or span a relation
    (``author__name``). The value is a comma-separated list of terms; rows whose
    value is ``NULL`` sort last in both directions. An unlisted or malformed term
    raises :class:`rn_forge.web.InvalidOrderBy`, as does a repeated field.
    """

    ordering_param = ORDER_BY_PARAM

    @override
    def get_ordering(
        self, request: Request, queryset: Any, view: Any
    ) -> tuple[str, ...] | list[str] | list[OrderBy] | None:
        terms = parse_order_by(
            request.query_params.get(self.ordering_param),
            allowed=[camelize_key(f) for f in self.get_valid_fields(queryset, view)],
        )
        if not terms:
            return self.get_default_ordering(view)  # pyright: ignore[reportUnknownMemberType]  # DRF stub
        return [
            F(underscore_key(t.field)).desc(nulls_last=True)
            if t.descending
            else F(underscore_key(t.field)).asc(nulls_last=True)
            for t in terms
        ]

    @override
    def get_valid_fields(
        self, queryset: Any, view: Any, context: Any = None
    ) -> list[str]:
        fields = getattr(view, "ordering_fields", None)
        return [str(f) for f in fields] if fields else []

    @override
    def get_schema_operation_parameters(self, view: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": self.ordering_param,
                "required": False,
                "in": "query",
                "description": (
                    "Sort order: a comma-separated list of fields, each optionally "
                    "followed by `asc` or `desc`, e.g. `team, score desc`."
                ),
                "schema": {"type": "string"},
            }
        ]


def _term(item: object) -> OrderField:
    """The wire term for an ordering expression built by :class:`OrderByFilter`."""
    expression = cast(OrderBy, item)
    return OrderField(
        camelize_key(str(cast(Any, expression.expression).name)),
        descending=expression.descending,
    )


def _default_terms(ordering: Sequence[Any], pk_name: str) -> list[OrderField]:
    """The terms of a view's default ordering strings, without the primary key."""
    terms: list[OrderField] = []
    for item in ordering:
        path = str(item).lstrip("-")
        if path not in ("pk", pk_name):
            terms.append(OrderField(camelize_key(path), str(item).startswith("-")))
    return terms


def _wire_value(value: object) -> SortValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return value.isoformat() if isinstance(value, date) else str(value)


def _row_value(row: object, path: str) -> object:
    """The value at a ``__``-separated field *path* of a model instance or mapping."""
    if isinstance(row, Mapping):
        return cast(Mapping[str, object], row).get(path)
    value: object = row
    for name in path.split("__"):
        value = None if value is None else getattr(value, name)
    return value


def _after(keys: Sequence[tuple[str, bool, bool]], values: Sequence[SortValue]) -> Q:
    """The rows past *values*: for some key, every earlier one equal and it beyond.

    Each key is ``(path, descending, is_pk)``. ``NULL`` sorts last, so a non-key
    value is followed by ``NULL`` rows, and nothing follows a ``NULL``.
    """
    arms: list[Q] = []
    for i, ((path, descending, is_pk), value) in enumerate(zip(keys, values)):
        if value is None:
            if is_pk:
                raise InvalidCursor("Malformed page token", error_code=400)
            continue
        beyond = Q(**{f"{path}__{'lt' if descending else 'gt'}": value})
        if not is_pk:
            beyond |= Q(**{f"{path}__isnull": True})
        for (earlier, _, _), v in zip(keys[:i], values[:i]):
            beyond &= Q(**{f"{earlier}__isnull": True} if v is None else {earlier: v})
        arms.append(beyond)
    after = arms[0]
    for arm in arms[1:]:
        after |= arm
    return after


class CursorPagination(drf_pagination.CursorPagination):
    """Keyset pagination emitting the AIP-158 envelope over the shared cursor codec.

    Rows are ordered by every ``orderBy`` term and then the primary key, so a
    field need not be unique or non-null. Without ``orderBy`` the view's default
    ordering supplies the terms. Pagination is forward-only. Invalid tokens raise :class:`rn_forge.web.InvalidCursor`.
    """

    cursor_query_param = DEFAULT_PAGE_TOKEN_PARAM
    ordering = "pk"
    page_size: int | None = None  # None defers to the settings facade
    max_page_size: int | None = None
    _order_by = ""
    _term_paths: tuple[str, ...] = ()
    _pk_name = "pk"

    @override
    def get_page_size(self, request: Request) -> int:
        return _page_size(
            request, page_size=self.page_size, max_page_size=self.max_page_size
        )

    # DRF's own keyset filter compares one position and skips ties with an offset
    # its cursor holds; the shared token has no offset, so this filters on the
    # whole order instead, which is what the SQLAlchemy stack does.
    @override
    def paginate_queryset(
        self, queryset: QuerySet[Any], request: Request, view: Any = None
    ) -> list[Any] | None:
        self.page_size = self.get_page_size(request)
        requested = self.get_ordering(request, queryset, view)  # pyright: ignore[reportUnknownMemberType]  # DRF stub
        pk_name = queryset.model._meta.pk.name
        terms = [_term(o) for o in requested if isinstance(o, OrderBy)]
        if not terms:
            terms = _default_terms(requested, pk_name)
        self._order_by = format_order_by(terms)
        self._pk_name = pk_name
        token = self._decode_token(request, terms)

        paths = [underscore_key(t.field) for t in terms]
        self._term_paths = tuple(paths)
        keys = [(p, t.descending) for p, t in zip(paths, terms)]
        if not keys:
            keys = [("pk", str(requested[0]).startswith("-"))]
        elif not any(p in ("pk", pk_name) for p, _ in keys):
            keys.append(("pk", keys[-1][1]))
        flagged = [(p, d, p in ("pk", pk_name)) for p, d in keys]
        self.ordering = tuple(
            ("-" if d else "") + p
            if is_pk
            else (F(p).desc(nulls_last=True) if d else F(p).asc(nulls_last=True))
            for p, d, is_pk in flagged
        )
        queryset = queryset.order_by(*self.ordering)
        if token is not None:
            values = [*token.sort_keys]
            if len(values) < len(keys):
                values.append(token.entity_id)
            try:
                queryset = queryset.filter(_after(flagged, values))
            except (ValueError, TypeError, DjangoValidationError) as exc:
                raise InvalidCursor("Malformed page token", error_code=400) from exc

        results = list(queryset[: self.page_size + 1])
        self.page = results[: self.page_size]
        self.has_next = len(results) > self.page_size
        return self.page

    def _decode_token(self, request: Request, terms: list[OrderField]) -> Cursor | None:
        raw = request.query_params.get(self.cursor_query_param)
        if raw is None:
            return None
        token = decode_cursor(raw)
        check_cursor_order(token, terms)
        return token

    def get_next_page_token(self) -> str | None:
        """Return the token for the page after this one, or ``None`` on the last."""
        if not self.has_next or not self.page:
            return None
        last = self.page[-1]
        sort_keys = tuple(_wire_value(_row_value(last, p)) for p in self._term_paths)
        entity_id = _row_value(last, "pk")
        if entity_id is None:
            entity_id = _row_value(last, self._pk_name)
        return encode_cursor(sort_keys, str(entity_id), self._order_by)

    @override
    def get_paginated_response(self, data: Any) -> Response:
        page = Page[Any](items=data, next_page_token=self.get_next_page_token())
        return Response(page.as_body())

    @override
    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["items", "nextPageToken"],
            "properties": {
                "items": schema,
                "nextPageToken": {
                    "type": "string",
                    "nullable": True,
                    "description": "Opaque; absent or null on the last page.",
                },
            },
        }

    @override
    def get_schema_operation_parameters(self, view: Any) -> list[dict[str, Any]]:
        conf = rnf_settings.rn_forge_django_settings.drf.pagination
        return [
            {
                "name": self.cursor_query_param,
                "required": False,
                "in": "query",
                "description": "The previous page's `nextPageToken`.",
                "schema": {"type": "string"},
            },
            {
                "name": conf.page_size_query_param,
                "required": False,
                "in": "query",
                "description": "Requested page size; clamped to the cap, never rejected.",
                "schema": {"type": "integer"},
            },
        ]


class LegacyPageNumberPagination(drf_pagination.PageNumberPagination):
    """Page-number pagination with DRF's standard envelope and a size cap."""

    page_size: int | None = None  # None defers to the settings facade
    page_size_query_param = "pageSize"
    max_page_size: int | None = None

    @override
    def get_page_size(self, request: Request) -> int:
        return _page_size(
            request, page_size=self.page_size, max_page_size=self.max_page_size
        )
