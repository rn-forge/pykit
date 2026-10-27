# Changelog

Notable changes to `rn-forge-auth`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- `validate_return_to` and `InvalidReturnTo`, which accept only a relative path
  under configured prefixes; `SessionBody`, the camelCase `/auth/session`
  body; and `CallbackError`, the closed list of callback error codes.
- The `rn-forge-auth` package scaffold: the `rn_forge.auth` core and the
  `oidc` extra for the `rn_forge.auth.oidc` adapter.
- `Principal`, `Requirement`, `Authenticator`, `AsyncAuthenticator`,
  `Authorizer`, `ScopeAuthorizer` and `principal_from_claims`, moved from
  `rn-forge-web` into the `rn_forge.auth` core, and `OidcAuthenticator`, moved
  from `rn_forge.web.oidc` into `rn_forge.auth.oidc`.
- `JwtVerifier`, `discover_oidc`, `fetch_json`, `FetchJson`, `OidcConfiguration`
  and `TokenVerificationError`, moved from `rn_forge.commons.integration.auth`
  into `rn_forge.auth.oidc`. `JwtVerifier` gains `from_jwks_url`.
- The identity and authorization contracts: `ExternalIdentity`,
  `IdentityProvider`, `ProviderKind`, `LoginStart`, `LoginTransaction`,
  `SessionInfo`, `AccountResolver`, `AccountRejected`, `AuthorizationContext`,
  `AuthorizationContextProvider` and `ResourcePolicy`.
- `requirement_for`, `effective_permissions` and `Mechanism`.
  `DEFAULT_PERMISSION_ACTION_MAP`, moved from `rn-forge-django`.
- `AuthorizationContextCache`, which caches an `AuthorizationContextProvider`
  by account and authorization version with a TTL, with
  `AuthorizationVersions`, `InMemoryAuthorizationVersions` and
  `AccountStateWriter`.
- `IdTokenVerifier`, the ID-token profile, which runs Authlib's `CodeIDToken`
  and checks `auth_time` against `max_age`, and `LogoutTokenVerifier`, the
  back-channel logout-token profile, which checks `typ`, the `iat` window and a
  single-use `jti`.
- `ReplayStore` and `InMemoryReplayStore`, the single-use and revoked-`sid`
  records.
- `JwtVerifier` and `OidcAuthenticator` take `mode` (`"rfc9068"` or
  `"rfc7519"`) and `login_client_id`; the latter is refused as an audience
  outside RFC 9068 mode.

### Changed

- Breaking: `JwtVerifier` rejects a token carrying `nonce` or `events`, and
  enforces `typ`: `JWT` or none by default, `at+jwt` in RFC 9068 mode.
- The `oidc` extra adds `authlib>=1.9.1` and `joserfc>=1.7.7`.
- Breaking: `Principal` gains `external_subject`, `permissions`, `attributes`,
  `auth_time` and `amr`, and `mechanism` is the `Mechanism` literal
  (`"session"`, `"bearer"` or `"basic"`) instead of `str`.
- Breaking: `Requirement` gains `any_permission` and `all_permissions`, checked
  against `Principal.permissions`, and loses `any_role` and `all_roles`.
- `JwtVerifier` takes its keys from PyJWT's `PyJWKClient`, replacing
  `JwksCache`. `from_issuer` and `from_jwks_url` take `lifespan` (default 300
  seconds) and `cooldown_duration` (default 30 seconds) in place of `max_age`,
  and `from_jwks_url` no longer takes `fetch`: only the discovery document uses
  `fetch_json`. The `oidc` extra is `pyjwt[crypto]` alone; it requires PyJWT
  2.15.0 or later.
