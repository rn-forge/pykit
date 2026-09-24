from __future__ import annotations

import base64
import json

import pytest

rest_framework = pytest.importorskip("rest_framework")

from django.db import models  # noqa: E402
from django.test import override_settings  # noqa: E402
from rest_framework.request import Request  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.drf.exceptions import problem_details_exception_handler  # noqa: E402
from rn_forge.django.drf.pagination import (  # noqa: E402
    CursorPagination,
    LegacyPageNumberPagination,
    OrderByFilter,
)
from rn_forge.web import InvalidCursor, InvalidOrderBy, decode_cursor, encode_cursor  # noqa: E402


class _PagedRow(models.Model):
    label = models.CharField(max_length=20)

    class Meta:
        app_label = "rn_forge_django"


def _request(**query: str) -> Request:
    return Request(APIRequestFactory().get("/rows/", query))


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_PagedRow)


@pytest.fixture
def rows(db):
    _PagedRow.objects.all().delete()
    return [_PagedRow.objects.create(pk=i, label=f"row-{i}") for i in range(1, 6)]


def _page(paginator, request):
    page = paginator.paginate_queryset(_PagedRow.objects.all(), request)
    data = [{"id": row.pk} for row in page]
    return json.loads(json.dumps(paginator.get_paginated_response(data).data))


@pytest.mark.unit
class TestPageSize:
    def test_cursor_defaults_come_from_settings(self) -> None:
        assert CursorPagination().get_page_size(_request()) == 50

    def test_legacy_defaults_come_from_settings(self) -> None:
        assert LegacyPageNumberPagination().get_page_size(_request()) == 50

    @pytest.mark.parametrize("cls", [CursorPagination, LegacyPageNumberPagination])
    def test_over_large_page_size_is_clamped_not_rejected(self, cls) -> None:
        assert cls().get_page_size(_request(pageSize="100000")) == 200

    @pytest.mark.parametrize("cls", [CursorPagination, LegacyPageNumberPagination])
    def test_page_size_query_param_is_honoured(self, cls) -> None:
        assert cls().get_page_size(_request(pageSize="7")) == 7

    @pytest.mark.parametrize("cls", [CursorPagination, LegacyPageNumberPagination])
    def test_settings_override_takes_effect_at_request_time(self, cls) -> None:
        paginator = cls()
        with override_settings(
            RN_FORGE_DJANGO={
                "DRF": {
                    "PAGINATION": {
                        "PAGE_SIZE": 3,
                        "PAGE_SIZE_QUERY_PARAM": "limit",
                        "MAX_PAGE_SIZE": 5,
                    }
                }
            }
        ):
            assert paginator.get_page_size(_request()) == 3
            assert paginator.get_page_size(_request(limit="9")) == 5
            assert paginator.get_page_size(_request(pageSize="4")) == 3
        assert paginator.get_page_size(_request()) == 50

    def test_subclass_attributes_win_over_settings(self) -> None:
        class Small(CursorPagination):
            page_size = 2
            max_page_size = 2

        assert Small().get_page_size(_request(pageSize="9")) == 2


@pytest.mark.unit
class TestTokens:
    def test_tampered_token_raises_invalid_cursor(self) -> None:
        with pytest.raises(InvalidCursor):
            CursorPagination().decode_cursor(_request(pageToken="!!!"))

    def test_tampered_token_renders_as_a_400_problem(self) -> None:
        request = _request(pageToken="!!!")
        try:
            CursorPagination().decode_cursor(request)
        except InvalidCursor as exc:
            response = problem_details_exception_handler(
                exc, {"request": request, "view": None}
            )
        assert response.status_code == 400

    def test_drf_encoded_cursor_is_rejected(self) -> None:
        drf_token = base64.b64encode(b"p=3").decode()
        with pytest.raises(InvalidCursor):
            CursorPagination().decode_cursor(_request(pageToken=drf_token))


@pytest.mark.integration
class TestCursorEnvelope:
    def test_first_page_is_the_aip158_envelope(self, rows) -> None:
        paginator = CursorPagination()
        body = _page(paginator, _request(pageSize="2"))
        assert body == {
            "items": [{"id": 1}, {"id": 2}],
            "nextPageToken": encode_cursor("2", "2"),
        }
        assert "totalSize" not in body

    def test_token_decodes_with_the_shared_codec(self, rows) -> None:
        body = _page(CursorPagination(), _request(pageSize="2"))
        cursor = decode_cursor(body["nextPageToken"])
        assert (cursor.sort_key, cursor.entity_id) == ("2", "2")

    def test_pages_walk_to_a_null_token(self, rows) -> None:
        seen: list[int] = []
        token = None
        for _ in range(5):
            query = {"pageSize": "2", **({"pageToken": token} if token else {})}
            body = _page(CursorPagination(), _request(**query))
            seen += [item["id"] for item in body["items"]]
            token = body["nextPageToken"]
            if token is None:
                break
        assert seen == [1, 2, 3, 4, 5]
        assert token is None

    def test_over_large_page_size_returns_the_capped_page(self, rows) -> None:
        class Capped(CursorPagination):
            max_page_size = 3

        body = _page(Capped(), _request(pageSize="1000"))
        assert len(body["items"]) == 3

    def test_no_previous_token_is_emitted(self, rows) -> None:
        body = _page(CursorPagination(), _request(pageSize="2"))
        assert set(body) == {"items", "nextPageToken"}


class _OrderedView:
    filter_backends = (OrderByFilter,)
    ordering_fields = ("id", "label")


@pytest.mark.integration
class TestOrderBy:
    def _ordered_page(self, request):
        paginator = CursorPagination()
        page = paginator.paginate_queryset(
            _PagedRow.objects.all(), request, view=_OrderedView()
        )
        data = [{"id": row.pk} for row in page]
        return json.loads(json.dumps(paginator.get_paginated_response(data).data))

    def test_descending_order_and_token_binds_it(self, rows) -> None:
        body = self._ordered_page(_request(pageSize="2", orderBy="id desc"))
        assert body["items"] == [{"id": 5}, {"id": 4}]
        assert decode_cursor(body["nextPageToken"]).order_by == "id desc"
        follow = self._ordered_page(
            _request(pageSize="2", orderBy="id desc", pageToken=body["nextPageToken"])
        )
        assert follow["items"] == [{"id": 3}, {"id": 2}]

    def test_token_with_a_different_order_is_rejected(self, rows) -> None:
        body = self._ordered_page(_request(pageSize="2", orderBy="id desc"))
        with pytest.raises(InvalidCursor):
            self._ordered_page(_request(pageToken=body["nextPageToken"]))

    def test_unlisted_field_is_rejected(self, rows) -> None:
        with pytest.raises(InvalidOrderBy):
            self._ordered_page(_request(orderBy="secret"))
