"""HTTP conformance cases for pagination behavior."""

from __future__ import annotations

from typing import Final

from rn_forge.web.conformance._shared import (
    _BOOKS_GET,
    _ITEMS_PATH,
    _JSON,
    _PROBLEM,
    PAGE_1_NEXT_TOKEN,
    _problem_body,
)
from rn_forge.web.conformance.types import ConformanceCase, RequestSpec
from rn_forge.web.pagination import encode_cursor
from rn_forge.web.problem import BAD_REQUEST

__all__ = ["PAGINATION_CASES"]

_ORDER_ID_DESC: Final = "id desc"

_PROFILE_PATH: Final = "/conformance/profiles/1"

_PROFILE_ADA: Final = {
    "id": "1",
    "displayName": "Ada",
    "address": {"city": "London", "postcode": "N1"},
    "phones": [{"kind": "home", "number": "1"}, {"kind": "work", "number": "2"}],
    "settings": {"theme": "dark"},
}

_PEOPLE_PATH: Final = "/conformance/people"

_ORDER_TEAM_SCORE_DESC: Final = "team,score desc"

ORDERED_PAGE_1_NEXT_TOKEN: Final = encode_cursor(("2",), "2", _ORDER_ID_DESC)
"""The deterministic token returned by the first ordered page."""

COMPOSITE_PAGE_1_TOKEN: Final = encode_cursor(("a", 10), "1", _ORDER_TEAM_SCORE_DESC)

COMPOSITE_PAGE_2_TOKEN: Final = encode_cursor(("b", 5), "4", _ORDER_TEAM_SCORE_DESC)

COMPOSITE_NULL_TOKEN: Final = encode_cursor(("a", None), "3", _ORDER_TEAM_SCORE_DESC)

_PEOPLE: Final = {
    1: ("a", 10),
    2: ("b", None),
    3: ("a", None),
    4: ("b", 5),
    5: ("a", 10),
}


def _people(*ids: int) -> list[dict[str, object]]:
    """The ``/conformance/people`` items with these ids, in this order."""
    return [{"id": str(i), "team": _PEOPLE[i][0], "score": _PEOPLE[i][1]} for i in ids]


