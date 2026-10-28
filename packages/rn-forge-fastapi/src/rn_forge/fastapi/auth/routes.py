"""The shared HTTP auth surface (``/auth/...``) as a FastAPI router.

Mount it with :func:`auth_router`::

    app.add_middleware(SessionMiddleware, sessions=sessions_for(config))
    app.include_router(auth_router(config))

:class:`~rn_forge.fastapi.auth.sessions.SessionMiddleware` resolves the session
and runs the CSRF check; a router mounted without it is unprotected.

The identity providers, account resolver, authorization context provider and
stores are :mod:`rn_forge.auth` objects the application builds and passes in
:class:`AuthRoutesConfig`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from rn_forge.auth import (
    AccountRejected,
    AccountResolver,
    AccountStateWriter,
    AuthorizationContextProvider,
    CallbackError,
    DevelopmentIdentityProvider,
    IdentityProvider,
    InMemoryReplayStore,
    InMemorySessionStore,
    InMemoryTransactionStore,
    InvalidReturnTo,
    LoginFailed,
    LoginFlow,
    LoginRequest,
    ReplayStore,
    SessionBody,
    SessionInfo,
    SessionStore,
    TransactionStore,
    audit,
    validate_return_to,
)
from rn_forge.fastapi.auth.csrf import CsrfProtection, CsrfStore, InMemoryCsrfStore
from rn_forge.fastapi.auth.proxies import TrustedProxies
from rn_forge.fastapi.auth.rate_limit import InMemoryRateLimiter, RateLimit, RateLimiter
from rn_forge.fastapi.auth.sessions import (
    ActiveSession,
    Sessions,
    refuse_in_memory,
    request_session,
)
from rn_forge.web import (
    PROBLEM_MEDIA_TYPE,
    ProblemType,
    SessionRequired,
    TooManyRequests,
    default_registry,
    render_problem,
)

if TYPE_CHECKING:
    from rn_forge.auth.oidc import BackchannelLogout

__all__ = ["TRANSACTION_COOKIE", "AuthRoutesConfig", "auth_router", "sessions_for"]

_LOGGER = logging.getLogger(__name__)

TRANSACTION_COOKIE = "__Host-login-tx"
"""The cookie that binds a callback to the browser that began the login."""

_TRANSACTION_MAX_AGE = 600
_PASSWORD_PER_CLIENT = RateLimit(30, timedelta(minutes=5))
_PASSWORD_PER_ACCOUNT = RateLimit(10, timedelta(minutes=5))
_CALLBACK_PER_CLIENT = RateLimit(60, timedelta(minutes=5))
_NO_STORE = {"Cache-Control": "max-age=0, no-cache, no-store, must-revalidate, private"}


@dataclass(frozen=True)
class AuthRoutesConfig:
    """What :func:`auth_router` needs to serve the auth routes.

    Attributes:
        providers: The identity providers, by provider ID. A provider of kind
            ``development`` is served only while ``debug`` is true.
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
        sessions: Holds the login sessions.
        transactions: Holds logins between redirect and callback.
        csrf: Holds each session's CSRF token and the anonymous sessions that
            protect the login request.
        trusted_origins: Origins, besides the request's own, that may send an
            unsafe request.
        trusted_proxies: Peer addresses or CIDR networks whose
            ``X-Forwarded-Proto``, ``X-Forwarded-Host`` and
            ``X-Forwarded-For`` are believed.
        replay: Holds replayed token IDs and revoked ``sid`` values.
        idle_timeout: How long a session may sit unused.
        absolute_timeout: How long a session lives whatever its use, and how
            long a revoked ``sid`` stays revoked.
        limiter: Counts hits for the rate limits.
        password_client_limit: Password login attempts per client address in a
            window; ``None`` for no limit. The client is the peer, or the
            forwarded client when the peer is in ``trusted_proxies``.
        password_account_limit: Password login attempts per submitted username
            in a window; ``None`` for no limit.
        callback_client_limit: Callback requests per client address in a window.
            Callbacks are limited per client only, because no account is known
            before the response is verified; ``None`` for no limit.
        debug: Serves the ``development`` provider and accepts in-memory
            stores. Otherwise an in-memory sessions, transactions, replay,
            CSRF or rate-limit store is refused.
        clock: Returns the current time, aware.
        problem_type_base: Prefix of the ``type`` URI of the problem responses;
            required, so that ``csrf-failed`` and ``forbidden`` differ in
            ``type``.

    Raises:
        ValueError: *problem_type_base* is empty.
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
    sessions: SessionStore = field(default_factory=InMemorySessionStore)
    transactions: TransactionStore = field(default_factory=InMemoryTransactionStore)
    replay: ReplayStore = field(default_factory=InMemoryReplayStore)
    csrf: CsrfStore = field(default_factory=InMemoryCsrfStore)
    trusted_origins: Sequence[str] = ()
    trusted_proxies: Sequence[str] = ()
    limiter: RateLimiter = field(default_factory=InMemoryRateLimiter)
    password_client_limit: RateLimit | None = _PASSWORD_PER_CLIENT
    password_account_limit: RateLimit | None = _PASSWORD_PER_ACCOUNT
    callback_client_limit: RateLimit | None = _CALLBACK_PER_CLIENT
    idle_timeout: timedelta = timedelta(minutes=30)
    absolute_timeout: timedelta = timedelta(hours=12)
    debug: bool = False
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    problem_type_base: str = ""

    def __post_init__(self) -> None:
        if not self.problem_type_base:
            raise ValueError(
                "problem_type_base must be set: without it csrf-failed and "
                "forbidden differ only in detail"
            )


