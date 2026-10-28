"""The login session's content, kept in ``django.contrib.sessions``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.http import HttpRequest
from rn_forge.auth import SessionInfo

__all__ = ["end_session", "read_session", "start_session"]

SESSION_KEY = "rn_forge_auth"


def start_session(request: HttpRequest, info: SessionInfo) -> None:
    """Store *info* under a new session ID, so a pre-login ID is never reused."""
    request.session.cycle_key()
    request.session[SESSION_KEY] = {
        "account_id": info.account_id,
        "session_version": info.session_version,
        "provider": info.provider,
        "issuer": info.issuer,
        "external_subject": info.external_subject,
        "created_at": info.created_at.isoformat(),
        "expires_at": info.expires_at.isoformat(),
        "auth_time": info.auth_time.isoformat() if info.auth_time else None,
        "amr": sorted(info.amr),
        "session_ref": info.session_ref,
        "id_token": info.id_token,
    }


def read_session(request: HttpRequest) -> SessionInfo | None:
    """Return the request's login session, or ``None`` when it has none."""
    document: dict[str, Any] | None = request.session.get(SESSION_KEY)
    if document is None:
        return None
    auth_time = document["auth_time"]
    return SessionInfo(
        account_id=document["account_id"],
        session_version=document["session_version"],
        provider=document["provider"],
        issuer=document["issuer"],
        external_subject=document["external_subject"],
        created_at=datetime.fromisoformat(document["created_at"]),
        expires_at=datetime.fromisoformat(document["expires_at"]),
        auth_time=datetime.fromisoformat(auth_time) if auth_time else None,
        amr=frozenset(document["amr"]),
        session_ref=document["session_ref"],
        id_token=document["id_token"],
    )


def end_session(request: HttpRequest) -> None:
    """Delete the request's session and its cookie."""
    request.session.flush()
