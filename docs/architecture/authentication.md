# Authentication across packages

Four runtime packages split authentication between them: commons verifies tokens, web defines what "authenticated" and "denied" look like on the wire, and each framework package binds that contract to its requests. Use this page to find the package guide for your stack.

| Package | Responsibility | Standards |
| --- | --- | --- |
| `rn-forge-commons` | Fetch and cache JSON Web Key Sets (JWKS), discover OpenID Connect (OIDC) providers, and verify JSON Web Tokens (JWTs). It has no HTTP server types. | RFC 7519, RFC 7517, RFC 8414, OIDC Discovery 1.0 |
| `rn-forge-web` | Define `Principal`, credentials, authentication and authorization protocols, requirements, and the shared 401/403 problem response. Its optional `OidcAuthenticator` uses the commons verifier and maps verified claims to a principal. | RFC 6750 §3, RFC 7617, RFC 9457 |
| `rn-forge-django` | Bind those contracts to Django REST Framework. It also provides Django session, Security Assertion Markup Language (SAML) and locally issued JWT login flows. | — |
| `rn-forge-fastapi` | Bind those contracts to FastAPI security dependencies. It validates bearer tokens supplied by an identity provider. | — |

An absent or invalid credential produces a 401 response with an authentication challenge. A valid principal that lacks a required scope produces 403 without a challenge. The framework adapters use the same `rn-forge-web` requirement rule.

## Mechanisms by stack

| Mechanism | `rn-forge-django` | `rn-forge-fastapi` |
| --- | --- | --- |
| Bearer (OIDC/OAuth2 access token → `Principal`) | `PrincipalBearerAuthentication`, or `JWKSBearerAuthentication` built from a JWKS URL | `bearer_auth()` |
| Basic (development and internal use only) | `PrincipalBasicAuthentication` | `basic_auth()` |
| SAML (browser redirect → session) | `SAMLLoginViewMixin`, `SAMLLoginAPIView` | Not supported |
| Local username/password → session or JWT | `BasicLoginAPIView`, `JWTAuthentication`, `UserTokenView` | Not applicable: no login or session layer |

SAML is Django-only because it ends in a browser redirect and a session, which only a stack with a login layer can own. FastAPI consumes tokens an identity provider already issued.

## Choose a flow

| Application | Flow | Package guide |
| --- | --- | --- |
| Django with an interactive SAML or username/password login | Complete login with a session, or exchange a short-lived token for a SimpleJWT pair. | [Django Auth](../rn-forge-django/guides/auth.md) |
| Django API receiving externally issued bearer tokens | Use `JWKSBearerAuthentication` or supply a `PrincipalBearerAuthentication` authenticator. | [Django Auth](../rn-forge-django/guides/auth.md) |
| FastAPI receiving externally issued bearer tokens | Create one `OidcAuthenticator`, pass it to `bearer_auth`, and apply `requires` for scopes. | [FastAPI Wiring](../rn-forge-fastapi/guides/wiring.md) |

The identity provider issues externally managed access tokens. `rn-forge-commons` verifies them, `rn-forge-web` maps claims and decides the failure contract, and the framework package binds that contract to a request. An application with different claim names supplies its own claim-to-principal mapping.

## Out of scope

pykit is not an authorization server: OAuth2 authorization code and PKCE flows, and token issuance generally, belong to the identity provider. Django's login flows are the one exception, because a Django application is often the session owner. [ADR-0006](../adr/ADR-0006.md) records this boundary.

API keys, mutual TLS and signed requests can use a custom `rn-forge-web` authenticator; the packages do not provide built-in flows for them.

The deferred cross-package review of login, session and token boundaries, including the owner's SAML-to-JWT question, is [F8.2](../specs/epics/E8-django-scope-and-auth/F8.2-auth-review.md).
