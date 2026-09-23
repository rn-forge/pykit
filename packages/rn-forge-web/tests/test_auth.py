"""Tests for rn_forge.web.auth."""

import pytest
from assertpy import assert_that

from rn_forge.web.auth import (
    AUTH_FAILED_DETAIL,
    Authorizer,
    Credentials,
    Principal,
    Requirement,
    ScopeAuthorizer,
    challenge_header,
    parse_authorization,
)
from rn_forge.web.exceptions import AuthenticationFailed, PermissionDenied
from rn_forge.web.problem import default_registry

pytestmark = pytest.mark.unit


# --- Principal ------------------------------------------------------------


def test_subject_is_the_only_required_field():
    principal = Principal(subject="u1")
    assert_that(principal.issuer).is_none()
    assert_that(principal.scopes).is_empty()
    assert_that(principal.mechanism).is_equal_to("bearer")


def test_principal_round_trips_through_the_dataclass_mixin():
    principal = Principal(
        subject="u1",
        issuer="https://idp.example",
        scopes=frozenset({"read"}),
        roles=frozenset({"admin"}),
        tenant="t1",
        claims={"email": "u@example.com"},
        mechanism="bearer",
    )
    restored = Principal.from_dict(principal.as_dict())
    assert_that(restored).is_equal_to(principal)


def test_scopes_and_roles_are_separate():
    principal = Principal(
        subject="u1", scopes=frozenset({"read"}), roles=frozenset({"admin"})
    )
    assert_that(principal.scopes).does_not_contain("admin")
    assert_that(principal.roles).does_not_contain("read")


def test_credentials_carry_the_scheme_verbatim():
    creds = Credentials(scheme="Bearer", token="abc")
    assert_that(creds.scheme).is_equal_to("Bearer")
    assert_that(creds.extras).is_empty()


# --- Requirement ----------------------------------------------------------


READER = Principal(
    subject="u1", scopes=frozenset({"read", "list"}), roles=frozenset({"staff"})
)


def test_an_empty_requirement_means_authenticated_not_denied():
    assert_that(Requirement().is_satisfied_by(Principal(subject="u1"))).is_true()


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        (Requirement(any_scope=frozenset({"read"})), True),
        (Requirement(any_scope=frozenset({"read", "write"})), True),
        (Requirement(any_scope=frozenset({"write"})), False),
        (Requirement(all_scopes=frozenset({"read", "list"})), True),
        (Requirement(all_scopes=frozenset({"read", "write"})), False),
        (Requirement(any_role=frozenset({"staff"})), True),
        (Requirement(any_role=frozenset({"admin"})), False),
        (Requirement(all_roles=frozenset({"staff"})), True),
        (Requirement(all_roles=frozenset({"staff", "admin"})), False),
    ],
)
def test_each_of_the_four_set_forms(requirement, expected):
    assert_that(requirement.is_satisfied_by(READER)).is_equal_to(expected)


def test_the_clauses_are_anded_together():
    both = Requirement(all_scopes=frozenset({"read"}), all_roles=frozenset({"admin"}))
    assert_that(both.is_satisfied_by(READER)).is_false()


# --- the authorizer -------------------------------------------------------


def test_the_default_authorizer_satisfies_the_protocol():
    assert_that(isinstance(ScopeAuthorizer(), Authorizer)).is_true()


def test_authorize_permits_a_satisfied_requirement():
    ScopeAuthorizer().authorize(
        READER, requires=Requirement(all_scopes=frozenset({"read"}))
    )


def test_a_scope_miss_raises_permission_denied_not_authentication_failed():
    """The 401/403 boundary: the caller IS authenticated."""
    authorizer = ScopeAuthorizer()
    requirement = Requirement(all_scopes=frozenset({"write"}))
    assert_that(authorizer.authorize).raises(PermissionDenied).when_called_with(
        READER, requires=requirement
    )
    with pytest.raises(PermissionDenied):
        authorizer.authorize(READER, requires=requirement)


def test_permission_denied_is_not_an_authentication_failure():
    assert_that(issubclass(PermissionDenied, AuthenticationFailed)).is_false()


def test_the_authorizer_is_silent_when_no_log_is_injected():
    """A library that logs where the consumer did not ask is worse than one that does not."""
    with pytest.raises(PermissionDenied):
        ScopeAuthorizer().authorize(
            READER, requires=Requirement(all_roles=frozenset({"admin"}))
        )


def test_the_injected_log_receives_the_refusal():
    seen: list[tuple[str, dict]] = []
    authorizer = ScopeAuthorizer(log=lambda msg, ctx: seen.append((msg, dict(ctx))))
    with pytest.raises(PermissionDenied):
        authorizer.authorize(
            READER, requires=Requirement(all_roles=frozenset({"admin"}))
        )
    assert_that(seen).is_length(1)
    assert_that(seen[0][0]).is_equal_to("authorization.denied")
    assert_that(seen[0][1]["subject"]).is_equal_to("u1")


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
