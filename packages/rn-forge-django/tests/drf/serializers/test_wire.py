from __future__ import annotations

from dataclasses import asdict

import pytest

from rn_forge.django.drf.serializers import (
    CheckResultSerializer,
    HealthReportSerializer,
    PageSerializer,
    ProblemDetailSerializer,
)
from rn_forge.web import CheckResult, HealthReport, Page, ProblemDetail

pytestmark = pytest.mark.unit


def _round_trips(serializer_class, data) -> None:
    serializer = serializer_class(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.data == data


def test_problem_detail_mirror_round_trips() -> None:
    problem = ProblemDetail(
        type="about:blank", title="Conflict", status=409, detail="x", instance="/o/1"
    )
    _round_trips(ProblemDetailSerializer, problem.as_body())


@pytest.mark.parametrize("token", ["abc", None])
def test_page_mirror_round_trips(token) -> None:
    page = Page(items=[{"id": "1"}, 2], next_page_token=token, total_size=None)
    _round_trips(PageSerializer, asdict(page))


def test_check_result_mirror_round_trips() -> None:
    result = CheckResult(
        status="warn", reason="slow", remediation="scale", details={"ms": 900}
    )
    _round_trips(CheckResultSerializer, asdict(result))


def test_health_report_mirror_round_trips() -> None:
    report = HealthReport(
        status="fail",
        checks={"db": CheckResult(status="fail", reason="down")},
        http_status=503,
    )
    _round_trips(HealthReportSerializer, report.as_body())


@pytest.mark.parametrize(
    ("serializer_class", "component"),
    [
        (ProblemDetailSerializer, "ProblemDetail"),
        (PageSerializer, "Page"),
        (CheckResultSerializer, "CheckResult"),
        (HealthReportSerializer, "HealthReport"),
    ],
)
def test_component_names_match_the_fastapi_side(serializer_class, component) -> None:
    assert serializer_class.__name__.removesuffix("Serializer") == component
