"""AIP-158 cursor pagination and legacy page-number pagination for DRF."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast, override

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, QuerySet
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
    ``snake_case`` names. An unlisted or malformed term raises
    :class:`rn_forge.web.InvalidOrderBy`, as does more than one term.
    """

    ordering_param = ORDER_BY_PARAM

    @override
    def get_ordering(
        self, request: Request, queryset: Any, view: Any
    ) -> tuple[str, ...] | list[str] | None:
        terms = parse_order_by(
            request.query_params.get(self.ordering_param),
            allowed=[camelize_key(f) for f in self.get_valid_fields(queryset, view)],
        )
        if not terms:
            return self.get_default_ordering(view)  # pyright: ignore[reportUnknownMemberType]  # DRF stub
        return [
            f"-{underscore_key(t.field)}" if t.descending else underscore_key(t.field)
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
                "description": "Sort order: one field, e.g. `displayName desc`.",
                "schema": {"type": "string"},
            }
        ]


def _order_terms(request: Request, ordering: list[str]) -> list[OrderField]:
    """The request's explicit ordering as wire terms; empty when ``orderBy`` is absent."""
    if ORDER_BY_PARAM not in request.query_params:
        return []
    return [
        OrderField(camelize_key(f.lstrip("-")), descending=f.startswith("-"))
        for f in ordering
    ]


class CursorPagination(drf_pagination.CursorPagination):
    """Keyset pagination emitting the AIP-158 envelope over the shared cursor codec.

    Rows are ordered by the first ``orderBy`` field and then the primary key, so
    the field need not be unique. Pagination is forward-only. Invalid tokens raise
    :class:`rn_forge.web.InvalidCursor`.
    """

    cursor_query_param = DEFAULT_PAGE_TOKEN_PARAM
    ordering = "pk"
    page_size: int | None = None  # None defers to the settings facade
    max_page_size: int | None = None
    _order_by = ""

    @override
    def get_page_size(self, request: Request) -> int:
        return _page_size(
            request, page_size=self.page_size, max_page_size=self.max_page_size
        )

    # DRF's own keyset filter compares one position and skips ties with an offset
    # its cursor holds; the shared token has no offset, so this filters on
    # (sort field, pk) instead, which is what the SQLAlchemy stack does.
    @override
    def paginate_queryset(
        self, queryset: QuerySet[Any], request: Request, view: Any = None
    ) -> list[Any] | None:
        self.page_size = self.get_page_size(request)
        requested = self.get_ordering(request, queryset, view)  # pyright: ignore[reportUnknownMemberType]  # DRF stub
        terms = _order_terms(request, list(requested))
        self._order_by = format_order_by(terms)
        token = self._decode_token(request, terms)

        sort = requested[0]
        field, descending = sort.lstrip("-"), sort.startswith("-")
        unique = field in ("pk", queryset.model._meta.pk.name)
        self.ordering = (sort,) if unique else (sort, "-pk" if descending else "pk")
        queryset = queryset.order_by(*self.ordering)
        if token is not None:
            beyond = "lt" if descending else "gt"
            after = Q(**{f"{field}__{beyond}": token.sort_key})
            if not unique:
                after |= Q(**{field: token.sort_key, f"pk__{beyond}": token.entity_id})
            try:
                queryset = queryset.filter(after)
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
        position: str = self._get_position_from_instance(last, self.ordering)  # pyright: ignore[reportUnknownMemberType]
        entity_id = (
            cast(Mapping[str, object], last).get("pk", position)
            if isinstance(last, Mapping)
            else getattr(last, "pk", position)
        )
        return encode_cursor(position, str(entity_id), self._order_by)

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
