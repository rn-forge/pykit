"""Tests for tabular negotiation, Content-Disposition and the transfer wire shapes."""

import pytest
from assertpy import assert_that

from rn_forge.web.conformance import case_by_id
from rn_forge.web.transfer import (
    TABULAR_FORMATS,
    RowError,
    content_disposition,
    export_cap_problem,
    import_report_body,
    negotiate_tabular_format,
    row_errors_problem,
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
