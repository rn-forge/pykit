# Auth

`rn_forge.django.auth` binds the login, session, CSRF and authorization design
of `rn-forge-auth` (a separate package, which holds the framework-neutral
contracts, login flows and OIDC adapter) to Django and DRF. It serves a browser
single-page application through a server-side session, and API clients through
bearer tokens, with one account and one authorization model behind both.

The app is installable (label `rn_forge_django_auth`). It also carries
[legacy](#legacy-login-and-credential-code) credential and authorization code.

## Setup

An end-to-end configuration with one OIDC provider, local password login and,
in development, a fixture-account provider. Install `rn-forge-django` with the
`drf`, `oidc` and `redis` extras.

Settings:

```python
# settings.py
from rn_forge.django.auth import CSRF_MIDDLEWARE, CSRF_SETTINGS, SESSION_SETTINGS

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "rn_forge.django.auth",  # run `manage.py migrate` for the link and state tables
    "myapp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # ... your other middleware ...
    CSRF_MIDDLEWARE,
]

globals().update(SESSION_SETTINGS)  # db-backed sessions, the __Host-session cookie
globals().update(CSRF_SETTINGS)  # Angular's XSRF-TOKEN cookie and X-XSRF-TOKEN header

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://localhost:6379/1",
    }
}

RN_FORGE_DJANGO = {"AUTH": {"PROBLEM_TYPE_BASE": "https://errors.example.com/"}}

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
}
```

`LogoutTokenVerifier.from_issuer` reads the provider's discovery document when
it is called, so the provider must be reachable at startup.

The Redis cache backend holds login transactions, replay records and revoked
session IDs, which every worker must share; the `redis` extra installs its
client. The session cookie is `Secure`, so serve development over `localhost`
or HTTPS.

The auth objects, built once:

```python
# myapp/auth_config.py
from django.conf import settings
from django.contrib.auth import authenticate
from rn_forge.auth import (
    AuthorizationContextCache,
    DevelopmentAccount,
    DevelopmentIdentityProvider,
    PasswordIdentityProvider,
)
from rn_forge.auth.oidc import BackchannelLogout, LogoutTokenVerifier, OidcProvider
from rn_forge.django.auth import AuthRoutesConfig, CacheReplayStore
from rn_forge.django.auth.accounts import (
    DjangoAccountResolver,
    DjangoAccountStateWriter,
    ProviderPolicy,
)
from rn_forge.django.auth.authorization import DjangoAuthorizationContextProvider
from rn_forge.django.auth.drf import PrincipalSessionAuthentication, sessions_for
from rn_forge.django.auth.drf.oidc import JWKSBearerAuthentication

ISSUER = "https://login.example.com/tenant/v2.0"


def verify_password(username: str, password: str) -> str | None:
    user = authenticate(username=username, password=password)
    return str(user.pk) if user else None


replay = CacheReplayStore()
resolver = DjangoAccountResolver(
    {
        "acme": ProviderPolicy(
            provisioning="jit",
            email_domains=frozenset({"example.com"}),
            authoritative_domains=frozenset({"example.com"}),
        ),
        # A local user is linked once: resolver.link("local", str(user.pk), user)
        "password": ProviderPolicy(),
        "development": ProviderPolicy(provisioning="jit"),
    }
)
contexts = AuthorizationContextCache(
    DjangoAuthorizationContextProvider(), writer=DjangoAccountStateWriter()
)

providers = {
    "acme": OidcProvider(
        id="acme",
        issuer=ISSUER,
        client_id="orders-web",
        client_secret="...",
        redirect_uri="https://app.example.com/auth/callback/acme",
    ),
    "password": PasswordIdentityProvider(verify_password),
}
if settings.DEBUG:
    providers["development"] = DevelopmentIdentityProvider(
        [DevelopmentAccount("alice", name="Alice")], debug=True
    )

config = AuthRoutesConfig(
    providers=providers,
    accounts=resolver,
    contexts=contexts,
    account_state=contexts,  # writes through to DjangoAccountStateWriter
    return_to_prefixes=["/app"],
    default_return_to="/app",
    provider_names={"acme": "Acme SSO", "password": "Password"},
    replay=replay,
    backchannel={
        "acme": BackchannelLogout(
            LogoutTokenVerifier.from_issuer(
                ISSUER, client_id="orders-web", replay_store=replay
            ),
            resolver,
        )
    },
)


class Session(PrincipalSessionAuthentication):
    sessions = sessions_for(config)


class Bearer(JWKSBearerAuthentication):
    jwks_url = "https://login.example.com/tenant/discovery/v2.0/keys"
    issuer = ISSUER
    audience = "api://orders"
    accounts = resolver
    contexts = contexts
```

A view lists the classes it accepts:

```python
# myapp/api/views.py
from rest_framework.views import APIView

from myapp.auth_config import Bearer, Session


class OrderView(APIView):
    authentication_classes = [Session, Bearer]
```

The URLconf and the authorization signals:

```python
# myapp/urls.py
from django.urls import include, path
from rn_forge.django.auth import auth_urlpatterns

from myapp.auth_config import config

urlpatterns = [
    *auth_urlpatterns(config, prefix="auth"),
    path("api/", include("myapp.api.urls")),
]
```

```python
# myapp/apps.py
from django.apps import AppConfig


class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self) -> None:
        from rn_forge.django.auth.authorization import connect_authorization_signals

        from myapp.auth_config import contexts

        connect_authorization_signals(contexts)
```

`auth_urlpatterns` checks the session, CSRF and cache settings when it builds
the URLconf and raises `ImproperlyConfigured` for a configuration it refuses
([Defaults and startup checks](#defaults-and-startup-checks)).

## Routes and responses

`auth_urlpatterns(config, prefix="auth")` serves these routes under the prefix.
The URL names are `rn-forge-auth-<route>`. A `401` from any of them is a
`problem+json` response with no `WWW-Authenticate` header.

| Method | Path | Response |
| -- | -- | -- |
| `GET` | `providers` | `200`, a list of `{id, name, kind}`. `kind` is `oidc`, `oauth2`, `password` or `development`; the development provider is listed only in `DEBUG` |
| `GET` | `login/{provider}?return_to=` | `302` to the identity provider, with the `__Host-login-tx` cookie. A `return_to` outside `return_to_prefixes` redirects to the error route. An unknown provider is `404` |
| `GET` | `login/development?account=` | In `DEBUG` only (otherwise `404`): without `account`, an HTML list of the fixture accounts; with it, signs in and redirects to `return_to` |
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
timeout). It omits `name`, `email` and `picture`: the default resolver stores
none. `Cache-Control: no-store` is set on session responses.

The login transaction lives in the cache for 10 minutes behind the
`__Host-login-tx` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no
`Domain`). A callback that carries more than one transaction cookie is
rejected, and a transaction is consumed atomically, so a callback works once.

## Sessions and revocation

Sessions are `django.contrib.sessions` with the `db` or `cached_db` engine, in
the `__Host-session` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no
`Domain`). The session holds the account ID, the account's session version at
login, provider, issuer, external subject, `auth_time`, `amr`, `session_ref`
and the ID token (only with `rp_initiated_logout`), and never permissions: those
are computed on each request.

