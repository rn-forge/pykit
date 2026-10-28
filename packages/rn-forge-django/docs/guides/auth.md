# Auth

`rn_forge.django.auth` is an installable Django app (label
`rn_forge_django_auth`) providing login flows and DRF
authentication/authorization building blocks. Add it to `INSTALLED_APPS` to use
the bundled `User`/`Group`/`Permission` viewsets and migrations.

## Login flows

All login flows produce a normalized `LoginPayload(user=..., claims=...)` and
share a common `complete_login()` hook that decides what happens next (start a
Django session, mint an exchange token, or mint a final JWT pair).

**Basic (username/password) → session:**

```python
from rn_forge.django.auth.basic.views import BasicLoginAPIView


class LoginView(BasicLoginAPIView):
    """POST {username, password} -> Django session + build_login_response() payload."""
```

**Basic/SAML → short-lived exchange token → JWT:** login views that mix in
`LoginExchangeViewMixin` (via `BasicLoginAPIView`/`SAMLLoginAPIView`) return an
`exchange_token` instead of creating a session. The client then calls
`UserTokenView` to trade that token for a SimpleJWT access/refresh pair:

```python
from rn_forge.django.auth.jwt.views import UserTokenView
```

**SAML:** subclass `SAMLLoginViewMixin`/`SAMLLoginAPIView` and implement
`build_saml_request_data()`, `get_saml_user_lookup()`, and `get_user()` (plus
`create_user_for_login()` if `auto_create_user = True`).
`RN_FORGE_DJANGO["AUTH"]["SAML"]` supplies the `python3-saml` settings dict and
default `RETURN_TO` — see [Settings](settings.md).

```python
RN_FORGE_DJANGO = {"AUTH": {"SAML": {"SETTINGS": {...}, "RETURN_TO": "/app"}}}
```

Reusable router + `user-token/` endpoint:

```python
from rn_forge.django.auth.urls import urlpatterns
```

## DRF authentication and permissions

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rn_forge.django.auth.jwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rn_forge.django.auth.drf.permissions.AuthorizationPermission",
    ],
}
```

`JWTAuthentication` wraps SimpleJWT's authenticator so `request.auth` is a
`JWTCredentials` (subclass of `BaseCredentials`) rather than a raw validated
token.

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

## Externally issued tokens: `PrincipalBearerAuthentication`

For an API whose callers hold tokens issued by an identity provider — Entra ID,
Auth0, Okta, Keycloak — rather than a local `User`, bind DRF to the
`rn_forge.auth` contract. The token is verified by an
`rn_forge.auth.Authenticator` you supply, and `request.user` is the resulting
`rn_forge.auth.Principal`:

```python
from rest_framework.views import APIView
from rn_forge.auth import Requirement
from rn_forge.auth.oidc import OidcAuthenticator
from rn_forge.django.auth.drf import PrincipalBearerAuthentication, requires


class ApiBearer(PrincipalBearerAuthentication):
    authenticator = OidcAuthenticator.from_issuer(
        "https://login.example.com/tenant/v2.0", audience="api://orders"
    )
    realm = "orders"


class OrderView(APIView):
    authentication_classes = [ApiBearer]
    permission_classes = [requires(Requirement(all_scopes=frozenset({"orders:read"})))]
```

With `problem_details_exception_handler` installed: no or invalid credentials
are a **401** `problem+json` with an RFC 6750
`WWW-Authenticate: Bearer realm="orders"` challenge and a detail that never says
why verification failed; valid credentials lacking the scope are a **403** with
no challenge. The same `Requirement` evaluates identically on
`rn-forge-fastapi`.

Verifying the JWT is the authenticator's job, and you do not have to write one:
`rn_forge.auth.oidc.OidcAuthenticator` (`rn-forge-auth`'s `oidc` extra, which
Django's `oidc` extra brings) is the shared implementation, so this stack accepts exactly the
tokens a FastAPI service accepts. `JWKSBearerAuthentication` below builds one
for you from class attributes.

For the bundled JWKS binding, install `rn-forge-django[oidc]` and define one
subclass with the provider's key-set URL, issuer and audience:

```python
from rn_forge.django.auth.drf.oidc import JWKSBearerAuthentication


class ApiBearer(JWKSBearerAuthentication):
    jwks_url = "https://idp.example.com/.well-known/jwks.json"
    issuer = "https://idp.example.com/"
    audience = "api://orders"
```

Use that class in the view's `authentication_classes`, and install
`problem_details_exception_handler` in `REST_FRAMEWORK["EXCEPTION_HANDLER"]` for
the shared problem response. The binding caches its authenticator and key set
per subclass and process; `cache_timeout` (300 seconds) sets how long a fetched
key set is kept and `cooldown_duration` (30 seconds) the fewest seconds between
two fetches, which bounds how often an unknown `kid` can reach the IdP. Override `claims_to_principal()` when the provider
uses nonstandard role or scope claims.

Build the authenticator **once, at import or startup** — it holds the JWKS
cache, so a per-request instance refetches the key set on every call. For an IdP
whose roles or scopes sit somewhere non-standard (Keycloak's nested
`realm_access.roles`, an Okta group claim), pass a `claims_to_principal`
override.

The JWKS endpoint an authenticator fetches is IdP configuration:

| IdP | `jwks_url` |
| -- | -- |
| Entra ID | `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys` |
| Auth0 | `https://{domain}/.well-known/jwks.json` |
| Okta | `https://{domain}/oauth2/{authorization-server-id}/v1/keys` |

