from __future__ import annotations

import json

import pytest
from assertpy import assert_that

rest_framework = pytest.importorskip("rest_framework")

from django.http import Http404  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from rest_framework import exceptions as drf_exceptions  # noqa: E402
from rest_framework.request import Request  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.drf.exceptions import (  # noqa: E402
    _field_errors,
    problem_details_exception_handler,
    problem_registry,
)
from opentelemetry import trace  # noqa: E402

from rn_forge.django.exceptions import problem_details_handler404  # noqa: E402
from rn_forge.web import (  # noqa: E402
    PROBLEM_MEDIA_TYPE,
    DomainConflict,
    ProblemType,
    PreconditionRequired,
    VersionConflict,
)

_TRACER = trace.get_tracer(__name__)

pytestmark = pytest.mark.unit


def _context(path: str = "/orders/7/") -> dict[str, object]:
    return {"request": Request(APIRequestFactory().get(path)), "view": None}


def _handle(exc: Exception, **kwargs):
    response = problem_details_exception_handler(exc, _context(), **kwargs)
    return response, json.loads(response.content)


class TestStatusMapping:
    def test_domain_conflict_is_409(self) -> None:
        response, body = _handle(DomainConflict("Order already dispatched"))
        assert response.status_code == 409
        assert body["detail"] == "Order already dispatched"
        assert body["title"] == "Conflict"

    def test_version_conflict_is_412_not_409(self) -> None:
        response, _ = _handle(VersionConflict("stale"))
        assert response.status_code == 412

    def test_precondition_required_is_428(self) -> None:
        response, _ = _handle(PreconditionRequired("needed"))
        assert response.status_code == 428

    def test_drf_exception_keeps_its_status_and_detail(self) -> None:
        response, body = _handle(drf_exceptions.NotFound("No such order"))
        assert response.status_code == 404
        assert body["detail"] == "No such order"
        assert body["title"] == "Not Found"

    def test_django_http404_is_404(self) -> None:
        response, _ = _handle(Http404("gone"))
        assert response.status_code == 404

    def test_custom_registry_overrides_a_row(self) -> None:
        registry = problem_registry().register(
            DomainConflict, ProblemType("order-locked", 423, "Locked")
        )
        response, body = _handle(DomainConflict("locked"), registry=registry)
        assert response.status_code == 423
        assert body["title"] == "Locked"


class TestBody:
    def test_content_type_is_problem_json(self) -> None:
        response, _ = _handle(DomainConflict("x"))
        assert response["Content-Type"] == PROBLEM_MEDIA_TYPE

    def test_scalar_detail_has_no_errors_member(self) -> None:
        _, body = _handle(drf_exceptions.ParseError("Malformed JSON"))
        assert body["detail"] == "Malformed JSON"
        assert "errors" not in body

    def test_field_errors_are_pointers_and_status_is_422(self) -> None:
        response, body = _handle(
            drf_exceptions.ValidationError({"name": ["This field is required."]})
        )
        assert response.status_code == 422
        assert body["detail"] == "Validation Error"
        assert body["errors"] == [
            {"pointer": "/name", "detail": "This field is required."}
        ]

    def test_nested_field_errors_are_normalized(self) -> None:
        _, body = _handle(
            drf_exceptions.ValidationError({"lines": [{"sku": ["Unknown sku."]}, {}]})
        )
        assert body["errors"] == [{"pointer": "/lines/0/sku", "detail": "Unknown sku."}]

    def test_non_field_validation_list(self) -> None:
        _, body = _handle(drf_exceptions.ValidationError("Totals do not add up."))
        assert body["errors"] == [{"pointer": "", "detail": "Totals do not add up."}]

    def test_instance_is_the_request_path(self) -> None:
        _, body = _handle(DomainConflict("x"))
        assert body["instance"] == "/orders/7/"

    def test_trace_id_present_when_a_span_is_recording(self) -> None:
        with _TRACER.start_as_current_span("test-span") as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
            _, body = _handle(DomainConflict("x"))
        assert body["trace_id"] == trace_id

    def test_trace_id_null_when_no_span_is_recording(self) -> None:
        _, body = _handle(DomainConflict("x"))
        assert body["trace_id"] is None


class TestServerErrors:
    def test_unhandled_exception_is_500_without_internal_detail(self) -> None:
        response, body = _handle(RuntimeError("password=hunter2"))
        assert response.status_code == 500
        assert "hunter2" not in response.content.decode()
        assert body["detail"] == "An unexpected error occurred."


class TestAuth:
    def test_401_carries_a_challenge_and_says_nothing_about_why(self) -> None:
        response, body = _handle(drf_exceptions.AuthenticationFailed("bad signature"))
        assert response.status_code == 401
        assert body["detail"] == "Authentication failed."
        assert response["WWW-Authenticate"].startswith("Bearer")

    def test_403_has_no_challenge(self) -> None:
        response, _ = _handle(drf_exceptions.PermissionDenied())
        assert response.status_code == 403
        assert not response.has_header("WWW-Authenticate")


class TestHandler404:
    def test_routing_404_is_a_problem(self) -> None:
        response = problem_details_handler404(RequestFactory().get("/nope/"))
        body = json.loads(response.content)
        assert response.status_code == 404
        assert response["Content-Type"] == PROBLEM_MEDIA_TYPE
        assert body["detail"] == "Not Found"
        assert body["instance"] == "/nope/"


# --- DRF error trees to field errors --------------------------------------


def test_field_errors_flat():
    assert_that(_field_errors({"name": ["This field is required."]})).is_equal_to(
        [{"pointer": "/name", "detail": "This field is required."}]
    )


def test_field_errors_multiple_messages_share_a_pointer():
    assert_that(_field_errors({"name": ["too short", "not unique"]})).is_equal_to(
        [
            {"pointer": "/name", "detail": "too short"},
            {"pointer": "/name", "detail": "not unique"},
        ]
    )


def test_field_errors_recurse_into_a_nested_serializer():
    assert_that(_field_errors({"address": {"postcode": ["invalid"]}})).is_equal_to(
        [{"pointer": "/address/postcode", "detail": "invalid"}]
    )


def test_field_errors_index_a_list_of_nested_serializers():
    assert_that(_field_errors({"items": [{}, {"qty": ["must be > 0"]}]})).is_equal_to(
        [{"pointer": "/items/1/qty", "detail": "must be > 0"}]
    )


def test_field_errors_of_a_top_level_message_list_point_at_the_root():
    assert_that(_field_errors(["bad", "worse"])).is_equal_to(
        [{"pointer": "", "detail": "bad"}, {"pointer": "", "detail": "worse"}]
    )


def test_field_errors_of_a_scalar_are_empty():
    assert_that(_field_errors("plain")).is_empty()
