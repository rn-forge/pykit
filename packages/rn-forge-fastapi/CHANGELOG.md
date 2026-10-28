# Changelog

Notable changes to `rn-forge-fastapi`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- The `/auth` surface over `rn-forge-auth`. `auth_router(config, prefix="/auth")`,
  configured by `AuthRoutesConfig`, returns an `APIRouter` serving `providers`,
  `login/{provider}`, `callback/{provider}`, `session`, `logout`, `logout/all`,
  `backchannel-logout/{provider}` and `login/password` over `LoginFlow`, with the
  responses, error codes and `__Host-login-tx` cookie of the Django binding. The
  development provider exists only with `debug=True`. `AuthRoutesConfig` raises
  `ValueError` without a `problem_type_base`. The stores' synchronous calls and
  the Authlib providers run in the thread pool. The auth guide describes the
  setup, configuration defaults and the protocols an application implements.
- Login sessions. `SessionMiddleware(sessions=sessions_for(config))` resolves the
  session once per request over a `SessionStore` behind the `__Host-session`
  cookie, extends the 30-minute idle expiry and refreshes the cookie on every
  request except `GET /auth/session`, and clears a cookie that names no valid
  session. `Sessions.read` enforces the 12-hour absolute timeout and deletes a
  session whose version differs from its account's, whose account is inactive or
  whose `session_ref` is revoked. `active_session(request)` returns the resolved
  session, and `await rotate_session(request)` gives it a new ID after a
  privilege change. The middleware takes `untouched_paths`, `login_path` and
  `csrf_exempt_prefixes` for a router mounted under another prefix.
- Synchronizer-token CSRF protection. `SessionMiddleware` checks an unsafe
  request that carries the `__Host-session` cookie (live, anonymous or stale), or
  goes to `/auth/login/password`, and never back-channel logout; a cookie-less
  request to an application route is left alone. The `X-XSRF-TOKEN` header must
  equal, in constant time, the token stored for the session, which the readable
  `XSRF-TOKEN` cookie carries. The `Origin` (or `Referer` over HTTPS) must be the
  request's own origin or one of `trusted_origins`, `Sec-Fetch-Site: cross-site`
  is rejected, forwarded scheme and host count only from a `trusted_proxies`
  peer, and a `Bearer` `Authorization` header skips the check. A failure is the
  `403` `csrf-failed` problem. Tokens live in a `CsrfStore` keyed by session ID:
  `InMemoryCsrfStore`, and `RedisCsrfStore`. `GET /auth/session` always sets the
  cookie, starting a 10-minute anonymous session when there is no session, so
  login is protected. Login replaces the session ID and the token, logout starts
  a new anonymous session, and `rotate_session` carries the token to the new ID.
- Rate limits on `/auth/login/password` (per client and per submitted username)
  and the callback routes (per client), with the defaults of the Django binding,
  set by `AuthRoutesConfig`'s `limiter`, `password_client_limit`,
  `password_account_limit` and `callback_client_limit` (`RateLimit(limit,
  window)`, or `None` for no limit). A limited request is the `too-many-requests`
  problem, `429` with `Retry-After`. `InMemoryRateLimiter` counts in a fixed
  window; `RedisRateLimiter` counts with `INCR` and `EXPIRE`. The client is the
  connection's peer, or the nearest address in `X-Forwarded-For` that is not a
  trusted proxy when the peer is in `trusted_proxies`.
- Authentication and authorization dependencies. `current_principal(bearer=None)`
  yields the session `Principal` (roles and permissions from the account's
  authorization context, `auth_time` and `amr` from the session) or the bearer
  one; a request with an `Authorization` header is authenticated by `bearer`
  alone, so an invalid token is a `401` even with a valid session cookie.
  `requires_permission(authenticate, key, action, action_map=None)` enforces
  `requirement_for(key, action)`. `PolicyGuard(policy, hides_existence=False)`
  applies a `ResourcePolicy`: `scope(principal, action, query)` narrows a query of
  any type, and `check(principal, action, obj)` returns the object or raises
  `403`, or `404` when `hides_existence` is true.
- Audit events on the `rn_forge.audit.auth` channel, with the names and fields of
  the Django binding: `login.success`, `login.failure`, `logout`, `logout.all`,
  `logout.backchannel`, `account.rejected`, `account.disabled` and `rate_limited`
  from the routes, and `authorization.denied` from `requires`,
  `requires_permission` and `PolicyGuard`. A provisioning `AccountResolver`
  records `account.provisioned` with `rn_forge.auth.audit`.
- The `redis` extra, which names `rn-forge-auth[redis]`. Outside `debug`,
  `auth_router` and `Sessions` refuse in-memory session, transaction, replay,
  CSRF and rate-limit stores with a `RuntimeError`; the Redis stores are
  `rn_forge.auth.redis` and, for CSRF tokens and the rate limiter, the
  `rn_forge.fastapi.auth.redis` module, which the package facade does not import.
