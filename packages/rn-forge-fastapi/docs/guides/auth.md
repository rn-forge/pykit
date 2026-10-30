# Auth

`rn_forge.fastapi.auth` binds the login, session, CSRF and authorization design
of `rn-forge-auth` (a separate package, which holds the framework-neutral
contracts, login flows, session and replay stores and the OIDC adapter) to
FastAPI. It serves a browser single-page application through a server-side
session, and API clients through bearer tokens, with one account and one
authorization model behind both. `rn-forge-auth` documents the providers and
stores; this page documents the FastAPI side. The Django binding in
`rn-forge-django` serves the same routes, responses and audit events.

The session, CSRF and rate-limit state is shared by every worker, so outside
development it lives in Redis. Install `rn-forge-fastapi` with the `redis`
extra, and with `oidc` for OIDC login or JWKS bearer tokens.

## Setup

An end-to-end configuration with one OIDC provider, local password login and,
in development, a fixture-account provider:

```python
# myapp/auth_config.py
from redis import Redis
from rn_forge.auth import (
    AuthorizationContextCache,
    DevelopmentAccount,
    DevelopmentIdentityProvider,
    PasswordIdentityProvider,
)
from rn_forge.auth.oidc import OidcProvider
from rn_forge.auth.redis import (
    RedisAuthorizationVersions,
    RedisReplayStore,
    RedisSessionStore,
    RedisTransactionStore,
)
from rn_forge.fastapi.auth import AuthRoutesConfig
from rn_forge.fastapi.auth.redis import RedisCsrfStore, RedisRateLimiter

from myapp.accounts import MyAccountResolver, MyAccountState, MyContexts, check_password

DEBUG = False
redis = Redis.from_url("redis://localhost:6379/0")

contexts = AuthorizationContextCache(
    MyContexts(),
    versions=RedisAuthorizationVersions(redis),
    writer=MyAccountState(),
)

providers = {
    "acme": OidcProvider(
        id="acme",
        issuer="https://login.example.com/tenant/v2.0",
        client_id="orders-web",
        client_secret="...",
        redirect_uri="https://app.example.com/auth/callback/acme",
    ),
    "password": PasswordIdentityProvider(check_password),
}
if DEBUG:
    providers["development"] = DevelopmentIdentityProvider(
        [DevelopmentAccount("alice", name="Alice")], debug=True
    )

config = AuthRoutesConfig(
    providers=providers,
    accounts=MyAccountResolver(),
    contexts=contexts,
    account_state=contexts,  # writes through to MyAccountState
    problem_type_base="https://errors.example.com/",
    return_to_prefixes=["/app"],
    default_return_to="/app",
    provider_names={"acme": "Acme SSO", "password": "Password"},
    sessions=RedisSessionStore(redis),
    transactions=RedisTransactionStore(redis),
    replay=RedisReplayStore(redis),
    csrf=RedisCsrfStore(redis),
    limiter=RedisRateLimiter(redis),
    trusted_origins=["https://app.example.com"],
    debug=DEBUG,
)
```

Mount the router and the middleware:

```python
# myapp/main.py
from rn_forge.fastapi import FastApiApp, SessionMiddleware, auth_router
from rn_forge.fastapi.auth import sessions_for

from myapp.auth_config import config

app = FastApiApp(...)
app.add_middleware(SessionMiddleware, sessions=sessions_for(config))
app.include_router(auth_router(config))
```

`sessions_for(config)` builds the `Sessions` from the same stores and timeouts
as the routes, so the middleware and the routes agree. `SessionMiddleware`
resolves the session once per request and runs the CSRF check; a router
mounted without it is unprotected, and `current_principal` raises
`RuntimeError` for a session request. `add_middleware` wraps the application,
so the middleware added last is outermost. Add `SessionMiddleware` before the
middleware that should also decorate its responses (security headers, CORS), so
a `csrf-failed` rejection, which the middleware answers itself, carries them.

