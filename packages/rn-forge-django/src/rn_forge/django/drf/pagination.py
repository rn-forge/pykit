"""AIP-158 cursor pagination and legacy page-number pagination for DRF."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast, override

from rest_framework import pagination as drf_pagination
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.commons.exceptions import AppException
from rn_forge.django import settings as rnf_settings
from rn_forge.web import (
    DEFAULT_PAGE_TOKEN_PARAM,
    Page,
    clamp_page_size,
    decode_cursor,
    encode_cursor,
)

__all__ = ["CursorPagination", "LegacyPageNumberPagination"]


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


class CursorPagination(drf_pagination.CursorPagination):
    """Keyset pagination emitting the AIP-158 envelope over the shared cursor codec.

    Pagination is forward-only and the first ordering field must be unique.
    Invalid tokens raise :class:`rn_forge.web.InvalidCursor`.
    """

    cursor_query_param = DEFAULT_PAGE_TOKEN_PARAM
    ordering = "pk"
    page_size: int | None = None  # None defers to the settings facade
    max_page_size: int | None = None

    @override
    def get_page_size(self, request: Request) -> int:
        return _page_size(
            request, page_size=self.page_size, max_page_size=self.max_page_size
        )

    @override
    def decode_cursor(self, request: Request) -> drf_pagination.Cursor | None:
        raw = request.query_params.get(self.cursor_query_param)
        if raw is None:
            return None
        token = decode_cursor(raw)
        return drf_pagination.Cursor(offset=0, reverse=False, position=token.sort_key)

    def get_next_page_token(self) -> str | None:
        """Return the token for the page after this one, or ``None`` on the last."""
        # DRF sets these in paginate_queryset and its stubs leave them untyped.
        has_next = cast(bool, self.has_next)  # pyright: ignore[reportUnknownMemberType]
        page = cast(list[object], self.page)  # pyright: ignore[reportUnknownMemberType]
        if not has_next or not page:
            return None
        next_position = cast(str | None, self.next_position)  # pyright: ignore[reportUnknownMemberType]
        last = page[-1]
        position: str = self._get_position_from_instance(last, self.ordering)  # pyright: ignore[reportUnknownMemberType]
        AppException.check(
            position != next_position,
            "Cursor pagination needs a unique first ordering field; {} repeats {!r}",
            self.ordering[0],
            position,
        )
        entity_id = (
            cast(Mapping[str, object], last).get("pk", position)
            if isinstance(last, Mapping)
            else getattr(last, "pk", position)
        )
        return encode_cursor(position, str(entity_id))

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
