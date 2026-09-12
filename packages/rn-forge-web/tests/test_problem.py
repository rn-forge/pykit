"""Tests for rn_forge.web.problem."""

import pytest
from assertpy import assert_that

from rn_forge.web.exceptions import (
    AuthenticationFailed,
    DomainConflict,
    IdempotencyKeyReuse,
    PermissionDenied,
    PreconditionRequired,
    RemoteProblem,
    VersionConflict,
)
from rn_forge.web.problem import (
    BLANK_TYPE,
    CONFLICT,
    GENERIC_SERVER_DETAIL,
    INTERNAL_ERROR,
    PRECONDITION_FAILED,
    PRECONDITION_REQUIRED,
    ProblemDetail,
    ProblemRegistry,
    ProblemType,
    default_registry,
    errors_from_field_map,
    errors_from_pointer_list,
    problem_from_body,
)

pytestmark = pytest.mark.unit


# --- the wire shape -------------------------------------------------------


def test_as_body_flattens_extensions_to_the_top_level():
    problem = ProblemDetail(
        type="about:blank",
        title="Conflict",
        status=409,
        detail="nope",
        instance="/orders/1",
        extensions={"correlation_id": "abc", "errors": [{"pointer": "/x"}]},
    )
    assert_that(problem.as_body()).is_equal_to(
        {
            "type": "about:blank",
            "title": "Conflict",
            "status": 409,
            "detail": "nope",
            "instance": "/orders/1",
            "correlation_id": "abc",
            "errors": [{"pointer": "/x"}],
        }
    )


def test_core_members_win_a_collision_with_an_extension():
    problem = ProblemDetail(
        type="about:blank",
        title="Conflict",
        status=409,
        detail="nope",
        instance="/orders/1",
        extensions={"status": 500, "title": "Wrong"},
    )
    body = problem.as_body()
    assert_that(body["status"]).is_equal_to(409)
    assert_that(body["title"]).is_equal_to("Conflict")


# --- the registry ---------------------------------------------------------


def test_mro_resolution_finds_a_base_class_row():
    class AdapterConflict(DomainConflict):
        pass

    registry = default_registry()
    assert_that(registry.problem_for(AdapterConflict("x"))).is_equal_to(CONFLICT)


def test_the_most_derived_registration_wins_over_a_base():
    """VersionConflict subclasses DomainConflict; it must resolve to 412, not 409."""
    registry = default_registry()
    assert_that(registry.problem_for(VersionConflict("x"))).is_equal_to(
        PRECONDITION_FAILED
    )


def test_an_unregistered_exception_falls_back():
    registry = ProblemRegistry()
    assert_that(registry.problem_for(RuntimeError("x"))).is_equal_to(INTERNAL_ERROR)


def test_a_custom_fallback_is_honoured():
    row = ProblemType("teapot", 418, "I'm a teapot")
    registry = ProblemRegistry(fallback=row)
    assert_that(registry.problem_for(RuntimeError("x"))).is_equal_to(row)


def test_register_returns_self_for_chaining():
    registry = ProblemRegistry()
    assert_that(registry.register(RuntimeError, CONFLICT)).is_same_as(registry)


def test_type_is_about_blank_without_a_type_base():
    registry = default_registry()
    problem = registry.build(DomainConflict("clash"), instance="/x")
    assert_that(problem.type).is_equal_to(BLANK_TYPE)


def test_type_base_is_prefixed_to_the_slug():
    registry = default_registry(type_base="https://errors.example.com/")
    problem = registry.build(DomainConflict("clash"), instance="/x")
    assert_that(problem.type).is_equal_to("https://errors.example.com/conflict")


def test_default_registry_returns_independent_instances():
    first, second = default_registry(), default_registry()
    first.register(RuntimeError, CONFLICT)
    assert_that(second.problem_for(RuntimeError("x"))).is_equal_to(INTERNAL_ERROR)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (DomainConflict("x"), 409),
        (VersionConflict("x"), 412),
        (PreconditionRequired("x"), 428),
        (IdempotencyKeyReuse("x"), 409),
        (AuthenticationFailed("x"), 401),
        (PermissionDenied("x"), 403),
        (KeyError("x"), 404),
        (ValueError("x"), 422),
    ],
)
def test_default_registry_status_codes(exc, expected):
    assert_that(default_registry().problem_for(exc).status).is_equal_to(expected)


def test_remote_problem_maps_to_502():
    upstream = problem_from_body(409, {"title": "Conflict", "status": 409})
    exc = RemoteProblem(upstream)
    assert_that(default_registry().problem_for(exc).status).is_equal_to(502)
    assert_that(exc.problem).is_equal_to(upstream)


