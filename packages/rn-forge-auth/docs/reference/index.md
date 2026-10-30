# Reference

The API reference is generated from source docstrings with `mkdocstrings`.

The core, `rn_forge.auth`:

- [Principal](principal.md)
- [Permissions](permissions.md)
- [Authorization](authorization.md)
- [Identity](identity.md)
- [Login flow](flow.md)
- [Accounts](accounts.md)
- [Authorization context](context.md)
- [Authorization context cache](context_cache.md)
- [Resource policy](policy.md)
- [Session, transaction and replay stores](stores.md)
- [Return target](redirects.md)
- [Session body](session_body.md)
- [Audit events](audit.md)
- [Security-control conformance](conformance.md)

The adapters, each imported directly:

- [OIDC](oidc.md), `rn_forge.auth.oidc`, behind the `oidc` extra
- [Redis](redis.md), `rn_forge.auth.redis`, behind the `redis` extra
- [Testing](testing.md), `rn_forge.auth.testing`, behind the `oidc` extra
