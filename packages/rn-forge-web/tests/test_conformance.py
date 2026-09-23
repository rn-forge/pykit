"""Tests for the conformance table itself.

Trivial assertions, and still worth having: they are what makes deleting a
section of coverage fail rather than pass quietly.
"""

import pytest
from assertpy import assert_that

from rn_forge.web.conformance import (
    CASES,
    REDACTED,
    VARIABLE_MEMBERS,
    cases_for,
    redact,
)

pytestmark = pytest.mark.unit

AREAS = (
    "problem",
    "concurrency",
    "pagination",
    "idempotency",
    "health",
    "auth",
    "casing",
    "correlation",
    "deprecation",
    "discovery",
    "security",
    "cors",
)


def test_the_table_is_not_empty():
    assert_that(CASES).is_not_empty()


def test_every_id_is_unique():
    ids = [case.id for case in CASES]
    assert_that(sorted(ids)).is_equal_to(sorted(set(ids)))


@pytest.mark.parametrize("area", AREAS)
def test_every_area_has_at_least_one_case(area):
    """Every area named in ConformanceArea needs at least one case."""
    assert_that(cases_for(area)).described_as(area).is_not_empty()


def test_cases_for_returns_only_that_area():
    for case in cases_for("auth"):
        assert_that(case.area).is_equal_to("auth")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_case_is_well_formed(case):
    assert_that(case.id).is_not_empty()
    assert_that(case.description).is_not_empty()
    assert_that(case.request.path).starts_with("/")
    assert_that(case.request.method).is_in("GET", "POST", "PATCH", "PUT", "DELETE")
    assert_that(case.expect_status).is_between(100, 599)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_expectation_survives_redaction_idempotently(case):
    once = redact(case.expect_body)
    assert_that(redact(once)).is_equal_to(once)
    assert_that(once).is_equal_to(dict(case.expect_body))


def test_redact_blanks_every_variable_member():
    body = {name: "actual" for name in VARIABLE_MEMBERS}
    assert_that(redact(body)).is_equal_to({name: REDACTED for name in VARIABLE_MEMBERS})


def test_redact_leaves_contract_members_alone():
    assert_that(redact({"status": 409, "title": "Conflict"})).is_equal_to(
        {"status": 409, "title": "Conflict"}
    )


def test_redact_recurses_into_nested_mappings():
    assert_that(redact({"outer": {"instance": "/x", "keep": 1}})).is_equal_to(
        {"outer": {"instance": REDACTED, "keep": 1}}
    )


def test_redact_recurses_into_lists_of_mappings():
    assert_that(redact({"items": [{"instance": "/x"}, {"keep": 1}]})).is_equal_to(
        {"items": [{"instance": REDACTED}, {"keep": 1}]}
    )


def test_redact_leaves_lists_of_scalars_alone():
    assert_that(redact({"tags": ["a", "b"]})).is_equal_to({"tags": ["a", "b"]})


def test_the_403_case_asserts_the_absence_of_a_challenge():
    """The negative half of the auth contract; no positive assertion catches it."""
    case = next(c for c in CASES if c.expect_status == 403)
    assert_that(case.expect_absent_headers).contains("WWW-Authenticate")


def test_the_401_case_carries_the_rfc6750_challenge():
    case = next(c for c in CASES if c.expect_status == 401)
    assert_that(case.expect_headers["WWW-Authenticate"]).starts_with("Bearer ")


PROBLEM_CASES = tuple(
    case
    for case in CASES
    if case.expect_headers.get("Content-Type") == "application/problem+json"
)


def test_every_case_declares_a_content_type():
    """304 is the one status RFC 9110 §15.4.5 forbids a body, hence a type, for."""
    for case in CASES:
        if case.expect_status == 304:
            continue
        assert_that(case.expect_headers).described_as(case.id).contains_key(
            "Content-Type"
        )


def test_every_failure_is_a_problem_body_except_the_readiness_verdict():
    """A 503 from /readyz is the endpoint's normal representation, not an error."""
    for case in CASES:
        if case.expect_status >= 400 and case.area != "health":
            assert_that(case.expect_headers["Content-Type"]).described_as(
                case.id
            ).is_equal_to("application/problem+json")


@pytest.mark.parametrize("case", PROBLEM_CASES, ids=lambda c: c.id)
def test_every_problem_body_carries_the_five_rfc9457_core_members(case):
    assert_that(set(case.expect_body)).contains(
        "type", "title", "status", "detail", "instance"
    )


@pytest.mark.parametrize("case", PROBLEM_CASES, ids=lambda c: c.id)
def test_every_problem_body_status_matches_its_http_status(case):
    assert_that(case.expect_body["status"]).is_equal_to(case.expect_status)


@pytest.mark.parametrize("case", PROBLEM_CASES, ids=lambda c: c.id)
def test_every_problem_body_carries_the_correlation_extension(case):
    """A user-reported error id is only findable in the logs if it is in the body."""
    assert_that(case.expect_body).contains_key("correlation_id")


def test_the_readiness_503_is_a_health_report_not_a_problem():
    case = next(c for c in CASES if c.area == "health" and c.expect_status == 503)
    assert_that(case.expect_headers["Content-Type"]).is_equal_to("application/json")
    assert_that(set(case.expect_body)).is_equal_to({"status", "checks"})


def test_response_body_keys_are_camel_case():
    """The casing rule, asserted structurally over the whole table."""
    exempt = {"correlation_id", "service-desc", "service-doc"} | set(VARIABLE_MEMBERS)

    def walk(node, case_id):
        if isinstance(node, dict):
            for key, value in node.items():
                if key not in exempt:
                    assert_that(key).described_as(f"{case_id}:{key}").matches(
                        r"^[a-z][a-zA-Z0-9]*$"
                    )
                walk(value, case_id)
        elif isinstance(node, list):
            for item in node:
                walk(item, case_id)

    for case in CASES:
        walk(dict(case.expect_body), case.id)
