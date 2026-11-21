from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest
from rn_forge.auth import (
    AccountRejected,
    AuthorizationContext,
    CompletedLogin,
    ExternalIdentity,
    LoginFailed,
    SessionInfo,
)
from rn_forge.auth.admission import AdmittedLogin, admit_login

pytestmark = pytest.mark.unit


class _Accounts:
    def __init__(self, account_id: str | None = "acct-ada") -> None:
        self.account_id = account_id
        self.reject_reason: str | None = None
        self.identities: list[ExternalIdentity] = []

    def resolve(self, identity: ExternalIdentity) -> str:
        self.identities.append(identity)
        if self.reject_reason is not None:
            raise AccountRejected(self.reject_reason)
        assert self.account_id is not None
        return self.account_id

    def lookup(self, issuer: str, subject: str) -> str | None:
        return self.account_id


class _Contexts:
    def __init__(self, context: AuthorizationContext) -> None:
        self.context = context
        self.accounts: list[str] = []

    def resolve(self, account_id: str) -> AuthorizationContext:
        self.accounts.append(account_id)
        return self.context


def _identity() -> ExternalIdentity:
    return ExternalIdentity(
        provider="other",
        issuer="https://issuer.example",
        subject="subject-ada",
        auth_time=datetime(2026, 1, 2, tzinfo=UTC),
        amr=frozenset({"pwd", "mfa"}),
        session_ref="session-ref",
        id_token="id-token",
    )


def _admit(
    completed: CompletedLogin,
    *,
    accounts: _Accounts | None = None,
    contexts: _Contexts | None = None,
) -> AdmittedLogin:
    return admit_login(
        completed,
        provider_id="acme",
        accounts=accounts or _Accounts(),
        contexts=contexts
        or _Contexts(AuthorizationContext(active=True, session_version=4)),
        now=datetime(2026, 2, 3, tzinfo=UTC),
        absolute_timeout=timedelta(hours=12),
        return_to_prefixes=["/app"],
        default_return_to="/home",
    )


def test_admit_login_builds_the_session_content() -> None:
    now = datetime(2026, 2, 3, tzinfo=UTC)
    admitted = _admit(CompletedLogin(_identity(), "/app/orders"))
    assert isinstance(admitted, AdmittedLogin)
    assert admitted.account_id == "acct-ada"
    assert admitted.session == SessionInfo(
        account_id="acct-ada",
        session_version=4,
        provider="other",
        issuer="https://issuer.example",
        external_subject="subject-ada",
        created_at=now,
        expires_at=now + timedelta(hours=12),
        auth_time=datetime(2026, 1, 2, tzinfo=UTC),
        amr=frozenset({"pwd", "mfa"}),
        session_ref="session-ref",
        id_token="id-token",
    )


def test_admit_login_keeps_a_valid_return_to() -> None:
    assert _admit(CompletedLogin(_identity(), "/app/orders")).return_to == "/app/orders"


@pytest.mark.parametrize("return_to", ["//evil.example", "/other"])
def test_admit_login_replaces_an_invalid_return_to_with_the_default(
    return_to: str,
) -> None:
    assert _admit(CompletedLogin(_identity(), return_to)).return_to == "/home"


def test_a_rejected_identity_is_not_provisioned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    accounts = _Accounts()
    accounts.reject_reason = "not provisioned"
    contexts = _Contexts(AuthorizationContext(active=True, session_version=4))
    caplog.set_level(logging.INFO)
    login = CompletedLogin(_identity(), "/app")
    with pytest.raises(LoginFailed) as caught:
        _admit(login, accounts=accounts, contexts=contexts)
    assert caught.value.code == "account_not_provisioned"
    assert caught.value.reason == "not provisioned"
    assert contexts.accounts == []
    assert [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("audit event=")
    ] == ["audit event=account.rejected provider='acme' reason='not provisioned'"]


def test_an_inactive_account_is_access_denied(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    login = CompletedLogin(_identity(), "/app")
    contexts = _Contexts(AuthorizationContext(active=False, session_version=4))
    with pytest.raises(LoginFailed) as caught:
        _admit(login, contexts=contexts)
    assert caught.value.code == "access_denied"
    assert caught.value.reason == "account is not active"
    assert [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("audit event=")
    ] == ["audit event=account.disabled account_id='acct-ada' provider='acme'"]


def test_admission_emits_neither_login_success_nor_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    _admit(CompletedLogin(_identity(), "/app"))
    rejected = _Accounts()
    rejected.reject_reason = "not provisioned"
    for accounts, contexts in (
        (rejected, _Contexts(AuthorizationContext(active=True, session_version=4))),
        (_Accounts(), _Contexts(AuthorizationContext(active=False, session_version=4))),
    ):
        login = CompletedLogin(_identity(), "/app")
        with pytest.raises(LoginFailed):
            _admit(login, accounts=accounts, contexts=contexts)
    events = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("audit event=")
    ]
    assert not any(
        "login.success" in event or "login.failure" in event for event in events
    )
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def test_the_audit_provider_is_the_provider_id_argument(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    admitted = _admit(CompletedLogin(_identity(), "/app"))
    assert admitted.session.provider == "other"
    accounts = _Accounts()
    accounts.reject_reason = "not provisioned"
    login = CompletedLogin(_identity(), "/app")
    with pytest.raises(LoginFailed):
        _admit(login, accounts=accounts)
    assert any("provider='acme'" in record.getMessage() for record in caplog.records)


def test_the_result_is_frozen() -> None:
    admitted = _admit(CompletedLogin(_identity(), "/app"))
    with pytest.raises(FrozenInstanceError):
        admitted.return_to = "/elsewhere"  # type: ignore[misc]
