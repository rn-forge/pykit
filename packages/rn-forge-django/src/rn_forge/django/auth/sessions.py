"""The login session, kept in ``django.contrib.sessions``.

Every read of the session goes through :meth:`Sessions.read`, which enforces
the absolute timeout and the revocation checks. Idle expiry is Django's own
session expiry: it is pushed forward on a normal read and left alone by a read
that passes ``touch=False``. This works because ``SESSION_SAVE_EVERY_REQUEST``
is false (see :data:`SESSION_SETTINGS`), so an unmodified session is not
re-saved and its expiry does not move.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from rn_forge.auth import (
    AuthorizationContext,
    AuthorizationContextProvider,
    ReplayStore,
    SessionInfo,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "SESSION_COOKIE",
    "SESSION_SETTINGS",
    "ActiveSession",
    "Sessions",
    "check_session_settings",
    "rotate_session",
]

SESSION_COOKIE: Final = "__Host-session"
SESSION_KEY = "rn_forge_auth"

SESSION_SETTINGS: Final[dict[str, Any]] = {
    "SESSION_ENGINE": "django.contrib.sessions.backends.cached_db",
    "SESSION_COOKIE_NAME": SESSION_COOKIE,
    "SESSION_COOKIE_SECURE": True,
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_PATH": "/",
    "SESSION_COOKIE_DOMAIN": None,
    "SESSION_SAVE_EVERY_REQUEST": False,
}
"""Django settings for the session and its cookie.

Spread into your settings module: ``globals().update(SESSION_SETTINGS)``.
The ``__Host-`` prefix forbids a ``Domain`` and requires ``Secure`` and
``Path=/``. ``SESSION_SAVE_EVERY_REQUEST`` stays false so that reading the
session does not extend it.
"""

_SIGNED_COOKIES = "django.contrib.sessions.backends.signed_cookies"
_DB_ENGINES = (
    "django.contrib.sessions.backends.db",
    "django.contrib.sessions.backends.cached_db",
)


@dataclass(frozen=True)
class ActiveSession:
    """A session that passed every check, with its account's current context.

    Attributes:
        info: The session's content.
        context: The account's authorization context.
    """

    info: SessionInfo
    context: AuthorizationContext


def rotate_session(request: HttpRequest) -> None:
    """Give the request's session a new ID and keep its content.

    Call it after a change of the account's privileges, so a session ID that
    was seen before the change is useless afterwards.
    """
    request.session.cycle_key()


def check_session_settings(*, cache_aliases: Iterable[str]) -> None:
    """Refuse session settings that cannot work or are unsafe.

    ``SESSION_SAVE_EVERY_REQUEST`` must be false in every mode. Outside
    ``DEBUG``, the cookie settings must equal :data:`SESSION_SETTINGS`, the
    session engine must be ``db`` or ``cached_db`` (a signed-cookie engine
    cannot revoke sessions), and neither the session
    cache nor *cache_aliases* may be Django's local-memory cache.

    Raises:
        ImproperlyConfigured: A setting is refused.
    """
    if settings.SESSION_SAVE_EVERY_REQUEST:
        raise ImproperlyConfigured(
            "SESSION_SAVE_EVERY_REQUEST must be False: it would let "
            "GET /auth/session extend the session"
        )
    if settings.DEBUG:
        return
    if settings.SESSION_ENGINE == _SIGNED_COOKIES:
        raise ImproperlyConfigured(
            "The signed-cookie session engine cannot revoke sessions; use "
            "the db or cached_db engine"
        )
    if settings.SESSION_ENGINE not in _DB_ENGINES:
        raise ImproperlyConfigured(
            f"SESSION_ENGINE {settings.SESSION_ENGINE!r} is not supported; "
            "use the db or cached_db engine"
        )
    for name, expected in SESSION_SETTINGS.items():
        if name != "SESSION_ENGINE" and getattr(settings, name) != expected:
            raise ImproperlyConfigured(f"{name} must be {expected!r}")
    aliases = list(cache_aliases)
    if settings.SESSION_ENGINE == _DB_ENGINES[1]:
        aliases.append(settings.SESSION_CACHE_ALIAS)
    for alias in aliases:
        if isinstance(caches[alias], LocMemCache):
            raise ImproperlyConfigured(
                f"Cache {alias!r} is Django's local-memory cache, which is not "
                "shared between processes; use the Redis cache backend"
            )


class Sessions:
    """Starts, reads and ends login sessions.

    Args:
        contexts: Supplies the account's current context for the checks.
        replay: Says which ``(issuer, sid)`` pairs are revoked.
        idle_timeout: How long a session may sit unused.
        absolute_timeout: How long a session lives whatever its use.
    """

    def __init__(
        self,
        *,
        contexts: AuthorizationContextProvider,
        replay: ReplayStore,
        idle_timeout: timedelta,
        absolute_timeout: timedelta,
    ) -> None:
        self._contexts = contexts
        self._replay = replay
        self._idle = idle_timeout
        self._absolute = absolute_timeout

    @staticmethod
    def now() -> datetime:
        """The current time, aware."""
        return datetime.now(UTC)

    def start(self, request: HttpRequest, info: SessionInfo) -> None:
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
        request.session.set_expiry(self._remaining(info, self.now()))

    def read(self, request: HttpRequest, *, touch: bool = True) -> ActiveSession | None:
        """Return the request's session, or ``None`` when it has none.

        A session past its absolute timeout, whose recorded version differs
        from its account's, whose account is inactive, or whose ``session_ref``
        is revoked, is deleted and read as absent.

        Args:
            request: The request.
            touch: Move the idle expiry forward. ``False`` reads without
                extending the session.
        """
        document: dict[str, Any] | None = request.session.get(SESSION_KEY)
        if document is None:
            return None
        info = _parse(document)
        moment = self.now()
        if moment >= info.expires_at:
            return self._reject(request)
        context = self._contexts.resolve(info.account_id)
        if (
            not context.active
            or context.session_version != info.session_version
            or (
                info.session_ref is not None
                and self._replay.is_sid_revoked(info.issuer, info.session_ref)
            )
        ):
            return self._reject(request)
        if touch:
            request.session.set_expiry(self._remaining(info, moment))
        return ActiveSession(info, context)

    def end(self, request: HttpRequest) -> None:
        """Delete the request's session and its cookie."""
        request.session.flush()

    def _reject(self, request: HttpRequest) -> None:
        self.end(request)

    def _remaining(self, info: SessionInfo, moment: datetime) -> int:
        """Seconds until the idle expiry, capped at the absolute timeout."""
        return max(1, int(min(self._idle, info.expires_at - moment).total_seconds()))


def _parse(document: dict[str, Any]) -> SessionInfo:
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
