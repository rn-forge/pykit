"""Redis implementations of the session, transaction, replay and version stores.

Requires the ``redis`` extra and Redis 6.2 or later.
"""

from __future__ import annotations

import json
import math
import secrets
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import quote

from redis import Redis
from rn_forge.auth.identity import LoginTransaction, SessionInfo

__all__ = [
    "RedisAuthorizationVersions",
    "RedisReplayStore",
    "RedisSessionStore",
    "RedisTransactionStore",
]

DEFAULT_PREFIX = "rn-forge-auth:"


def _seconds(ttl: timedelta) -> int:
    return max(1, math.ceil(ttl.total_seconds()))


def _text(value: object) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class RedisTransactionStore:
    """:class:`~rn_forge.auth.stores.TransactionStore` over Redis.

    :meth:`consume` is one ``GETDEL``, so exactly one caller receives a
    transaction whichever process it runs in.

    Args:
        client: The Redis client.
        prefix: Prepended to every key.
    """

    def __init__(self, client: Redis, *, prefix: str = DEFAULT_PREFIX) -> None:
        self._client = client
        self._prefix = f"{prefix}tx:"

    def save(self, transaction: LoginTransaction, *, ttl: timedelta) -> None:
        """Store *transaction* with ``SET ... EX``."""
        document = {
            "id": transaction.id,
            "provider": transaction.provider,
            "return_to": transaction.return_to,
            "created_at": transaction.created_at.isoformat(),
            "state": transaction.state,
            "nonce": transaction.nonce,
            "code_verifier": transaction.code_verifier,
            "extra": dict(transaction.extra),
        }
        self._client.set(
            self._prefix + transaction.id, json.dumps(document), ex=_seconds(ttl)
        )

    def consume(self, transaction_id: str) -> LoginTransaction | None:
        """Remove and return the transaction with ``GETDEL``."""
        raw = _text(self._client.getdel(self._prefix + transaction_id))
        if raw is None:
            return None
        document = cast("dict[str, Any]", json.loads(raw))
        return LoginTransaction(
            id=document["id"],
            provider=document["provider"],
            return_to=document["return_to"],
            created_at=datetime.fromisoformat(document["created_at"]),
            state=document["state"],
            nonce=document["nonce"],
            code_verifier=document["code_verifier"],
            extra=cast("Mapping[str, str]", document["extra"]),
        )


