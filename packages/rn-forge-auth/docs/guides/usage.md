# Authentication and authorization

The package has one core and two adapters. `rn_forge.auth` holds the contracts
and needs no third-party package. `rn_forge.auth.oidc` verifies OIDC bearer
tokens, and `rn_forge.auth.redis` keeps sessions and single-use records in
Redis; both import the core and the core never imports them. The `oidc` extra
installs `pyjwt[crypto]` and `authlib`, the `redis` extra installs `redis`, and
the `rn_forge.auth` facade re-exports neither adapter.

## How the pieces fit

A login and each later request pass through the same stages:

```text
provider -> ExternalIdentity -> AccountResolver -> account ID
  -> session (SessionInfo) or bearer token
  -> AuthorizationContext -> Principal
  -> Requirement (route) -> ResourcePolicy (object and query)
```

1. An `IdentityProvider` authenticates the user and returns an
   `ExternalIdentity`. The login is held in a `TransactionStore` while the
   browser is away.
2. An `AccountResolver` maps the identity to an internal account ID, or rejects
   the login. A `SessionStore` then holds a `SessionInfo` under a random ID.
3. On each request, a session or a verified bearer token identifies the account.
   An `AuthorizationContextProvider`, usually behind an
   `AuthorizationContextCache`, returns the account's current permissions, and
   the binding builds a `Principal`. For a bearer caller the token's scopes
   limit those permissions and never add to them.
4. An `Authorizer` checks the route's `Requirement` against the `Principal`. A
   `ResourcePolicy` then checks the object, or narrows the query.

| Guide | Covers |
| -- | -- |
| [Contracts](contracts.md) | Identity, account resolution, authorization context and cache, `Principal` and `Requirement`, permissions and the scope limit, resource policy, `return_to` and the session body |
| [Token profiles](tokens.md) | `JwtVerifier`, `IdTokenVerifier` and `LogoutTokenVerifier`, modes, the login-client rule, key rotation and cooldown |
| [Stores](stores.md) | The four store protocols, in-memory and Redis, and the atomic operation each relies on |
| [Testing](testing.md) | `FakeOidcProvider` and its failure switches |

## Installing

Declare the package from pykit's index, with the extras you use:

```toml
dependencies = ["rn-forge-auth[oidc,redis]>=0.1.0,<0.2"]
```

The base install, `rn-forge-auth`, is enough to write your own authenticator.
Importing `rn_forge.auth.oidc` without the extra fails with
`ModuleNotFoundError` for `jwt`. `rn-forge-django[oidc]` and
`rn-forge-fastapi[oidc]` already name `rn-forge-auth[oidc]`. Importing
`rn_forge.auth.redis` without the `redis` extra fails with
`ModuleNotFoundError` for `redis`.


## With rn-forge-web and the framework packages

`rn-forge-web` owns the wire contract that surrounds these types:

- `Credentials`, the raw scheme and token lifted off a request;
- `parse_authorization`, which reads an `Authorization` header into
  `Credentials`;
- `challenge_header`, which builds the `WWW-Authenticate` value;
- `AUTH_FAILED_DETAIL`, the fixed 401 detail, `"Authentication failed."`;
- the `AuthenticationFailed` and `PermissionDenied` exceptions.

This package adds the verified caller and the decisions made about it. A
framework binding does the plumbing between them: it parses the header, calls
the `Authenticator`, turns `AuthenticationFailed` into a 401 with a challenge
and `AUTH_FAILED_DETAIL`, and turns `PermissionDenied` into a 403.
`rn-forge-django` binds `Principal` to DRF with `PrincipalBearerAuthentication`,
`JWKSBearerAuthentication` and `requires`; `rn-forge-fastapi` binds it with
`bearer_auth`, `basic_auth` and `requires`. See those packages' guides for
wiring.
