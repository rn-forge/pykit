# Guides

- [Authentication and authorization](usage.md) — how the pieces fit, from
  identity provider to `ResourcePolicy`; installing the core and the extras; and
  how the package meets `rn-forge-web` and the framework packages.
- [Contracts](contracts.md) — identity providers, account resolution, the
  authorization context and its cache, `Principal` and `Requirement`,
  permissions and the scope limit, resource policy, `return_to` and the session
  body.
- [Token profiles](tokens.md) — the access-token, ID-token and logout-token
  verifiers, their modes, the login-client rule and key-set caching.
- [Stores](stores.md) — the transaction, session, replay and version stores, in
  memory and on Redis.
- [Testing](testing.md) — the in-process fake OIDC provider and its failure
  switches.
