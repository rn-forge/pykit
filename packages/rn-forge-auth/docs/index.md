# rn-forge-auth

`rn-forge-auth` holds authentication primitives, built on `rn-forge-web`:
`Principal`, `Requirement`, the `Authenticator` and `Authorizer` contracts,
`ScopeAuthorizer` and `principal_from_claims`.

The base install gives the core, `rn_forge.auth`. The `oidc` extra adds
`pyjwt[crypto]` for the adapter, `rn_forge.auth.oidc`, which the core never
imports.

## Where to start

- [Authentication and authorization](guides/usage.md) covers installing the core
  and the `oidc` extra, the contracts and OIDC bearer verification.
- The [API reference](reference/index.md) is generated from the docstrings.
