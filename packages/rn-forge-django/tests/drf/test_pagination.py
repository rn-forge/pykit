from __future__ import annotations

import base64
import json
from itertools import permutations, product

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


class _Person(models.Model):
    team = models.CharField(max_length=10, null=True)
    score = models.IntegerField(null=True)

    class Meta:
        app_label = "rn_forge_django"


class _Author(models.Model):
    name = models.CharField(max_length=10, null=True)

    class Meta:
        app_label = "rn_forge_django"


class _Book(models.Model):
    author = models.ForeignKey(_Author, null=True, on_delete=models.CASCADE)

    class Meta:
        app_label = "rn_forge_django"


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_PagedRow, _Person, _Author, _Book)


@pytest.fixture
def rows(db):
    _PagedRow.objects.all().delete()
    return [_PagedRow.objects.create(pk=i, label=f"row-{i}") for i in range(1, 6)]


def _page(paginator, request):
    page = paginator.paginate_queryset(_PagedRow.objects.all(), request)
    data = [{"id": row.pk} for row in page]
    return json.loads(json.dumps(paginator.get_paginated_response(data).data))


def _paginate(request):
    return CursorPagination().paginate_queryset(_PagedRow.objects.all(), request)


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
        request = _request(pageToken="!!!")
        with pytest.raises(InvalidCursor):
            _paginate(request)

    def test_tampered_token_renders_as_a_400_problem(self) -> None:
        request = _request(pageToken="!!!")
        try:
            _paginate(request)
        except InvalidCursor as exc:
            response = problem_details_exception_handler(
                exc, {"request": request, "view": None}
            )
        assert response.status_code == 400

    def test_drf_encoded_cursor_is_rejected(self) -> None:
        drf_token = base64.b64encode(b"p=3").decode()
        request = _request(pageToken=drf_token)
        with pytest.raises(InvalidCursor):
            _paginate(request)


@pytest.mark.integration
class TestCursorEnvelope:
    def test_first_page_is_the_aip158_envelope(self, rows) -> None:
        paginator = CursorPagination()
        body = _page(paginator, _request(pageSize="2"))
        assert body == {
            "items": [{"id": 1}, {"id": 2}],
            "nextPageToken": encode_cursor((), "2"),
        }
        assert "totalSize" not in body

    def test_token_decodes_with_the_shared_codec(self, rows) -> None:
        body = _page(CursorPagination(), _request(pageSize="2"))
        cursor = decode_cursor(body["nextPageToken"])
        assert (cursor.sort_keys, cursor.entity_id) == ((), "2")

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
        request = _request(pageToken=body["nextPageToken"])
        with pytest.raises(InvalidCursor):
            self._ordered_page(request)

    def test_unlisted_field_is_rejected(self, rows) -> None:
        request = _request(orderBy="secret")
        with pytest.raises(InvalidOrderBy):
            self._ordered_page(request)


@pytest.mark.integration
class TestNonUniqueSortField:
    """Rows sharing a sort value are neither skipped nor repeated across pages."""

    @pytest.fixture
    def tied(self, db):
        _PagedRow.objects.all().delete()
        for pk, label in enumerate("bbbaabbb", start=1):
            _PagedRow.objects.create(pk=pk, label=label)

    def _walk(self, order_by: str, page_size: int) -> list[int]:
        seen: list[int] = []
        token = None
        while True:
            query = {"pageSize": str(page_size), "orderBy": order_by}
            if token:
                query["pageToken"] = token
            paginator = CursorPagination()
            page = paginator.paginate_queryset(
                _PagedRow.objects.all(), _request(**query), view=_OrderedView()
            )
            seen += [row.pk for row in page]
            token = paginator.get_next_page_token()
            if token is None:
                return seen

    @pytest.mark.parametrize("page_size", [1, 2, 3])
    def test_ascending_walk_visits_every_row_once_in_order(self, tied, page_size):
        assert self._walk("label", page_size) == [4, 5, 1, 2, 3, 6, 7, 8]

    @pytest.mark.parametrize("page_size", [1, 2, 3])
    def test_descending_walk_visits_every_row_once_in_order(self, tied, page_size):
        assert self._walk("label desc", page_size) == [8, 7, 6, 3, 2, 1, 5, 4]

    def test_token_value_that_does_not_fit_the_field_is_rejected(self, tied):
        token = encode_cursor(("not-a-number",), "1", "id")
        paginator = CursorPagination()
        queryset = _PagedRow.objects.all()
        request = _request(orderBy="id", pageToken=token)
        view = _OrderedView()
        with pytest.raises(InvalidCursor):
            paginator.paginate_queryset(queryset, request, view=view)


PEOPLE = [
    (1, "a", 10),
    (2, "b", None),
    (3, "a", None),
    (4, "b", 5),
    (5, "a", 10),
    (6, None, 7),
    (7, None, None),
    (8, "b", 5),
    (9, "a", 3),
    (10, None, 7),
]


class _PeopleView:
    filter_backends = (OrderByFilter,)
    ordering_fields = ("id", "team", "score")


class _DefaultOrderedView:
    filter_backends = (OrderByFilter,)
    ordering_fields = ("id", "team", "score")
    ordering = ("-score",)


class _BooksView:
    filter_backends = (OrderByFilter,)
    ordering_fields = ("id", "author__name")


def _walk_view(model, view, order_by: str, page_size: int) -> list[int]:
    seen: list[int] = []
    token = None
    while True:
        query = {"pageSize": str(page_size), "orderBy": order_by}
        if token:
            query["pageToken"] = token
        paginator = CursorPagination()
        page = paginator.paginate_queryset(
            model.objects.all(), _request(**query), view=view
        )
        seen += [row.pk for row in page]
        token = paginator.get_next_page_token()
        if token is None:
            return seen


