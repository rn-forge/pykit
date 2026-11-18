"""JSON-safe mappings for persisted sessions and login transactions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from rn_forge.auth.identity import LoginTransaction, SessionInfo

__all__ = [
    "session_from_record",
    "session_to_record",
    "transaction_from_record",
    "transaction_to_record",
]


def session_to_record(info: SessionInfo) -> dict[str, Any]:
    """Return the mapping with the eleven persisted session fields for *info*."""
    return {
        "account_id": info.account_id,
        "session_version": info.session_version,
        "provider": info.provider,
        "issuer": info.issuer,
        "external_subject": info.external_subject,
        "created_at": info.created_at.isoformat(),
        "expires_at": info.expires_at.isoformat(),
        "auth_time": info.auth_time.isoformat() if info.auth_time is not None else None,
        "amr": sorted(info.amr),
        "session_ref": info.session_ref,
        "id_token": info.id_token,
    }


def session_from_record(record: dict[str, Any]) -> SessionInfo:
    """Build a session from a mapping containing every persisted session field."""
    auth_time = record["auth_time"]
    return SessionInfo(
        account_id=record["account_id"],
        session_version=record["session_version"],
        provider=record["provider"],
        issuer=record["issuer"],
        external_subject=record["external_subject"],
        created_at=datetime.fromisoformat(record["created_at"]),
        expires_at=datetime.fromisoformat(record["expires_at"]),
        auth_time=datetime.fromisoformat(auth_time) if auth_time is not None else None,
        amr=frozenset(cast("list[str]", record["amr"])),
        session_ref=record["session_ref"],
        id_token=record["id_token"],
    )


def transaction_to_record(tx: LoginTransaction) -> dict[str, Any]:
    """Return the mapping with the eight persisted transaction fields for *tx*."""
    return {
        "id": tx.id,
        "provider": tx.provider,
        "return_to": tx.return_to,
        "created_at": tx.created_at.isoformat(),
        "state": tx.state,
        "nonce": tx.nonce,
        "code_verifier": tx.code_verifier,
        "extra": dict(tx.extra),
    }


def transaction_from_record(record: dict[str, Any]) -> LoginTransaction:
    """Build a transaction from a complete mapping, retaining its ``extra`` mapping."""
    return LoginTransaction(
        id=record["id"],
        provider=record["provider"],
        return_to=record["return_to"],
        created_at=datetime.fromisoformat(record["created_at"]),
        state=record["state"],
        nonce=record["nonce"],
        code_verifier=record["code_verifier"],
        extra=record["extra"],
    )
