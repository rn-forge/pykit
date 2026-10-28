# Changelog

Notable changes to `rn-forge-django`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- The `/auth` surface over `rn-forge-auth`, in `rn_forge.django.auth`.
  `auth_urlpatterns(config, prefix="auth")`, configured by `AuthRoutesConfig`,
  serves `providers`, `login/{provider}`, `callback/{provider}`, `session`,
  `logout`, `logout/all`, `backchannel-logout/{provider}` and `login/password`
  over `LoginFlow`. Providers, the account resolver and the authorization
  context provider are `rn-forge-auth` objects passed in the configuration;
  there is no settings block for them. The development provider exists only
  under `DEBUG`. A callback error redirects to the error route with one of
  `access_denied`, `account_not_provisioned` and `login_failed`.
- Login transactions, replay records and revoked session IDs in Django's cache:
  `CacheTransactionStore` and `CacheReplayStore`, behind the `__Host-login-tx`
  cookie. The `redis` extra names `rn-forge-auth[redis]`, the client for
  Django's Redis cache backend.
- Sessions on `django.contrib.sessions` (`db` or `cached_db`).
  `SESSION_SETTINGS` carries the `__Host-session` cookie settings. `Sessions`
  applies a 30-minute sliding idle timeout and a 12-hour absolute timeout
  (`AuthRoutesConfig.idle_timeout` and `absolute_timeout`), and deletes a
  session whose version differs from its account's, whose account is inactive,
  or whose `session_ref` is revoked. `GET /auth/session` does not extend the
  session. `rotate_session` gives a session a new ID after a privilege change.
- CSRF protection for session routes. `AuthCsrfMiddleware` adds the
  `Sec-Fetch-Site: cross-site` rejection and the `Bearer` `Authorization`
  exemption to `CsrfViewMiddleware`. `CSRF_SETTINGS` configures Angular's
  `XSRF-TOKEN` cookie and `X-XSRF-TOKEN` header, and `csrf_failure_view`
  answers the `403` `csrf-failed` problem. `/auth/session` always sets the
  cookie, and login and logout rotate the token. `enforce_csrf` runs the same
  check for DRF views, which are `csrf_exempt`.
- `RN_FORGE_DJANGO["AUTH"]["PROBLEM_TYPE_BASE"]`. `auth_urlpatterns` raises
  `ImproperlyConfigured` without it, so `csrf-failed` and `forbidden` differ in
  `type`, and refuses unsafe session, CSRF and cache settings at startup.
- Rate limiting: `FixedWindowLimiter` and `RateLimit`, a fixed-window counter
  over Django's cache. `/auth/login/password` is limited per client and per
  username, callbacks per client, with limits on `AuthRoutesConfig`. A limited
  request is a `429` `too-many-requests` problem with `Retry-After`.
- Audit events on the `rn_forge.audit.auth` `AppLogger` channel: login success
  and failure, logout, account provisioned, rejected and disabled,
  authorization denied and rate limiting.
- Account resolution. `DjangoAccountResolver` is an `AccountResolver` over the
  Django user model and the `ExternalAccount` link model, unique on
  `(issuer, subject)`, with the auth app's first migration, which also adds
  `AccountState` for the session version. A per-provider `ProviderPolicy` sets
  `existing` or `jit` provisioning, an email-domain allowlist and the domains
  for which a verified email links to an existing user; an optional `sync` hook
  copies attributes at each login, and `link` records service accounts.
  `DjangoAccountStateWriter` persists session versions and the `active` flag.
- Authorization from Django groups and permissions:
  `DjangoAuthorizationContextProvider` (staff and superuser bypass as roles),
  `connect_authorization_signals` for cache invalidation,
  `PermissionKeyPermission` and `ResourcePolicyViewMixin`.
- `PrincipalSessionAuthentication` yields a `session` principal from
  `Sessions.read` and enforces CSRF; `sessions_for(config)` builds its
  `Sessions` from `AuthRoutesConfig`. A request with an `Authorization` header
  is authenticated by the bearer class alone.

### Changed

- `rn_forge_django_settings` is built on first use, so a settings module can
  import this package before it defines `RN_FORGE_DJANGO`.
- `problem_details_exception_handler` renders with `PROBLEM_TYPE_BASE` when it
  is set.
- Breaking: `PrincipalBearerAuthentication` and `JWKSBearerAuthentication`
  need `accounts` and `contexts` class attributes. They resolve the token's
  `(issuer, subject)` through `AccountResolver.lookup` (never provisioning) and
  answer `401` for an unlinked or inactive account. The principal's `subject` is
  the account ID, its roles, tenant and attributes come from the authorization
  context, and its permissions are the context's limited by `scope_map`.
