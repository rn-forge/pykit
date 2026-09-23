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
    field_error,
    problem_from_body,
    render_problem,
    unmapped_exceptions,
)
from opentelemetry import trace

from rn_forge.web.auth import AUTH_FAILED_DETAIL
from rn_forge.web.tracing import current_trace_id

_TRACER = trace.get_tracer(__name__)

pytestmark = pytest.mark.unit


# --- the wire shape -------------------------------------------------------


def test_as_body_flattens_extensions_to_the_top_level():
    problem = ProblemDetail(
        type="about:blank",
        title="Conflict",
        status=409,
        detail="nope",
        instance="/orders/1",
        extensions={"trace_id": "abc", "errors": [{"pointer": "/x"}]},
    )
    assert_that(problem.as_body()).is_equal_to(
        {
            "type": "about:blank",
            "title": "Conflict",
            "status": 409,
            "detail": "nope",
            "instance": "/orders/1",
            "trace_id": "abc",
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
        (IdempotencyKeyReuse("x"), 422),
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
        DomainConflict("x"), instance="/orders/9", extensions={"trace_id": "abc"}
    )
    assert_that(problem.instance).is_equal_to("/orders/9")
    assert_that(problem.as_body()["trace_id"]).is_equal_to("abc")


# --- exception-carried extensions and table audit -------------------------


def test_extensions_are_merged_from_the_exception():
    class TaggedConflict(DomainConflict):
        def problem_extensions(self):
            return {"current_version": 7}

    problem = default_registry().build(TaggedConflict("clash"), instance="/x")
    assert_that(problem.as_body()["current_version"]).is_equal_to(7)


def test_an_explicit_extension_overrides_the_exceptions_own():
    class TaggedConflict(DomainConflict):
        def problem_extensions(self):
            return {"current_version": 7}

    problem = default_registry().build(
        TaggedConflict("clash"), instance="/x", extensions={"current_version": 9}
    )
    assert_that(problem.as_body()["current_version"]).is_equal_to(9)


def test_nothing_is_merged_for_a_5xx_row():
    class TaggedError(RuntimeError):
        def problem_extensions(self):
            return {"leaked": "internal"}

    problem = default_registry().build(TaggedError("boom"), instance="/x")
    assert_that(problem.as_body()).does_not_contain_key("leaked")


def test_an_exception_without_the_method_is_unaffected():
    problem = default_registry().build(DomainConflict("clash"), instance="/x")
    assert_that(problem.as_body()).does_not_contain_key("current_version")


def test_unmapped_exceptions_finds_a_subclass_resolving_to_the_fallback():
    class Unregistered(RuntimeError):
        pass

    registry = ProblemRegistry().register(ValueError, CONFLICT)
    found = unmapped_exceptions(registry, RuntimeError, ValueError)
    assert_that(found).contains(Unregistered)


def test_unmapped_exceptions_excludes_a_subclass_resolving_through_its_base():
    class RegisteredChild(ValueError):
        pass

    registry = ProblemRegistry().register(ValueError, CONFLICT)
    found = unmapped_exceptions(registry, ValueError)
    assert_that(found).does_not_contain(RegisteredChild)


def test_fallback_property_returns_the_registrys_fallback_row():
    row = ProblemType("teapot", 418, "I'm a teapot")
    registry = ProblemRegistry(fallback=row)
    assert_that(registry.fallback).is_equal_to(row)


# --- the two normalizers --------------------------------------------------


def test_rows_is_a_read_only_view_in_registration_order():
    registry = (
        ProblemRegistry()
        .register(KeyError, CONFLICT)
        .register(ValueError, INTERNAL_ERROR)
    )
    assert_that(list(registry.rows())).is_equal_to([KeyError, ValueError])
    with pytest.raises(TypeError):
        registry.rows()[RuntimeError] = CONFLICT  # type: ignore[index]


def test_problem_for_status_prefers_the_first_registered_row():
    """A framework 404 must render exactly like a registered LookupError."""
    assert_that(default_registry().problem_for_status(404).slug).is_equal_to(
        "not-found"
    )
    assert_that(default_registry().problem_for_status(409)).is_equal_to(CONFLICT)


def test_problem_for_status_derives_an_unregistered_row_from_the_reason_phrase():
    row = default_registry().problem_for_status(405)
    assert_that(row).is_equal_to(
        ProblemType("method-not-allowed", 405, "Method Not Allowed")
    )


def test_problem_for_status_slugs_punctuated_phrases():
    assert_that(ProblemRegistry().problem_for_status(418).slug).is_equal_to(
        "i-m-a-teapot"
    )


def test_problem_for_status_without_a_reason_phrase_falls_back():
    assert_that(ProblemRegistry().problem_for_status(499)).is_equal_to(INTERNAL_ERROR)


def test_build_uses_an_explicit_row_instead_of_resolving_one():
    problem = default_registry().build(
        RuntimeError("Not Found"),
        instance="/x",
        problem=ProblemType("not-found", 404, "Not Found"),
    )
    assert_that(problem.status).is_equal_to(404)
    assert_that(problem.detail).is_equal_to("Not Found")


def test_field_error_builds_an_rfc6901_pointer():
    assert_that(field_error(("items", 1, "qty"), "must be > 0")).is_equal_to(
        {"pointer": "/items/1/qty", "detail": "must be > 0"}
    )


def test_field_error_with_an_empty_path_points_at_the_root():
    assert_that(field_error((), "bad")).is_equal_to({"pointer": "", "detail": "bad"})


def test_field_error_escapes_rfc6901_reserved_characters():
    assert_that(field_error(("a/b~c",), "bad")["pointer"]).is_equal_to("/a~1b~0c")


# --- the rendered response ------------------------------------------------


def test_render_problem_carries_the_current_trace_id():
    with _TRACER.start_as_current_span("test-span"):
        trace_id = current_trace_id()
        rendered = render_problem(
            default_registry(), DomainConflict("taken"), instance="/x"
        )
    assert_that(rendered.status).is_equal_to(409)
    assert_that(rendered.body["traceId"]).is_equal_to(trace_id)


def test_render_problem_carries_null_outside_a_span():
    rendered = render_problem(default_registry(), DomainConflict("x"), instance="/")
    assert_that(rendered.body["traceId"]).is_none()


def test_render_problem_masks_a_401_detail_and_adds_a_challenge():
    rendered = render_problem(
        default_registry(),
        AuthenticationFailed("signature expired"),
        instance="/x",
        detail="signature expired",
        realm="api",
    )
    assert_that(rendered.body["detail"]).is_equal_to(AUTH_FAILED_DETAIL)
    assert_that(rendered.headers["WWW-Authenticate"]).contains('realm="api"')


def test_render_problem_keeps_a_challenge_the_caller_supplied():
    rendered = render_problem(
        default_registry(),
        AuthenticationFailed("x"),
        instance="/x",
        headers={"www-authenticate": 'Basic realm="own"'},
    )
    assert_that(rendered.headers).is_equal_to({"www-authenticate": 'Basic realm="own"'})


def test_render_problem_never_challenges_a_403():
    rendered = render_problem(default_registry(), PermissionDenied("no"), instance="/")
    assert_that(rendered.headers).does_not_contain_key("WWW-Authenticate")


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
