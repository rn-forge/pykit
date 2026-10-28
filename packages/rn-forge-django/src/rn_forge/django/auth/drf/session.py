"""Session authentication for DRF: the login session as a :class:`~rn_forge.auth.Principal`."""

from __future__ import annotations

from typing import ClassVar, override

from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request
from rn_forge.auth import Principal, SessionInfo
from rn_forge.django.auth.routes import AuthRoutesConfig
from rn_forge.django.auth.sessions import Sessions
from rn_forge.django.drf import RequestUtils
from rn_forge.django.drf.exceptions import NO_CHALLENGE

__all__ = ["PrincipalSessionAuthentication", "sessions_for"]


def sessions_for(config: AuthRoutesConfig) -> Sessions:
    """A :class:`Sessions` with the same collaborators and timeouts as the routes of *config*."""
    return Sessions(
        contexts=config.contexts,
        replay=config.replay,
        idle_timeout=config.idle_timeout,
        absolute_timeout=config.absolute_timeout,
    )


class PrincipalSessionAuthentication(BaseAuthentication):
    """Authenticate the login session into a ``mechanism="session"`` principal.

    Subclass and set ``sessions``, typically to ``sessions_for(config)`` of the
    :class:`~rn_forge.django.auth.routes.AuthRoutesConfig` given to
    ``auth_urlpatterns``. ``request.auth`` is the session's
    :class:`~rn_forge.auth.SessionInfo`. The read extends the idle timeout.

    A request with an ``Authorization`` header is never authenticated here:
    list a bearer class first and the header alone decides, so an invalid token
    is a ``401`` even with a valid session cookie.

    As the first authentication class of a view, an unauthenticated request is
    a ``401`` problem with no ``WWW-Authenticate`` header, provided the view
    uses :func:`~rn_forge.django.drf.exceptions.problem_details_exception_handler`.
    A bearer class first keeps the ``Bearer`` challenge.
    """

    sessions: ClassVar[Sessions]

    @override
    def authenticate(self, request: Request) -> tuple[Principal, SessionInfo] | None:
        django_request = RequestUtils.get_django_request(request)
        if "Authorization" in django_request.headers:
            return None
        active = self.sessions.read(django_request)
        if active is None:
            return None
        info, context = active.info, active.context
        tenant = context.attributes.get("tenant")
        principal = Principal(
            subject=info.account_id,
            issuer=info.issuer,
            external_subject=info.external_subject,
            permissions=context.permissions,
            roles=context.roles,
            tenant=tenant if isinstance(tenant, str) else None,
            attributes=context.attributes,
            mechanism="session",
            auth_time=info.auth_time,
            amr=info.amr,
        )
        return principal, info

    @override
    def authenticate_header(self, request: Request) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]  # DRF stubs type the base as returning None; DRF reads a str
        return NO_CHALLENGE
