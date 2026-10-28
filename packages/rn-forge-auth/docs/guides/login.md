# Login providers

A login provider turns a framework request into an `ExternalIdentity`.
`LoginFlow` runs the providers for a framework binding. Every provider
implements `IdentityProvider`, so a binding handles OIDC, OAuth 2.0, password
and development logins the same way.

| Provider | Module | Extra |
| -- | -- | -- |
| `OidcProvider` | `rn_forge.auth.oidc` | `oidc` |
| `OidcProvider.oauth2(...)` | `rn_forge.auth.oidc` | `oidc` |
| `PasswordIdentityProvider` | `rn_forge.auth.local` | none |
| `DevelopmentIdentityProvider` | `rn_forge.auth.local` | none |

`rn_forge.auth.oidc` needs the `oidc` extra and is imported directly. The
`rn_forge.auth` facade re-exports `LoginFlow`, `LoginFailed`, `LoginRequest`
and the `rn_forge.auth.local` providers.

## The request and the flow

A provider reads two mappings from the request: `query`, the URL parameters
(the IdP's callback arrives there), and `form`, the decoded `POST` fields (a
password login arrives there). A binding passes its native request when it has
both, or a small wrapper:

```python
from dataclasses import dataclass, field
from collections.abc import Mapping


@dataclass(frozen=True)
class Request:
    query: Mapping[str, str] = field(default_factory=dict)
    form: Mapping[str, str] = field(default_factory=dict)
```

`LoginFlow` holds the providers by ID, a `TransactionStore` and the allowed
`return_to` prefixes:

```python
from datetime import timedelta

from rn_forge.auth import InMemoryTransactionStore, LoginFlow

flow = LoginFlow(
    {"acme": acme_provider},
    InMemoryTransactionStore(),
    return_to_prefixes=["/app"],
    ttl=timedelta(seconds=600),  # the default
)
```

A binding mounts two routes over it:

```python
# GET /auth/login/acme?return_to=/app/orders
start = flow.begin("acme", request, return_to="/app/orders")
# Set a cookie holding start.transaction.id; redirect to start.redirect_url.

# GET /auth/callback/acme
identity = flow.complete("acme", request, transaction_id=cookie_value)
# Clear the cookie, resolve the account, start the session.
```

`begin` checks `return_to` with `validate_return_to`, asks the provider for the
redirect, and saves the transaction for the TTL. `complete` consumes the
transaction first, so a callback works once whatever its outcome, then rejects a
missing, expired, already used or foreign transaction (one that another provider
began) before the provider sees the response. The transaction cookie is
`__Host-login-tx` with `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/` and
`Max-Age=600`: `Lax` sends it on the IdP's top-level redirect back, and the
`__Host-` prefix stops a sibling subdomain from planting one. Reject a callback
that carries more than one. Because the transaction binds the
callback to the browser that started it, a callback replayed in another browser
fails.

Every failure is one exception, `LoginFailed`, with a `code` from
`CallbackError`: `login_failed`, or `access_denied` when the IdP returned
`error=access_denied`. Send the code to the error route and keep `reason` in the
logs; it names the failed check and must not reach the user. An invalid
`return_to` and an unknown provider are `login_failed` too. Any other exception
a provider raises is logged and also becomes `login_failed`.

## OIDC

```python
from rn_forge.auth.oidc import OidcProvider

acme_provider = OidcProvider(
    id="acme",
    issuer="https://login.acme.example",
    client_id="orders-web",
    client_secret="...",
    redirect_uri="https://app.example/auth/callback/acme",
)
```

