"""RP-initiated logout (OidcProvider.logout_redirect) and BackchannelLogout."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

pytest.importorskip("authlib")

from rn_forge.auth import (  # noqa: E402
    ExternalIdentity,
    InMemoryReplayStore,
    SessionInfo,
)
from rn_forge.auth.oidc import (  # noqa: E402
    BackchannelLogout,
    LogoutRevocation,
    LogoutTokenVerifier,
    OidcProvider,
    TokenVerificationError,
)
from rn_forge.auth.testing import FakeOidcProvider  # noqa: E402

pytestmark = pytest.mark.unit

type Make = Callable[..., OidcProvider]


def _session(id_token: str | None = "the.id.token") -> SessionInfo:
    now = datetime.now(UTC)
    return SessionInfo(
        account_id="acc-1",
        session_version=1,
        provider="acme",
        issuer="x",
        external_subject="u1",
        created_at=now,
        expires_at=now + timedelta(hours=8),
        id_token=id_token,
    )


class TestLogoutRedirect:
    def test_enabled_returns_the_end_session_url(
        self, idp: FakeOidcProvider, make_provider: Make
    ) -> None:
        provider = make_provider(rp_initiated_logout=True)

        url = provider.logout_redirect(
            _session(), post_logout_redirect="https://app.example/bye"
        )

        assert url is not None
        parts = urlsplit(url)
        assert url.removesuffix(f"?{parts.query}") == idp.end_session_endpoint
        assert parse_qs(parts.query) == {
            "id_token_hint": ["the.id.token"],
            "post_logout_redirect_uri": ["https://app.example/bye"],
            "client_id": [idp.client_id],
        }

    def test_disabled_by_default(
        self, idp: FakeOidcProvider, make_provider: Make
    ) -> None:
        assert (
            make_provider().logout_redirect(_session(), post_logout_redirect="/bye")
            is None
        )

    def test_no_end_session_endpoint_returns_none(
        self, idp: FakeOidcProvider, make_provider: Make
    ) -> None:
        idp.advertise_end_session = False
        provider = make_provider(rp_initiated_logout=True)

        assert provider.logout_redirect(_session(), post_logout_redirect="/bye") is None

    def test_no_id_token_returns_none(
        self, idp: FakeOidcProvider, make_provider: Make
    ) -> None:
        provider = make_provider(rp_initiated_logout=True)

        assert (
            provider.logout_redirect(_session(None), post_logout_redirect="/bye")
            is None
        )

    def test_oauth2_mode_returns_none(
        self, idp: FakeOidcProvider, make_oauth2_provider: Make
    ) -> None:
        provider = make_oauth2_provider()

        assert provider.logout_redirect(_session(), post_logout_redirect="/bye") is None


class _Accounts:
    def __init__(self, linked: dict[tuple[str, str], str]) -> None:
        self._linked = linked

    def resolve(self, identity: ExternalIdentity) -> str:
        raise AssertionError("a logout never provisions")

    def lookup(self, issuer: str, subject: str) -> str | None:
        return self._linked.get((issuer, subject))


@pytest.fixture
def handler(idp: FakeOidcProvider) -> BackchannelLogout:
    verifier = LogoutTokenVerifier.from_jwks_url(
        idp.jwks_url,
        issuer=idp.issuer,
        client_id=idp.client_id,
        replay_store=InMemoryReplayStore(),
    )
    return BackchannelLogout(verifier, _Accounts({(idp.issuer, "u1"): "acc-1"}))


class TestBackchannelLogout:
    def test_a_sid_names_the_session_to_revoke(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        result = handler.handle(idp.logout_token(sid="s-1"))

        assert result == LogoutRevocation(idp.issuer, sid="s-1")

    def test_a_sid_wins_over_a_sub(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        result = handler.handle(idp.logout_token(sid="s-1", sub="u1"))

        assert result == LogoutRevocation(idp.issuer, sid="s-1", subject="u1")

    def test_a_linked_sub_names_the_account(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        result = handler.handle(idp.logout_token(sub="u1"))

        assert result == LogoutRevocation(idp.issuer, subject="u1", account_id="acc-1")

    def test_an_unlinked_sub_names_no_account(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        result = handler.handle(idp.logout_token(sub="stranger"))

        assert result.account_id is None
        assert result.sid is None

    def test_a_nonce_is_rejected(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        token = idp.logout_token(sid="s-1", nonce="n")
        with pytest.raises(TokenVerificationError, match="nonce"):
            handler.handle(token)

    def test_a_replayed_jti_is_rejected(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        token = idp.logout_token(sid="s-1")
        handler.handle(token)

        with pytest.raises(TokenVerificationError, match="already used"):
            handler.handle(token)

    def test_a_stale_iat_is_rejected(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        token = idp.logout_token(sid="s-1", iat=int(time.time()) - 3600)

        with pytest.raises(TokenVerificationError, match="issued more than"):
            handler.handle(token)

    def test_an_id_token_is_rejected(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": idp.issuer,
            "aud": idp.client_id,
            "sub": "u1",
            "sid": "s-1",
            "iat": now,
            "exp": now + 300,
            "nonce": "n",
        }

        token = idp.sign(claims, typ="JWT")
        with pytest.raises(TokenVerificationError):
            handler.handle(token)

    def test_a_forged_signature_is_rejected(
        self, idp: FakeOidcProvider, handler: BackchannelLogout
    ) -> None:
        token = idp.logout_token(sid="s-1")
        forged = token.rsplit(".", 1)[0] + ".AAAA"

        with pytest.raises(TokenVerificationError):
            handler.handle(forged)
