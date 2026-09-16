# Auth across web, django and fastapi

How authentication and authorization are layered across `rn-forge-commons`, `rn-forge-web`,
`rn-forge-django` and `rn-forge-fastapi`, and what a new consuming app has to do. See each
package's own docs for API detail — `rn-forge-web`'s `auth.py`, `rn-forge-django`'s auth guide
(`packages/rn-forge-django/docs/guides/auth.md`), and `rn-forge-fastapi`'s `auth.py`. This page is
the cross-package summary that none of those, individually, can be.

## The three layers

| Layer | Owns | Standards |
| --- | --- | --- |
| `rn-forge-commons` | Verification: JWKS fetch/cache/rotation, JWT signature and claims validation, OIDC discovery (`JwksCache`, `JwtVerifier`, `discover_oidc`). No HTTP-server concept. | RFC 7519, 7517, 8414, OIDC Discovery 1.0 |
| `rn-forge-web` | The contract: `Principal`, `Requirement`, the `Authenticator`/`Authorizer` protocols, and the failure wire shape (401 vs 403, the `WWW-Authenticate` challenge, `problem+json`) — plus `oidc.OidcAuthenticator`, the one implementation joining commons' verifier to the contract (`auth` extra). | RFC 6750 §3, RFC 7617, RFC 9457 |
| `rn-forge-django` / `rn-forge-fastapi` | The binding only: a DRF `BaseAuthentication` / a FastAPI `Security` dependency, each producing the same `web.Principal`. | — |

`web` never verifies a token itself — it only defines what "verified" and "denied" look like on
the wire. Verification is `commons`'s job; the 401/403 boundary is fixed by rule, not judgement:
no or invalid credentials → 401 with a challenge; valid credentials missing scope/role → 403 with
no challenge.

## What each framework package supports

| Mechanism | `rn-forge-django` | `rn-forge-fastapi` |
| --- | --- | --- |
| Bearer (OIDC/OAuth2 access token → `Principal`) | `PrincipalBearerAuthentication` | `bearer_auth()` |
| Basic (dev/internal only) | `PrincipalBasicAuthentication` | `basic_auth()` |
| SAML (browser redirect → session) | `SAMLLoginViewMixin` / `SAMLLoginAPIView` | not supported |
| Local username/password → session or JWT | `BasicLoginAPIView`, `JWTAuthentication`, `UserTokenView` | not applicable (no login/session concept) |

SAML is Django-only by design: it terminates in a browser redirect and a session, not a bearer
token, so it only makes sense where there's a login/session layer. FastAPI is a stateless API
framework — it consumes tokens an IdP already issued, it doesn't run a login flow.

## Is bearer/basic the whole picture?

For token-based API auth, yes — bearer (OIDC/OAuth2 access tokens) is what this stack is built
around, with basic as the explicitly-dev-only fallback. Outside that:

- **SAML** — covered above, Django-only, session-based.
- **API keys / mTLS / HMAC-signed requests** — not modelled here. The `Authenticator` protocol in
  `rn-forge-web` is generic (`Credentials` in, `Principal` out), so a service-to-service auth
  scheme can be added as a custom `Authenticator` without touching the contract.
- **OAuth2 Authorization Code / PKCE (issuing tokens)** — deliberately out of scope. pykit is not
  an authorization server; login/token issuance is the IdP's job, and Django's login flows are the
  one exception because Django apps often *are* the session owner.
- **Session cookies** — Django's basic-login flow produces one directly; no bearer-token wrapping
  needed.

## Steps for a new app

### Django + SAML IdP (e.g. Google Workspace) — interactive login, session-based

1. Add `rn_forge.django.auth` to `INSTALLED_APPS`.
2. Configure `RN_FORGE_DJANGO["AUTH"]["SAML"]["SETTINGS"]` with the IdP's SAML metadata (the
   `python3-saml` settings dict) and a `RETURN_TO`.
3. Subclass `SAMLLoginViewMixin`/`SAMLLoginAPIView`, implementing `build_saml_request_data()`,
   `get_saml_user_lookup()`, `get_user()` (and `create_user_for_login()` if auto-provisioning).
4. Pick the post-login target via `complete_login()`: a Django session, or mix in
   `LoginExchangeViewMixin` for a short-lived exchange token → `UserTokenView` for a JWT pair.
5. Mount `rn_forge.django.auth.urls.urlpatterns` (or your own router).
6. Protect API views: `DEFAULT_AUTHENTICATION_CLASSES = [JWTAuthentication]`,
   `DEFAULT_PERMISSION_CLASSES = [AuthorizationPermission]`, `AuthorizationViewMixin` +
   `permission_key` on viewsets.

### FastAPI + OAuth2 IdP (e.g. Ping) — bearer token validation, no login flow

1. Install the `oidc` extra: `uv add "rn-forge-fastapi[oidc]"`. It brings
   `rn-forge-web[auth]`, and with it `rn-forge-commons`'s verifier.
2. Build the authenticator **once, at startup** — discovery and the JWKS fetch happen here, not
   per request:

   ```python
   from rn_forge.web.oidc import OidcAuthenticator

   authenticator = OidcAuthenticator.from_issuer(
       "https://idp.example.com/tenant", audience="api://orders"
   )
   ```

   Use `OidcAuthenticator.from_jwks_url(...)` instead for an IdP that publishes no discovery
   document, or to pin the key-set URL.
3. Build the dependency: `bearer_auth(authenticator=authenticator, log=...)`.
4. Guard routes: `requires(bearer_auth(...), Requirement(all_scopes={"orders:read"}))`.
5. Register `rn_forge.fastapi.register_problem_handlers` so auth failures come back as
   `problem+json` with the correct 401/403 and `WWW-Authenticate`.

Django reaches the same authenticator through `JWKSBearerAuthentication`, which builds one from
its `jwks_url`/`issuer`/`audience` class attributes — so both stacks accept the same tokens.

The asymmetry is structural, not accidental: an IdP-driven SAML login needs a session owner
(Django), an OAuth2 access token needs only verification (commons + web + the framework binding),
since the IdP already ran its own login flow before your app ever sees the token.

## The shared OIDC `Authenticator`

`rn_forge.web.oidc.OidcAuthenticator` is the one implementation of the
`JwtVerifier` → catch `TokenVerificationError` → `principal_from_claims()` → `Principal` chain.
Both framework bindings use it, so a token accepted by a Django service is accepted by a FastAPI
service configured against the same IdP.

It lives in `rn-forge-web`, not `rn-forge-commons`, because its signature is `Credentials` in and
`Principal` out — both web types, and commons cannot depend on web. It stays inside the
"verify and map claims" boundary: it does not issue tokens, run a login flow or own a session.

Behind web's `auth` extra, since it is the one module in the package with a third-party
dependency (PyJWT, via `rn-forge-commons[auth]`). It is deliberately **not** re-exported from
`rn_forge.web` — import `rn_forge.web.oidc` directly.

Two things it does not decide for you: an IdP whose roles or scopes sit somewhere non-standard
(Keycloak's nested `realm_access.roles`, an Okta group claim) needs a `claims_to_principal`
override, and the authenticator must be built once at startup — a per-request instance refetches
the key set on every call.

---

## My followup thoughts

SAML is a login flow into the provider. once logged in, it is a post back into the backend from where it could issue a JWT and all furture frontend to backend conversations happen using that JWT
