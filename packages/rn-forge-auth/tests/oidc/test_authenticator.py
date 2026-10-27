"""Tests for OidcAuthenticator. No test calls a real IdP."""

from __future__ import annotations

import time

import pytest
from assertpy import assert_that

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from rn_forge.auth import Principal  # noqa: E402
from rn_forge.auth.oidc import OidcAuthenticator  # noqa: E402
from rn_forge.web import AuthenticationFailed, Credentials  # noqa: E402

pytestmark = pytest.mark.unit

AUDIENCE = "api://orders"
CLAIMS = {"scp": "orders.read orders.write", "roles": ["Reader"], "tid": "t-1"}


def _authenticator(idp, **kwargs):
    return OidcAuthenticator.from_jwks_url(
        idp.jwks_url, issuer=idp.issuer, audience=AUDIENCE, **kwargs
    )


def _bearer(token: str) -> Credentials:
    return Credentials("Bearer", token)


class TestOidcAuthenticator:
    def test_a_valid_token_maps_to_a_principal(self, idp) -> None:
        token = idp.token(**CLAIMS)

        principal = _authenticator(idp).authenticate(credentials=_bearer(token))

        assert_that(principal.subject).is_equal_to("u1")
        assert_that(principal.issuer).is_equal_to(idp.issuer)
        assert_that(principal.scopes).is_equal_to(
            frozenset({"orders.read", "orders.write"})
        )
        assert_that(principal.roles).is_equal_to(frozenset({"Reader"}))
        assert_that(principal.tenant).is_equal_to("t-1")
        assert_that(principal.mechanism).is_equal_to("bearer")

    @pytest.mark.parametrize(
        "claims",
        [
            {"exp": int(time.time()) - 60},
            {"aud": "api://other"},
            {"iss": "https://evil.example.com"},
            {"forged": True},
            {"kid": "unknown"},
            {"malformed": True},
        ],
        ids=["expired", "audience", "issuer", "signature", "kid", "malformed"],
    )
    def test_verification_failures_raise_authentication_failed(
        self, idp, claims
    ) -> None:
        if claims.pop("malformed", False):
            token = "not-a-jwt"
        elif claims.pop("forged", False):
            token = idp.token(key=idp.forged_key)
        elif "kid" in claims:
            token = idp.token(key=idp.forged_key, kid=claims["kid"])
        else:
            token = idp.token(**claims)
        authenticator = _authenticator(idp)
        credentials = _bearer(token)

        with pytest.raises(AuthenticationFailed) as caught:
            authenticator.authenticate(credentials=credentials)

        assert_that(caught.value.error_code).is_equal_to(401)

    def test_the_reason_rides_on_the_exception_for_the_binding_to_log(
        self, idp
    ) -> None:
        """The message is for the log; the binding renders AUTH_FAILED_DETAIL."""
        authenticator = _authenticator(idp)
        credentials = _bearer(idp.token(exp=int(time.time()) - 60))

        with pytest.raises(AuthenticationFailed) as caught:
            authenticator.authenticate(credentials=credentials)

        assert_that(caught.value.message).is_not_empty()

    def test_a_non_bearer_scheme_is_refused(self, idp) -> None:
        authenticator = _authenticator(idp)
        credentials = Credentials("Basic", idp.token())

        with pytest.raises(AuthenticationFailed):
            authenticator.authenticate(credentials=credentials)

    def test_the_key_set_is_fetched_once_across_calls(self, idp) -> None:
        authenticator = _authenticator(idp)

        for _ in range(3):
            authenticator.authenticate(credentials=_bearer(idp.token()))

        assert_that(idp.fetches("/keys")).is_equal_to(1)

    def test_from_issuer_discovers_the_key_set_url(self, idp) -> None:
        authenticator = OidcAuthenticator.from_issuer(idp.issuer, audience=AUDIENCE)

        principal = authenticator.authenticate(credentials=_bearer(idp.token()))

        assert_that(principal.subject).is_equal_to("u1")
        assert_that(idp.requests[0]).ends_with("/.well-known/openid-configuration")
        assert_that(idp.fetches("/keys")).is_equal_to(1)

    def test_from_issuer_runs_discovery_once_not_per_request(self, idp) -> None:
        """Discovery on construction, the key set once on first use, then neither."""
        authenticator = OidcAuthenticator.from_issuer(idp.issuer, audience=AUDIENCE)
        assert_that(idp.requests).is_length(1)

        for _ in range(3):
            authenticator.authenticate(credentials=_bearer(idp.token()))

        assert_that(idp.fetches("/.well-known/openid-configuration")).is_equal_to(1)
        assert_that(idp.fetches("/keys")).is_equal_to(1)

    def test_claims_to_principal_override_is_used(self, idp) -> None:
        def custom(claims):
            return Principal(
                subject=f"custom:{claims['sub']}", scopes=frozenset({"orders.read"})
            )

        authenticator = _authenticator(idp, claims_to_principal=custom)
        principal = authenticator.authenticate(credentials=_bearer(idp.token()))

        assert_that(principal.subject).is_equal_to("custom:u1")
        assert_that(principal.scopes).is_equal_to(frozenset({"orders.read"}))

    def test_it_satisfies_the_authenticator_protocol(self, idp) -> None:
        from rn_forge.auth import Authenticator

        assert_that(isinstance(_authenticator(idp), Authenticator)).is_true()
