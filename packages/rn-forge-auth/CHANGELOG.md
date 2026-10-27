# Changelog

Notable changes to `rn-forge-auth`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- The `rn-forge-auth` package scaffold: the `rn_forge.auth` core and the
  `oidc` extra for the `rn_forge.auth.oidc` adapter.
- `Principal`, `Requirement`, `Authenticator`, `AsyncAuthenticator`,
  `Authorizer`, `ScopeAuthorizer` and `principal_from_claims`, moved from
  `rn-forge-web` into the `rn_forge.auth` core, and `OidcAuthenticator`, moved
  from `rn_forge.web.oidc` into `rn_forge.auth.oidc`.
