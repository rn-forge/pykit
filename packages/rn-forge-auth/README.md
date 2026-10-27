# rn-forge-auth

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-auth/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-auth/CHANGELOG.md)
· [Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-auth) ·
[All pykit packages](https://rn-forge.github.io/pykit/)

Authentication primitives for Python programming, built on `rn-forge-web`. The
base install carries no third-party dependencies; the `oidc` extra adds
`pyjwt[crypto]` for the OIDC adapter.

- `rn_forge.auth` — the core: `Principal`, `Requirement`, `Authenticator`,
  `AsyncAuthenticator`, `Authorizer`, `ScopeAuthorizer` and
  `principal_from_claims`. The facade re-exports the core only.
- `rn_forge.auth.oidc` — `OidcAuthenticator`, behind the `oidc` extra. The core
  never imports it; `.importlinter` proves that.
