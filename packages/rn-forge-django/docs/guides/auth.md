# Auth

`rn_forge.django.auth` is an installable Django app (label `rn_forge_django_auth`) providing
login flows and DRF authentication/authorization building blocks. Add it to `INSTALLED_APPS` to
use the bundled `User`/`Group`/`Permission` viewsets and migrations.

## Login flows

All login flows produce a normalized `LoginPayload(user=..., claims=...)` and share a common
`complete_login()` hook that decides what happens next (start a Django session, mint an exchange
token, or mint a final JWT pair).

**Basic (username/password) → session:**

```python
from rn_forge.django.auth.basic.views import BasicLoginAPIView


class LoginView(BasicLoginAPIView):
    """POST {username, password} -> Django session + build_login_response() payload."""
```

**Basic/SAML → short-lived exchange token → JWT:** login views that mix in
`LoginExchangeViewMixin` (via `BasicLoginAPIView`/`SAMLLoginAPIView`) return an
`exchange_token` instead of creating a session. The client then calls `UserTokenView` to trade
that token for a SimpleJWT access/refresh pair:

```python
from rn_forge.django.auth.jwt.views import UserTokenView
```

**SAML:** subclass `SAMLLoginViewMixin`/`SAMLLoginAPIView` and implement
`build_saml_request_data()`, `get_saml_user_lookup()`, and `get_user()` (plus
`create_user_for_login()` if `auto_create_user = True`). `RN_FORGE_DJANGO["AUTH"]["SAML"]`
supplies the `python3-saml` settings dict and default `RETURN_TO` — see
[Settings](settings.md).

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

`JWTAuthentication` wraps SimpleJWT's authenticator so `request.auth` is a `JWTCredentials`
(subclass of `BaseCredentials`) rather than a raw validated token.

`BaseCredentials` exposes `is_authenticated`, `is_staff_user` (staff/superuser bypass),
`user_id`, `email`, and `has_permission(key)` / `has_any_permission(keys)`.

`AuthorizationPermission` denies unauthenticated requests, allows staff/superuser through, and
otherwise defers to the view's `validate_permissions()` — implemented by
`AuthorizationViewMixin` (mix into any `BaseAPIView`/`BaseModelViewSet`):

```python
from rn_forge.django.auth.drf.mixins import AuthorizationViewMixin
from rn_forge.django.drf.views import BaseModelViewSet


class OrderViewSet(AuthorizationViewMixin, BaseModelViewSet):
    permission_key = "app.order"
```

`permission_key` is combined with the current action (`list`, `retrieve`, `create`, `export`,
...) through a permission-action map to build the final key checked against
`credentials.has_permission(...)` — e.g. `app.order.read` for `retrieve`. The default map lives
in `DEFAULT_PERMISSION_ACTION_MAP`; override per-request-app defaults via
`RN_FORGE_DJANGO["DRF"]["VIEWS"]["PERMISSION_ACTION_MAP"]` or per-view via
`permission_action_map`. Override `should_validate_object_permissions()` /
`validate_object_permissions()` for row-level checks.

Use `PermissionKeyViewMixin` instead when you want permission-key resolution without full
`AuthorizationViewMixin` request-access plumbing (e.g. on plain `GenericAPIView`s).

## Externally issued tokens: `PrincipalBearerAuthentication`

For an API whose callers hold tokens issued by an identity provider — Entra ID, Auth0, Okta,
Keycloak — rather than a local `User`, bind DRF to the `rn_forge.web` auth contract. The token is
verified by an `rn_forge.web.Authenticator` you supply, and `request.user` is the resulting
`rn_forge.web.Principal`:

```python
from rest_framework.views import APIView
from rn_forge.django.auth.drf import PrincipalBearerAuthentication, requires
from rn_forge.web import Requirement


class ApiBearer(PrincipalBearerAuthentication):
    authenticator = JwksAuthenticator(jwks_url=..., audience="api://orders", issuer=...)
    realm = "orders"


class OrderView(APIView):
    authentication_classes = [ApiBearer]
    permission_classes = [requires(Requirement(all_scopes=frozenset({"orders:read"})))]
```

With `problem_details_exception_handler` installed: no or invalid credentials are a **401**
`problem+json` with an RFC 6750 `WWW-Authenticate: Bearer realm="orders"` challenge and a detail that
never says why verification failed; valid credentials lacking the scope are a **403** with no
challenge. The same `Requirement` evaluates identically on `rn-forge-fastapi`.

Verifying the JWT is the authenticator's job. There is no JWKS verifier in this package, and none in
`rn-forge-commons` yet; when commons ships one it sits behind the same `Authenticator` protocol and
nothing here changes. The JWKS endpoint an authenticator fetches is IdP configuration:

| IdP | `jwks_url` |
| --- | --- |
| Entra ID | `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys` |
| Auth0 | `https://{domain}/.well-known/jwks.json` |
| Okta | `https://{domain}/oauth2/{authorization-server-id}/v1/keys` |

`PrincipalBasicAuthentication` is the RFC 7617 twin, producing the same `Principal` and the same
401. **It is for local development and simple internal deployments only.**

## Built-in auth management viewsets

`rn_forge.django.auth.drf.views` ships ready-to-mount viewsets for the standard Django auth
models, wired through `AuthorizedExportModelViewSet` / `AuthorizedUpsertImportModelViewSet`:
`PermissionViewSet`, `GroupViewSet`, `UserViewSet`, `UserUpsertImportViewSet`. Mount them (or
`rn_forge.django.auth.urls.urlpatterns`, which already registers them) under your API root.
