"""Tests for rn_forge.auth.flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from assertpy import assert_that

from rn_forge.auth import (
    ExternalIdentity,
    InMemoryTransactionStore,
    LoginFailed,
    LoginFlow,
    LoginStart,
    LoginTransaction,
    ProviderKind,
    SessionInfo,
)

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class _Request:
    query: dict[str, str] = field(default_factory=dict[str, str])
    form: dict[str, str] = field(default_factory=dict[str, str])


class _Provider:
    kind: ProviderKind = "development"

    def __init__(self, id: str, *, fail_with: Exception | None = None) -> None:
        self.id = id
        self._fail_with = fail_with
        self.completed: list[LoginTransaction] = []

    def begin(self, request: _Request, *, return_to: str) -> LoginStart:
        if self._fail_with is not None:
            raise self._fail_with
        transaction = LoginTransaction(
            id=f"tx-{len(self.completed)}-{return_to}",
            provider=self.id,
            return_to=return_to,
            created_at=datetime.now(UTC),
        )
        return LoginStart(transaction, "https://idp.example/authorize")

    def complete(
        self, request: _Request, transaction: LoginTransaction
    ) -> ExternalIdentity:
        if self._fail_with is not None:
            raise self._fail_with
        self.completed.append(transaction)
        return ExternalIdentity(self.id, "local", "u1")

    def logout_redirect(
        self, session: SessionInfo, *, post_logout_redirect: str
    ) -> str | None:
        return None


class _Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def _flow(
    *providers: _Provider, clock: _Clock | None = None
) -> tuple[LoginFlow[_Request], InMemoryTransactionStore]:
    store = InMemoryTransactionStore(clock=clock or _Clock())
    flow = LoginFlow[_Request](
        {p.id: p for p in providers}, store, return_to_prefixes=["/app"]
    )
    return flow, store


def test_begin_saves_the_transaction_and_returns_the_start() -> None:
    provider = _Provider("a")
    flow, _ = _flow(provider)

    start = flow.begin("a", _Request(), return_to="/app/orders")
    identity = flow.complete("a", _Request(), transaction_id=start.transaction.id)

    assert_that(start.redirect_url).is_equal_to("https://idp.example/authorize")
    assert_that(identity.subject).is_equal_to("u1")
    assert_that(provider.completed).is_equal_to([start.transaction])


@pytest.mark.parametrize(
    "return_to", ["https://evil.example/app", "//evil.example", "/other", ""]
)
def test_begin_rejects_a_return_to_outside_the_prefixes(return_to: str) -> None:
    flow, _ = _flow(_Provider("a"))

    with pytest.raises(LoginFailed) as caught:
        flow.begin("a", _Request(), return_to=return_to)

    assert_that(caught.value.code).is_equal_to("login_failed")


def test_an_unknown_provider_fails() -> None:
    flow, _ = _flow(_Provider("a"))

    with pytest.raises(LoginFailed):
        flow.begin("b", _Request(), return_to="/app")
    with pytest.raises(LoginFailed):
        flow.complete("b", _Request(), transaction_id="x")


def test_a_transaction_is_consumed_once() -> None:
    flow, _ = _flow(_Provider("a"))
    start = flow.begin("a", _Request(), return_to="/app")
    flow.complete("a", _Request(), transaction_id=start.transaction.id)

    with pytest.raises(LoginFailed) as caught:
        flow.complete("a", _Request(), transaction_id=start.transaction.id)

    assert_that(caught.value.code).is_equal_to("login_failed")


@pytest.mark.parametrize("transaction_id", [None, "", "unknown"])
def test_a_missing_transaction_fails(transaction_id: str | None) -> None:
    flow, _ = _flow(_Provider("a"))

    with pytest.raises(LoginFailed):
        flow.complete("a", _Request(), transaction_id=transaction_id)


def test_a_transaction_expires_after_600_seconds_by_default() -> None:
    clock = _Clock()
    flow, _ = _flow(_Provider("a"), clock=clock)
    start = flow.begin("a", _Request(), return_to="/app")
    clock.now = 600.0

    with pytest.raises(LoginFailed):
        flow.complete("a", _Request(), transaction_id=start.transaction.id)


def test_a_transaction_is_valid_just_before_the_ttl() -> None:
    clock = _Clock()
    flow, _ = _flow(_Provider("a"), clock=clock)
    start = flow.begin("a", _Request(), return_to="/app")
    clock.now = 599.0

    flow.complete("a", _Request(), transaction_id=start.transaction.id)


def test_the_ttl_is_configurable() -> None:
    clock = _Clock()
    store = InMemoryTransactionStore(clock=clock)
    flow = LoginFlow[_Request](
        {"a": _Provider("a")},
        store,
        return_to_prefixes=["/"],
        ttl=timedelta(seconds=10),
    )
    start = flow.begin("a", _Request(), return_to="/x")
    clock.now = 10.0

    with pytest.raises(LoginFailed):
        flow.complete("a", _Request(), transaction_id=start.transaction.id)


def test_a_transaction_of_another_provider_fails() -> None:
    first, second = _Provider("a"), _Provider("b")
    flow, _ = _flow(first, second)
    start = flow.begin("a", _Request(), return_to="/app")

    with pytest.raises(LoginFailed):
        flow.complete("b", _Request(), transaction_id=start.transaction.id)

    assert_that(second.completed).is_empty()


def test_a_provider_login_failed_passes_through() -> None:
    denied = LoginFailed("access_denied", "denied")
    flow, _ = _flow(_Provider("a", fail_with=denied))
    store_start = _Provider("a").begin(_Request(), return_to="/app")
    flow._transactions.save(store_start.transaction, ttl=timedelta(seconds=60))  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(LoginFailed) as caught:
        flow.complete("a", _Request(), transaction_id=store_start.transaction.id)

    assert_that(caught.value.code).is_equal_to("access_denied")


def test_any_other_provider_error_becomes_login_failed() -> None:
    flow, _ = _flow(_Provider("a", fail_with=RuntimeError("boom")))

    with pytest.raises(LoginFailed) as caught:
        flow.begin("a", _Request(), return_to="/app")

    assert_that(caught.value.code).is_equal_to("login_failed")
    assert_that(caught.value.reason).does_not_contain("boom")


def test_the_failure_reason_goes_to_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    flow, _ = _flow(_Provider("a"))

    with pytest.raises(LoginFailed):
        flow.complete("a", _Request(), transaction_id="unknown")

    assert_that(caplog.text).contains("transaction missing, expired or used")