# --- the 5xx detail policy ------------------------------------------------


def test_5xx_detail_is_suppressed():
    problem = default_registry().build(
        RuntimeError("connection string is postgres://user:hunter2@db"),
        instance="/x",
    )
    assert_that(problem.detail).is_equal_to(GENERIC_SERVER_DETAIL)
    assert_that(problem.detail).does_not_contain("hunter2")


def test_an_explicit_detail_overrides_the_5xx_policy():
    problem = default_registry().build(
        RuntimeError("boom"), instance="/x", detail="Upstream is down for maintenance."
    )
    assert_that(problem.detail).is_equal_to("Upstream is down for maintenance.")


def test_below_500_the_detail_is_the_exception_message():
    problem = default_registry().build(
        DomainConflict("Order dispatched"), instance="/x"
    )
    assert_that(problem.detail).is_equal_to("Order dispatched")


def test_an_empty_message_below_500_falls_back_to_the_title():
    problem = default_registry().build(DomainConflict(""), instance="/x")
    assert_that(problem.detail).is_equal_to("Conflict")


def test_build_carries_instance_and_extensions():
    problem = default_registry().build(
        DomainConflict("x"), instance="/orders/9", extensions={"correlation_id": "abc"}
    )
    assert_that(problem.instance).is_equal_to("/orders/9")
    assert_that(problem.as_body()["correlation_id"]).is_equal_to("abc")


# --- the two normalizers --------------------------------------------------


def test_pointer_list_from_pydantic_errors():
    raw = [
        {"loc": ("body", "name"), "msg": "Field required", "type": "missing"},
        {"loc": ("body", "items", 0, "qty"), "msg": "must be > 0"},
    ]
    assert_that(errors_from_pointer_list(raw)).is_equal_to(
        [
            {"pointer": "/body/name", "message": "Field required"},
            {"pointer": "/body/items/0/qty", "message": "must be > 0"},
        ]
    )


def test_pointer_list_handles_an_empty_loc():
    assert_that(errors_from_pointer_list([{"loc": (), "msg": "bad"}])).is_equal_to(
        [{"pointer": "", "message": "bad"}]
    )


def test_field_map_flat():
    assert_that(
        errors_from_field_map({"name": ["This field is required."]})
    ).is_equal_to([{"pointer": "/name", "message": "This field is required."}])


def test_field_map_multiple_messages_share_a_pointer():
    result = errors_from_field_map({"name": ["too short", "not unique"]})
    assert_that(result).is_equal_to(
        [
            {"pointer": "/name", "message": "too short"},
            {"pointer": "/name", "message": "not unique"},
        ]
    )


def test_field_map_recurses_into_a_nested_serializer():
    """The bug being fixed on the way through: cims's handler drops these."""
    result = errors_from_field_map({"address": {"postcode": ["invalid"]}})
    assert_that(result).is_equal_to(
        [{"pointer": "/address/postcode", "message": "invalid"}]
    )


def test_field_map_indexes_a_list_of_nested_serializers():
    result = errors_from_field_map({"items": [{}, {"qty": ["must be > 0"]}]})
    assert_that(result).is_equal_to(
        [{"pointer": "/items/1/qty", "message": "must be > 0"}]
    )


def test_field_map_escapes_rfc6901_reserved_characters():
    result = errors_from_field_map({"a/b~c": ["bad"]})
    assert_that(result).is_equal_to([{"pointer": "/a~1b~0c", "message": "bad"}])


# --- the client-side direction --------------------------------------------


def test_problem_from_body_parses_a_complete_body():
    problem = problem_from_body(
        409,
        {
            "type": "https://e.example/conflict",
            "title": "Conflict",
            "status": 409,
            "detail": "already dispatched",
            "instance": "/orders/1",
            "order_id": 1,
        },
    )
    assert_that(problem.type).is_equal_to("https://e.example/conflict")
    assert_that(problem.status).is_equal_to(409)
    assert_that(problem.extensions).is_equal_to({"order_id": 1})


def test_problem_from_body_tolerates_an_empty_body():
    problem = problem_from_body(404, {})
    assert_that(problem.type).is_equal_to(BLANK_TYPE)
    assert_that(problem.status).is_equal_to(404)
    assert_that(problem.title).is_empty()


def test_problem_from_body_falls_back_to_the_http_status():
    """An upstream that omits `status`, or sends a non-integer one, must not 500 us."""
    assert_that(problem_from_body(503, {"status": "oops"}).status).is_equal_to(503)


def test_problem_from_body_round_trips_through_as_body():
    original = default_registry().build(DomainConflict("clash"), instance="/x")
    assert_that(problem_from_body(409, original.as_body())).is_equal_to(original)
