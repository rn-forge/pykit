# Token profiles

`rn_forge.auth.oidc` verifies JWTs for bearer authentication, the OIDC callback
and back-channel logout. It needs the `oidc` extra and is imported directly. The
core never imports it. The contracts it feeds are in [Contracts](contracts.md);
the in-process provider for testing it is in [Testing](testing.md).

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
