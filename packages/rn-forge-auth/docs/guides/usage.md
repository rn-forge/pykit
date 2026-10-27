# Authentication and authorization

The package has one core and one adapter. `rn_forge.auth` holds the contracts
and needs no third-party package. `rn_forge.auth.oidc` verifies OIDC bearer
tokens and imports the core; the core never imports it. The `oidc` extra
installs `pyjwt[crypto]` and `authlib` for the adapter, and the `rn_forge.auth` facade does
not re-export the adapter.

## Installing

Declare the package from pykit's index, with the extra when you verify OIDC
tokens:

```toml
dependencies = ["rn-forge-auth[oidc]>=0.1.0,<0.2"]
```

The base install, `rn-forge-auth`, is enough to write your own authenticator.
Importing `rn_forge.auth.oidc` without the extra fails with
`ModuleNotFoundError` for `jwt`. `rn-forge-django[oidc]` and
`rn-forge-fastapi[oidc]` already name `rn-forge-auth[oidc]`.

## Principal and Requirement

`Principal` is the verified caller, a frozen dataclass. `subject` is the only
required field. `permissions` holds the effective permissions, `scopes` the
token's delegated scopes (empty for a session), and `roles`, `tenant` and
`attributes` the application's authorization data. `mechanism` is `"session"`,
`"bearer"` or `"basic"` and defaults to `"bearer"`; `claims` keeps every
verified claim; `external_subject`, `auth_time` and `amr` record how the caller
authenticated.

`Requirement` is a declarative access check with four frozen sets. The sets are
ANDed together; the members of an `any_*` set are ORed:

| Field | Satisfied when |
| -- | -- |
| `any_scope` | empty, or the principal holds at least one of them |
| `all_scopes` | the principal holds every one of them |
| `any_permission` | empty, or the principal's permissions include at least one of them |
| `all_permissions` | the principal's permissions include every one of them |

An empty `Requirement()` is satisfied by any principal: it means
"authenticated", not "denied". Routes require permissions, never roles; the
scope clauses can only narrow access further.

```python
from rn_forge.auth import Principal, Requirement

requirement = Requirement(any_scope=frozenset({"orders:read", "orders:admin"}))
caller = Principal(subject="u-1", scopes=frozenset({"orders:read"}))
requirement.is_satisfied_by(caller)  # True
```

### Permissions and the scope limit

`requirement_for` builds the requirement for a resource key and an action:
`requirement_for("orders", "partial_update")` requires `orders.update`.
`DEFAULT_PERMISSION_ACTION_MAP` maps the action names; an `action_map` argument
overrides entries of it, and an action named by neither map is used as is.

A token's scopes limit, and never grant, permissions. `effective_permissions`
returns a session or basic caller's account permissions unchanged, and for a
bearer caller keeps only the permissions that its scopes allow through your
scope map. A scope the map does not name allows nothing.

```python
from rn_forge.auth import effective_permissions, requirement_for

permissions = effective_permissions(
    frozenset({"orders.read", "orders.update"}),
    mechanism="bearer",
    scopes=frozenset({"orders:read"}),
    scope_map={"orders:read": frozenset({"orders.list", "orders.read"})},
)  # frozenset({"orders.read"})
requirement_for("orders", "partial_update")  # needs orders.update: denied
```

## Authenticators and authorizers

The contracts are runtime-checkable protocols.

- `Authenticator.authenticate(*, credentials)` turns a `Credentials` into a
  `Principal`. `AsyncAuthenticator` is the awaitable counterpart. A failure
  raises `rn_forge.web.AuthenticationFailed`; its message must not say which
  part of the credentials was wrong.
- `Authorizer.authorize(principal, *, requires)` returns when the request may
  proceed and raises `rn_forge.web.PermissionDenied` when it may not. It never
  raises `AuthenticationFailed`: the caller is already authenticated, which is
  the line between 401 and 403.

`ScopeAuthorizer` is the shipped `Authorizer`. It evaluates the `Requirement`
and raises `PermissionDenied` with a fixed message. Pass `log` to be told about
each refusal; it is called as `log("authorization.denied", context)`, where
`context` holds `subject`, `mechanism` and `required`.

```python
from rn_forge.auth import ScopeAuthorizer

authorizer = ScopeAuthorizer(log=lambda message, context: print(message, context))
authorizer.authorize(caller, requires=requirement)
```

## Mapping claims to a principal

`principal_from_claims(claims, *, mechanism="bearer")` is the default mapping
from already-verified claims:

| Principal | Claim |
| -- | -- |
| `subject` | `sub`, required |
| `issuer` | `iss` |
| `scopes` | `scope` (space-delimited string) and `scp` (string or list), combined |
| `roles` | `roles` (a list) |
| `tenant` | `tid` |

It raises `AuthenticationFailed` when `sub` is missing or empty. A claim of the
wrong type for `issuer` or `tenant` is ignored, not an error.

An identity provider that keeps roles elsewhere, such as Keycloak's
`realm_access.roles`, needs its own mapping. Any callable from verified claims
to a `Principal` works; `Principal.claims` still holds the whole token:

```python
from dataclasses import replace

from rn_forge.auth import Principal, principal_from_claims


def keycloak_principal(claims: dict[str, object]) -> Principal:
    principal = principal_from_claims(claims)
    realm = claims.get("realm_access")
    roles = realm.get("roles", ()) if isinstance(realm, dict) else ()
    return replace(principal, roles=frozenset(str(role) for role in roles))
```

Hand it to `OidcAuthenticator` as `claims_to_principal`.

## OIDC bearer tokens

`OidcAuthenticator` is an `Authenticator` for `Bearer` credentials. It verifies
the token with a `JwtVerifier`, then maps the claims with `claims_to_principal`,
which defaults to `principal_from_claims`. A scheme other than `Bearer` raises
`AuthenticationFailed`.

