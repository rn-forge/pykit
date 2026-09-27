"""Tests for rn_forge.web.oidc. No test calls a real IdP."""

from __future__ import annotations

import time

import pytest
from assertpy import assert_that

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

from rn_forge.web import AuthenticationFailed, Credentials, Principal  # noqa: E402
from rn_forge.web.oidc import OidcAuthenticator  # noqa: E402

pytestmark = pytest.mark.unit

ISSUER = "https://idp.example.com/tenant"
AUDIENCE = "api://orders"
JWKS_URL = f"{ISSUER}/keys"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FORGED = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key=KEY, kid="k1", **claims):
    payload = {
        "sub": "u1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        "scp": "orders.read orders.write",
        "roles": ["Reader"],
        "tid": "t-1",
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


class FakeIdP:
    """Serves discovery and the key set, counting every fetch."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url):
        self.calls.append(url)
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": ISSUER, "jwks_uri": JWKS_URL}
        jwk = {**RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1"}
        return {"keys": [jwk]}


def _authenticator(**kwargs):
    return OidcAuthenticator.from_jwks_url(
        JWKS_URL, issuer=ISSUER, audience=AUDIENCE, fetch=FakeIdP(), **kwargs
    )


def _bearer(token: str) -> Credentials:
    return Credentials("Bearer", token)


class TestOidcAuthenticator:
    def test_a_valid_token_maps_to_a_principal(self) -> None:
        principal = _authenticator().authenticate(credentials=_bearer(_token()))

        assert_that(principal.subject).is_equal_to("u1")
        assert_that(principal.issuer).is_equal_to(ISSUER)
        assert_that(principal.scopes).is_equal_to(
            frozenset({"orders.read", "orders.write"})
        )
        assert_that(principal.roles).is_equal_to(frozenset({"Reader"}))
        assert_that(principal.tenant).is_equal_to("t-1")
        assert_that(principal.mechanism).is_equal_to("bearer")

    @pytest.mark.parametrize(
        "token",
        [
            _token(exp=int(time.time()) - 60),
            _token(aud="api://other"),
            _token(iss="https://evil.example.com"),
            _token(key=FORGED),
            _token(kid="unknown"),
            "not-a-jwt",
        ],
        ids=["expired", "audience", "issuer", "signature", "kid", "malformed"],
    )
    def test_verification_failures_raise_authentication_failed(self, token) -> None:
        authenticator = _authenticator()

        with pytest.raises(AuthenticationFailed) as caught:
            authenticator.authenticate(credentials=_bearer(token))

        assert_that(caught.value.error_code).is_equal_to(401)

    def test_the_reason_rides_on_the_exception_for_the_binding_to_log(self) -> None:
        """The message is for the log; the binding renders AUTH_FAILED_DETAIL."""
        authenticator = _authenticator()

        with pytest.raises(AuthenticationFailed) as caught:
            authenticator.authenticate(
                credentials=_bearer(_token(exp=int(time.time()) - 60))
            )

        assert_that(caught.value.message).is_not_empty()

    def test_a_non_bearer_scheme_is_refused(self) -> None:
        authenticator = _authenticator()

        with pytest.raises(AuthenticationFailed):
            authenticator.authenticate(credentials=Credentials("Basic", _token()))

    def test_the_key_set_is_fetched_once_across_calls(self) -> None:
        idp = FakeIdP()
        authenticator = OidcAuthenticator.from_jwks_url(
            JWKS_URL, issuer=ISSUER, audience=AUDIENCE, fetch=idp
        )

        for _ in range(3):
            authenticator.authenticate(credentials=_bearer(_token()))

        assert_that(idp.calls).is_length(1)

    def test_from_issuer_discovers_the_key_set_url(self) -> None:
        idp = FakeIdP()

        authenticator = OidcAuthenticator.from_issuer(
            ISSUER, audience=AUDIENCE, fetch=idp
        )
        principal = authenticator.authenticate(credentials=_bearer(_token()))

        assert_that(principal.subject).is_equal_to("u1")
        assert_that(idp.calls[0]).ends_with("/.well-known/openid-configuration")
        assert_that(idp.calls).contains(JWKS_URL)

    def test_from_issuer_runs_discovery_once_not_per_request(self) -> None:
        """Discovery on construction, the key set once on first use, then neither."""
        idp = FakeIdP()
        authenticator = OidcAuthenticator.from_issuer(
            ISSUER, audience=AUDIENCE, fetch=idp
        )
        assert_that(idp.calls).is_length(1)

        for _ in range(3):
            authenticator.authenticate(credentials=_bearer(_token()))

        discovery = "/.well-known/openid-configuration"
        assert_that([url for url in idp.calls if url.endswith(discovery)]).is_length(1)
        assert_that([url for url in idp.calls if url == JWKS_URL]).is_length(1)

    def test_claims_to_principal_override_is_used(self) -> None:
        def custom(claims):
            return Principal(
                subject=f"custom:{claims['sub']}", scopes=frozenset({"orders.read"})
            )

        authenticator = _authenticator(claims_to_principal=custom)
        principal = authenticator.authenticate(credentials=_bearer(_token()))

        assert_that(principal.subject).is_equal_to("custom:u1")
        assert_that(principal.scopes).is_equal_to(frozenset({"orders.read"}))

    def test_it_satisfies_the_authenticator_protocol(self) -> None:
        from rn_forge.web import Authenticator

        assert_that(isinstance(_authenticator(), Authenticator)).is_true()
