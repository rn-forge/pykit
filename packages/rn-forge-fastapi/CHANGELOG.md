# Changelog

Notable changes to `rn-forge-fastapi`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- The `/auth` surface over `rn-forge-auth`: `auth_router(config, prefix="/auth")`,
  configured by `AuthRoutesConfig`, returns an `APIRouter` serving `providers`,
  `login/{provider}`, `callback/{provider}`, `session`, `logout`, `logout/all`,
  `backchannel-logout/{provider}` and `login/password` over `LoginFlow`, with
  the responses, error codes and `__Host-login-tx` cookie of the Django binding.
  The development provider exists only with `debug=True`. `Sessions` keeps the
  login session in an `rn-forge-auth` `SessionStore` behind the `__Host-session`
  cookie. The stores' synchronous calls and the Authlib providers run in the
  thread pool.
- `SessionMiddleware` resolves the login session once per request over a
  `SessionStore`, extends the 30-minute idle expiry and refreshes the
  `__Host-session` cookie on every request except `GET /auth/session`, and
  clears a cookie that names no valid session. `Sessions.read` enforces the
  12-hour absolute timeout and deletes a session whose version differs from
  its account's, whose account is inactive or whose `session_ref` is revoked.
  `active_session(request)` returns the resolved session, and
  `await rotate_session(request)` gives it a new ID after a privilege change.
  `sessions_for(config)` builds the `Sessions` the routes use; `AuthRoutesConfig`
  gains `clock`.
- Outside `debug`, `auth_router` and `Sessions` refuse in-memory session,
  transaction and replay stores with a `RuntimeError`.
- The `redis` extra names `rn-forge-auth[redis]`.
- Synchronizer-token CSRF protection. `SessionMiddleware` checks an unsafe
  request that carries the `__Host-session` cookie (live, anonymous or stale),
  or goes to `/auth/login/password` (`login_path`), and never back-channel
  logout; a cookie-less request to an application route is left alone: the `X-XSRF-TOKEN` header must equal, in
  constant time, the token stored for the session, which the readable
  `XSRF-TOKEN` cookie carries. The `Origin` (or `Referer` over HTTPS) must be
  the request's own origin or one of `trusted_origins`, `Sec-Fetch-Site:
  cross-site` is rejected, forwarded scheme and host count only from a
  `trusted_proxies` peer, and a `Bearer` `Authorization` header skips the check.
  A failure is the `403` `csrf-failed` problem. Tokens live in a `CsrfStore`
  keyed by session ID: `InMemoryCsrfStore`, and `RedisCsrfStore` in
  `rn_forge.fastapi.auth.redis` (the `redis` extra, not imported by the
  facade). `GET /auth/session` always sets the cookie, starting a 10-minute
  anonymous session behind `__Host-session` when there is no session, so
  `/auth/login/password` is protected. Login replaces the session ID and the
  token, logout starts a new anonymous session with a new token, and
  `rotate_session` carries the token to the new ID. `AuthRoutesConfig` gains
  `csrf`, `trusted_origins` and `trusted_proxies`, and `Sessions` takes a
  `CsrfProtection`.
- `AuthRoutesConfig` raises `ValueError` without a `problem_type_base`, and
  outside `debug` an in-memory CSRF store is refused like the other stores.

### Changed

- `rn_forge.fastapi.auth` is a package; `bearer_auth`, `basic_auth` and
  `requires` import from it as before.
- Breaking: depends on `rn-forge-auth` and imports `Principal`, `Requirement`
  and the authenticator contracts from it. The `oidc` extra names
  `rn-forge-auth[oidc]` instead of `rn-forge-web[auth]`.

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