PAGINATION_CASES: Final[tuple[ConformanceCase, ...]] = (
    ConformanceCase(
        id="pagination.first-page-carries-a-next-token",
        area="pagination",
        description="The AIP-158 envelope: items + nextPageToken, and totalSize absent by default.",
        request=RequestSpec("GET", _ITEMS_PATH, query={"pageSize": "2"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "1"}, {"id": "2"}],
            "nextPageToken": PAGE_1_NEXT_TOKEN,
        },
    ),
    ConformanceCase(
        id="pagination.last-page-has-a-null-next-token",
        area="pagination",
        description=(
            "nextPageToken is present and null on the last page rather than omitted, "
            "so a generated client's type does not change shape between pages."
        ),
        request=RequestSpec(
            "GET",
            _ITEMS_PATH,
            query={"pageSize": "2", "pageToken": PAGE_1_NEXT_TOKEN},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": [{"id": "3"}], "nextPageToken": None},
    ),
    ConformanceCase(
        id="pagination.oversized-page-size-is-clamped-not-rejected",
        area="pagination",
        description=(
            "AIP-158: coerce down to the maximum. A FastAPI Query(le=...) would 422 here, "
            "and that is the divergence this case exists to catch."
        ),
        request=RequestSpec("GET", _ITEMS_PATH, query={"pageSize": "1000"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "1"}, {"id": "2"}],
            "nextPageToken": PAGE_1_NEXT_TOKEN,
        },
    ),
    ConformanceCase(
        id="pagination.tampered-page-token-is-400",
        area="pagination",
        description="A malformed opaque token is InvalidCursor → 400, never a 500.",
        request=RequestSpec(
            "GET", _ITEMS_PATH, query={"pageToken": "!!!not-base64!!!"}
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "Malformed page token"),
    ),
    ConformanceCase(
        id="pagination.order-by-descending-binds-the-token",
        area="pagination",
        description=(
            "AIP-132: orderBy reorders the list, and the next token carries that "
            "order so it cannot be replayed under another."
        ),
        request=RequestSpec(
            "GET",
            _ITEMS_PATH,
            query={"pageSize": "2", "orderBy": _ORDER_ID_DESC},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [{"id": "3"}, {"id": "2"}],
            "nextPageToken": ORDERED_PAGE_1_NEXT_TOKEN,
        },
    ),
    ConformanceCase(
        id="pagination.order-by-unlisted-field-is-400",
        area="pagination",
        description="An orderBy field the endpoint does not list is a 400, never silently ignored.",
        request=RequestSpec("GET", _ITEMS_PATH, query={"orderBy": "secret"}),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "Cannot order by 'secret'; allowed: id"),
    ),
    ConformanceCase(
        id="pagination.order-by-several-fields-sorts-by-each-in-turn",
        area="pagination",
        description=(
            "AIP-132: orderBy is a comma-separated list; each term breaks the "
            "ties of the one before, with its own direction."
        ),
        request=RequestSpec(
            "GET",
            _PEOPLE_PATH,
            query={"orderBy": _ORDER_TEAM_SCORE_DESC, "pageSize": "5"},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": _people(5, 1, 3, 4, 2), "nextPageToken": None},
    ),
    ConformanceCase(
        id="pagination.nulls-sort-last-ascending",
        area="pagination",
        description="Rows whose value is null come after those that have one, ascending.",
        request=RequestSpec("GET", _PEOPLE_PATH, query={"orderBy": "score"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": _people(4, 1, 5, 2, 3), "nextPageToken": None},
    ),
    ConformanceCase(
        id="pagination.nulls-sort-last-descending",
        area="pagination",
        description="Rows whose value is null come after those that have one, descending too.",
        request=RequestSpec("GET", _PEOPLE_PATH, query={"orderBy": "score desc"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": _people(5, 1, 4, 3, 2), "nextPageToken": None},
    ),
    ConformanceCase(
        id="pagination.first-page-carries-a-composite-token",
        area="pagination",
        description=(
            "The token holds one sort value per orderBy term, so the next page "
            "can resume from the whole order."
        ),
        request=RequestSpec(
            "GET",
            _PEOPLE_PATH,
            query={"orderBy": _ORDER_TEAM_SCORE_DESC, "pageSize": "2"},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": _people(5, 1), "nextPageToken": COMPOSITE_PAGE_1_TOKEN},
    ),
    ConformanceCase(
        id="pagination.composite-token-resumes-within-a-tie",
        area="pagination",
        description="Rows tied on every term but the key are neither skipped nor repeated.",
        request=RequestSpec(
            "GET",
            _PEOPLE_PATH,
            query={
                "orderBy": _ORDER_TEAM_SCORE_DESC,
                "pageSize": "2",
                "pageToken": COMPOSITE_PAGE_1_TOKEN,
            },
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": _people(3, 4), "nextPageToken": COMPOSITE_PAGE_2_TOKEN},
    ),
    ConformanceCase(
        id="pagination.composite-token-resumes-after-a-null",
        area="pagination",
        description="A token whose last value is null resumes among the rows that are null there.",
        request=RequestSpec(
            "GET",
            _PEOPLE_PATH,
            query={
                "orderBy": _ORDER_TEAM_SCORE_DESC,
                "pageSize": "3",
                "pageToken": COMPOSITE_NULL_TOKEN,
            },
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"items": _people(4, 2), "nextPageToken": None},
    ),
    ConformanceCase(
        id="pagination.repeated-order-by-field-is-400",
        area="pagination",
        description="A field named twice in orderBy is a 400, never silently ignored.",
        request=RequestSpec("GET", _PEOPLE_PATH, query={"orderBy": "team,team desc"}),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "orderBy names 'team' more than once"),
    ),
    ConformanceCase(
        id="pagination.token-with-the-wrong-number-of-values-is-400",
        area="pagination",
        description="A token with fewer values than orderBy has terms is rejected as malformed.",
        request=RequestSpec(
            "GET",
            _PEOPLE_PATH,
            query={
                "orderBy": _ORDER_TEAM_SCORE_DESC,
                "pageToken": encode_cursor(("a",), "1", _ORDER_TEAM_SCORE_DESC),
            },
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "Malformed page token"),
    ),
    ConformanceCase(
        id="pagination.token-under-a-different-order-by-is-400",
        area="pagination",
        description="A token issued for the default order is rejected once orderBy changes.",
        request=RequestSpec(
            "GET",
            _ITEMS_PATH,
            query={"orderBy": _ORDER_ID_DESC, "pageToken": PAGE_1_NEXT_TOKEN},
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "pageToken does not match orderBy"),
    ),
    ConformanceCase(
        id="read-mask.get-returns-only-the-masked-fields",
        area="read-mask",
        description="AIP-157: readMask names top-level fields, and only those are returned.",
        request=RequestSpec(
            "GET", _PROFILE_PATH, query={"readMask": "displayName,settings"}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"displayName": "Ada", "settings": {"theme": "dark"}},
    ),
    ConformanceCase(
        id="read-mask.nested-path-selects-a-sub-field",
        area="read-mask",
        description="A dotted path selects one field of a declared object.",
        request=RequestSpec("GET", _PROFILE_PATH, query={"readMask": "address.city"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"address": {"city": "London"}},
    ),
    ConformanceCase(
        id="read-mask.path-through-a-list-applies-to-each-element",
        area="read-mask",
        description="A path through a list of objects applies to every element.",
        request=RequestSpec("GET", _PROFILE_PATH, query={"readMask": "phones.number"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"phones": [{"number": "1"}, {"number": "2"}]},
    ),
    ConformanceCase(
        id="read-mask.overlapping-paths-merge",
        area="read-mask",
        description="A path and one of its sub-paths merge to the whole object.",
        request=RequestSpec(
            "GET", _PROFILE_PATH, query={"readMask": "address,address.city"}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"address": {"city": "London", "postcode": "N1"}},
    ),
    ConformanceCase(
        id="read-mask.star-is-the-whole-resource",
        area="read-mask",
        description="A readMask of * returns the whole resource.",
        request=RequestSpec("GET", _PROFILE_PATH, query={"readMask": "*"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_PROFILE_ADA,
    ),
    ConformanceCase(
        id="read-mask.list-masks-each-item",
        area="read-mask",
        description="On a collection the mask applies to each item, and the page members stay.",
        request=RequestSpec(
            "GET", "/conformance/profiles", query={"readMask": "id,displayName"}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [
                {"id": "1", "displayName": "Ada"},
                {"id": "2", "displayName": "Grace"},
            ],
            "nextPageToken": None,
        },
    ),
    ConformanceCase(
        id="read-mask.unknown-path-is-400",
        area="read-mask",
        description="A path that names no declared field is a 400, never ignored.",
        request=RequestSpec("GET", _PROFILE_PATH, query={"readMask": "nickname"}),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(BAD_REQUEST, "Unknown readMask path 'nickname'"),
    ),
    ConformanceCase(
        id="read-mask.path-inside-a-free-form-field-is-400",
        area="read-mask",
        description="A free-form JSON field is a leaf: a path inside it names nothing declared.",
        request=RequestSpec("GET", _PROFILE_PATH, query={"readMask": "settings.theme"}),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            BAD_REQUEST, "Unknown readMask path 'settings.theme'"
        ),
    ),
    ConformanceCase(
        id="read-mask.star-with-other-paths-is-400",
        area="read-mask",
        description="* selects everything, so combining it with a path is a 400.",
        request=RequestSpec("GET", _PROFILE_PATH, query={"readMask": "*,displayName"}),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            BAD_REQUEST, "readMask '*' cannot be combined with other paths"
        ),
    ),
    ConformanceCase(
        id="read-mask.masked-read-keeps-the-etag",
        area="read-mask",
        description="A masked read carries the resource's ETag, so a client can follow with If-Match.",
        request=RequestSpec("GET", _PROFILE_PATH, query={"readMask": "displayName"}),
        expect_status=200,
        expect_headers={**_JSON, "ETag": 'W/"1:1"'},
        expect_body={"displayName": "Ada"},
    ),
    ConformanceCase(
        id="read-mask.batch-get-masks-each-item",
        area="read-mask",
        description="A :batchGet applies the mask to each resource.",
        request=RequestSpec("GET", _BOOKS_GET, query={"ids": "1", "readMask": "name"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"books": [{"name": "alpha"}]},
    ),
)
