# rn-forge-auth

`rn-forge-auth` holds authentication primitives, built on `rn-forge-web`:
`Principal`, `Requirement`, the `Authenticator` and `Authorizer` contracts,
`ScopeAuthorizer` and `principal_from_claims`.

The base install gives the core, `rn_forge.auth`. The `oidc` extra adds
`pyjwt[crypto]` for the adapter, `rn_forge.auth.oidc`, which the core never imports.