Build it once at startup with discovery, which reads the issuer's
`/.well-known/openid-configuration`:

```python
from rn_forge.auth.oidc import OidcAuthenticator

authenticator = OidcAuthenticator.from_issuer(
    "https://login.example.com/",
    audience="orders-api",
)
```

Or pin the key-set URL and skip discovery, for an identity provider that
publishes no discovery document:

```python
authenticator = OidcAuthenticator.from_jwks_url(
    "https://login.example.com/keys",
    issuer="https://login.example.com/",
    audience="orders-api",
)
```

Discovery runs once, inside `from_issuer`; the authenticator then holds the key
set cache, so reuse one instance rather than building one per request. The
discovery document's `issuer` must equal the issuer it was fetched for, and a
mismatch raises `TokenVerificationError`.

Verification requires `exp`, `iss` and `aud` as well as checking them. A token
without `exp` is rejected rather than treated as non-expiring. The `algorithms`
list, `("RS256",)` by default, is an allow-list: a token whose header names
another algorithm, including `none`, is rejected. The header must carry a `kid`.
`leeway` tolerates clock skew, in seconds, on `exp`, `nbf` and `iat`.

### Token profiles

An identity provider issues several kinds of JWT, and each has its own verifier
used at exactly one place. A token valid under one is never accepted by another.

| Verifier | Used at | Accepts |
| -- | -- | -- |
| `JwtVerifier` | Bearer authentication on API routes | An access token. |
| `IdTokenVerifier` | The OIDC callback | An ID token for your login client, checked against the nonce you sent. |
| `LogoutTokenVerifier` | The back-channel logout endpoint | A logout token, accepted once. |

`JwtVerifier` takes `mode`. With `"rfc7519"` (the default) it accepts a `typ`
of `JWT` or none, requires `iss`, `aud` and `exp`, and validates `sub`, `nbf`
and `iat` when present. With `"rfc9068"` it accepts only `typ` `at+jwt` or
`application/at+jwt` and requires `iss`, `exp`, `aud`, `sub`, `client_id`,
`iat` and `jti`. In both modes it rejects any token that carries `nonce` or
`events`, which an ID token and a logout token do.

Pass your OIDC login client ID as `login_client_id`. An API audience equal to
it is refused with `ValueError` unless `mode="rfc9068"`, because otherwise an ID
token issued to your login client would pass as an access token.

`IdTokenVerifier.verify(token, nonce=..., access_token=...)` checks signature,
`iss`, `aud`, `azp`, `exp`, `iat`, `nonce` and, when an access token is given,
`at_hash`. With `max_age` set, `auth_time` is required and must be no older
than that many seconds.

`LogoutTokenVerifier` needs a `ReplayStore`, such as `InMemoryReplayStore`
(one process only). It requires the back-channel logout event, a `sid` or
`sub`, no `nonce`, an `iat` no older than `max_age_seconds` (120 by default),
and a `jti` it has not accepted before. The `jti` is stored under
`"{iss}|{jti}"` until the token expires, and only once every other check has
passed.

All three build with `from_issuer` or `from_jwks_url`, and all refuse a key-set
URL that is not HTTPS.

### The key-set cache

Signing keys come from PyJWT's `PyJWKClient`, configured by two options on
`from_issuer` and `from_jwks_url`:

| Option | Default | Meaning |
| -- | -- | -- |
| `lifespan` | 300 seconds | How long a fetched key set stays cached. |
| `cooldown_duration` | 30 seconds | The fewest seconds between two key set fetches. A token with an unknown `kid` triggers a refetch only after this long. |

The cooldown bounds how often a stream of tokens with unknown `kid` values can
make the process call the identity provider.

### The HTTPS rule

The adapter fetches key material only over HTTPS. Plain HTTP is accepted only
for `localhost`, `127.0.0.1` and `::1`, which is what a test server needs.
`fetch_json`, which reads the discovery document, checks its URL, and the JWKS
URL, whether it came from discovery or from `from_jwks_url`, is checked too; a
violation raises `TokenVerificationError`. The `fetch` argument of `from_issuer`
replaces `fetch_json` for the discovery document only, so a replacement
transport owns the check on that one URL. The key set itself is always fetched
by `PyJWKClient`.

### Failure reasons are for logs

`TokenVerificationError` carries the specific reason a token, key set or
discovery document failed: an expired token, an unknown `kid`, an audience
mismatch. The reason is for logs. `OidcAuthenticator` re-raises it as
`AuthenticationFailed` so the framework binding can log it, and the response
body must never repeat it: a 401 body is `AUTH_FAILED_DETAIL`, so a caller
cannot tell which check failed.

## Caching authorization contexts

`AuthorizationContextCache` wraps an `AuthorizationContextProvider` so a request
does not recompute the account's permissions every time. It keeps one entry per
account in process memory and serves it while the account's authorization
version and the global version are unchanged and the entry is younger than the
TTL (60 seconds by default).

```python
cache = AuthorizationContextCache(provider, ttl=timedelta(seconds=30), writer=writer)

cache.invalidate("acct-1")   # one account's permissions changed
cache.invalidate_all()       # a role definition or an import changed many
cache.set_active("acct-1", False)          # writer, then invalidate
new_version = cache.bump_session_version("acct-1")
```

Use `set_active` and `bump_session_version` for the two values that revoke
access, so no cached context outlives the change; they need an
`AccountStateWriter` that the application implements. A change made behind the
cache's back, such as a direct database edit, applies once the TTL passes.

The default `InMemoryAuthorizationVersions` is not shared across processes, so
with several workers a bump reaches only the worker that made it and the others
rely on the TTL. A shared `AuthorizationVersions` implementation fixes that.

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