When the router is mounted under a prefix other than `/auth`, tell the
middleware the paths it has special rules for:

```python
app.add_middleware(
    SessionMiddleware,
    sessions=sessions_for(config),
    untouched_paths=["/api/auth/session"],
    login_path="/api/auth/login/password",
    csrf_exempt_prefixes=["/api/auth/backchannel-logout/"],
)
app.include_router(auth_router(config, prefix="/api/auth"))
```

The session cookie is `Secure`, so serve development over `localhost` or HTTPS.

## Routes and responses

`auth_router(config, prefix="/auth")` serves these routes under the prefix. It
is left out of the OpenAPI document. A `401` from any of them is a
`problem+json` response with no `WWW-Authenticate` header.

| Method | Path | Response |
| -- | -- | -- |
| `GET` | `providers` | `200`, a list of `{id, name, kind}`. `kind` is `oidc`, `oauth2`, `password` or `development`; the development provider is listed only with `debug=True` |
| `GET` | `login/{provider}?return_to=` | `302` to the identity provider, with the `__Host-login-tx` cookie. A `return_to` outside `return_to_prefixes` is replaced by `default_return_to`. An unknown provider is `404`; `login/password` is `405` |
| `GET` | `login/development?account=` | With `debug=True` only (otherwise `404`): without `account`, an HTML list of the fixture accounts; with it, signs in and redirects to `return_to` |
| `GET` | `callback/{provider}` | `302` to `return_to`, or to the error route; `429` when rate limited |
| `GET` | `session` | `200` with the session body, or `401`. Always sets the CSRF cookie |
| `POST` | `logout` | `200 {"redirect": url or null}`; `401` without a session |
| `POST` | `logout/all` | `200 {"redirect": null}`; `401` without a session |
| `POST` | `backchannel-logout/{provider}` | `200`; `400` for an invalid logout token; `404` for a provider with no handler |
| `POST` | `login/password` | `200` with the session body, `401` for any failure, or `429` |

A callback error redirects to `error_route` (`/auth/error`) with `?error=` set
to one of `access_denied`, `account_not_provisioned` and `login_failed`.
Details go to the log, never into the URL. A password login failure is one `401`
whatever its cause, so the response does not reveal which accounts exist. The
login body is JSON or form-encoded `{username, password}`.

The session body is camelCase: `subject` (the account ID), `provider`, `roles`,
`permissions`, `attributes`, `authTime`, `amr` and `expiresAt` (the absolute
timeout). Session responses carry `Cache-Control: no-store`.

The login transaction lives in its store for 10 minutes behind the
`__Host-login-tx` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no
`Domain`). A callback that carries more than one transaction cookie is
rejected, and a transaction is consumed atomically, so a callback works once.
The stores' synchronous calls and the Authlib providers run in the thread pool.

## Configuration

`AuthRoutesConfig` is a frozen dataclass. `providers`, `accounts`, `contexts`
and `account_state` are required, and so is `problem_type_base` (a
`ValueError` otherwise): it is the prefix of the `type` URI of the problem
responses, which is what tells `csrf-failed` from `forbidden`.

| Field | Default |
| -- | -- |
| URL prefix (`auth_router(prefix=)`) | `/auth` |
| `return_to_prefixes` / `default_return_to` | `("/",)` / `/` |
| `error_route` | `/auth/error` |
| `post_logout_redirect` | `/` |
| `idle_timeout` / `absolute_timeout` | 30 minutes / 12 hours |
| `trusted_origins` / `trusted_proxies` | none / none |
| `password_client_limit` | 30 per 5 minutes |
| `password_account_limit` | 10 per 5 minutes |
| `callback_client_limit` | 60 per 5 minutes |
| `sessions`, `transactions`, `replay`, `csrf`, `limiter` | in-memory stores, refused unless `debug=True` |
| `debug` | `False` |
| Session cookie | `__Host-session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain` |
| Login transaction cookie | `__Host-login-tx`, same flags, `Max-Age=600` |
| CSRF cookie / header | `XSRF-TOKEN` (not `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`) / `X-XSRF-TOKEN` |
| Anonymous session lifetime | 10 minutes |

