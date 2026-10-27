# rn-forge-auth

`rn-forge-auth` holds authentication and authorization primitives, built on
`rn-forge-web`: the identity, account-resolution and authorization-context
contracts, `Principal` and `Requirement`, the `Authenticator` and `Authorizer`
contracts, session, transaction and replay stores, and the OIDC token profiles.

The base install gives the core, `rn_forge.auth`. The `oidc` extra adds
`pyjwt[crypto]` and `authlib` for the adapter, `rn_forge.auth.oidc`, and for the
fake provider in `rn_forge.auth.testing`; the `redis` extra adds `redis` for
`rn_forge.auth.redis`. The core imports none of them.

## Where to start

- [Authentication and authorization](guides/usage.md) shows how the pieces fit
  and covers installing the core and its extras.
- [Contracts](guides/contracts.md), [Token profiles](guides/tokens.md),
  [Stores](guides/stores.md) and [Testing](guides/testing.md) cover each
  subsystem.
- The [API reference](reference/index.md) is generated from the docstrings.
