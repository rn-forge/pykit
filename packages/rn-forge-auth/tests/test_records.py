import json
from datetime import UTC, datetime

import pytest
from rn_forge.auth.identity import LoginTransaction, SessionInfo

CREATED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
EXPIRES = datetime(2026, 2, 2, 3, 4, 5, tzinfo=UTC)
SESSION_KEYS = {
    "account_id",
    "session_version",
    "provider",
    "issuer",
    "external_subject",
    "created_at",
    "expires_at",
    "auth_time",
    "amr",
    "session_ref",
    "id_token",
}
TRANSACTION_KEYS = {
    "id",
    "provider",
    "return_to",
    "created_at",
    "state",
    "nonce",
    "code_verifier",
    "extra",
}


@pytest.mark.parametrize("auth_time", ["2026-01-01T00:00:00+00:00", None])
def test_session_old_shape_decodes_identically(auth_time: str | None) -> None:
    from rn_forge.auth.records import session_from_record

    when = datetime.fromisoformat(auth_time) if auth_time else None
    record = {
        "account_id": "acct",
        "session_version": 3,
        "provider": "provider",
        "issuer": "issuer",
        "external_subject": "external",
        "created_at": CREATED.isoformat(),
        "expires_at": EXPIRES.isoformat(),
        "auth_time": auth_time,
        "amr": ["pwd"],
        "session_ref": "sid",
        "id_token": "secret-token",
    }
    expected = SessionInfo(
        account_id="acct",
        session_version=3,
        provider="provider",
        issuer="issuer",
        external_subject="external",
        created_at=CREATED,
        expires_at=EXPIRES,
        auth_time=when,
        amr=frozenset({"pwd"}),
        session_ref="sid",
        id_token="secret-token",
    )
    assert session_from_record(record) == expected


def test_transaction_old_shape_decodes_identically() -> None:
    from rn_forge.auth.records import transaction_from_record

    record = {
        "id": "tx",
        "provider": "provider",
        "return_to": "/home",
        "created_at": CREATED.isoformat(),
        "state": "state-secret",
        "nonce": "nonce-secret",
        "code_verifier": "verifier-secret",
        "extra": {"prompt": "login"},
    }
    expected = LoginTransaction(
        id="tx",
        provider="provider",
        return_to="/home",
        created_at=CREATED,
        state="state-secret",
        nonce="nonce-secret",
        code_verifier="verifier-secret",
        extra={"prompt": "login"},
    )
    assert transaction_from_record(record) == expected


def test_transaction_extra_keeps_the_stored_mapping() -> None:
    from rn_forge.auth.records import transaction_from_record

    extra = {"prompt": "login"}
    transaction = transaction_from_record(
        {
            "id": "tx",
            "provider": "provider",
            "return_to": "/home",
            "created_at": CREATED.isoformat(),
            "state": None,
            "nonce": None,
            "code_verifier": None,
            "extra": extra,
        }
    )
    assert transaction.extra is extra


@pytest.mark.parametrize("amr", [frozenset(), frozenset({"pwd", "mfa"})])
@pytest.mark.parametrize("auth_time", [None, CREATED])
@pytest.mark.parametrize("session_ref", [None, "sid"])
@pytest.mark.parametrize("id_token", [None, "token"])
def test_session_round_trips_optional_fields(
    amr: frozenset[str],
    auth_time: datetime | None,
    session_ref: str | None,
    id_token: str | None,
) -> None:
    from rn_forge.auth.records import session_from_record, session_to_record

    session = SessionInfo(
        account_id="acct",
        session_version=3,
        provider="provider",
        issuer="issuer",
        external_subject="external",
        created_at=CREATED,
        expires_at=EXPIRES,
        auth_time=auth_time,
        amr=amr,
        session_ref=session_ref,
        id_token=id_token,
    )
    assert session_from_record(session_to_record(session)) == session


@pytest.mark.parametrize("state", [None, "s"])
@pytest.mark.parametrize("nonce", [None, "n"])
@pytest.mark.parametrize("code_verifier", [None, "v"])
@pytest.mark.parametrize("extra", [{}, {"prompt": "login"}])
def test_transaction_round_trips_optional_fields(
    state: str | None,
    nonce: str | None,
    code_verifier: str | None,
    extra: dict[str, str],
) -> None:
    from rn_forge.auth.records import transaction_from_record, transaction_to_record

    transaction = LoginTransaction(
        id="tx",
        provider="provider",
        return_to="/home",
        created_at=CREATED,
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
        extra=extra,
    )
    assert transaction_from_record(transaction_to_record(transaction)) == transaction


def test_encoded_records_are_json_serialisable() -> None:
    from rn_forge.auth.records import session_to_record, transaction_to_record

    session = SessionInfo(
        account_id="acct",
        session_version=1,
        provider="p",
        issuer="i",
        external_subject="s",
        created_at=CREATED,
        expires_at=EXPIRES,
        amr=frozenset({"z", "a"}),
    )
    transaction = LoginTransaction(
        id="tx", provider="p", return_to="/", created_at=CREATED
    )
    session_record = session_to_record(session)
    transaction_record = transaction_to_record(transaction)
    json.dumps(session_record)
    json.dumps(transaction_record)
    assert session_record["amr"] == ["a", "z"]
    assert set(session_record) == SESSION_KEYS
    assert set(transaction_record) == TRANSACTION_KEYS


@pytest.mark.parametrize("record_kind", ["session", "transaction"])
def test_secrets_are_not_in_repr(record_kind: str) -> None:
    info = SessionInfo(
        account_id="acct",
        session_version=1,
        provider="p",
        issuer="i",
        external_subject="s",
        created_at=CREATED,
        expires_at=EXPIRES,
        id_token="token-secret",
    )
    transaction = LoginTransaction(
        id="tx",
        provider="p",
        return_to="/",
        created_at=CREATED,
        state="state-secret",
        nonce="nonce-secret",
        code_verifier="verifier-secret",
    )
    if record_kind == "session":
        assert "token-secret" not in repr(info)
    else:
        for secret in ("state-secret", "nonce-secret", "verifier-secret"):
            assert secret not in repr(transaction)


@pytest.mark.parametrize(
    ("record", "missing_key"),
    [
        (
            {
                "account_id": "a",
                "session_version": 1,
                "provider": "p",
                "issuer": "i",
                "external_subject": "s",
                "created_at": CREATED.isoformat(),
                "expires_at": EXPIRES.isoformat(),
                "auth_time": None,
                "amr": [],
                "session_ref": None,
                "id_token": None,
            },
            key,
        )
        for key in SESSION_KEYS
    ],
)
def test_session_decode_requires_every_old_key(
    record: dict[str, object], missing_key: str
) -> None:
    from rn_forge.auth.records import session_from_record

    del record[missing_key]
    with pytest.raises(KeyError, match=missing_key):
        session_from_record(record)


@pytest.mark.parametrize(
    ("record", "missing_key"),
    [
        (
            {
                "id": "tx",
                "provider": "p",
                "return_to": "/",
                "created_at": CREATED.isoformat(),
                "state": None,
                "nonce": None,
                "code_verifier": None,
                "extra": {},
            },
            key,
        )
        for key in TRANSACTION_KEYS
    ],
)
def test_transaction_decode_requires_every_old_key(
    record: dict[str, object], missing_key: str
) -> None:
    from rn_forge.auth.records import transaction_from_record

    del record[missing_key]
    with pytest.raises(KeyError, match=missing_key):
        transaction_from_record(record)