`PrincipalBasicAuthentication` is the RFC 7617 twin, producing the same
`Principal` and the same 401. **It is for local development and simple internal
deployments only.**

## Built-in auth management viewsets

`rn_forge.django.auth.drf.views` ships ready-to-mount viewsets for the standard
Django auth models, wired through `AuthorizedModelViewSet`: `PermissionViewSet`,
`GroupViewSet`, `UserViewSet`. Mount them (or
`rn_forge.django.auth.urls.urlpatterns`, which already registers them) under
your API root.

## Authorization from Django groups and permissions

`rn_forge.django.auth.authorization.DjangoAuthorizationContextProvider` builds
an `AuthorizationContext` from a user's groups and permissions. Roles are group
names. Django `app_label.codename` permissions become dotted keys:
`add`/`change`/`delete`/`view` of a model map to
`<app_label>.<model>.create`/`update`/`delete`/`read` (`view` also grants
`list`), so `inventory.change_stock` is `inventory.stock.update`. A custom
permission keeps `<app_label>.<codename>`. A staff or superuser account gets the
`staff` or `superuser` role and every permission key, so the bypass shows in
`/auth/session`. Wrap the provider in an `AuthorizationContextCache` and call
`connect_authorization_signals(cache)` once at startup: changes to users,
groups, permissions and their relations, including those made through the
`User`, `Group` and `Permission` viewsets, then invalidate the affected
accounts.

On a view, `PermissionKeyPermission` requires the key built by
`rn_forge.auth.requirement_for` from `permission_key` and the action, and
`ResourcePolicyViewMixin` applies a `ResourcePolicy`: `scope` narrows the
queryset (so counts and pages cover only permitted rows) and `allows` guards
each object, answering `404` instead of `403` when `policy_hides_existence` is
true. Both are in `rn_forge.django.auth.drf`.

## Auth routes

`auth_urlpatterns(config, prefix="auth")` serves the shared `/auth` surface:
`providers`, `login/{provider}`, `callback/{provider}`, `session`, `logout`,
`logout/all`, `backchannel-logout/{provider}` and `login/password`. The project
builds the providers from `rn_forge.auth` (`OidcProvider`,
`PasswordIdentityProvider`, `DevelopmentIdentityProvider`) and an
`AccountResolver`, an `AuthorizationContextProvider` and an `AccountStateWriter`,
and passes them in `AuthRoutesConfig`; there is no settings block for providers:

```python
from rn_forge.django.auth import AuthRoutesConfig, auth_urlpatterns

urlpatterns = [
    *auth_urlpatterns(
        AuthRoutesConfig(
            providers={"acme": acme_provider},
            accounts=accounts,
            contexts=contexts,
            account_state=account_state,
            return_to_prefixes=["/app"],
        )
    ),
]
```

Sessions are `django.contrib.sessions` with the `db` or `cached_db` engine, so
`SessionMiddleware` must be installed. Spread `SESSION_SETTINGS` into your
settings for the `__Host-session` cookie (`HttpOnly`, `Secure`,
`SameSite=Lax`, `Path=/`, no `Domain`) and keep
`SESSION_SAVE_EVERY_REQUEST` false:

```python
from rn_forge.django.auth import SESSION_SETTINGS

globals().update(SESSION_SETTINGS)
```

`auth_urlpatterns` checks these settings when the URLconf is built and raises
`ImproperlyConfigured`. In every mode it refuses `SESSION_SAVE_EVERY_REQUEST`
(it would let `GET /auth/session` extend the session). Outside `DEBUG` it also
refuses cookie settings that differ from `SESSION_SETTINGS`, any session engine other than `db` or `cached_db` (the signed-cookie
engine cannot revoke sessions), and Django's local-memory cache for the session cache and for the
login-transaction and replay stores.

The session holds the account ID, the account's session version at login,
provider, issuer, external subject, `auth_time`, `amr`, `session_ref` and the
ID token (only with RP-initiated logout), and never permissions. It has a
30-minute sliding idle timeout and a 12-hour absolute timeout
(`AuthRoutesConfig.idle_timeout` and `absolute_timeout`). `Sessions.read`
is the one place that reads the session: it deletes it, and the caller answers
`401`, when the absolute timeout has passed, the recorded version differs from
the account's, the account is inactive, or the `session_ref` is revoked. A
normal read moves the idle expiry forward; `touch=False`, which
`GET /auth/session` uses, does not. Call `rotate_session(request)` after a
change of the account's privileges to give the session a new ID.

