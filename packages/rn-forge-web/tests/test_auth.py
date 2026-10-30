"""Tests for rn_forge.web.auth."""

import pytest
from assertpy import assert_that

from rn_forge.web.auth import (
    AUTH_FAILED_DETAIL,
    Credentials,
    challenge_header,
    parse_authorization,
)
from rn_forge.web.auth import CSRF_FAILED_DETAIL
from rn_forge.web.exceptions import (
    AuthenticationFailed,
    CsrfFailed,
    PermissionDenied,
    SessionRequired,
)
from rn_forge.web.problem import default_registry, render_problem

pytestmark = pytest.mark.unit


def test_credentials_carry_the_scheme_verbatim():
    creds = Credentials(scheme="Bearer", token="abc")
    assert_that(creds.scheme).is_equal_to("Bearer")
    assert_that(creds.extras).is_empty()


def test_permission_denied_is_not_an_authentication_failure():
    assert_that(issubclass(PermissionDenied, AuthenticationFailed)).is_false()


# --- the failure wire contract --------------------------------------------


def test_the_401_and_403_rows_are_registered():
    registry = default_registry()
    assert_that(registry.problem_for(AuthenticationFailed("x")).status).is_equal_to(401)
    assert_that(registry.problem_for(PermissionDenied("x")).status).is_equal_to(403)
    assert_that(registry.problem_for(AuthenticationFailed("x")).slug).is_equal_to(
        "unauthorized"
    )
    assert_that(registry.problem_for(PermissionDenied("x")).slug).is_equal_to(
        "forbidden"
    )


def test_the_401_body_carries_no_verification_reason():
    """Expired, bad signature and unknown kid must all look identical on the wire."""
    registry = default_registry()
    problem = registry.build(
        AuthenticationFailed("token expired at 2026-01-01, kid=abc"),
        instance="/private",
        detail=AUTH_FAILED_DETAIL,
    )
    body = problem.as_body()
    assert_that(body["detail"]).is_equal_to("Authentication failed.")
    assert_that(str(body)).does_not_contain("expired").does_not_contain("kid")


# --- challenge_header, against the RFCs' own examples ---------------------


def test_bare_bearer_challenge():
    assert_that(challenge_header()).is_equal_to("Bearer")


def test_rfc6750_realm_example():
    """RFC 6750 §3: `WWW-Authenticate: Bearer realm="example"`."""
    assert_that(challenge_header(realm="example")).is_equal_to('Bearer realm="example"')


def test_rfc6750_invalid_token_example():
    """RFC 6750 §3, second example, verbatim."""
    assert_that(
        challenge_header(
            realm="example",
            error="invalid_token",
            error_description="The access token expired",
        )
    ).is_equal_to(
        'Bearer realm="example", error="invalid_token", '
        'error_description="The access token expired"'
    )


def test_rfc6750_insufficient_scope_carries_the_scope():
    assert_that(
        challenge_header(realm="example", error="insufficient_scope", scope="read")
    ).is_equal_to('Bearer realm="example", error="insufficient_scope", scope="read"')


def test_rfc7617_basic_example():
    """RFC 7617 §2: `WWW-Authenticate: Basic realm="WallyWorld"`."""
    assert_that(challenge_header(scheme="Basic", realm="WallyWorld")).is_equal_to(
        'Basic realm="WallyWorld"'
    )


def test_a_quoted_string_parameter_is_escaped():
    assert_that(challenge_header(realm='say "hi"')).is_equal_to(
        'Bearer realm="say \\"hi\\""'
    )


def test_omitted_parameters_do_not_appear():
    assert_that(challenge_header(error="invalid_request")).is_equal_to(
        'Bearer error="invalid_request"'
    )


def test_parse_authorization_matches_the_scheme_case_insensitively():
    assert_that(parse_authorization("bearer  tok ", "Bearer")).is_equal_to(
        Credentials("Bearer", "tok")
    )


@pytest.mark.parametrize("header", [None, "", "Basic dXNlcjpwdw=="])
def test_parse_authorization_is_none_when_absent_or_another_scheme(header):
    assert_that(parse_authorization(header, "Bearer")).is_none()


# --- session-only 401 and csrf-failed -------------------------------------


def test_a_session_required_failure_is_a_401_unauthorized():
    row = default_registry().problem_for(SessionRequired("no cookie"))
    assert_that((row.status, row.slug)).is_equal_to((401, "unauthorized"))


def test_a_session_required_401_carries_no_challenge_and_the_generic_detail():
    rendered = render_problem(
        default_registry(), SessionRequired("cookie expired"), instance="/auth/session"
    )
    assert_that(rendered.status).is_equal_to(401)
    assert_that(rendered.headers).does_not_contain_key("WWW-Authenticate")
    assert_that(rendered.body["detail"]).is_equal_to(AUTH_FAILED_DETAIL)


def test_a_bearer_401_still_carries_its_challenge():
    rendered = render_problem(
        default_registry(), AuthenticationFailed("x"), instance="/x", realm="api"
    )
    assert_that(rendered.headers["WWW-Authenticate"]).is_equal_to('Bearer realm="api"')


def test_a_caller_supplied_challenge_still_wins_on_a_session_required_401():
    rendered = render_problem(
        default_registry(),
        SessionRequired("x"),
        instance="/x",
        headers={"WWW-Authenticate": "Bearer"},
    )
    assert_that(rendered.headers).is_equal_to({"WWW-Authenticate": "Bearer"})


def test_csrf_failed_is_a_403_with_its_own_slug_and_is_not_a_permission_denial():
    row = default_registry().problem_for(CsrfFailed("origin mismatch"))
    assert_that((row.status, row.slug)).is_equal_to((403, "csrf-failed"))
    assert_that(issubclass(CsrfFailed, PermissionDenied)).is_false()


def test_the_csrf_failed_type_is_distinguishable_with_a_type_base():
    rendered = render_problem(
        default_registry(type_base="https://errors.example/"),
        CsrfFailed("origin mismatch"),
        instance="/auth/logout",
    )
    assert_that(rendered.body["type"]).is_equal_to("https://errors.example/csrf-failed")
    assert_that(rendered.body["title"]).is_equal_to("CSRF Failed")


def test_the_csrf_failed_body_never_names_the_check_that_failed():
    rendered = render_problem(
        default_registry(),
        CsrfFailed("Origin https://evil.example not trusted"),
        instance="/auth/logout",
        detail="token mismatch",
    )
    assert_that(rendered.body["detail"]).is_equal_to(CSRF_FAILED_DETAIL)
    assert_that(str(rendered.body)).does_not_contain("evil").does_not_contain("token")
    assert_that(rendered.headers).does_not_contain_key("WWW-Authenticate")