- **Timeouts.** A 30-minute sliding idle timeout (`idle_timeout`) and a 12-hour
  absolute timeout (`absolute_timeout`). A normal read moves the idle expiry
  forward; `GET /auth/session` reads with `touch=False` and does not.
- **One read path.** `Sessions.read` deletes the session, and the caller
  answers `401`, when the absolute timeout has passed, the recorded session
  version differs from the account's, the account is inactive, or the
  `session_ref` is revoked.
- **New IDs.** Login gives the session a new ID. Call
  `rotate_session(request)` after a change to the account's privileges.
- **Logout.** `/auth/logout` ends the current session. `/auth/logout/all` and a
  back-channel logout that names only `sub` bump the account's session version,
  which ends every session of the account on its next request. A back-channel
  logout with a `sid` revokes that session only, until the absolute timeout.
  With `rp_initiated_logout` on the provider, `/auth/logout` returns the
  identity provider's end-session URL.
- **Disabling.** `contexts.set_active(account_id, False)` (or any change that
  makes the account inactive) fails the account's next request with `401`.

The authorization context cache is local to each process: a change made in
another process applies after the cache's `ttl` (60 seconds by default), or at
once through the cache that made it. Lower `ttl` where that delay matters.

## CSRF

Every unsafe method on a session-authenticated route is protected by
`AuthCsrfMiddleware`, a `CsrfViewMiddleware` subclass. The cookie is
`XSRF-TOKEN` and the header `X-XSRF-TOKEN`, Angular's defaults; the cookie is
not `HttpOnly` so that Angular can copy it into the header.

- `GET /auth/session` always sets the cookie, including when it answers `401`,
  so `POST /auth/login/password` is protected before sign-in. The token rotates
  at login and at logout.