- Breaking: `DEFAULT_PERMISSION_ACTION_MAP` moved from
  `rn_forge.django.auth.drf.mixins` to `rn_forge.auth`.
- Breaking: depends on `rn-forge-auth` and imports `Principal`, `Requirement`
  and the authenticator contracts from it. The `oidc` extra names
  `rn-forge-auth[oidc]` instead of `rn-forge-web[auth]`.
- Breaking: `JWKSBearerAuthentication` loses its `fetch` hook, and its
  `cache_timeout` now means the key-set `lifespan` in seconds, default 300 in
  place of 86400. The new `cooldown_duration` (default 30 seconds) is the
  fewest seconds between two key set fetches.
- The `oidc` and `all` extras no longer name `rn-forge-commons[auth]`, which no
  longer exists.
- **Breaking:** `AuthorizedAPIView` and `AuthorizedModelViewSet` check
  `PermissionKeyPermission` over `BaseAPIView` and `BaseModelViewSet`, so
  `UserViewSet`, `GroupViewSet` and `PermissionViewSet` still require their
  `permission_key`. A subclass that relied on the removed mixins' attributes
  and hooks (`credentials`, `user`, `is_request_authorized`,
  `validate_permissions`, `validate_object_permissions`) must move to a
  `Requirement` or a `ResourcePolicy`. The principal now comes from
  `request.user`, the staff and superuser bypass comes from the authorization
  context, and an action map is the view's `permission_action_map`.
- The package declares the MIT licence and is published to PyPI.

### Removed

- **Breaking:** the locally issued JWT flows are gone, with the `jwt` extra and
  `djangorestframework-simplejwt`: `rn_forge.django.auth.jwt`
  (`JWTAuthentication`, `JWTCredentials`, `JWTUtils`, `LoginExchangeViewMixin`,
  `JWTAuthenticationViewMixin`, `UserTokenView`) and the `user-token/` route of
  `rn_forge.django.auth.urls`. Authenticate API clients with the OIDC bearer
  classes in `rn_forge.django.auth.drf`.
- **Breaking:** the `rn_forge.django.auth.basic` and `rn_forge.django.auth.saml`
  views (`BasicLoginAPIView`, `BasicLoginViewMixin`, `SAMLLoginAPIView`,
  `SAMLLoginViewMixin`, `SampleSAMLLoginAPIView`) are gone, along with the
  `RN_FORGE_DJANGO["AUTH"]["SAML"]` setting and `AuthSAMLSettings`. A SAML IdP
  federates through a broker that speaks OIDC.
- **Breaking:** `BaseCredentials` and `LoginPayload` (`rn_forge.django.auth.credentials`
  and `rn_forge.django.auth.payload`), `AuthorizationViewMixin` and
  `PermissionKeyViewMixin` (`rn_forge.django.auth.drf.mixins`) and
  `AuthorizationPermission` (`rn_forge.django.auth.drf.permissions`) are gone.
  Check permissions with `PermissionKeyPermission` and `ResourcePolicyViewMixin`.
- **Breaking:** `BaseLoginViewMixin`, `BaseLoginAPIView` and `LogoutAPIView`
  (`rn_forge.django.auth.drf.authentication`) are gone. `auth_urlpatterns`
  serves login and logout.
- **Breaking:** the `saml` extra is gone, and with it the `python3-saml`
  dependency.
- **Breaking:** the `RN_FORGE_DJANGO["DRF"]["VIEWS"]` settings block
  (`PERMISSION_ACTION_MAP`), `DRFViewsSettings` and `DRFViewsSettingsDict` are
  gone; set `permission_action_map` on the view.

## [0.5.1] - 2026-10-25

### Changed

- Requires its rn-forge dependencies by version range from pykit's index
  (ADR-0004), not by git URL.

## [0.5.0] - 2026-10-16

### Changed

- Breaking: the `transfer` extra names `rn-forge-data` and no longer pulls
  `django-import-export[xlsx]`; it installs `django-import-export` alone. The
  `fixtures` extra names `rn-forge-data[pandas]` in place of
  `rn-forge-commons[excel,pandas]`.

### Fixed

- `rn_forge.django.drf.transfer` imported `openpyxl` without declaring it, and
  worked only because another dependency installed it. The `transfer` extra
  now declares it through `rn-forge-data`, and the extra's smoke check imports
  the module from a clean install.

## [0.4.0] - 2026-10-05

### Added