@dataclass(frozen=True)
class _Request:
    query: Mapping[str, str]
    form: Mapping[str, str]


@dataclass(frozen=True)
class _Started:
    """A completed login: the session to hand the browser and where to send it."""

    return_to: str
    session_id: str
    csrf_token: str
    info: SessionInfo


class _Views:
    def __init__(self, config: AuthRoutesConfig) -> None:
        self._config = config
        self._registry = default_registry(type_base=config.problem_type_base)
        if not config.debug:
            refuse_in_memory(
                transaction_store=config.transactions, rate_limiter=config.limiter
            )
        self._proxies = TrustedProxies(config.trusted_proxies)
        self.sessions = sessions_for(config)
        self._flow = LoginFlow[LoginRequest](
            config.providers,
            config.transactions,
            return_to_prefixes=config.return_to_prefixes,
        )

    # Routes -----------------------------------------------------------------

    async def providers(self, request: Request) -> Response:
        names = self._config.provider_names
        return JSONResponse(
            [
                {"id": p.id, "name": names.get(p.id, p.id), "kind": p.kind}
                for p in self._config.providers.values()
                if self._served(p)
            ]
        )

    async def login(self, request: Request, provider_id: str) -> Response:
        if provider_id == "password":
            return Response(
                status_code=HTTPStatus.METHOD_NOT_ALLOWED, headers={"Allow": "POST"}
            )
        provider = self._navigable(provider_id)
        if provider is None:
            return self._not_found(request)
        query = dict(request.query_params)
        login_request = _Request(query=query, form={})
        development = provider.kind == "development"
        if development and "account" not in query:
            return self._account_list(request, provider)
        return_to = query.get("return_to", self._config.default_return_to)
        try:
            start = await run_in_threadpool(
                self._flow.begin, provider_id, login_request, return_to=return_to
            )
            if development:
                return await self._signed_in(
                    request, provider_id, login_request, start.transaction.id
                )
        except LoginFailed as exc:
            self._audit_failure(provider_id, exc)
            return self._redirect(self._error_url(exc.code))
        if start.redirect_url is None:
            return self._not_found(request)
        response = _no_store(RedirectResponse(start.redirect_url, status_code=302))
        response.set_cookie(
            TRANSACTION_COOKIE,
            start.transaction.id,
            max_age=_TRANSACTION_MAX_AGE,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    async def callback(self, request: Request, provider_id: str) -> Response:
        if self._navigable(provider_id) is None:
            return self._not_found(request)
        limited = await self._limit(
            request,
            "callback",
            ("client", self._client(request), self._config.callback_client_limit),
        )
        if limited is not None:
            return limited
        try:
            response = await self._signed_in(
                request,
                provider_id,
                _Request(query=dict(request.query_params), form={}),
                self._transaction_cookie(request),
            )
        except LoginFailed as exc:
            self._audit_failure(provider_id, exc)
            response = self._redirect(self._error_url(exc.code))
        response.delete_cookie(
            TRANSACTION_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
        )
        return response

    async def password_login(self, request: Request) -> Response:
        provider = next(
            (p for p in self._config.providers.values() if p.kind == "password"), None
        )
        if provider is None:
            return self._not_found(request)
        login_request = _Request(query={}, form=await _credentials(request))
        username = login_request.form.get("username", "").strip().lower()
        limited = await self._limit(
            request,
            "password",
            ("client", self._client(request), self._config.password_client_limit),
            ("account", username, self._config.password_account_limit),
        )
        if limited is not None:
            return limited
        try:
            started = await run_in_threadpool(
                self._begin_and_complete, provider.id, login_request, request
            )
        except LoginFailed as exc:
            self._audit_failure(provider.id, exc)
            # Every failure answers alike, so the response cannot tell which
            # accounts exist.
            return self._unauthorized(request)
        return await self._session_response(request, started=started)

    async def session(self, request: Request) -> Response:
        response = await self._session_response(request)
        _, active = await self._resolve(request)
        token, anonymous_id = await run_in_threadpool(
            self.sessions.ensure_csrf, self.sessions.session_id(request), active
        )
        if anonymous_id is not None:
            self.sessions.set_anonymous_cookie(response, anonymous_id)
        self.sessions.csrf.set_cookie(response, token)
        return response

    async def logout(self, request: Request) -> Response:
        session_id, active = await self._resolve(request)
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
        response = _no_store(JSONResponse({"redirect": redirect}))
        await self._end(response, session_id)
        audit("logout", account_id=info.account_id, provider=info.provider)
        return response

    async def logout_all(self, request: Request) -> Response:
        session_id, active = await self._resolve(request)
        if active is None:
            return self._unauthorized(request)
        await run_in_threadpool(
            self._config.account_state.bump_session_version, active.info.account_id
        )
        response = _no_store(JSONResponse({"redirect": None}))
        await self._end(response, session_id)
        audit(
            "logout.all",
            account_id=active.info.account_id,
            provider=active.info.provider,
        )
        return response

    async def _end(self, response: Response, session_id: str | None) -> None:
        """End the session and hand the browser a fresh anonymous session and token."""

        def end() -> tuple[str, str]:
            self.sessions.end(session_id)
            return self.sessions.start_anonymous()

        anonymous_id, token = await run_in_threadpool(end)
        self.sessions.set_anonymous_cookie(response, anonymous_id)
        self.sessions.csrf.set_cookie(response, token)

    async def backchannel_logout(self, request: Request, provider_id: str) -> Response:
        from rn_forge.auth.oidc import TokenVerificationError  # needs the oidc extra

        handler = self._config.backchannel.get(provider_id)
        if handler is None:
            return self._not_found(request)
        form = _form(await request.body())
        try:
            revocation = await run_in_threadpool(
                handler.handle, form.get("logout_token", "")
            )
        except TokenVerificationError as exc:
            _LOGGER.warning("Back-channel logout from %s refused: %s", provider_id, exc)
            return _no_store(Response(status_code=HTTPStatus.BAD_REQUEST))
        if revocation.sid is not None:
            await run_in_threadpool(
                self._config.replay.revoke_sid,
                revocation.issuer,
                revocation.sid,
                ttl=self._config.absolute_timeout,
            )
            audit("logout.backchannel", provider=provider_id, scope="session")
        elif revocation.account_id is not None:
            await run_in_threadpool(
                self._config.account_state.bump_session_version, revocation.account_id
            )
            audit(
                "logout.backchannel",
                provider=provider_id,
                scope="account",
                account_id=revocation.account_id,
            )
        return _no_store(Response())

    # Login ------------------------------------------------------------------

    async def _signed_in(
        self,
        request: Request,
        provider_id: str,
        login_request: LoginRequest,
        transaction_id: str | None,
    ) -> Response:
        started = await run_in_threadpool(
            self._complete,
            provider_id,
            login_request,
            transaction_id,
            self.sessions.session_id(request),
        )
        response = self._redirect(started.return_to)
        self._start_cookies(response, started)
        return response

    def _begin_and_complete(
        self, provider_id: str, login_request: LoginRequest, request: Request
    ) -> _Started:
        start = self._flow.begin(
            provider_id, login_request, return_to=self._config.default_return_to
        )
        return self._complete(
            provider_id,
            login_request,
            start.transaction.id,
            self.sessions.session_id(request),
        )

    def _complete(
        self,
        provider_id: str,
        login_request: LoginRequest,
        transaction_id: str | None,
        previous_session_id: str | None,
    ) -> _Started:
        """Finish a login and start the session; runs in the thread pool."""
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
        info = SessionInfo(
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
        )
        session_id, token = self.sessions.start(info, previous=previous_session_id)
        audit("login.success", account_id=account_id, provider=provider_id)
        return _Started(self._return_to(completed.return_to), session_id, token, info)

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

    def _client(self, request: Request) -> str:
        peer = request.client.host if request.client else None
        return self._proxies.client(peer, request.headers.getlist("x-forwarded-for"))

    async def _limit(
        self,
        request: Request,
        scope: str,
        *counters: tuple[str, str, RateLimit | None],
    ) -> Response | None:
        """Count one hit on each counter; answer ``429`` for the first one over."""
        for by, subject, rate in counters:
            if rate is None:
                continue
            retry_after = await run_in_threadpool(
                self._config.limiter.hit, f"{scope}:{by}", subject, rate
            )
            if retry_after is not None:
                audit("rate_limited", scope=scope, by=by, retry_after=retry_after)
                return _no_store(
                    self._problem(
                        request,
                        TooManyRequests("Too many requests", retry_after=retry_after),
                    )
                )
        return None

    @staticmethod
    def _refused(code: CallbackError, provider_id: str, reason: str) -> LoginFailed:
        _LOGGER.warning("Login with %s refused: %s", provider_id, reason)
        return LoginFailed(code, reason)

    @staticmethod
    def _transaction_cookie(request: Request) -> str | None:
        # Starlette's cookie parsing keeps one value per name, so duplicates
        # are counted in the raw header.
        values = [
            value.strip()
            for name, _, value in (
                part.partition("=")
                for header in request.headers.getlist("cookie")
                for part in header.split(";")
            )
            if name.strip() == TRANSACTION_COOKIE
        ]
        if len(values) > 1:
            raise LoginFailed("login_failed", "more than one transaction cookie")
        return values[0] if values else None

    # Providers --------------------------------------------------------------

    def _served(self, provider: IdentityProvider[LoginRequest]) -> bool:
        return provider.kind != "development" or self._config.debug

    def _navigable(self, provider_id: str) -> IdentityProvider[LoginRequest] | None:
        """The provider for a browser-navigated route, or ``None`` if there is none."""
        provider = self._config.providers.get(provider_id)
        if provider is None or provider.kind == "password":
            return None
        return provider if self._served(provider) else None

    def _account_list(
        self, request: Request, provider: IdentityProvider[LoginRequest]
    ) -> Response:
        if not isinstance(provider, DevelopmentIdentityProvider):
            return Response(status_code=HTTPStatus.NOT_FOUND)
        return _no_store(
            HTMLResponse(provider.render_accounts(login_url=request.url.path))
        )

    # Responses --------------------------------------------------------------

    async def _resolve(
        self, request: Request
    ) -> tuple[str | None, ActiveSession | None]:
        """The request's session: the middleware's, else a read that does not extend it."""
        resolved = request_session(request)
        if resolved is not None:
            return resolved
        session_id = self.sessions.session_id(request)
        return session_id, await run_in_threadpool(
            self.sessions.read, session_id, touch=False
        )

    async def _session_response(
        self,
        request: Request,
        *,
        started: _Started | None = None,
    ) -> Response:
        if started is not None:
            active = await run_in_threadpool(
                self.sessions.read, started.session_id, touch=False
            )
        else:
            _, active = await self._resolve(request)
        if active is None:
            return self._unauthorized(request)
        body = SessionBody.build(active.info, active.context)
        response = _no_store(JSONResponse(body.to_json()))
        if started is not None:
            self._start_cookies(response, started)
        return response

    def _start_cookies(self, response: Response, started: _Started) -> None:
        self.sessions.set_cookie(response, started.session_id, started.info)
        self.sessions.csrf.set_cookie(response, started.csrf_token)

    def _error_url(self, code: str) -> str:
        return f"{self._config.error_route}?{urlencode({'error': code})}"

    @staticmethod
    def _redirect(url: str) -> Response:
        return _no_store(RedirectResponse(url, status_code=302))

    def _unauthorized(self, request: Request) -> Response:
        return _no_store(self._problem(request, SessionRequired("no session")))

    def _not_found(self, request: Request) -> Response:
        row = self._registry.problem_for_status(HTTPStatus.NOT_FOUND)
        return self._problem(
            request, LookupError("no such auth route"), problem=row, detail=row.title
        )

    def _problem(
        self,
        request: Request,
        exc: BaseException,
        *,
        problem: ProblemType | None = None,
        detail: str | None = None,
    ) -> Response:
        rendered = render_problem(
            self._registry,
            exc,
            instance=request.url.path,
            problem=problem,
            detail=detail,
        )
        return JSONResponse(
            rendered.body,
            status_code=rendered.status,
            media_type=PROBLEM_MEDIA_TYPE,
            headers=dict(rendered.headers),
        )


def sessions_for(config: AuthRoutesConfig) -> Sessions:
    """A :class:`Sessions` with the stores and timeouts of *config*.

    Pass it to :class:`~rn_forge.fastapi.auth.sessions.SessionMiddleware` so the
    middleware and the routes of ``auth_router(config)`` agree.

    Raises:
        RuntimeError: ``config.debug`` is false and a store is held in memory.
    """
    return Sessions(
        store=config.sessions,
        contexts=config.contexts,
        replay=config.replay,
        csrf=CsrfProtection(
            store=config.csrf,
            problem_type_base=config.problem_type_base,
            trusted_origins=config.trusted_origins,
            trusted_proxies=config.trusted_proxies,
        ),
        idle_timeout=config.idle_timeout,
        absolute_timeout=config.absolute_timeout,
        debug=config.debug,
        clock=config.clock,
    )


def _no_store[ResponseT: Response](response: ResponseT) -> ResponseT:
    response.headers.update(_NO_STORE)
    return response


def _form(body: bytes) -> dict[str, str]:
    return dict(parse_qsl(body.decode("utf-8", errors="replace")))


async def _credentials(request: Request) -> dict[str, str]:
    """The ``username`` and ``password`` of a JSON or form-encoded login request."""
    body = await request.body()
    media_type = request.headers.get("content-type", "").partition(";")[0].strip()
    if media_type == "application/json":
        try:
            document: object = json.loads(body)
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
    return _form(body)


def auth_router(config: AuthRoutesConfig, *, prefix: str = "/auth") -> APIRouter:
    """Return a router serving every auth route under *prefix*.

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
        prefix: The URL prefix, with a leading slash and none at the end;
            empty for none.

    Returns:
        The router, to pass to ``FastAPI.include_router``.
    """
    views = _Views(config)
    router = APIRouter(prefix=prefix.rstrip("/"), include_in_schema=False)
    router.add_api_route("/providers", views.providers, methods=["GET"])
    router.add_api_route("/login/password", views.password_login, methods=["POST"])
    router.add_api_route("/login/{provider_id}", views.login, methods=["GET"])
    router.add_api_route("/callback/{provider_id}", views.callback, methods=["GET"])
    router.add_api_route("/session", views.session, methods=["GET"])
    router.add_api_route("/logout", views.logout, methods=["POST"])
    router.add_api_route("/logout/all", views.logout_all, methods=["POST"])
    router.add_api_route(
        "/backchannel-logout/{provider_id}",
        views.backchannel_logout,
        methods=["POST"],
    )
    return router