`backchannel` maps provider IDs to the back-channel logout handlers
(`rn_forge.auth.oidc.BackchannelLogout`, which needs the `oidc` extra);
`provider_names` maps IDs to display names; `clock` replaces the time source in
tests.

`trusted_proxies` lists the peer addresses or CIDR networks, such as
`10.0.0.0/8`, whose `X-Forwarded-Proto`, `X-Forwarded-Host` and
`X-Forwarded-For` headers are believed. From any other peer those headers are
ignored, so a client cannot forge its own origin or address.

## Production storage

In-memory stores are held per process, so a second worker would not see a
revocation, a transaction or a CSRF token. Outside `debug`, `auth_router` and
`Sessions` refuse them with a `RuntimeError` naming the store: sessions,
transactions, replay, CSRF and the rate limiter. Install the `redis` extra and
use:

| Store | Class |
| -- | -- |
| Login sessions | `rn_forge.auth.redis.RedisSessionStore` |
| Login transactions | `rn_forge.auth.redis.RedisTransactionStore` |
| Replayed token IDs and revoked `sid` values | `rn_forge.auth.redis.RedisReplayStore` |
| Authorization context versions | `rn_forge.auth.redis.RedisAuthorizationVersions` |
| CSRF tokens | `rn_forge.fastapi.auth.redis.RedisCsrfStore` |
| Rate limits | `rn_forge.fastapi.auth.redis.RedisRateLimiter` |

They take a `redis.Redis` client and need Redis 6.2 or later. The Redis modules
of this package are not imported by `rn_forge.fastapi`, so a deployment without
the extra can import the rest. `RedisAuthorizationVersions` goes to the
`AuthorizationContextCache`, so that a change made in one process invalidates
the cached context in every process; without it a change applies after the
cache's `ttl` (60 seconds by default).

## Sessions and revocation

The login session is a `rn-forge-auth` `SessionStore` entry behind the
`__Host-session` cookie. It holds the account ID, the account's session version
at login, provider, issuer, external subject, `auth_time`, `amr`, `session_ref`
and the ID token (only with `rp_initiated_logout`), and never permissions:
those are computed on each request.

- **Timeouts.** A 30-minute sliding idle timeout (`idle_timeout`) and a 12-hour
  absolute timeout (`absolute_timeout`). `SessionMiddleware` extends the idle
  expiry and refreshes the cookie on every request except `GET /auth/session`,
  so a client that polls the session does not keep it alive.
- **One read path.** `Sessions.read` deletes the session, and the request is
  unauthenticated, when the absolute timeout has passed, the recorded session
  version differs from the account's, the account is inactive, or the
  `session_ref` is revoked. A cookie that names no valid session is cleared.
- **New IDs.** Login replaces the session ID, and the CSRF token with it. Call
  `await rotate_session(request)` after a change to the account's privileges,
  so an ID seen before the change is useless afterwards; the middleware sets
  the new cookie.
- **Logout.** `/auth/logout` ends the current session and starts a new
  anonymous one. `/auth/logout/all` and a back-channel logout that names only
  `sub` bump the account's session version through `account_state`, which ends
  every session of the account on its next request. A back-channel logout with
  a `sid` revokes that session only, until the absolute timeout. With
  `rp_initiated_logout` on the provider, `/auth/logout` returns the identity
  provider's end-session URL.
- **Disabling.** `contexts.set_active(account_id, False)` (or any change that
  makes the account inactive) ends the account's sessions at their next
  request.