The provider reads the discovery document on first use and checks that it
names the configured issuer. It sends `state`, a nonce and a PKCE S256
challenge, and records all three, with the verifier, on the transaction. On the
callback it requires the same `state`, then checks the `iss` parameter
([RFC 9207](https://www.rfc-editor.org/rfc/rfc9207)): a different `iss` fails,
and a missing one fails when discovery advertises
`authorization_response_iss_parameter_supported`. It then exchanges the code and
verifies the ID token with `IdTokenVerifier`, including the nonce and `at_hash`.
The secrets stay out of the logs.

| Argument | Effect |
| -- | -- |
| `scopes` | Defaults to `openid email profile`; `openid` is required |
| `max_age` | Sent on the authorization request; an ID token whose `auth_time` is older fails |
| `userinfo` | `"auto"` (default) calls UserInfo when the ID token has no `email`; `"always"` and `"never"` do as named. The UserInfo `sub` must equal the ID token's, and the ID token wins any other conflict |
| `claim_mapper` | Replaces `default_claim_mapper` |
| `token_hook` | Receives the identity and the upstream tokens |
| `rp_initiated_logout` | Lets `logout_redirect` return the IdP's logout URL |
| `token_endpoint_auth_method` | `client_secret_basic` by default; a public client (`client_secret=None`) sends none |
| `algorithms`, `leeway`, `timeout`, `fetch` | The accepted ID-token algorithms (`RS256`), clock skew, the back-channel timeout, and the discovery transport |

### Claim mapping

`default_claim_mapper` fills `sub`, `email`, `email_verified`, `name`,
`picture`, `groups`, `auth_time` and `amr`, takes `sid` as `session_ref`, and
puts the remaining claims, except the token-protocol ones, in `attributes`. To
change that, pass a function of the provider ID and the verified claims. It may
raise `LoginFailed` to refuse the login:

```python
from rn_forge.auth import ExternalIdentity, LoginFailed
from rn_forge.auth.oidc import default_claim_mapper


def acme_mapper(provider: str, claims):
    identity = default_claim_mapper(provider, claims)
    if not identity.email_verified:
        raise LoginFailed("login_failed", "email is not verified")
    return identity
```

### Upstream tokens

pykit stores no upstream token. The access and refresh tokens are dropped
after the exchange unless the application passes a `token_hook`, which is called
once the login has succeeded:

```python
def keep_tokens(identity, tokens):  # tokens is an UpstreamTokens
    vault.save(identity.issuer, identity.subject, tokens.refresh_token)
```

The tokens have no `repr`, so a logged `UpstreamTokens` does not leak them.

### Logout

With `rp_initiated_logout=True`, `logout_redirect(session, post_logout_redirect=...)`
returns the discovered `end_session_endpoint` with `id_token_hint`,
`post_logout_redirect_uri` and `client_id`. It returns `None`, and the binding
logs out locally only, when the flag is off, the provider advertises no
endpoint, or the session kept no ID token. A session keeps its ID token
(`SessionInfo.id_token`) only when the application enables RP-initiated logout.
Signing out of the app does not normally need to sign the user out of their
whole IdP session, so the flag is off by default.

## OAuth 2.0 providers

A server that issues no ID token, such as GitHub, uses `OidcProvider.oauth2`
with explicit endpoints and a fixed issuer string. The flow keeps `state` and
PKCE, sends no nonce, and calls the user endpoint with the access token:

```python
from rn_forge.auth import ExternalIdentity
from rn_forge.auth.oidc import OAuth2Endpoints, OidcProvider


def github_mapper(provider, claims):
    return ExternalIdentity(
        provider=provider,
        issuer=claims["iss"],
        subject=claims["sub"],
        email=claims.get("email"),
        name=claims.get("name"),
        picture=claims.get("avatar_url"),
    )


github = OidcProvider.oauth2(
    id="github",
    issuer="https://github.com",
    endpoints=OAuth2Endpoints(
        authorization="https://github.com/login/oauth/authorize",
        token="https://github.com/login/oauth/access_token",
        user="https://api.github.com/user",
    ),
    client_id="...",
    client_secret="...",
    redirect_uri="https://app.example/auth/callback/github",
    scopes=["read:user", "user:email"],
    subject_field="id",
    claim_mapper=github_mapper,
)
```

The user endpoint's JSON object becomes the claim set, with `iss` set to
`issuer` and `sub` set to the `subject_field` member as a string, so GitHub's
numeric `id` works. A user without that member fails the login. The default
mapper reads the standard names; a provider with other names (`avatar_url`
here) needs a mapper. The `iss` response check applies only when you pass
`response_issuer`, because most OAuth 2.0 servers send none. Such a provider has
no ID token to keep, so `logout_redirect` returns `None`, and `token_hook`
receives `UpstreamTokens` with `id_token=None`. A failed user call, an HTTP
error or a non-object body is `login_failed`.

## Back-channel logout

When the user signs out at the IdP, it posts a logout token to the application.
`BackchannelLogout` validates it under the logout-token profile (see
[Token profiles](tokens.md)) and says what to revoke:

```python
from rn_forge.auth import InMemoryReplayStore
from rn_forge.auth.oidc import BackchannelLogout, LogoutTokenVerifier

replay = InMemoryReplayStore()
logout = BackchannelLogout(
    LogoutTokenVerifier.from_issuer(
        "https://login.acme.example", client_id="orders-web", replay_store=replay
    ),
    accounts,  # an AccountResolver; only lookup() is called
)
```

The binding mounts `POST /auth/backchannel-logout/acme`, reads the form field
`logout_token`, and applies the result:

```python
from rn_forge.auth.oidc import TokenVerificationError

try:
    revocation = logout.handle(form["logout_token"])
except TokenVerificationError:
    return response(400)
if revocation.sid is not None:
    replay.revoke_sid(revocation.issuer, revocation.sid, ttl=SESSION_ABSOLUTE_TIMEOUT)
elif revocation.account_id is not None:
    account_state.bump_session_version(revocation.account_id)
return response(200)
```

The handler changes no state of its own except the token's `jti` record, because
the revoked-`sid` lifetime (the sessions' absolute timeout) and the
session-version store belong to the binding. A token with a `sid` revokes that
session only. A token with only `sub` names the account linked to
`(issuer, sub)` through `AccountResolver.lookup`, whose session version the
binding bumps; an unlinked `sub` gives `account_id=None` and nothing to do.
Answer a failed token with `400` and log the exception message, which says which
check failed.

## Password login

`PasswordIdentityProvider` needs no extra. The application supplies a verifier
that returns the account's stable subject, or `None` for an unknown account or a
wrong password:

```python
from rn_forge.auth.local import PasswordIdentityProvider


def verify(username: str, password: str) -> str | None:
    account = accounts_by_name.get(username)
    return account.id if account and hasher.check(password, account.hash) else None


password = PasswordIdentityProvider(verify)  # id="password"
```

`begin` returns a transaction and no redirect, since the login is a form. The
login page posts `username` and `password`, and the binding calls `complete`
with those form fields. The identity has issuer `local` and `amr` of `{"pwd"}`.
An unknown account and a wrong password fail with the same `LoginFailed`. Rate
limiting per account and per client belongs to the binding, and the provider
never logs or keeps the password. SSO or passkeys are preferred in production.

## Development login

`DevelopmentIdentityProvider` lists fixture accounts so that a developer, or an
end-to-end test, signs in without a password. Construction raises
`DevelopmentModeRequired` unless the caller passes `debug=True`; wire it to the
framework's debug flag, never to a constant:

```python
from rn_forge.auth.local import DevelopmentAccount, DevelopmentIdentityProvider

dev = DevelopmentIdentityProvider(
    [
        DevelopmentAccount("alice", email="alice@example.com", name="Alice"),
        DevelopmentAccount("bob", groups=frozenset({"staff"})),
    ],
    debug=settings.DEBUG,
)
html = dev.render_accounts(login_url="/auth/login/development")
```

`render_accounts` returns this markup, with every value HTML-escaped; an
end-to-end test can rely on the attributes:

```html
<ul data-rn-forge-dev-accounts>
<li><a href="/auth/login/development?account=alice" data-account="alice">Alice</a></li>
</ul>
```

The link text is the account's name, or its subject when it has none. The
provider accepts the account as the `account` form field or query parameter, so
a test can sign in directly. The identity has issuer `development` and `amr` of
`{"dev"}`. An unknown account fails with `LoginFailed`.

## Connecting a SAML IdP through a broker

pykit speaks no SAML. A SAML IdP federates through a broker (Keycloak, Entra ID,
Auth0, Okta and others), which runs the SAML exchange and then logs the user in
to the application over OIDC. The application configures the broker as one
ordinary `OidcProvider`; the SAML connection is the broker's configuration, not
the application's. Most workforce IdPs also speak OIDC, and a direct connection
to them needs no broker.

With Keycloak:

1. Create a realm for the application and an OpenID Connect client in it (a
   confidential client with the standard flow, your callback URL as a valid
   redirect URI, and a secret).
2. Under identity providers, add a SAML v2.0 provider with an alias such as
   `saml-idp`. Give it the SAML IdP's entity ID and single sign-on URL, and
   require signed assertions. Import the IdP's metadata when it publishes it.
3. Add attribute mappers from the SAML attributes to user attributes (`email`,
   `firstName`, `lastName`), so that they reach the ID token as claims.
4. Configure `OidcProvider` with the realm's issuer, `https://<host>/realms/<realm>`,
   and the client's ID and secret. To send users straight to the SAML IdP, add
   Keycloak's `kc_idp_hint=saml-idp` parameter to the redirect URL.

```python
broker = OidcProvider(
    id="keycloak",
    issuer="https://sso.example/realms/acme",
    client_id="orders-web",
    client_secret="...",
    redirect_uri="https://app.example/auth/callback/keycloak",
)
```

The identity's issuer is the broker, and its subject is the broker's user ID, so
an account links to `(broker issuer, broker subject)` whichever IdP the user
signed in through. The SAML assertion is the broker's to validate; the
application sees only the broker's signed ID token. `tests/broker/` holds a
working configuration: `realms/idp-realm.json` is a SAML IdP, and
`realms/broker-realm.json` is a broker realm with the client, the SAML identity
provider and the attribute mappers above. [Testing](testing.md) describes how
to run them.