- A rejection is the `403` `csrf-failed` problem (`CSRF_FAILURE_VIEW`); its
  reason is logged, never sent. `PROBLEM_TYPE_BASE` makes it differ in `type`
  from a permission denial.
- Beyond Django's token and origin check, `AuthCsrfMiddleware` rejects
  `Sec-Fetch-Site: cross-site` on an unsafe method, even from a trusted origin.
- Requests with a `Bearer` `Authorization` header skip the check, as does the
  back-channel logout route, which carries a signed token. A `Basic` header does
  not: browsers replay cached Basic credentials on their own.
- `CSRF_TRUSTED_ORIGINS` lists the other origins that may post. Behind a proxy,
  Django takes the request's scheme and host from forwarded headers only when
  `SECURE_PROXY_SSL_HEADER` and `USE_X_FORWARDED_HOST` are set, and the
  forwarded host must be in `ALLOWED_HOSTS`. Without them a forged
  `X-Forwarded-*` header does not make a foreign `Origin` acceptable.
- DRF wraps its views in `csrf_exempt`, so the middleware does not guard them.
  `PrincipalSessionAuthentication` calls `enforce_csrf(request)` for the
  sessions it authenticates; a custom session class does the same.

## Accounts and linking

`DjangoAccountResolver` links external identities to Django users through the
`ExternalAccount` model, unique on `(issuer, subject)`; run the auth app's
migration. A `ProviderPolicy` per provider ID decides what an unlinked identity
gets; a provider with no policy is rejected.

- `provisioning="existing"` rejects an identity with no account;
  `provisioning="jit"` creates one on first login, limited to `email_domains`
  when set (which also requires a verified email).
- `authoritative_domains` lists the email domains for which the provider is
  authoritative: only there does a verified email link to an existing user.
  Unverified emails never link and are not stored on provisioned users.
- `sync(user, identity)`, passed to the resolver, runs at every login to copy
  attributes onto the user.
- `resolver.link(issuer, subject, user)` links a service account or a local
  password user explicitly.

A rejected login redirects with `?error=account_not_provisioned`, and a login by
an inactive account with `?error=access_denied`. The session version behind
`/auth/logout/all` is stored by `DjangoAccountStateWriter` and read by
`DjangoAuthorizationContextProvider`.

## Authentication

`PrincipalSessionAuthentication` yields a `Principal` with
`mechanism="session"` from `Sessions.read`; `request.auth` is the
`SessionInfo`. Subclass it and set `sessions = sessions_for(config)`.

`PrincipalBearerAuthentication` and `JWKSBearerAuthentication` verify an
externally issued token, then resolve its `(issuer, subject)` through
`AccountResolver.lookup`. They never provision: an unlinked subject, or an
inactive account, is `401`. The principal's `subject` is the account ID; its
roles and attributes come from the authorization context, and its permissions
are the account's, limited to what the token's scopes allow through
`scope_map`:

```python
class Bearer(JWKSBearerAuthentication):
    ...
    scope_map = {"orders:read": frozenset({"orders.list", "orders.read"})}
```

List the classes on each view or on a shared base view, not in
`DEFAULT_AUTHENTICATION_CLASSES`: that setting is imported while DRF imports its
views, and the module that defines these classes imports DRF's views too.

**One credential per request.** A request with an `Authorization` header is
authenticated by the bearer class alone: an invalid token is `401` even with a
valid session cookie, and the session class ignores the request. List the
classes a view accepts. A view whose first class is the session class answers
an unauthenticated request with `401` and no `WWW-Authenticate` header; with a
bearer class first, it answers with the `Bearer` challenge. Both need the
problem-details exception handler.

### Bearer tokens in detail