`active_session(request)` returns the `ActiveSession` (the `SessionInfo` and the
account's current authorization context) the middleware resolved, or `None`.

## CSRF

Unsafe methods on session-authenticated routes are protected by a synchronizer
token, which `SessionMiddleware` checks for the `/auth` routes and for the
application's own routes alike. The token is random and kept in the `CsrfStore`
under the session ID; the readable `XSRF-TOKEN` cookie hands it to the browser,
and the request repeats it in `X-XSRF-TOKEN`, which are Angular's defaults. The
comparison is constant-time.

- `GET /auth/session` always sets the cookie, including when it answers `401`.
  With no session it starts an anonymous session, a 10-minute entry behind
  `__Host-session` that holds only a token, so `POST /auth/login/password` is
  protected before sign-in.
- Login replaces the session ID and the token; logout starts a new anonymous
  session with a new token; `rotate_session` carries the token to the new ID.
- **Checked:** an unsafe request that carries the `__Host-session` cookie,
  whether it names a live session, an anonymous one or nothing known, and a
  request to the password login path (`login_path`), which a browser can reach
  with no cookie.
- **Exempt:** `GET`, `HEAD`, `OPTIONS` and `TRACE`; a request with a `Bearer`
  `Authorization` header; the paths under `csrf_exempt_prefixes` (back-channel
  logout, which carries a signed token); and a request with no session cookie to
  an application route, which has no session to ride. A `Basic` header is not
  exempt: browsers replay cached Basic credentials on their own.
- **Origin.** The `Origin` header (the `Referer` over HTTPS when there is no
  `Origin`) must be the request's own origin or one of `trusted_origins`, and
  `Sec-Fetch-Site: cross-site` is rejected even from a trusted origin. The
  request's own scheme and host come from `X-Forwarded-Proto` and
  `X-Forwarded-Host` only when the peer is in `trusted_proxies`.
- A rejection is the `403` `csrf-failed` problem; its reason is logged, never
  sent.

## Authentication

`current_principal(bearer=None)` returns a dependency that yields a `Principal`
from the login session (`mechanism="session"`, the account's roles and
permissions from its authorization context, and the session's `auth_time` and
`amr`), or from a bearer token when `bearer` is given.

`bearer_auth` verifies an externally issued token, then resolves its
`(issuer, subject)` through `AccountResolver.lookup`. It never provisions: a
token with no linked account, or whose account is inactive, is `401`. The
principal's `subject` is the account ID, its roles, tenant and attributes come
from the authorization context, and its permissions are the account's, limited
to what the token's scopes allow through `scope_map`:

```python
from rn_forge.auth.oidc import OidcAuthenticator
from rn_forge.fastapi.auth import bearer_auth, current_principal

from myapp.auth_config import config, contexts

bearer = bearer_auth(
    authenticator=OidcAuthenticator.from_issuer(
        "https://login.example.com/tenant/v2.0", audience="api://orders"
    ),
    accounts=config.accounts,
    contexts=contexts,
    scope_map={"orders:read": frozenset({"orders.list", "orders.read"})},
)
caller = current_principal(bearer=bearer)
```

Build the authenticator once at startup: it holds the JWKS cache.

**One credential per request.** A request with an `Authorization` header is
authenticated by `bearer` alone: an invalid token is `401` even with a valid
session cookie, and without `bearer` the header makes the request
unauthenticated. Any other request is authenticated by the session. An
unauthenticated request is `401` with the `Bearer` challenge when `bearer` is
given, and without a challenge otherwise, and the failure reason goes to the
`log` callback, never the response.

`basic_auth(authenticator=...)` is the RFC 7617 twin for an authenticator you
supply and does not link accounts. It is for local development and simple
internal deployments only.

## Authorization

`requires(caller, Requirement(...))` authenticates, then enforces the
requirement with `rn_forge.auth.ScopeAuthorizer` (or the `authorizer` you pass).
Insufficient access is a `403` with no challenge.
`requires_permission(caller, permission_key, action)` enforces the key that
`rn_forge.auth.requirement_for` builds from the base key and an explicit
action, `list`, `retrieve` or `partial_update` for example; `action_map`
overrides the default action-to-verb map:

```python
from fastapi import APIRouter, Depends
from rn_forge.auth import Principal, Requirement
from rn_forge.fastapi.auth import requires, requires_permission

router = APIRouter()


@router.get("/orders")
async def list_orders(
    principal: Principal = Depends(requires_permission(caller, "orders", "list")),
): ...


@router.post("/reports")
async def run_report(
    principal: Principal = Depends(
        requires(caller, Requirement(all_scopes=frozenset({"reports:run"})))
    ),
): ...
```

`PolicyGuard(policy, hides_existence=False)` applies a `ResourcePolicy`.
`guard.scope(principal, action, query)` narrows a query of any type, such as a
SQLAlchemy `select`, so rows, counts and pages cover only permitted rows;
`guard.check(principal, action, obj)` returns the object or raises `403`, or
`404` when `hides_existence` is true:

```python
from rn_forge.fastapi.auth import PolicyGuard
from sqlalchemy import select

guard = PolicyGuard(OrderPolicy(), hides_existence=True)


@router.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    principal: Principal = Depends(caller),
    session: Session = Depends(db_session),
):
    order = session.scalar(
        guard.scope(principal, "retrieve", select(Order).where(Order.id == order_id))
    )
    if order is None:
        raise LookupError("Not found")
    return guard.check(principal, "retrieve", order)
```

## Rate limits and audit events

`POST /auth/login/password` and `GET /auth/callback/{provider}` are rate limited
with a fixed-window counter in `limiter`. The client is the connection's peer,
or the nearest address in `X-Forwarded-For` that is not a trusted proxy when the
peer is in `trusted_proxies`. Password login is limited per client and per
submitted username (hashed in the key); callbacks per client only, because no
account is known before the response is verified. Each limit is a
`RateLimit(limit, window)`, or `None` for none. A limited request is the `429`
`too-many-requests` problem with `Retry-After`. Windows are aligned to the
clock, so a client can use a limit twice around a window boundary.

Security-relevant events are `INFO` records on the `rn_forge.audit.auth`
channel, in the form `audit event=<name> key='value' ...`:

| Event | Emitted when |
| -- | -- |
| `login.success` | A login starts a session |
| `login.failure` | A login fails (provider, code, reason) |
| `logout`, `logout.all`, `logout.backchannel` | A session or sessions end |
| `account.provisioned` | A provisioning resolver creates an account |
| `account.rejected` | The resolver refuses an identity |
| `account.disabled` | An inactive account logs in |
| `authorization.denied` | `requires`, `requires_permission` or `PolicyGuard` denies a request |
| `rate_limited` | A request is answered `429` |

Events carry account IDs, provider IDs, codes and short reasons, and never a
token, code, assertion, password, session ID or email address.

## What the application implements

The binding takes these `rn_forge.auth` protocols; every method is synchronous
and runs in the thread pool.

- **`AccountResolver`.** `resolve(identity)` links, provisions or rejects an
  external identity at login and returns the account ID, raising
  `AccountRejected` to refuse it; `lookup(issuer, subject)` is the read-only
  form `bearer_auth` uses. A resolver that creates accounts records
  `account.provisioned` once the account is committed:

    ```python
    from rn_forge.auth import audit

    audit("account.provisioned", account_id=account.id, provider=identity.provider)
    ```

- **`AuthorizationContextProvider`.** `resolve(account_id)` returns the
  `AuthorizationContext`: `active`, `session_version`, `permissions`, `roles`
  and `attributes`. Wrap it in an `AuthorizationContextCache` and call
  `contexts.invalidate(account_id)` when a role or permission changes.
- **`AccountStateWriter`.** `set_active(account_id, active)` and
  `bump_session_version(account_id)` persist the state the context carries.
  `/auth/logout/all` and a back-channel logout call them; the cache above
  writes through to it.
- **`ResourcePolicy`.** `allows(principal, action, resource)` and
  `scope(principal, action, query)`, for `PolicyGuard`.
- **`PasswordVerifier`.** For `PasswordIdentityProvider`: a callable
  `(username, password) -> subject | None`. Hash comparison and the user lookup
  are yours.