class RedisSessionStore:
    """:class:`~rn_forge.auth.stores.SessionStore` over Redis.

    Each session is a JSON value whose key expires at the earlier of the idle
    expiry and ``SessionInfo.expires_at``. :meth:`rotate` removes the old key
    with ``GETDEL`` before it writes the new one.

    Args:
        client: The Redis client.
        prefix: Prepended to every key.
        clock: Returns the current time as an aware datetime.
    """

    def __init__(
        self,
        client: Redis,
        *,
        prefix: str = DEFAULT_PREFIX,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._prefix = f"{prefix}session:"
        self._clock = clock

    def create(self, session: SessionInfo, *, idle_ttl: timedelta) -> str:
        """Store *session* under a new random ID."""
        session_id = secrets.token_urlsafe(32)
        self._write(session_id, session, idle_ttl)
        return session_id

    def get(self, session_id: str) -> SessionInfo | None:
        """Return the session without changing its expiry."""
        raw = _text(self._client.get(self._prefix + session_id))
        if raw is None:
            return None
        session = _decode_session(raw)
        return session if session.expires_at > self._clock() else None

    def touch(self, session_id: str, *, idle_ttl: timedelta) -> bool:
        """Reset the key's expiry to the idle timeout, capped at ``expires_at``."""
        session = self.get(session_id)
        if session is None:
            return False
        ttl = self._ttl(session, idle_ttl)
        return bool(self._client.expire(self._prefix + session_id, _seconds(ttl)))

    def delete(self, session_id: str) -> None:
        """Remove the session."""
        self._client.delete(self._prefix + session_id)

    def rotate(self, session_id: str, *, idle_ttl: timedelta) -> str | None:
        """Move the session to a new ID."""
        raw = _text(self._client.getdel(self._prefix + session_id))
        if raw is None:
            return None
        session = _decode_session(raw)
        if session.expires_at <= self._clock():
            return None
        new_id = secrets.token_urlsafe(32)
        self._write(new_id, session, idle_ttl)
        return new_id

    def _ttl(self, session: SessionInfo, idle_ttl: timedelta) -> timedelta:
        return min(idle_ttl, session.expires_at - self._clock())

    def _write(
        self, session_id: str, session: SessionInfo, idle_ttl: timedelta
    ) -> None:
        self._client.set(
            self._prefix + session_id,
            _encode_session(session),
            ex=_seconds(self._ttl(session, idle_ttl)),
        )


def _encode_session(session: SessionInfo) -> str:
    return json.dumps(
        {
            "account_id": session.account_id,
            "session_version": session.session_version,
            "provider": session.provider,
            "issuer": session.issuer,
            "external_subject": session.external_subject,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "auth_time": _iso(session.auth_time),
            "amr": sorted(session.amr),
            "session_ref": session.session_ref,
            "id_token": session.id_token,
        }
    )


def _decode_session(raw: str) -> SessionInfo:
    document = cast("dict[str, Any]", json.loads(raw))
    return SessionInfo(
        account_id=document["account_id"],
        session_version=document["session_version"],
        provider=document["provider"],
        issuer=document["issuer"],
        external_subject=document["external_subject"],
        created_at=datetime.fromisoformat(document["created_at"]),
        expires_at=datetime.fromisoformat(document["expires_at"]),
        auth_time=_parse(document["auth_time"]),
        amr=frozenset(cast("list[str]", document["amr"])),
        session_ref=document["session_ref"],
        id_token=document["id_token"],
    )


class RedisReplayStore:
    """:class:`~rn_forge.auth.stores.ReplayStore` over Redis.

    :meth:`record_once` is one ``SET ... NX EX``.

    Args:
        client: The Redis client.
        prefix: Prepended to every key.
    """

    def __init__(self, client: Redis, *, prefix: str = DEFAULT_PREFIX) -> None:
        self._client = client
        self._seen = f"{prefix}replay:"
        self._revoked = f"{prefix}revoked-sid:"

    def record_once(self, key: str, *, ttl: timedelta) -> bool:
        """Record *key* with ``SET NX EX``."""
        return bool(self._client.set(self._seen + key, 1, nx=True, ex=_seconds(ttl)))

    def revoke_sid(self, issuer: str, sid: str, *, ttl: timedelta) -> None:
        """Mark the session revoked with ``SET EX``."""
        self._client.set(self._revoked_key(issuer, sid), 1, ex=_seconds(ttl))

    def is_sid_revoked(self, issuer: str, sid: str) -> bool:
        """Return whether the revocation key exists."""
        return bool(self._client.exists(self._revoked_key(issuer, sid)))

    def _revoked_key(self, issuer: str, sid: str) -> str:
        return f"{self._revoked}{quote(issuer, safe='')}:{quote(sid, safe='')}"


class RedisAuthorizationVersions:
    """:class:`~rn_forge.auth.context_cache.AuthorizationVersions` over Redis.

    Each bump is an ``INCR``, so it is visible to every process that shares the
    Redis server.

    Args:
        client: The Redis client.
        prefix: Prepended to every key.
    """

    def __init__(self, client: Redis, *, prefix: str = DEFAULT_PREFIX) -> None:
        self._client = client
        self._account = f"{prefix}authz-version:"
        self._global = f"{prefix}authz-version-global"

    def current(self, account_id: str) -> tuple[int, int]:
        """Read the account and global versions with one ``MGET``."""
        values = cast(
            "list[object]",
            self._client.mget([self._account_key(account_id), self._global]),
        )
        account, global_ = (int(_text(v) or 0) for v in values)
        return account, global_

    def bump(self, account_id: str) -> None:
        """Increase the account's version."""
        self._client.incr(self._account_key(account_id))

    def bump_all(self) -> None:
        """Increase the global version."""
        self._client.incr(self._global)

    def _account_key(self, account_id: str) -> str:
        return self._account + quote(account_id, safe="")
