# Authentication and authorization

The package has one core and two adapters. `rn_forge.auth` holds the contracts
and needs no third-party package. `rn_forge.auth.oidc` verifies OIDC bearer
tokens, and `rn_forge.auth.redis` keeps sessions and single-use records in
Redis; both import the core and the core never imports them. The `oidc` extra
installs `pyjwt[crypto]` and `authlib`, the `redis` extra installs `redis`, and
the `rn_forge.auth` facade re-exports neither adapter.

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

## Stores

Four protocols hold server-side state. Each has an in-memory implementation in
the core and a Redis implementation in `rn_forge.auth.redis`.

| Protocol | Holds | Redis operation it relies on |
| -- | -- | -- |
| `TransactionStore` | Login transactions between the redirect and the callback. `consume` returns the transaction to exactly one caller. | `SET ... EX` to save, `GETDEL` to consume |
| `SessionStore` | Login sessions under random IDs. `create`, `get`, `touch`, `delete` and `rotate`. | `SET ... EX`, `GET`, `EXPIRE`, `GETDEL` |
| `ReplayStore` | Single-use values, such as logout-token `jti`, and revoked `(issuer, sid)` pairs. | `SET key 1 NX EX` for `record_once`, `SET ... EX` and `EXISTS` for revoked `sid` values |
| `AuthorizationVersions` | The counters behind `AuthorizationContextCache`. | `INCR` per account and for the global counter, `MGET` to read |

A session ends at its idle expiry or at `SessionInfo.expires_at`, whichever
comes first. `get` does not extend the idle expiry, so a poll cannot keep an
idle session alive; `touch` extends it, never past `expires_at`. `rotate`
returns a new ID and leaves the old one unreadable. The stores do not check
session versions or revoked `sid` values; the framework binding does that after
`get`.

```python
from redis import Redis
from rn_forge.auth.redis import RedisSessionStore, RedisTransactionStore

client = Redis.from_url("redis://localhost:6379/0")
sessions = RedisSessionStore(client)
transactions = RedisTransactionStore(client, prefix="myapp-auth:")

session_id = sessions.create(session_info, idle_ttl=timedelta(minutes=30))
```

### Supported storage

Transactions, replay records and revoked `sid` values must be shared by every
worker, so a store used by more than one process must be backed by shared
storage whose operations above are atomic. The in-memory stores
(`InMemoryTransactionStore`, `InMemorySessionStore`, `InMemoryReplayStore` and
`InMemoryAuthorizationVersions`) are thread-safe but are not safe across
processes; use them in tests and single-process development only. The Redis
stores need Redis 6.2 or later (for `GETDEL`).

Every Redis store takes a client and a key `prefix` (`"rn-forge-auth:"` by
default). Expiries are whole seconds, rounded up, and at least one. A session
is stored as JSON, and a missing, expired or rotated-away key reads as absent.

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

## Return targets, the session body and callback errors

`validate_return_to` accepts a `return_to` only when it is a relative path under
one of the configured prefixes, matched on whole segments:

```python
from rn_forge.auth import InvalidReturnTo, validate_return_to

try:
    target = validate_return_to(raw, prefixes=["/app"])
except InvalidReturnTo:
    target = "/app"
```

It rejects absolute and scheme-relative URLs, backslashes, control characters,
percent-encoded slashes, backslashes and dots in the path, `..` segments and
paths outside the prefixes. A query string and fragment may follow the path.
The caller falls back to a default on `InvalidReturnTo`.

`SessionBody.build(session, context, name=..., email=..., picture=...)` makes
the `/auth/session` body; `subject` is the internal account ID. `to_json()`
returns camelCase keys, RFC 3339 UTC timestamps, sorted `roles`, `permissions`
and `amr`, and leaves out absent optional fields. The keys of `attributes` are
converted from snake_case to camelCase at every depth.

`CallbackError` is the closed list of codes a failed callback sends to the error
route: `access_denied`, `account_not_provisioned` and `login_failed`.

## Testing with the fake IdP

`rn_forge.auth.testing.FakeOidcProvider` is an OIDC provider that runs inside
the test process on `127.0.0.1` and an ephemeral port, so a test needs no
network. It needs the `oidc` extra and, like `rn_forge.auth.oidc`, is imported
directly. It serves discovery, a key set, an authorization endpoint that
approves a configured user without a login page, a token endpoint that checks
PKCE and client authentication, and UserInfo.

```python
from rn_forge.auth.oidc import IdTokenVerifier
from rn_forge.auth.testing import FakeOidcProvider

with FakeOidcProvider(redirect_uris=["http://127.0.0.1/callback"]) as idp:
    verifier = IdTokenVerifier.from_issuer(idp.issuer, client_id=idp.client_id)
    # Drive idp.authorization_endpoint and idp.token_endpoint, then:
    claims = verifier.verify(id_token, nonce=nonce, access_token=access_token)
```

In pytest, wrap it in a fixture:

```python
@pytest.fixture
def idp():
    with FakeOidcProvider() as provider:
        yield provider
```

Authorization codes are single use, and a PKCE verifier that does not match the
challenge is refused. `idp.requests` lists every request as a `RecordedRequest`
of method and path. `idp.rotate_key(retire_old=...)` adds a signing key, and
`idp.sign(...)`, `idp.access_token(profile=...)` and `idp.logout_token(sid=...)`
mint tokens for the verifier profiles. Set `idp.deny_authorization` for an
`access_denied` response.

### Failure switches

`idp.faults` is a `Faults`; every field is off by default and turns on one
failure:

| Field | The provider then |
| -- | -- |
| `response_iss` | Sends an `iss` in the authorization response that names another issuer |
| `response_iss_missing` | Leaves `iss` out of the authorization response |
| `discovery_issuer` | Names another issuer in its discovery document |
| `userinfo_sub_mismatch` | Returns a UserInfo `sub` that differs from the ID token's |
| `wrong_nonce`, `wrong_aud`, `wrong_azp`, `wrong_at_hash` | Mints an ID token with that claim wrong |
| `expired` | Mints an ID token whose `exp` is past |
| `alg_none` | Mints an unsigned ID token |
| `unknown_kid` | Signs the ID token with a key the key set does not list |

`discover_oidc` rejects `discovery_issuer`, and `IdTokenVerifier` rejects each
ID-token switch. The `iss` response check and the UserInfo `sub` check belong
to the login flow, not to a verifier here.

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
