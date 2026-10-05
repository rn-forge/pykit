"""Tests for tabular negotiation, Content-Disposition and the transfer wire shapes."""

import pytest
from assertpy import assert_that

from rn_forge.web.conformance import case_by_id
from rn_forge.web.exceptions import InvalidBatchGet, ItemsDenied, RowsInvalid
from rn_forge.web.problem import ProblemResponse, default_registry, render_problem
from rn_forge.web.transfer import (
    DUPLICATE_ID_DETAIL,
    NON_EMPTY_IDS_DETAIL,
    NON_EMPTY_LIST_DETAIL,
    TABULAR_FORMATS,
    BatchUpdateItem,
    ImportCounts,
    RowError,
    batch_get_ids,
    content_disposition,
    export_cap_problem,
    import_report_body,
    negotiate_tabular_format,
    parse_batch_update,
    parse_flag,
    row_cap_problem,
    row_errors_problem,
    unreadable_file_detail,
    unsupported_file_detail,
)

pytestmark = pytest.mark.unit

XLSX = TABULAR_FORMATS["xlsx"].media_type


@pytest.mark.parametrize(
    ("accept", "param", "expected"),
    [
        ("text/csv", None, "csv"),
        (XLSX, None, "xlsx"),
        ("text/csv;q=0.5, " + XLSX, None, "xlsx"),
        ("text/csv, application/json", None, None),
        ("application/json, text/csv;q=0.5", None, None),
        ("text/csv, */*;q=0.1", None, "csv"),
        ("*/*", None, None),
        ("text/csv;q=0", None, None),
        (None, None, None),
        ("application/json", "xlsx", "xlsx"),
        ("text/csv", "XLSX", "xlsx"),
        (None, "ods", None),
        (None, "bogus", None),
        ("TEXT/CSV", None, "csv"),
    ],
)
def test_negotiation(accept, param, expected):
    result = negotiate_tabular_format(accept, param, ["csv", "xlsx"])
    assert_that(result.extension if result else None).is_equal_to(expected)


def test_a_malformed_q_value_excludes_the_range():
    assert_that(negotiate_tabular_format("text/csv;q=x", None, ["csv"])).is_none()


def test_content_disposition_ascii():
    assert_that(content_disposition("orders.csv")).is_equal_to(
        "attachment; filename=\"orders.csv\"; filename*=UTF-8''orders.csv"
    )


def test_content_disposition_non_ascii_and_unsafe_characters():
    value = content_disposition('a/b"é\n.csv')
    assert_that(value).is_equal_to(
        "attachment; filename=\"ab'__.csv\"; filename*=UTF-8''ab%22%C3%A9%0A.csv"
    )


def test_import_report_body():
    assert_that(
        import_report_body(created=1, updated=2, skipped=3, validate_only=False)
    ).is_equal_to({"created": 1, "updated": 2, "skipped": 3, "validateOnly": False})


def test_row_errors_problem_points_at_the_cell():
    response = row_errors_problem(
        [RowError(12, "Quantity", "bad"), RowError(3, "", "row bad")],
        instance="/orders:import",
    )
    assert_that(response.status).is_equal_to(422)
    assert_that(response.body["errors"]).is_equal_to(
        [
            {"pointer": "/rows/12/Quantity", "detail": "bad"},
            {"pointer": "/rows/3", "detail": "row bad"},
        ]
    )


def test_row_errors_problem_root_and_escaping():
    response = row_errors_problem(
        [RowError(3, "a/b", "bad")], instance="/x", root="requests"
    )
    assert_that(response.body["errors"][0]["pointer"]).is_equal_to("/requests/3/a~1b")


def test_export_cap_problem_matches_the_conformance_case():
    response = export_cap_problem(1, instance="/orders")
    assert_that(response.status).is_equal_to(422)
    assert_that(response.body["type"]).is_equal_to("about:blank")
    assert_that(response.body["detail"]).is_equal_to(
        case_by_id("transfer.export-over-the-cap-is-422").expect_body["detail"]
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("0", False),
        ("yes", False),
        ("", False),
        (None, False),
    ],
)
def test_parse_flag(value: str | None, expected: bool) -> None:
    assert_that(parse_flag(value)).is_equal_to(expected)


