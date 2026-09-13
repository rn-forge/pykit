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
| `rn-forge-web` | The contract: `Principal`, `Requirement`, the `Authenticator`/`Authorizer` protocols, and the failure wire shape (401 vs 403, the `WWW-Authenticate` challenge, `problem+json`). | RFC 6750 §3, RFC 7617, RFC 9457 |
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

1. Add the `auth` extra for `rn-forge-commons`'s `JwtVerifier`/`JwksCache`/`discover_oidc`.
2. Call `discover_oidc()` against the IdP's `.well-known/openid-configuration` (or hardcode
   `issuer`/`jwks_uri`); build a `JwksCache` and a `JwtVerifier(audience=..., issuer=...)`.
3. Write an `Authenticator` adapter: verify the token via `JwtVerifier`, map the resulting claims
   through `rn_forge.web.principal_from_claims()`, and translate `TokenVerificationError` into
   `rn_forge.web.AuthenticationFailed`. This step is boilerplate every app currently repeats —
   see the open gap below.
4. Build the dependency: `bearer_auth(authenticator=your_authenticator, log=...)`.
5. Guard routes: `requires(bearer_auth(...), Requirement(all_scopes={"orders:read"}))`.
6. Register `rn_forge.fastapi.register_problem_handlers` so auth failures come back as
   `problem+json` with the correct 401/403 and `WWW-Authenticate`.

The asymmetry is structural, not accidental: an IdP-driven SAML login needs a session owner
(Django), an OAuth2 access token needs only verification (commons + web + the framework binding),
since the IdP already ran its own login flow before your app ever sees the token.

## Open gap: no ready-made OIDC `Authenticator`

Step 3 above (and its Django `PrincipalBearerAuthentication` equivalent) is identical glue code
every consuming app currently hand-writes: `JwtVerifier` → catch `TokenVerificationError` → map
via `principal_from_claims()` → `Principal`. Nothing in `rn-forge-web` or `rn-forge-commons` ships
this as a single `Authenticator` implementation today. This is tracked as pending in
[`web-library-plan.md`](plans/web-library-plan.md) Phase 10 — see the note there before adding a
one-off version in an app or in a framework package.
