# rn-forge-auth

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-auth/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-auth/CHANGELOG.md)
· [Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-auth) ·
[All pykit packages](https://rn-forge.github.io/pykit/)

Authentication and authorization primitives for Python programming, built on
`rn-forge-web`. The base install carries no third-party dependencies.

## Install

```toml
dependencies = ["rn-forge-auth>=0.1,<0.2"]
```

The `oidc` extra adds `pyjwt[crypto]`, `authlib`, `joserfc` and `requests`; the
`redis` extra adds `redis`. The table below names the module each enables.

## Minimum example

```python
from rn_forge.auth import Principal, Requirement, ScopeAuthorizer

caller = Principal(subject="u-1", scopes=frozenset({"orders:read"}))
requirement = Requirement(any_scope=frozenset({"orders:read", "orders:admin"}))
ScopeAuthorizer().authorize(caller, requires=requirement)
```

## Errors

An `Authenticator` raises `rn_forge.web.AuthenticationFailed` (401) and
`ScopeAuthorizer.authorize` raises `rn_forge.web.PermissionDenied` (403).
`link_bearer_principal` raises `PrincipalLinkError`. Importing
`rn_forge.auth.oidc` or `rn_forge.auth.redis` without its extra raises
`ModuleNotFoundError` (`jwt`, `redis`).

| Module | Extra | Holds |
| -- | -- | -- |
| `rn_forge.auth` | none | The core: the identity, account-resolution and authorization-context contracts, `Principal`, `Requirement`, `Authenticator`, `AsyncAuthenticator`, `Authorizer`, `ScopeAuthorizer`, `principal_from_claims`, permissions and the scope limit, `AuthorizationContextCache`, `ResourcePolicy`, the transaction, session and replay stores (in memory), `validate_return_to`, `SessionBody`, `LoginFlow` with `LoginFailed` and `LoginRequest`, and the local login providers of `rn_forge.auth.local` (`PasswordIdentityProvider`, `DevelopmentIdentityProvider`). The facade re-exports the core only. |
| `rn_forge.auth.oidc` | `oidc` (`pyjwt[crypto]`, `authlib`, `joserfc`, `requests`) | `OidcProvider` (OIDC and OAuth 2.0 login, with RP-initiated logout), `BackchannelLogout`, `OidcAuthenticator` and the access-token, ID-token and logout-token verifiers (`JwtVerifier`, `IdTokenVerifier`, `LogoutTokenVerifier`). The core never imports it; `.importlinter` proves that. |
| `rn_forge.auth.redis` | `redis` | `RedisTransactionStore`, `RedisSessionStore`, `RedisReplayStore` and `RedisAuthorizationVersions`. The core never imports it either. |
| `rn_forge.auth.testing` | `oidc` | `FakeOidcProvider` and `Faults`, an offline OIDC provider for tests. The core never imports it. |

Start with the
[guides](https://rn-forge.github.io/pykit/packages/rn-forge-auth/latest/guides/usage.html).
