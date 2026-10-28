# Changelog

Notable changes to `rn-forge-auth`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- The `rn-forge-auth` package: the `rn_forge.auth` core, the `oidc` extra for
  the `rn_forge.auth.oidc` adapter and the `redis` extra for the
  `rn_forge.auth.redis` adapter.
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
- `requirement_for`, `effective_permissions` and `Mechanism`, and
  `DEFAULT_PERMISSION_ACTION_MAP`, moved from `rn-forge-django`.
- `AuthorizationContextCache`, which caches an `AuthorizationContextProvider`
  by account and authorization version with a TTL, with
  `AuthorizationVersions`, `InMemoryAuthorizationVersions` and
  `AccountStateWriter`.
- `IdTokenVerifier`, the ID-token profile, which runs Authlib's `CodeIDToken`
  and checks `auth_time` against `max_age`, and `LogoutTokenVerifier`, the
  back-channel logout-token profile, which checks `typ`, the `iat` window and a
  single-use `jti`.
- `JwtVerifier` and `OidcAuthenticator` take `mode` (`"rfc9068"` or
  `"rfc7519"`) and `login_client_id`; the latter is refused as an audience
  outside RFC 9068 mode.
- `ReplayStore` and `InMemoryReplayStore`, the single-use and revoked-`sid`
  records.
- `TransactionStore` and `SessionStore`, with `InMemoryTransactionStore` and
  `InMemorySessionStore`, which are not safe across processes.
- `RedisTransactionStore`, `RedisSessionStore`, `RedisReplayStore` and
  `RedisAuthorizationVersions` in `rn_forge.auth.redis`.
- `validate_return_to` and `InvalidReturnTo`, which accept only a relative path
  under configured prefixes; `SessionBody`, the camelCase `/auth/session`
  body; and `CallbackError`, the closed list of callback error codes.
- `rn_forge.auth.testing`, behind the `oidc` extra: `FakeOidcProvider`, an
  in-process OIDC provider with discovery, key rotation, authorization, token
  and UserInfo endpoints and logout tokens, and `Faults`, a switch for each OIDC
  failure.
- The login adapters:
  - `LoginFlow` and `LoginFailed`, the framework-neutral login flow, and
    `LoginRequest`, the thin request protocol providers read. `begin` validates
    `return_to` and saves the transaction for 600 seconds; `complete` consumes
    it once, rejects a missing, expired, used or foreign transaction, and ends
    every failure in a `LoginFailed` carrying a `CallbackError`.
  - `OidcProvider` in `rn_forge.auth.oidc`, the OIDC login provider over
    Authlib's `OAuth2Session`: discovery with the issuer check, `state`, nonce,
    PKCE S256, the RFC 9207 `iss` check, `max_age`, ID-token verification and
    UserInfo with a `sub` check. `default_claim_mapper`, a `claim_mapper` hook
    and a `token_hook` (the only receiver of the upstream tokens,
    `UpstreamTokens`) shape the result. No token, code or verifier is logged.
  - `OidcProvider.oauth2` and `OAuth2Endpoints`, the same provider for an
    OAuth 2.0 server that issues no ID token: it keeps `state` and PKCE, sends
    no nonce, calls the user endpoint with the access token and maps the result
    (`subject_field` picks the subject, numbers are stringified). The `iss`
    response check applies only with `response_issuer`.
  - `OidcProvider.logout_redirect`, which returns the discovered
    `end_session_endpoint` with `id_token_hint`, `post_logout_redirect_uri` and
    `client_id` when the provider is built with `rp_initiated_logout=True`, and
    `BackchannelLogout` with `LogoutRevocation`, which validate a back-channel
    logout token and return the `(issuer, sid)` to revoke, or the account whose
    session version to bump for a token with only `sub`.
  - `PasswordIdentityProvider` and `DevelopmentIdentityProvider` in
    `rn_forge.auth.local`, with `PasswordVerifier`, `DevelopmentAccount` and
    `DevelopmentModeRequired`. Neither needs an extra.
  - `OidcConfiguration.metadata`, the whole discovery document.
- `FakeOidcProvider` gains `oauth2_only` and `auth_age`, and `Faults` gains
  `userinfo_error`.
- Optional Keycloak tests of the broker profile under `tests/broker/`, run by
  the non-gating `broker-profile` workflow.
- Guides for the contracts, the login providers (including connecting a SAML IdP
  through a broker), the token profiles, the stores, and the fake provider with
  the broker tests.

### Changed

- Breaking: `Principal` gains `external_subject`, `permissions`, `attributes`,
  `auth_time` and `amr`, and `mechanism` is the `Mechanism` literal
  (`"session"`, `"bearer"` or `"basic"`) instead of `str`.
- Breaking: `Requirement` gains `any_permission` and `all_permissions`, checked
  against `Principal.permissions`, and loses `any_role` and `all_roles`.
- Breaking: `JwtVerifier` rejects a token carrying `nonce` or `events`, and
  enforces `typ`: `JWT` or none by default, `at+jwt` in RFC 9068 mode.
- `JwtVerifier` takes its keys from PyJWT's `PyJWKClient`, replacing
  `JwksCache`. `from_issuer` and `from_jwks_url` take `lifespan` (default 300
  seconds) and `cooldown_duration` (default 30 seconds) in place of `max_age`,
  and `from_jwks_url` no longer takes `fetch`: only the discovery document uses
  `fetch_json`.
- The `oidc` extra is `pyjwt[crypto]` with `authlib>=1.9.1` and
  `joserfc>=1.7.7`; it requires PyJWT 2.15.0 or later.