`/auth/logout` ends the current session. `/auth/logout/all` and a back-channel
logout that names only `sub` bump the account's session version, which ends
every session of the account on its next request. A back-channel logout with a
`sid` revokes that session only.

### CSRF

Every unsafe method on a session-authenticated route is protected by
`AuthCsrfMiddleware`, a `CsrfViewMiddleware` subclass. Spread `CSRF_SETTINGS`
into your settings and add `CSRF_MIDDLEWARE` to `MIDDLEWARE`:

```python
from rn_forge.django.auth import CSRF_MIDDLEWARE, CSRF_SETTINGS

globals().update(CSRF_SETTINGS)
MIDDLEWARE = [..., CSRF_MIDDLEWARE]
RN_FORGE_DJANGO = {"AUTH": {"PROBLEM_TYPE_BASE": "https://errors.example.com/"}}
```

The cookie is `XSRF-TOKEN` and the header `X-XSRF-TOKEN`, Angular's defaults;
the cookie is not `HttpOnly` so that Angular can copy it into the header.
`GET /auth/session` always sets the cookie, including when it answers `401`, so
`POST /auth/login/password` is protected before sign-in. The token rotates at
login and logout. A rejection is the `403` `csrf-failed` problem
(`CSRF_FAILURE_VIEW`), and its reason is logged, never sent.

Beyond Django's token and origin check, `AuthCsrfMiddleware` rejects
`Sec-Fetch-Site: cross-site` on an unsafe method, even from a trusted origin.
Requests that carry a `Bearer` `Authorization` header skip the check, as does
the back-channel logout route, which carries a signed token. A `Basic` header
does not: browsers replay cached Basic credentials on their own.

DRF wraps its views in `csrf_exempt`, so the middleware does not guard them. A
session authentication class calls `enforce_csrf(request)` for the requests it
authenticates; it runs the same check and raises `CsrfFailed`.

`CSRF_TRUSTED_ORIGINS` lists the other origins that may post. Behind a proxy,
Django takes the request's scheme and host from forwarded headers only when you
set `SECURE_PROXY_SSL_HEADER` and `USE_X_FORWARDED_HOST`, and the forwarded host
must be in `ALLOWED_HOSTS`; without them a forged `X-Forwarded-*` header does
not make a foreign `Origin` acceptable.

`auth_urlpatterns` raises `ImproperlyConfigured` when `AuthCsrfMiddleware` is
not in `MIDDLEWARE`, when the cookie and header names, `HttpOnly`,
`CSRF_USE_SESSIONS` or `CSRF_FAILURE_VIEW` differ from `CSRF_SETTINGS`, outside
`DEBUG` when the other CSRF cookie settings differ, and in every mode when
`PROBLEM_TYPE_BASE` is unset: without a `type_base`, `csrf-failed` and
`forbidden` differ only in `detail`.

Login transactions (behind the `__Host-login-tx` cookie), replay
records and revoked session IDs live in Django's cache; use the Redis cache
backend in production, with the `redis` extra. A callback error redirects to
`error_route` with `?error=` set to `access_denied`, `account_not_provisioned`
or `login_failed`. `/auth/login/development` answers only while
`settings.DEBUG` is true.

## Accounts and authentication

`rn_forge.django.auth.accounts.DjangoAccountResolver` links external identities
to Django users through the `ExternalAccount` model (unique on
`(issuer, subject)`; run the auth app's migration). Give it a `ProviderPolicy`
per provider ID:

- `provisioning="existing"` rejects an identity with no account;
  `provisioning="jit"` creates one on first login, limited to
  `email_domains` when set (which also requires a verified email).
- `authoritative_domains` lists the email domains for which the provider is
  authoritative: only there does a verified email link to an existing user.
  Unverified emails never link and are not stored on provisioned users.
- `sync(user, identity)` runs at every login to copy attributes onto the user.
- `resolver.link(issuer, subject, user)` links a service account explicitly.

A rejected login redirects to the error route with
`?error=account_not_provisioned`. The session version behind
`/auth/logout/all` is kept by `DjangoAccountStateWriter` (pass it as
`AuthRoutesConfig.account_state`) and read by the default
`DjangoAuthorizationContextProvider`.

For DRF, list the classes the view accepts. A session-only view, or one listing
the session class first, answers `401` without a `WWW-Authenticate` header; a
view listing the bearer class first answers with its `Bearer` challenge. This
needs the problem-details exception handler:

```python
class Bearer(JWKSBearerAuthentication):
    jwks_url, issuer, audience = ..., ..., ...
    accounts = resolver
    contexts = cache
    scope_map = {"orders:read": frozenset({"orders.list", "orders.read"})}

class Session(PrincipalSessionAuthentication):
    sessions = sessions_for(config)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [Session, Bearer],
    "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
}
```

A request with an `Authorization` header is authenticated by the bearer class
alone: an invalid token, or one whose subject has no linked account, is `401`
even with a valid session cookie. Bearer lookup never provisions. The bearer
principal's permissions are the account's, limited to what its scopes allow
through `scope_map`.

The `/auth/session` body does not yet carry `name`, `email` or `picture`;
the default resolver does not store them.