- Tests tag each security control of `rn_forge.auth.conformance` with
  `@pytest.mark.security_control`, and fail when a control has no test.

### Changed

- `rn_forge.fastapi.auth` is a package; `bearer_auth`, `basic_auth` and `requires`
  import from it as before.
- Breaking: `bearer_auth()` takes `accounts` (an `AccountResolver`) and `contexts`
  (an `AuthorizationContextProvider`), and optionally `scope_map`. It resolves the
  token's `(issuer, subject)` with `accounts.lookup`, never provisions, and
  answers `401` for an unlinked or inactive account. The principal's `subject` is
  the account ID; roles, tenant and attributes come from the context, and
  permissions are the context's limited by the token's scopes. It returns a
  `BearerAuth` dependency.
- Breaking: depends on `rn-forge-auth` and imports `Principal`, `Requirement` and
  the authenticator contracts from it. The `oidc` extra names
  `rn-forge-auth[oidc]` instead of `rn-forge-web[auth]`.
- The package declares the MIT licence and is published to PyPI.

## [0.3.2] - 2026-10-25

### Changed

- Requires its rn-forge dependencies by version range from pykit's index
  (ADR-0004), not by git URL.

## [0.3.1] - 2026-10-18

### Fixed

- `FastApiApp` turns off FastAPI's native tracing (0.142 and later) unless the
  application passes `telemetry=`, so `AppConfig(tracing=False)` records no
  server spans.

## [0.3.0] - 2026-10-16

### Changed

- The `transfer` extra names `rn-forge-data` in place of
  `rn-forge-commons[excel]`.

## [0.2.0] - 2026-10-05

### Added

- Soft delete in AIP-164's shape: `soft_delete_router`
  (`DELETE {collection}/{id}` answering `200` with the resource, and
  `POST {collection}/{id}:undelete`), the `SoftDeleteStore` protocol and
  `SoftDeleteState`, and `show_deleted_param()`, all exported from
  `rn_forge.fastapi`.
- `read_mask_param(model)` and `masked(page, mask)` for the `readMask` query
  parameter. `batch_get_router` takes a new `read_mask` parameter (default
  `True`) and applies the mask.
- `batch_get_router` (`GET :batchGet`) and `batch_update_router`
  (`POST :batchUpdate`, one JSON Merge Patch and optional `ifMatch` per item)
  in `rn_forge.fastapi.transfer`, with the `BatchGetStore`, `BatchUpdateStore`
  and `Current` protocols. `batch_update_router` takes `require_if_match` and
  `codec`.
- Route factories in `rn_forge.fastapi.transfer` that match `rn-forge-django`'s
  transfer mixins: `import_router` (`POST :import`), `import_template_router`
  (`GET :importTemplate`), `batch_create_router` (`POST :batchCreate`) and
  `batch_delete_router` (`POST :batchDelete`). Each takes a dependency
  returning a store (`ImportStore`, `TemplateSource`, `BatchCreateStore`,
  `BatchDeleteStore`), `max_rows` and `dependencies=`. `tabular_export`
  applies the export cap inside an application's own list route. `RowsResult`
  gains `total`, `read_rows` takes `formats=` and raises `ValueError` with the
  shared unsupported and unreadable file details. A store raises `RowsInvalid`
  (422) or `ItemsDenied` (403) from `rn-forge-web` for a failure only it can
  find. The factories answer the shared 422s: a missing file, a missing or
  empty list, and a row cap. The transfer guide shows a complete resource over
  `rn-forge-sqlalchemy`'s `upsert` and `keyset`.
- JSON Merge Patch (RFC 7396) binding: `merge_patch_body()` checks the
  `application/merge-patch+json` media type (415 with `Accept-Patch`) and
  returns the raw body, `merge_into(model, current, body)` parses it, merges
  and validates against a pydantic model, and `merge_patch_openapi()` declares
  the request body. Declare `merge_patch_body()` before `require_if_match` and
  call `check_precondition` before `merge_into`. A `null` on a non-nullable
  field renders `This field may not be null.`

### Changed

- **Breaking:** `order_by_param` describes `orderBy` as a comma-separated list
  of fields and names the sortable fields. It described one field. It returns
  every term, as `parse_order_by` in `rn-forge-web` now accepts several and
  rejects a repeated field with 400.
- `read_rows` picks the format from the file extension, and uses the content
  type only when the file name has none, as `rn-forge-django` does. A `.pdf`
  sent as `text/csv` is now unsupported.

### Fixed

- `tabular_response` writes the CSV header row when there are no data rows.

## [0.1.0] - 2026-09-27

First release.
