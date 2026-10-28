"""The shared HTTP auth surface (``/auth/...``) as Django views and a URLconf.

Mount it with :func:`auth_urlpatterns`::

    urlpatterns = [*auth_urlpatterns(config), ...]

The project supplies ``django.contrib.sessions`` and its middleware. The
identity providers, account resolver and authorization context provider are
:mod:`rn_forge.auth` objects the project builds and passes in
:class:`AuthRoutesConfig`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseRedirect,
    JsonResponse,
)
from django.middleware.csrf import get_token, rotate_token
from django.urls import URLPattern, path
from django.utils.cache import add_never_cache_headers
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from rn_forge.auth import (
    AccountRejected,
    AccountResolver,
    AccountStateWriter,
    AuthorizationContextProvider,
    CallbackError,
    DevelopmentIdentityProvider,
    IdentityProvider,
    InvalidReturnTo,
    LoginFailed,
    LoginFlow,
    LoginRequest,
    ReplayStore,
    SessionBody,
    SessionInfo,
    TransactionStore,
    validate_return_to,
)
from rn_forge.commons.logging import AppLogger
from rn_forge.django import settings as facade
from rn_forge.django.auth.audit import audit
from rn_forge.django.auth.csrf import check_csrf_settings
from rn_forge.django.auth.rate_limit import FixedWindowLimiter, RateLimit
from rn_forge.django.auth.sessions import Sessions, check_session_settings
from rn_forge.django.auth.stores import CacheReplayStore, CacheTransactionStore
from rn_forge.django.exceptions import problem_details_response
from rn_forge.web import SessionRequired, TooManyRequests, default_registry

if TYPE_CHECKING:
    from rn_forge.auth.oidc import BackchannelLogout

__all__ = ["TRANSACTION_COOKIE", "AuthRoutesConfig", "auth_urlpatterns"]

_LOGGER = AppLogger.get_logger(__name__)

TRANSACTION_COOKIE = "__Host-login-tx"
"""The cookie that binds a callback to the browser that began the login."""

_TRANSACTION_MAX_AGE = 600


_PASSWORD_PER_CLIENT = RateLimit(30, timedelta(minutes=5))
_PASSWORD_PER_ACCOUNT = RateLimit(10, timedelta(minutes=5))
_CALLBACK_PER_CLIENT = RateLimit(60, timedelta(minutes=5))


@dataclass(frozen=True)
class AuthRoutesConfig:
    """What :func:`auth_urlpatterns` needs to serve the auth routes.

    Attributes:
        providers: The identity providers, by provider ID. A provider of kind
            ``development`` is served only while ``settings.DEBUG`` is true.
        accounts: Links, provisions or rejects each external identity.
        contexts: Supplies each account's authorization context.
        account_state: Persists the account's session version, which
            ``/auth/logout/all`` and a back-channel logout by ``sub`` bump.
        return_to_prefixes: Path prefixes a ``return_to`` may lie under.
        default_return_to: Where a password login lands, which has no
            ``return_to``.
        error_route: The SPA route a failed callback redirects to, with an
            ``error`` query parameter.
        post_logout_redirect: Where the identity provider returns the browser
            after RP-initiated logout.
        provider_names: Display names by provider ID; the ID by default.
        backchannel: Back-channel logout handlers, by provider ID.
        transactions: Holds logins between redirect and callback.
        replay: Holds replayed token IDs and revoked ``sid`` values.
        idle_timeout: How long a session may sit unused; a normal request
            extends it, ``GET /auth/session`` does not.
        absolute_timeout: How long a session lives whatever its use, and how
            long a revoked ``sid`` stays revoked.
        limiter: Counts hits for the rate limits, over a Django cache.
        password_client_limit: Password login attempts per client address
            (``REMOTE_ADDR``) in a window; ``None`` for no limit.
        password_account_limit: Password login attempts per submitted username
            in a window; ``None`` for no limit.
        callback_client_limit: Callback requests per client address in a window.
            Callbacks are limited per client only; ``None`` for no limit.
    """

    providers: Mapping[str, IdentityProvider[LoginRequest]]
    accounts: AccountResolver
    contexts: AuthorizationContextProvider
    account_state: AccountStateWriter
    return_to_prefixes: Sequence[str] = ("/",)
    default_return_to: str = "/"
    error_route: str = "/auth/error"
    post_logout_redirect: str = "/"
    provider_names: Mapping[str, str] = field(default_factory=dict[str, str])
    backchannel: Mapping[str, BackchannelLogout] = field(
        default_factory=dict[str, "BackchannelLogout"]
    )
    transactions: TransactionStore = field(default_factory=CacheTransactionStore)
    replay: ReplayStore = field(default_factory=CacheReplayStore)
    idle_timeout: timedelta = timedelta(minutes=30)
    absolute_timeout: timedelta = timedelta(hours=12)
    limiter: FixedWindowLimiter = field(default_factory=FixedWindowLimiter)
    password_client_limit: RateLimit | None = _PASSWORD_PER_CLIENT
    password_account_limit: RateLimit | None = _PASSWORD_PER_ACCOUNT
    callback_client_limit: RateLimit | None = _CALLBACK_PER_CLIENT


@dataclass(frozen=True)
class _Request:
    query: Mapping[str, str]
    form: Mapping[str, str]


class _Views:
    def __init__(self, config: AuthRoutesConfig) -> None:
        self._config = config
        self._registry = default_registry(
            type_base=facade.rn_forge_django_settings.auth.problem_type_base
        )
        self.sessions = Sessions(
            contexts=config.contexts,
            replay=config.replay,
            idle_timeout=config.idle_timeout,
            absolute_timeout=config.absolute_timeout,
        )
        self._flow = LoginFlow[LoginRequest](
            config.providers,
            config.transactions,
            return_to_prefixes=config.return_to_prefixes,
        )

    # Routes -----------------------------------------------------------------

    def providers(self, request: HttpRequest) -> HttpResponse:
        names = self._config.provider_names
        return JsonResponse(
            [
                {"id": p.id, "name": names.get(p.id, p.id), "kind": p.kind}
                for p in self._config.providers.values()
                if self._served(p)
            ],
            safe=False,
        )

    def login(self, request: HttpRequest, provider_id: str) -> HttpResponse:
        provider = self._navigable(provider_id)
        if provider is None:
            return self._not_found(request)
        login_request = _Request(query=request.GET.dict(), form={})
        development = provider.kind == "development"
        if development and "account" not in request.GET:
            return self._account_list(request, provider)
        return_to = request.GET.get("return_to", self._config.default_return_to)
        try:
            start = self._flow.begin(provider_id, login_request, return_to=return_to)
            if development:
                return self._signed_in(
                    request, provider_id, login_request, start.transaction.id
                )
        except LoginFailed as exc:
            self._audit_failure(provider_id, exc)
            return self._redirect(self._error_url(exc.code))
        if start.redirect_url is None:
            return self._not_found(request)
        response = HttpResponseRedirect(start.redirect_url)
        response.set_cookie(
            TRANSACTION_COOKIE,
            start.transaction.id,
            max_age=_TRANSACTION_MAX_AGE,
            secure=True,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return response

    def callback(self, request: HttpRequest, provider_id: str) -> HttpResponse:
        if self._navigable(provider_id) is None:
            return self._not_found(request)
        limited = self._limit(
            request,
            "callback",
            ("client", self._client(request), self._config.callback_client_limit),
        )
        if limited is not None:
            return limited
        try:
            response = self._signed_in(
                request,
                provider_id,
                _Request(query=request.GET.dict(), form={}),
                self._transaction_cookie(request),
            )
        except LoginFailed as exc:
            self._audit_failure(provider_id, exc)
            response = self._redirect(self._error_url(exc.code))
        response.delete_cookie(TRANSACTION_COOKIE, path="/")
        return response

    def password_login(self, request: HttpRequest) -> HttpResponse:
        provider = next(
            (p for p in self._config.providers.values() if p.kind == "password"), None
        )
        if provider is None:
            return self._not_found(request)
        login_request = _Request(query={}, form=_credentials(request))
        username = login_request.form.get("username", "").strip().lower()
        limited = self._limit(
            request,
            "password",
            ("client", self._client(request), self._config.password_client_limit),
            ("account", username, self._config.password_account_limit),
        )
        if limited is not None:
            return limited
        try:
            start = self._flow.begin(
                provider.id, login_request, return_to=self._config.default_return_to
            )
            self._complete(request, provider.id, login_request, start.transaction.id)
        except LoginFailed as exc:
            self._audit_failure(provider.id, exc)
            # Every failure answers alike, so the response cannot tell which
            # accounts exist.
            return self._unauthorized(request)
        return self._session_response(request)

    def session(self, request: HttpRequest) -> HttpResponse:
        get_token(request)  # sets the CSRF cookie, whatever the answer
        return self._session_response(request)

    def logout(self, request: HttpRequest) -> HttpResponse:
        active = self.sessions.read(request, touch=False)
        if active is None:
            return self._unauthorized(request)
        info = active.info
        provider = self._config.providers.get(info.provider)
        redirect = (
            provider.logout_redirect(
                info, post_logout_redirect=self._config.post_logout_redirect
            )
            if provider is not None
            else None
        )
        self.sessions.end(request)
        rotate_token(request)
        audit("logout", account_id=info.account_id, provider=info.provider)
        return _no_store(JsonResponse({"redirect": redirect}))

    def logout_all(self, request: HttpRequest) -> HttpResponse:
        active = self.sessions.read(request, touch=False)
        if active is None:
            return self._unauthorized(request)
        info = active.info
        self._config.account_state.bump_session_version(info.account_id)
        self.sessions.end(request)
        rotate_token(request)
        audit("logout.all", account_id=info.account_id, provider=info.provider)
        return _no_store(JsonResponse({"redirect": None}))

    def backchannel_logout(
        self, request: HttpRequest, provider_id: str
    ) -> HttpResponse:
        from rn_forge.auth.oidc import TokenVerificationError  # needs the oidc extra

        handler = self._config.backchannel.get(provider_id)
        if handler is None:
            return self._not_found(request)
        try:
            revocation = handler.handle(request.POST.get("logout_token", ""))
        except TokenVerificationError as exc:
            _LOGGER.warning(  # noqa: PLE1205  # brace-style log format
                "Back-channel logout from {} refused: {}", provider_id, exc
            )
            return _no_store(HttpResponse(status=HTTPStatus.BAD_REQUEST))
        if revocation.sid is not None:
            self._config.replay.revoke_sid(
                revocation.issuer, revocation.sid, ttl=self._config.absolute_timeout
            )
            audit("logout.backchannel", provider=provider_id, scope="session")
        elif revocation.account_id is not None:
            self._config.account_state.bump_session_version(revocation.account_id)
            audit(
                "logout.backchannel",
                provider=provider_id,
                scope="account",
                account_id=revocation.account_id,
            )
        return _no_store(HttpResponse())

    # Login ------------------------------------------------------------------

    def _signed_in(
        self,
        request: HttpRequest,
        provider_id: str,
        login_request: LoginRequest,
        transaction_id: str | None,
    ) -> HttpResponse:
        return_to = self._complete(request, provider_id, login_request, transaction_id)
        return self._redirect(return_to)

    def _complete(
        self,
        request: HttpRequest,
        provider_id: str,
        login_request: LoginRequest,
        transaction_id: str | None,
    ) -> str:
        """Finish a login, start the session and return where to send the user."""
        completed = self._flow.complete(
            provider_id, login_request, transaction_id=transaction_id
        )
        identity = completed.identity
        try:
            account_id = self._config.accounts.resolve(identity)
        except AccountRejected as exc:
            audit("account.rejected", provider=provider_id, reason=exc.reason)
            raise self._refused("account_not_provisioned", provider_id, exc.reason)
        context = self._config.contexts.resolve(account_id)
        if not context.active:
            audit("account.disabled", account_id=account_id, provider=provider_id)
            raise self._refused("access_denied", provider_id, "account is not active")
        moment = self.sessions.now()
        self.sessions.start(
            request,
            SessionInfo(
                account_id=account_id,
                session_version=context.session_version,
                provider=identity.provider,
                issuer=identity.issuer,
                external_subject=identity.subject,
                created_at=moment,
                expires_at=moment + self._config.absolute_timeout,
                auth_time=identity.auth_time,
                amr=identity.amr,
                session_ref=identity.session_ref,
                id_token=identity.id_token,
            ),
        )
        rotate_token(request)
        audit("login.success", account_id=account_id, provider=provider_id)
        return self._return_to(completed.return_to)

    def _return_to(self, return_to: str) -> str:
        try:
            return validate_return_to(
                return_to, prefixes=self._config.return_to_prefixes
            )
        except InvalidReturnTo:
            return self._config.default_return_to

    @staticmethod
    def _audit_failure(provider_id: str, exc: LoginFailed) -> None:
        audit("login.failure", provider=provider_id, code=exc.code, reason=exc.reason)

    @staticmethod
    def _client(request: HttpRequest) -> str:
        # Django resolves proxies through its own settings; REMOTE_ADDR is
        # the address it vouches for.
        return str(request.META.get("REMOTE_ADDR", ""))

    def _limit(
        self,
        request: HttpRequest,
        scope: str,
        *counters: tuple[str, str, RateLimit | None],
    ) -> HttpResponse | None:
        """Count one hit on each counter; answer ``429`` for the first one over."""
        for by, subject, rate in counters:
            if rate is None:
                continue
            retry_after = self._config.limiter.hit(f"{scope}:{by}", subject, rate)
            if retry_after is not None:
                audit("rate_limited", scope=scope, by=by, retry_after=retry_after)
                return _no_store(
                    problem_details_response(
                        TooManyRequests("Too many requests", retry_after=retry_after),
                        instance=request.path,
                        registry=self._registry,
                    )
                )
        return None

    @staticmethod
    def _refused(code: CallbackError, provider_id: str, reason: str) -> LoginFailed:
        _LOGGER.warning(  # noqa: PLE1205  # brace-style log format
            "Login with {} refused: {}", provider_id, reason
        )
        return LoginFailed(code, reason)

    @staticmethod
    def _transaction_cookie(request: HttpRequest) -> str | None:
        # Django's cookie parsing keeps one value per name, so duplicates are
        # counted in the raw header.
        values = [
            value.strip()
            for name, _, value in (
                part.partition("=")
                for part in request.META.get("HTTP_COOKIE", "").split(";")
            )
            if name.strip() == TRANSACTION_COOKIE
        ]
        if len(values) > 1:
            raise LoginFailed("login_failed", "more than one transaction cookie")
        return values[0] if values else None

    # Providers --------------------------------------------------------------

    @staticmethod
    def _served(provider: IdentityProvider[LoginRequest]) -> bool:
        return provider.kind != "development" or settings.DEBUG

    def _navigable(self, provider_id: str) -> IdentityProvider[LoginRequest] | None:
        """The provider for a browser-navigated route, or ``None`` if there is none."""
        provider = self._config.providers.get(provider_id)
        if provider is None or provider.kind == "password":
            return None
        return provider if self._served(provider) else None

    @staticmethod
    def _account_list(
        request: HttpRequest, provider: IdentityProvider[LoginRequest]
    ) -> HttpResponse:
        if not isinstance(provider, DevelopmentIdentityProvider):
            return HttpResponse(status=HTTPStatus.NOT_FOUND)
        return _no_store(HttpResponse(provider.render_accounts(login_url=request.path)))

    # Responses --------------------------------------------------------------

    def _session_response(self, request: HttpRequest) -> HttpResponse:
        active = self.sessions.read(request, touch=False)
        if active is None:
            return self._unauthorized(request)
        body = SessionBody.build(active.info, active.context)
        return _no_store(JsonResponse(body.to_json()))

    def _error_url(self, code: str) -> str:
        return f"{self._config.error_route}?{urlencode({'error': code})}"

    @staticmethod
    def _redirect(url: str) -> HttpResponse:
        return _no_store(HttpResponseRedirect(url))

    def _unauthorized(self, request: HttpRequest) -> HttpResponse:
        return _no_store(
            problem_details_response(
                SessionRequired("no session"),
                instance=request.path,
                registry=self._registry,
            )
        )

    def _not_found(self, request: HttpRequest) -> HttpResponse:
        row = self._registry.problem_for_status(HTTPStatus.NOT_FOUND)
        return problem_details_response(
            LookupError("no such auth route"),
            instance=request.path,
            registry=self._registry,
            problem=row,
            detail=row.title,
        )


def _no_store[ResponseT: HttpResponseBase](response: ResponseT) -> ResponseT:
    add_never_cache_headers(response)
    return response


def _credentials(request: HttpRequest) -> dict[str, str]:
    """The ``username`` and ``password`` of a JSON or form-encoded login request."""
    if request.content_type == "application/json":
        try:
            document: object = json.loads(request.body)
        except ValueError:
            return {}
        if not isinstance(document, dict):
            return {}
        fields = document  # pyright: ignore[reportUnknownVariableType]
        return {
            str(name): value  # pyright: ignore[reportUnknownArgumentType]
            for name, value in fields.items()  # pyright: ignore[reportUnknownVariableType]
            if isinstance(value, str)
        }
    return request.POST.dict()


def auth_urlpatterns(
    config: AuthRoutesConfig, *, prefix: str = "auth"
) -> list[URLPattern]:
    """Return the URL patterns of every auth route under *prefix*.

    | Method | Path |
    | -- | -- |
    | ``GET`` | ``providers`` |
    | ``GET`` | ``login/{provider}`` |
    | ``GET`` | ``callback/{provider}`` |
    | ``GET`` | ``session`` |
    | ``POST`` | ``logout`` |
    | ``POST`` | ``logout/all`` |
    | ``POST`` | ``backchannel-logout/{provider}`` |
    | ``POST`` | ``login/password`` |

    Args:
        config: The providers and collaborators the routes use.
        prefix: The URL prefix, without surrounding slashes.

    Returns:
        The patterns, named ``rn-forge-auth-<route>``.
    """
    check_csrf_settings()
    check_session_settings(
        cache_aliases=[
            store.alias
            for store in (config.transactions, config.replay)
            if isinstance(store, (CacheTransactionStore, CacheReplayStore))
        ]
        + [config.limiter.alias]
    )
    views = _Views(config)
    base = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
    return [
        path(
            f"{base}providers",
            require_GET(views.providers),
            name="rn-forge-auth-providers",
        ),
        path(
            f"{base}login/password",
            require_POST(views.password_login),
            name="rn-forge-auth-login-password",
        ),
        path(
            f"{base}login/<str:provider_id>",
            require_GET(views.login),
            name="rn-forge-auth-login",
        ),
        path(
            f"{base}callback/<str:provider_id>",
            require_GET(views.callback),
            name="rn-forge-auth-callback",
        ),
        path(
            f"{base}session", require_GET(views.session), name="rn-forge-auth-session"
        ),
        path(f"{base}logout", require_POST(views.logout), name="rn-forge-auth-logout"),
        path(
            f"{base}logout/all",
            require_POST(views.logout_all),
            name="rn-forge-auth-logout-all",
        ),
        path(
            f"{base}backchannel-logout/<str:provider_id>",
            csrf_exempt(require_POST(views.backchannel_logout)),
            name="rn-forge-auth-backchannel-logout",
        ),
    ]
