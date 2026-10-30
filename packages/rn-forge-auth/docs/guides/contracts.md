# Contracts

The core, `rn_forge.auth`, is a set of contracts and the values they exchange.
This guide walks them in the order a request meets them; the
[overview](usage.md) shows how they connect. For tokens, see
[Token profiles](tokens.md); for server-side state, see [Stores](stores.md).

## Identity providers and external identities

An `IdentityProvider[RequestT]` is one login method, generic over the framework's
native request type. It has an `id` and a `kind` (`ProviderKind`: `"oidc"`,
`"oauth2"`, `"password"` or `"development"`) and three methods:

- `begin(request, *, return_to)` returns a `LoginStart`: the `LoginTransaction`
  to persist and the `redirect_url` to send the browser to, or `None` when the
  provider takes a form instead, as password login does.
- `complete(request, transaction)` validates the provider's response against the
  transaction and returns an `ExternalIdentity`.
- `logout_redirect(session, *, post_logout_redirect)` returns the provider's
  logout URL, or `None` for a local logout only.

`ExternalIdentity` is a verified identity asserted by a provider: `provider`,
`issuer`, `subject`, and optionally `email`, `email_verified`, `name`, `picture`,
`groups`, `attributes`, `auth_time`, `amr` and `session_ref` (the OIDC `sid`).
Everything after this value is framework-neutral. `LoginTransaction` is the
state of one login in flight (`state`, `nonce`, `code_verifier`, `return_to`),
saved in a `TransactionStore` between `begin` and `complete`.

`SessionInfo` is what a login session stores: the internal `account_id`, the
`session_version` at login, how the user authenticated, and `expires_at`. It
holds no permissions; they are looked up per request (see
[Authorization context](#authorization-context-and-cache)).

## Account resolution

An `AccountResolver` maps an `ExternalIdentity` to an internal account ID.
`resolve(identity)` links, provisions or rejects a login and returns the account
ID; it raises `AccountRejected` when the login may not proceed. `lookup(issuer,
subject)` returns the linked account ID, or `None`, and never provisions.

`AccountRejected` carries a `reason` for logs. The user is never shown it: the
callback sends one of the `CallbackError` codes instead (see
[Return targets, the session body and callback errors](#return-targets-the-session-body-and-callback-errors)).

## Authorization context and cache

An `AuthorizationContext` is an account's current authorization data: `active`
(whether it may authenticate), `session_version`, `permissions`, `roles` (a
display hint and an input to your provider) and `attributes` (inputs to
attribute-based rules such as tenant or location). An
`AuthorizationContextProvider` returns it from an account ID with
`resolve(account_id)`.

A session holds only the account ID and its `session_version`. On each request
the binding fetches the current context, checks `active` and that the session's
version still matches, and builds the `Principal` from the context. Revoking a
permission, deactivating an account or bumping the session version therefore
takes effect on the next request, with no session to edit.

### Caching contexts

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


## Resource policy

A `Requirement` decides whether a caller may reach a route. A `ResourcePolicy`
decides what the caller may do with a particular object or set of objects:

- `allows(principal, action, resource)` returns whether the principal may
  perform the action on one resource.
- `scope(principal, action, query)` returns the query narrowed to what the
  principal may perform the action on, such as a queryset filtered by tenant.

It is generic over the resource and query types, so the application chooses
both. The core supplies the protocol only.

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
