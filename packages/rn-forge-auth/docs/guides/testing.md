# Testing with the fake IdP

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

## Failure switches

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