@pytest.mark.parametrize("kind", ["import", "batch"])
def test_row_cap_problem_names_kind_and_cap_without_errors(kind: str) -> None:
    body = row_cap_problem(kind, 5, instance="/x").body  # type: ignore[arg-type]

    assert_that(body["status"]).is_equal_to(422)
    assert_that(body["detail"]).is_equal_to(f"The {kind} exceeds the limit of 5 rows.")
    assert_that(body).does_not_contain_key("errors")


def test_file_details_and_import_counts() -> None:
    assert_that(unsupported_file_detail(("csv", "xlsx"))).is_equal_to(
        "Unsupported file type; use one of: csv, xlsx."
    )
    assert_that(unreadable_file_detail("csv")).is_equal_to(
        "The file could not be read as csv."
    )
    assert_that(NON_EMPTY_LIST_DETAIL).is_equal_to("A non-empty list is required.")
    assert_that(ImportCounts(1, 2, 3).updated).is_equal_to(2)


def test_rows_invalid_renders_as_row_errors_problem() -> None:
    errors = [RowError(2, "Quantity", "bad"), RowError(3, "", "whole row")]

    rendered = render_problem(
        default_registry(), RowsInvalid(errors, root="requests"), instance="/x"
    )

    expected = row_errors_problem(errors, instance="/x", root="requests")
    assert_that(rendered.body).is_equal_to(expected.body)
    assert_that(rendered.status).is_equal_to(422)
    assert_that(rendered.body["errors"][0]["pointer"]).is_equal_to(
        "/requests/2/Quantity"
    )


def test_items_denied_renders_a_403_with_pointers() -> None:
    exc = ItemsDenied({"1": ["nope"], 2: {"name": ["bad"]}}, root="requests")

    rendered = render_problem(default_registry(), exc, instance="/x")

    assert_that(rendered.status).is_equal_to(403)
    assert_that(rendered.body["type"]).is_equal_to("about:blank")
    assert_that(rendered.body["detail"]).is_equal_to("Forbidden")
    assert_that(rendered.body["errors"]).is_equal_to(
        [
            {"pointer": "/requests/1", "detail": "nope"},
            {"pointer": "/requests/2/name", "detail": "bad"},
        ]
    )


# --- :batchGet and :batchUpdate ------------------------------------------


def test_batch_get_ids_drops_empty_values_and_keeps_order_and_duplicates() -> None:
    assert_that(batch_get_ids(["3", "", "1", "3"], cap=None)).is_equal_to(
        ["3", "1", "3"]
    )


def test_batch_get_ids_does_not_split_a_comma_joined_value() -> None:
    assert_that(batch_get_ids(["1,2"], cap=5)).is_equal_to(["1,2"])


@pytest.mark.parametrize("values", [[], [""], ["", ""]])
def test_batch_get_ids_requires_a_non_empty_value(values: list[str]) -> None:
    with pytest.raises(InvalidBatchGet) as raised:
        batch_get_ids(values, cap=None)

    rendered = render_problem(default_registry(), raised.value, instance="/x")
    assert_that(rendered.status).is_equal_to(400)
    assert_that(rendered.body["detail"]).is_equal_to(NON_EMPTY_IDS_DETAIL)


def test_batch_get_ids_over_the_cap_is_a_400() -> None:
    with pytest.raises(InvalidBatchGet) as raised:
        batch_get_ids(["1", "2"], cap=1)

    rendered = render_problem(default_registry(), raised.value, instance="/x")
    assert_that(rendered.status).is_equal_to(400)
    assert_that(rendered.body["detail"]).is_equal_to(
        "The batch exceeds the limit of 1 rows."
    )


