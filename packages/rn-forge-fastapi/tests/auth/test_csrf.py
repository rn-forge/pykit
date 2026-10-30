"""The CSRF store and the checks, without an application around them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rn_forge.fastapi import CsrfProtection, CsrfStore, InMemoryCsrfStore
from rn_forge.web import CsrfFailed

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
OWN = {"host": "app.example"}


def _check(protection: CsrfProtection, **overrides: object) -> None:
    arguments: dict[str, object] = {
        "method": "POST",
        "headers": {"origin": "https://app.example", "x-xsrf-token": "t", **OWN},
        "scheme": "https",
        "peer": "10.0.0.1",
        "expected": "t",
    }
    protection.check(**arguments | overrides)  # type: ignore[arg-type]


@pytest.fixture
def protection() -> CsrfProtection:
    return CsrfProtection(store=InMemoryCsrfStore(), problem_type_base="")


class TestInMemoryCsrfStore:
    def test_it_satisfies_the_protocol(self) -> None:
        assert isinstance(InMemoryCsrfStore(), CsrfStore)

    def test_a_token_round_trips_and_is_deleted(self) -> None:
        store = InMemoryCsrfStore()
        store.save("k", "t", ttl=timedelta(minutes=1))

        assert store.get("k") == "t"
        store.delete("k")
        assert store.get("k") is None

    def test_a_token_expires(self) -> None:
        moment = [NOW]
        store = InMemoryCsrfStore(clock=lambda: moment[0])
        store.save("k", "t", ttl=timedelta(minutes=10))

        moment[0] = NOW + timedelta(minutes=9)
        assert store.get("k") == "t"
        moment[0] = NOW + timedelta(minutes=10)
        assert store.get("k") is None


class TestCheck:
    def test_a_matching_token_and_own_origin_pass(
        self, protection: CsrfProtection
    ) -> None:
        _check(protection)

    def test_a_safe_method_needs_nothing(self, protection: CsrfProtection) -> None:
        _check(protection, method="GET", headers={}, expected=None)

    def test_a_mismatched_token_fails(self, protection: CsrfProtection) -> None:
        with pytest.raises(CsrfFailed):
            _check(protection, expected="other")

    def test_a_non_ascii_token_fails_instead_of_raising_a_type_error(
        self, protection: CsrfProtection
    ) -> None:
        headers = {"origin": "https://app.example", "x-xsrf-token": "é", **OWN}

        with pytest.raises(CsrfFailed):
            _check(protection, headers=headers)

    def test_no_stored_token_fails(self, protection: CsrfProtection) -> None:
        with pytest.raises(CsrfFailed):
            _check(protection, expected=None)

    def test_the_proxy_peer_is_matched_by_network(self) -> None:
        protection = CsrfProtection(
            store=InMemoryCsrfStore(),
            problem_type_base="",
            trusted_proxies=["10.0.0.0/8"],
        )
        headers = {
            "origin": "https://public.example",
            "x-xsrf-token": "t",
            "host": "internal",
            "x-forwarded-host": "public.example",
            "x-forwarded-proto": "https",
        }

        _check(protection, headers=headers, scheme="http", peer="10.1.2.3")
        with pytest.raises(CsrfFailed):
            _check(protection, headers=headers, scheme="http", peer="192.0.2.1")
        with pytest.raises(CsrfFailed):
            _check(protection, headers=headers, scheme="http", peer=None)


def test_an_anonymous_id_cannot_be_a_session_id(protection: CsrfProtection) -> None:
    assert protection.is_anonymous(protection.new_anonymous_id())
    assert not protection.is_anonymous("abc-_123")
    assert not protection.is_anonymous(None)
