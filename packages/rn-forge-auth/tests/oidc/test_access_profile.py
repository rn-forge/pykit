"""The access-token profile: JwtVerifier in RFC 9068 and RFC 7519 modes."""

from __future__ import annotations

import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from rn_forge.auth.oidc import JwtVerifier, TokenVerificationError  # noqa: E402

pytestmark = pytest.mark.unit

AUDIENCE = "api://orders"
LOGIN_CLIENT = "web-login"


def _verifier(idp, mode="rfc7519", **kwargs):
    return JwtVerifier.from_jwks_url(
        idp.jwks_url, issuer=idp.issuer, audience=AUDIENCE, mode=mode, **kwargs
    )


def _claims(idp, **overrides):
    now = int(time.time())
    return {
        "iss": idp.issuer,
        "aud": AUDIENCE,
        "sub": "u1",
        "exp": now + 300,
        "iat": now,
        "jti": "j1",
        "client_id": "spa",
        **overrides,
    }


class TestRfc9068Mode:
    @pytest.mark.parametrize("typ", ["at+jwt", "application/at+jwt", "AT+JWT"])
    def test_an_access_token_type_is_accepted(self, idp, typ):
        claims = _verifier(idp, "rfc9068").verify(idp.sign(_claims(idp), typ=typ))
        assert claims["jti"] == "j1"

    @pytest.mark.parametrize("typ", [None, "JWT", "logout+jwt"])
    def test_any_other_typ_is_rejected(self, idp, typ):
        token = idp.sign(_claims(idp), typ=typ)
        verifier = _verifier(idp, "rfc9068")
        with pytest.raises(TokenVerificationError, match="typ"):
            verifier.verify(token)

    @pytest.mark.parametrize(
        "claim", ["iss", "exp", "aud", "sub", "client_id", "iat", "jti"]
    )
    def test_each_required_claim_is_required(self, idp, claim):
        token = idp.sign(_claims(idp, **{claim: None}), typ="at+jwt")
        verifier = _verifier(idp, "rfc9068")
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)


class TestRfc7519Mode:
    @pytest.mark.parametrize("typ", ["JWT", "jwt", None])
    def test_jwt_or_no_typ_is_accepted(self, idp, typ):
        token = idp.sign(
            {"iss": idp.issuer, "aud": AUDIENCE, "exp": int(time.time()) + 60}, typ=typ
        )
        assert _verifier(idp).verify(token)["aud"] == AUDIENCE

    @pytest.mark.parametrize("typ", ["at+jwt", "logout+jwt", "application/at+jwt"])
    def test_any_other_typ_is_rejected(self, idp, typ):
        token = idp.sign(_claims(idp), typ=typ)
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError, match="typ"):
            verifier.verify(token)

    @pytest.mark.parametrize("claim", ["iss", "aud", "exp"])
    def test_each_required_claim_is_required(self, idp, claim):
        token = idp.sign(_claims(idp, **{claim: None}))
        verifier = _verifier(idp)
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_optional_claims_are_validated_when_present(self, idp):
        future = int(time.time()) + 3600
        for bad in ({"nbf": future}, {"iat": future}, {"sub": 7}):
            verifier = _verifier(idp)
            token = idp.sign(_claims(idp, **bad))
            with pytest.raises(TokenVerificationError):
                verifier.verify(token)


@pytest.mark.parametrize("mode", ["rfc9068", "rfc7519"])
class TestEveryMode:
    def _token(self, idp, mode, **overrides):
        return idp.sign(
            _claims(idp, **overrides), typ="at+jwt" if mode == "rfc9068" else "JWT"
        )

    def test_a_valid_token_is_accepted(self, idp, mode):
        assert _verifier(idp, mode).verify(self._token(idp, mode))["sub"] == "u1"

    @pytest.mark.parametrize("claim", ["nonce", "events"])
    def test_a_token_carrying_nonce_or_events_is_rejected(self, idp, mode, claim):
        token = self._token(
            idp, mode, **{claim: {"x": {}} if claim == "events" else "n"}
        )
        verifier = _verifier(idp, mode)
        with pytest.raises(TokenVerificationError, match=claim):
            verifier.verify(token)

    def test_the_issuer_must_match_exactly(self, idp, mode):
        token = self._token(idp, mode, iss=idp.issuer + "/")
        verifier = _verifier(idp, mode)
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_the_audience_must_contain_ours(self, idp, mode):
        verifier = _verifier(idp, mode)
        token = self._token(idp, mode, aud=["other"])
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)
        assert _verifier(idp, mode).verify(
            self._token(idp, mode, aud=["other", AUDIENCE])
        )

    def test_an_hmac_token_is_rejected_by_the_allow_list(self, idp, mode):
        token = jwt.encode(
            _claims(idp),
            "a-secret-of-at-least-thirty-two-bytes",
            algorithm="HS256",
            headers={"kid": "k1"},
        )
        verifier = _verifier(idp, mode)
        with pytest.raises(TokenVerificationError, match="not accepted"):
            verifier.verify(token)


class TestLoginClientId:
    def test_an_audience_equal_to_the_login_client_is_refused(self, idp):
        with pytest.raises(ValueError, match="login client"):
            JwtVerifier.from_jwks_url(
                idp.jwks_url,
                issuer=idp.issuer,
                audience=[AUDIENCE, LOGIN_CLIENT],
                login_client_id=LOGIN_CLIENT,
            )

    def test_it_is_allowed_in_rfc9068_mode(self, idp):
        verifier = JwtVerifier.from_jwks_url(
            idp.jwks_url,
            issuer=idp.issuer,
            audience=LOGIN_CLIENT,
            login_client_id=LOGIN_CLIENT,
            mode="rfc9068",
        )
        token = idp.sign(_claims(idp, aud=LOGIN_CLIENT), typ="at+jwt")
        assert verifier.verify(token)["aud"] == LOGIN_CLIENT

    def test_a_different_audience_is_allowed_in_rfc7519_mode(self, idp):
        _verifier(idp, login_client_id=LOGIN_CLIENT)

    def test_the_constructor_applies_the_same_rule(self, idp):
        jwks = jwt.PyJWKClient(idp.jwks_url)

        with pytest.raises(ValueError, match="login client"):
            JwtVerifier(
                jwks=jwks,
                issuer=idp.issuer,
                audience=LOGIN_CLIENT,
                login_client_id=LOGIN_CLIENT,
            )