def test_batch_get_ids_at_the_cap_passes() -> None:
    assert_that(batch_get_ids(["1", "2"], cap=2)).is_equal_to(["1", "2"])


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({}, "This field is required."),
        ("not an object", "This field is required."),
        ({"requests": []}, NON_EMPTY_LIST_DETAIL),
        ({"requests": "x"}, NON_EMPTY_LIST_DETAIL),
        ({"requests": None}, NON_EMPTY_LIST_DETAIL),
    ],
)
def test_parse_batch_update_requires_a_non_empty_list(
    body: object, detail: str
) -> None:
    result = parse_batch_update(body, cap=None, instance="/x")

    assert_that(result).is_instance_of(ProblemResponse)
    assert_that(result.status).is_equal_to(422)
    assert_that(result.body["errors"]).is_equal_to(
        [{"pointer": "/requests", "detail": detail}]
    )


def test_parse_batch_update_over_the_cap_is_the_row_cap_problem() -> None:
    body = {"requests": [{"id": "1", "patch": {}}, {"id": "2", "patch": {}}]}

    result = parse_batch_update(body, cap=1, instance="/x")

    assert_that(result.status).is_equal_to(422)
    assert_that(result.body["detail"]).is_equal_to(
        row_cap_problem("batch", 1, instance="/x").body["detail"]
    )
    assert_that(result.body).does_not_contain_key("errors")


def test_parse_batch_update_returns_items_in_order_with_ids_as_strings() -> None:
    body = {
        "requests": [
            {"id": 2, "patch": {"name": "b"}, "ifMatch": 'W/"2:1"'},
            {"id": "3", "patch": {"note": None}},
            {"id": "4", "patch": {}, "ifMatch": None},
        ]
    }

    result = parse_batch_update(body, cap=3, instance="/x")

    assert_that(result).is_equal_to(
        [
            BatchUpdateItem(0, "2", {"name": "b"}, 'W/"2:1"'),
            BatchUpdateItem(1, "3", {"note": None}, None),
            BatchUpdateItem(2, "4", {}, None),
        ]
    )


def test_parse_batch_update_reports_every_malformed_item() -> None:
    body = {
        "requests": [
            {"patch": {}},
            {"id": "2", "patch": [1]},
            {"id": "3", "patch": {}, "ifMatch": 5},
            "not an object",
            {"id": True, "patch": {}},
            {"id": "6", "patch": {}},
        ]
    }

    with pytest.raises(RowsInvalid) as raised:
        parse_batch_update(body, cap=None, instance="/x")

    rendered = render_problem(default_registry(), raised.value, instance="/x")
    assert_that(rendered.status).is_equal_to(422)
    assert_that(rendered.body["detail"]).is_equal_to("One or more rows are invalid.")
    assert_that(rendered.body["errors"]).is_equal_to(
        [
            {"pointer": "/requests/0/id", "detail": "This field is required."},
            {
                "pointer": "/requests/1/patch",
                "detail": "A merge patch must be a JSON object.",
            },
            {"pointer": "/requests/2/ifMatch", "detail": "Not a valid string."},
            {"pointer": "/requests/3/id", "detail": "This field is required."},
            {
                "pointer": "/requests/3/patch",
                "detail": "A merge patch must be a JSON object.",
            },
            {"pointer": "/requests/4/id", "detail": "This field is required."},
        ]
    )


def test_parse_batch_update_reports_each_later_duplicate_id() -> None:
    body = {
        "requests": [
            {"id": "1", "patch": {}},
            {"id": 1, "patch": {}},
            {"id": "2", "patch": {}},
            {"id": "1", "patch": {}},
        ]
    }

    with pytest.raises(RowsInvalid) as raised:
        parse_batch_update(body, cap=None, instance="/x")

    rendered = render_problem(default_registry(), raised.value, instance="/x")
    assert_that(rendered.body["errors"]).is_equal_to(
        [
            {"pointer": "/requests/1/id", "detail": DUPLICATE_ID_DETAIL},
            {"pointer": "/requests/3/id", "detail": DUPLICATE_ID_DETAIL},
        ]
    )


def test_parse_batch_update_checks_shape_before_duplicates() -> None:
    body = {"requests": [{"id": "1", "patch": {}}, {"id": "1", "patch": 3}]}

    with pytest.raises(RowsInvalid) as raised:
        parse_batch_update(body, cap=None, instance="/x")

    assert_that([e.field for e in raised.value.errors]).is_equal_to(["patch"])