def _unpaged(model, view, order_by: str) -> list[int]:
    request = _request(pageSize="100", orderBy=order_by)
    page = CursorPagination().paginate_queryset(model.objects.all(), request, view=view)
    return [row.pk for row in page]


def _expected_people(terms: tuple[tuple[str, bool], ...]) -> list[int]:
    """Independent oracle: stable sorts from the last term to the first, nulls last."""
    index = {"id": 0, "team": 1, "score": 2}
    keys = [(index[f], d) for f, d in terms]
    if not any(i == 0 for i, _ in keys):
        keys.append((0, keys[-1][1] if keys else False))
    rows = list(PEOPLE)
    for i, descending in reversed(keys):
        present = sorted(
            (r for r in rows if r[i] is not None),
            key=lambda r: r[i],
            reverse=descending,
        )
        rows = present + [r for r in rows if r[i] is None]
    return [r[0] for r in rows]


def _every_ordering():
    for count in range(1, 4):
        for fields in permutations(("team", "score", "id"), count):
            for directions in product((False, True), repeat=count):
                yield tuple(zip(fields, directions))


@pytest.fixture
def people(db):
    _Person.objects.all().delete()
    for pk, team, score in PEOPLE:
        _Person.objects.create(pk=pk, team=team, score=score)


@pytest.mark.integration
class TestSeveralTerms:
    """Paging every ordering concatenates to the one unpaged query's rows."""

    @pytest.mark.parametrize("page_size", [1, 3])
    def test_every_ordering_pages_to_the_unpaged_order(self, people, page_size):
        for terms in _every_ordering():
            order_by = ",".join(f"{f} desc" if d else f for f, d in terms)
            unpaged = _unpaged(_Person, _PeopleView(), order_by)
            assert unpaged == _expected_people(terms), order_by
            walked = _walk_view(_Person, _PeopleView(), order_by, page_size)
            assert walked == unpaged, order_by

    def test_token_after_a_null_resumes_among_the_nulls(self, people):
        order_by = "team,score desc"
        token = encode_cursor(("a", None), "3", order_by)
        paginator = CursorPagination()
        page = paginator.paginate_queryset(
            _Person.objects.all(),
            _request(pageSize="10", orderBy=order_by, pageToken=token),
            view=_PeopleView(),
        )
        assert [row.pk for row in page] == [8, 4, 2, 10, 6, 7]

    def test_token_carries_one_value_per_term_with_null(self, people):
        paginator = CursorPagination()
        paginator.paginate_queryset(
            _Person.objects.all(),
            _request(pageSize="4", orderBy="team,score desc"),
            view=_PeopleView(),
        )
        cursor = decode_cursor(paginator.get_next_page_token())
        assert cursor.sort_keys == ("a", None)
        assert (cursor.entity_id, cursor.order_by) == ("3", "team,score desc")

    def test_token_with_the_wrong_number_of_values_is_rejected(self, people):
        token = encode_cursor(("a",), "1", "team,score desc")
        request = _request(orderBy="team,score desc", pageToken=token)
        with pytest.raises(InvalidCursor):
            CursorPagination().paginate_queryset(
                _Person.objects.all(), request, view=_PeopleView()
            )

    @pytest.mark.parametrize("keys", [("x",), (None,)], ids=["str", "null-key"])
    def test_value_that_does_not_fit_the_field_is_rejected(self, people, keys):
        field = "id" if keys == (None,) else "score"
        token = encode_cursor(keys, "1", field)
        request = _request(orderBy=field, pageToken=token)
        with pytest.raises(InvalidCursor):
            CursorPagination().paginate_queryset(
                _Person.objects.all(), request, view=_PeopleView()
            )

    def test_repeated_field_is_rejected(self, people):
        with pytest.raises(InvalidOrderBy):
            _unpaged(_Person, _PeopleView(), "team,team desc")

    @pytest.mark.parametrize("page_size", [1, 2, 3])
    def test_a_non_pk_default_ordering_is_honoured_without_order_by(
        self, people, page_size
    ):
        seen: list[int] = []
        token = None
        while True:
            query = {
                "pageSize": str(page_size),
                **({"pageToken": token} if token else {}),
            }
            paginator = CursorPagination()
            page = paginator.paginate_queryset(
                _Person.objects.all(), _request(**query), view=_DefaultOrderedView()
            )
            seen += [row.pk for row in page]
            token = paginator.get_next_page_token()
            if token is None:
                break
            assert decode_cursor(token).order_by == "score desc"
        assert seen == _expected_people((("score", True),))

    def test_a_related_lookup_pages_with_nulls_last(self, db):
        _Book.objects.all().delete()
        _Author.objects.all().delete()
        authors = {n: _Author.objects.create(name=n) for n in ("x", "y", None)}
        for pk, name in enumerate(["y", None, "x", "y", None, "x"], start=1):
            _Book.objects.create(pk=pk, author=authors[name])
        for order_by, expected in [
            ("author__name", [3, 6, 1, 4, 2, 5]),
            ("author__name desc", [4, 1, 6, 3, 5, 2]),
        ]:
            assert _unpaged(_Book, _BooksView(), order_by) == expected
            for size in (1, 2, 4):
                walked = _walk_view(_Book, _BooksView(), order_by, size)
                assert walked == expected, (order_by, size)

    def test_the_openapi_description_names_a_comma_separated_list(self):
        (parameter,) = OrderByFilter().get_schema_operation_parameters(_PeopleView())
        assert "comma-separated list" in parameter["description"]
