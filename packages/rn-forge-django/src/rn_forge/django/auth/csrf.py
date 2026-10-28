"""CSRF protection for the session-authenticated routes.

Django's ``CsrfViewMiddleware`` checks the token and, for an ``Origin`` or
(over HTTPS) ``Referer`` header, that the origin is the request's own or in
``CSRF_TRUSTED_ORIGINS``. Django takes the request's scheme and host from
forwarded headers only through ``SECURE_PROXY_SSL_HEADER`` and
``USE_X_FORWARDED_HOST``, which is how a proxy becomes trusted.
:class:`AuthCsrfMiddleware` adds what Django lacks: it rejects
``Sec-Fetch-Site: cross-site`` and skips requests that carry a ``Bearer``
``Authorization`` header.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.middleware.csrf import CsrfViewMiddleware
from rn_forge.commons.logging import AppLogger
from rn_forge.django import settings as facade
from rn_forge.django.exceptions import problem_details_response
from rn_forge.web import CsrfFailed, default_registry

__all__ = [
    "CSRF_FAILURE_VIEW",
    "CSRF_MIDDLEWARE",
    "CSRF_SETTINGS",
    "AuthCsrfMiddleware",
    "check_csrf_settings",
    "csrf_failure_view",
    "enforce_csrf",
]

_LOGGER = AppLogger.get_logger(__name__)

CSRF_MIDDLEWARE: Final = "rn_forge.django.auth.csrf.AuthCsrfMiddleware"
CSRF_FAILURE_VIEW: Final = "rn_forge.django.auth.csrf.csrf_failure_view"

CSRF_SETTINGS: Final[dict[str, Any]] = {
    "CSRF_COOKIE_NAME": "XSRF-TOKEN",
    "CSRF_HEADER_NAME": "HTTP_X_XSRF_TOKEN",
    "CSRF_COOKIE_HTTPONLY": False,
    "CSRF_COOKIE_SECURE": True,
    "CSRF_COOKIE_SAMESITE": "Lax",
    "CSRF_COOKIE_PATH": "/",
    "CSRF_COOKIE_DOMAIN": None,
    "CSRF_USE_SESSIONS": False,
    "CSRF_FAILURE_VIEW": CSRF_FAILURE_VIEW,
}
"""Django settings for the CSRF cookie and header.

Spread into your settings module with ``globals().update(CSRF_SETTINGS)``, and
add :data:`CSRF_MIDDLEWARE` to ``MIDDLEWARE``. The names are Angular's
``HttpClient`` defaults, and the cookie is readable by script, which Angular
needs to copy it into the header.
"""

# Settings the check enforces in every mode; the rest only outside DEBUG.
_ALWAYS = (
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "CSRF_COOKIE_HTTPONLY",
    "CSRF_USE_SESSIONS",
    "CSRF_FAILURE_VIEW",
)


class AuthCsrfMiddleware(CsrfViewMiddleware):
    """``CsrfViewMiddleware`` plus the cross-site and bearer rules."""

    def process_view(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        request: HttpRequest,
        callback: Callable[..., HttpResponseBase],
        callback_args: tuple[Any, ...],
        callback_kwargs: dict[str, Any],
    ) -> HttpResponseBase | None:
        """Check *request* unless it is exempt, safe, or carries credentials."""
        if _is_bearer(request):
            # A browser never adds a Bearer credential on its own; it does
            # replay cached Basic credentials, so those stay checked.
            request.csrf_processing_done = True  # type: ignore[attr-defined]
            return None
        if (
            request.method not in ("GET", "HEAD", "OPTIONS", "TRACE")
            and not getattr(callback, "csrf_exempt", False)
            and request.META.get("HTTP_SEC_FETCH_SITE") == "cross-site"
        ):
            # `_reject` is private to Django but is the one path to the failure view.
            return cast(Any, self)._reject(request, "Sec-Fetch-Site is cross-site")
        return super().process_view(request, callback, callback_args, callback_kwargs)


def _is_bearer(request: HttpRequest) -> bool:
    scheme, _, _ = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
    return scheme.lower() == "bearer"


def _protected(request: HttpRequest) -> HttpResponse:  # pragma: no cover
    raise AssertionError("never called")


def enforce_csrf(request: HttpRequest) -> None:
    """Run the check :class:`AuthCsrfMiddleware` runs, for a view it cannot guard.

    DRF wraps its views in ``csrf_exempt``, so a session authentication class
    calls this for the requests it authenticates. A safe method, and a request
    with a ``Bearer`` ``Authorization`` header, pass.

    Args:
        request: The Django request (a DRF request's ``_request``).

    Raises:
        CsrfFailed: The token, origin or fetch-metadata check failed.
    """
    middleware = AuthCsrfMiddleware(lambda _request: HttpResponse())
    middleware.process_request(request)
    if middleware.process_view(request, _protected, (), {}) is not None:
        raise CsrfFailed("CSRF check failed")


def csrf_failure_view(request: HttpRequest, reason: str = "") -> HttpResponse:
    """Answer a CSRF rejection with the ``403`` ``csrf-failed`` problem.

    The reason is logged and never sent.
    """
    _LOGGER.warning("CSRF check failed: {}", reason)  # noqa: PLE1205
    return problem_details_response(
        CsrfFailed(reason),
        instance=request.path,
        registry=default_registry(
            type_base=facade.rn_forge_django_settings.auth.problem_type_base
        ),
    )


def check_csrf_settings() -> None:
    """Refuse CSRF settings that leave the auth routes unprotected.

    Always: :data:`CSRF_MIDDLEWARE` is installed, and the cookie and header
    names, ``HttpOnly``, ``CSRF_USE_SESSIONS`` and the failure view match
    :data:`CSRF_SETTINGS`. Outside ``DEBUG``, the other cookie settings must
    match too. ``RN_FORGE_DJANGO["AUTH"]["PROBLEM_TYPE_BASE"]`` must be set in
    every mode, so that ``csrf-failed`` and ``forbidden`` differ in ``type``.

    Raises:
        ImproperlyConfigured: A requirement is not met.
    """
    if CSRF_MIDDLEWARE not in settings.MIDDLEWARE:
        raise ImproperlyConfigured(f"{CSRF_MIDDLEWARE} must be in MIDDLEWARE")
    for name, expected in CSRF_SETTINGS.items():
        if (name in _ALWAYS or not settings.DEBUG) and getattr(
            settings, name
        ) != expected:
            raise ImproperlyConfigured(f"{name} must be {expected!r}")
    if not facade.rn_forge_django_settings.auth.problem_type_base:
        raise ImproperlyConfigured(
            'RN_FORGE_DJANGO["AUTH"]["PROBLEM_TYPE_BASE"] must be set: without '
            "it csrf-failed and forbidden differ only in detail"
        )