- Soft delete in AIP-164's shape. `SoftDeleteModelMixin` and
  `SoftDeleteQuerySet` in `rn_forge.django.models` add a nullable, indexed
  `delete_time`, `soft_delete(actor=)`, `undelete(actor=)`, `.live()` and
  `.deleted()`, with an unfiltered default manager. `SoftDeleteMixin` in
  `rn_forge.django.drf.views` makes `DELETE` answer `200` with the resource,
  adds `POST {id}:undelete` and `showDeleted` on `list`, and answers `409` to
  `PUT` and `PATCH` on a deleted resource. `WireAutoSchema` documents the
  three.
- `ReadMaskMixin` in `rn_forge.django.drf`: `retrieve`, `list` and `batch_get`
  accept `readMask` and answer `200` with only the named fields.
  `BaseModelViewSet` includes it, and `WireAutoSchema` documents the parameter
  on those actions.
- `BatchGetMixin` (`GET :batchGet?ids=1&ids=2`) and `BatchUpdateMixin`
  (`POST :batchUpdate`, one JSON Merge Patch and optional `ifMatch` per item)
  in `rn_forge.django.drf.transfer`. `BatchUpdateMixin` has
  `batch_update_requires_if_match`, `etag_codec` and
  `validate_batch_update_item(instance, data)`. `batch_resource_name` is
  shared with `BatchCreateMixin`.

### Changed

- `BatchDeleteMixin` deletes each row through the view's `perform_destroy` in
  place of `instance.delete()`, so a `SoftDeleteMixin` viewset soft-deletes in
  a batch. For any other viewset the behavior is unchanged.
- **Breaking:** `CursorPagination` and `OrderByFilter` use every `orderBy` term,
  not the first. `ordering_fields` may name nullable fields and relation
  paths, `NULL` sorts last in both directions, and the `orderBy` OpenAPI
  description says it takes a comma-separated list. A view's non-primary-key
  default `ordering` supplies the terms when the request gives no `orderBy`.
  Page tokens issued before the change are rejected with 400.
- **Breaking:** `BaseModelViewSet`'s `PATCH` now takes
  `application/merge-patch+json` (RFC 7396) and answers `application/json`
  with 415 and `Accept-Patch`. `PUT` and `POST` still take `application/json`.
    - The merged document is validated as a full update; a top-level `null` sets
      the field to `null`, and read-only or unknown members are ignored.
    - A versioned instance enforces `If-Match` on `PATCH`, and `retrieve` and
      `PATCH` answer with an `ETag`.
    - New: `MergePatchMixin` and `MergePatchParser`, exported from
      `rn_forge.django.drf`.
- **Breaking:** the import and batch endpoints word their 422 details as
  `rn-forge-web` does, which `rn-forge-fastapi` also uses.
    - A request over `transfer.max_rows` on `:import`, `:batchCreate` and
      `:batchDelete` is a 422 problem with detail
      `The import exceeds the limit of N rows.` or
      `The batch exceeds the limit of N rows.` and no `errors` member. It was an
      `errors` entry with an empty pointer.
    - A `:import` request with no `file` part answers `This field is required.` at
      `/file`, not `No file was submitted.`.
    - A missing `requests` or `ids` member answers `This field is required.` at
      `/requests` or `/ids`. An empty list or a non-list still answers
      `A non-empty list is required.`.
    - `validateOnly` and `prefill` accept `true` or `1`, ignoring case, as before;
      the unsupported and unreadable `file` details are unchanged in wording.

### Removed

- **Breaking:** `rn_forge.django.utils.RequestUtils` and the DRF `RequestUtils`
  aliases are gone, so `RequestUtils` names only the DRF class.
    - `rn_forge.django.utils.RequestUtils.debug_request(request)` is now
      `rn_forge.django.views.debug_request(request)`.
    - `rn_forge.django.drf.DRFUtils` is now `rn_forge.django.drf.RequestUtils`.
    - `RequestUtils.get_request_param(request, key)` is now
      `RequestUtils.get_param(request, key)`.
    - `RequestUtils.get_request_data(request)` is now
      `RequestUtils.get_data(request)`.
    - `RequestUtils.get_request_value(request, key)` is now
      `RequestUtils.get_value(request, key)`.

## [0.3.0] - 2026-09-27

Released with pykit's first coordinated set of tags (release-1).

`rn-forge-django-v0.1.0` to `rn-forge-django-v0.2.2` predate this file; their
notes are on the [GitHub Releases](https://github.com/rn-forge/pykit/releases)
page.

### Fixed

- `BatchCreateMixin` reports an invalid item's errors under DRF 3.18, which keys
  `ListSerializer` errors by item index instead of listing them.