For an API whose callers hold tokens issued by an identity provider (Entra ID,
Auth0, Okta, Keycloak), `JWKSBearerAuthentication` (the `oidc` extra) verifies
the token against the provider's key set. Set `jwks_url`, `issuer`, `audience`,
`accounts` and `contexts` on a subclass, as in [Setup](#setup).
`cache_timeout` (300 seconds) is how long a fetched key set is kept,
`cooldown_duration` (30 seconds) the fewest seconds between two fetches, which
bounds how often an unknown `kid` can reach the provider, and `algorithms` and
`leeway` set the accepted algorithms and the clock skew. Override
`claims_to_principal()` where the provider keeps roles or scopes somewhere
non-standard, such as Keycloak's nested `realm_access.roles`. The authenticator
and key set are cached per subclass and process, so define the class once.

| Provider | `jwks_url` |
| -- | -- |
| Entra ID | `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys` |
| Auth0 | `https://{domain}/.well-known/jwks.json` |
| Okta | `https://{domain}/oauth2/{authorization-server-id}/v1/keys` |

To verify tokens some other way, subclass `PrincipalBearerAuthentication` and
set `authenticator` to any `rn_forge.auth.Authenticator`, with `accounts`,
`contexts` and optionally `realm`. Protect a view with
`requires(Requirement(all_scopes=...))`, a permission class over the principal's
scopes and roles, which evaluates identically on `rn-forge-fastapi`:

```python
from rest_framework.views import APIView
from rn_forge.auth import Requirement
from rn_forge.django.auth.drf import requires


class OrderView(APIView):
    authentication_classes = [Bearer]
    permission_classes = [requires(Requirement(all_scopes=frozenset({"orders:read"})))]
```

With `problem_details_exception_handler` installed, missing or invalid
credentials are a `401` `problem+json` with an RFC 6750
`WWW-Authenticate: Bearer` challenge and a detail that never says why
verification failed; valid credentials lacking the scope are a `403` with no
challenge.

`PrincipalBasicAuthentication` is the RFC 7617 twin: it produces a `Principal`
from an authenticator you supply and does not link accounts. **It is for local
development and simple internal deployments only.**

## Authorization

`DjangoAuthorizationContextProvider` builds an `AuthorizationContext` from a
user's groups and permissions. Roles are group names. Django
`app_label.codename` permissions become dotted keys: `add`, `change`, `delete`
and `view` of a model map to `<app_label>.<model>.create`, `update`, `delete`
and `read` (`view` also grants `list`), so `inventory.change_stock` is
`inventory.stock.update`. A custom permission keeps `<app_label>.<codename>`. A
staff or superuser account gets the `staff` or `superuser` role and every
permission key, so the bypass shows in `/auth/session`; pass `catalog=` for keys
that exist outside Django's permission table. An unknown or inactive user
resolves to an inactive context.

Wrap the provider in an `AuthorizationContextCache` and call
`connect_authorization_signals(cache)` once at startup ([Setup](#setup)):
changes to users, groups, permissions and their relations, including those made
through the `User`, `Group` and `Permission` viewsets, then invalidate the
affected accounts.

On a view, `PermissionKeyPermission` requires the key built by
`rn_forge.auth.requirement_for` from `permission_key` and the action, checked
against the request's principal; a view without a `permission_key` requires only
an authenticated principal. `ResourcePolicyViewMixin` applies a
`ResourcePolicy`: `scope` narrows the queryset, so counts and pages cover only
permitted rows, and `allows` guards each object, answering `404` instead of
`403` when `policy_hides_existence` is true. Both are in
`rn_forge.django.auth.drf`.

```python
from rn_forge.django.auth.drf import PermissionKeyPermission, ResourcePolicyViewMixin


class OrderViewSet(ResourcePolicyViewMixin, ModelViewSet):
    permission_classes = [PermissionKeyPermission]
    permission_key = "orders"
    resource_policy = OrderPolicy()
```

### Management viewsets

`rn_forge.django.auth.drf.views` ships ready-to-mount viewsets for the standard
Django auth models, wired through `AuthorizedModelViewSet`: `PermissionViewSet`,
`GroupViewSet`, `UserViewSet`. Mount them, or
`rn_forge.django.auth.urls.urlpatterns`, which already registers them, under
your API root.


## Rate limits and audit events

`POST /auth/login/password` and `GET /auth/callback/{provider}` are rate limited
with a fixed-window counter over Django's cache (`cache.add` and `cache.incr`),
in the cache alias of `AuthRoutesConfig.limiter` (`FixedWindowLimiter`). The
client is `REMOTE_ADDR`: Django resolves proxies through its own settings, and
`X-Forwarded-For` is never read here. Password login is limited per client and
per submitted username (hashed in the key); callbacks per client only, because
no account is known before the response is verified. Each limit is a
`RateLimit(limit, window)`, or `None` for none. A limited request is the `429`
`too-many-requests` problem with `Retry-After`. Windows are aligned to the
clock, so a client can use a limit twice around a window boundary.

Security-relevant events are `INFO` records on the `rn_forge.audit.auth`
`AppLogger` channel, in the form `audit event=<name> key='value' ...`:

| Event | Emitted when |
| -- | -- |
| `login.success` | A login starts a session |
| `login.failure` | A login fails (provider, code, reason) |
| `logout`, `logout.all`, `logout.backchannel` | A session or sessions end |
| `account.provisioned` | The resolver creates an account (after commit) |
| `account.rejected` | The resolver refuses an identity |
| `account.disabled` | An inactive account logs in, or `DjangoAccountStateWriter.set_active(False)` runs |
| `authorization.denied` | `PermissionKeyPermission` or `ResourcePolicyViewMixin` denies a request |
| `rate_limited` | A request is answered `429` |

Events carry account IDs, provider IDs, codes and short reasons, and never a
token, code, assertion, password, session ID or email address.

## Defaults and startup checks

Configured on `AuthRoutesConfig` unless noted:

| Setting | Default |
| -- | -- |
| URL prefix (`auth_urlpatterns(prefix=)`) | `auth` |
| `return_to_prefixes` / `default_return_to` | `("/",)` / `/` |
| `error_route` | `/auth/error` |
| `post_logout_redirect` | `/` |
| `idle_timeout` / `absolute_timeout` | 30 minutes / 12 hours |
| Login transaction lifetime | 10 minutes |
| `password_client_limit` | 30 per 5 minutes |
| `password_account_limit` | 10 per 5 minutes |
| `callback_client_limit` | 60 per 5 minutes |
| `transactions`, `replay`, `limiter` | Django's `default` cache |
| Session cookie | `__Host-session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain` |
| Login transaction cookie | `__Host-login-tx`, same flags, `Max-Age=600` |
| CSRF cookie / header | `XSRF-TOKEN` (not `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`) / `X-XSRF-TOKEN` |
| Authorization cache `ttl` | 60 seconds |

`auth_urlpatterns` raises `ImproperlyConfigured` when it builds the URLconf:

| Refused | Always | Outside `DEBUG` |
| -- | -- | -- |
| `SESSION_SAVE_EVERY_REQUEST` true | yes | yes |
| `AuthCsrfMiddleware` missing from `MIDDLEWARE` | yes | yes |
| CSRF cookie and header names, `HttpOnly`, `CSRF_USE_SESSIONS`, `CSRF_FAILURE_VIEW` differing from `CSRF_SETTINGS` | yes | yes |
| `RN_FORGE_DJANGO["AUTH"]["PROBLEM_TYPE_BASE"]` unset | yes | yes |
| Session cookie settings differing from `SESSION_SETTINGS` | no | yes |
| Other CSRF cookie settings differing from `CSRF_SETTINGS` | no | yes |
| A session engine other than `db` or `cached_db` (the signed-cookie engine cannot revoke sessions) | no | yes |
| Django's local-memory cache as the session cache, or for the transaction, replay or limiter store | no | yes |

`/auth/login/development` and the development provider's listing exist only
while `settings.DEBUG` is true.

## Legacy login and credential code

The code below predates the surface above. It is kept for existing applications
and is removed by the next breaking change; new applications should not adopt
it.

### Credential permissions

```python
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rn_forge.django.auth.drf.permissions.AuthorizationPermission",
    ],
}
```

`BaseCredentials` is the base for a `request.auth` object that wraps a user.

`BaseCredentials` exposes `is_authenticated`, `is_staff_user` (staff/superuser
bypass), `user_id`, `email`, and `has_permission(key)` /
`has_any_permission(keys)`.

`AuthorizationPermission` denies unauthenticated requests, allows
staff/superuser through, and otherwise defers to the view's
`validate_permissions()` — implemented by `AuthorizationViewMixin` (mix into any
`BaseAPIView`/`BaseModelViewSet`):

```python
from rn_forge.django.auth.drf.mixins import AuthorizationViewMixin
from rn_forge.django.drf.views import BaseModelViewSet


class OrderViewSet(AuthorizationViewMixin, BaseModelViewSet):
    permission_key = "app.order"
```

`permission_key` is combined with the current action (`list`, `retrieve`,
`create`, `export`, ...) through a permission-action map to build the final key
checked against `credentials.has_permission(...)` — e.g. `app.order.read` for
`retrieve`. The default map lives in `rn_forge.auth.DEFAULT_PERMISSION_ACTION_MAP`; override
per-request-app defaults via
`RN_FORGE_DJANGO["DRF"]["VIEWS"]["PERMISSION_ACTION_MAP"]` or per-view via
`permission_action_map`. Override `should_validate_object_permissions()` /
`validate_object_permissions()` for row-level checks.

Use `PermissionKeyViewMixin` instead when you want permission-key resolution
without full `AuthorizationViewMixin` request-access plumbing (e.g. on plain
`GenericAPIView`s).

