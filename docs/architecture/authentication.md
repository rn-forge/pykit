# Authentication across packages

This page shows how the four runtime packages divide token verification, HTTP authorization, and framework integration. Application developers can use it to choose the right package guide.

**Status:** done

**Owner:** pykit.

| Package | Responsibility |
| --- | --- |
| `rn-forge-commons` | Fetch and cache JSON Web Key Sets (JWKS), discover OpenID Connect (OIDC) providers, and verify JSON Web Tokens (JWTs). It has no HTTP server types. |
| `rn-forge-web` | Define `Principal`, credentials, authentication and authorization protocols, requirements, and the shared 401/403 problem response. Its optional `OidcAuthenticator` uses the commons verifier and maps verified claims to a principal. |
| `rn-forge-django` | Bind those contracts to Django REST Framework. It also provides Django session, Security Assertion Markup Language (SAML) and locally issued JWT login flows. |
| `rn-forge-fastapi` | Bind those contracts to FastAPI security dependencies. It validates bearer tokens supplied by an identity provider. |

An absent or invalid credential produces a 401 response with an authentication challenge. A valid principal that lacks a required scope produces 403 without a challenge. The framework adapters use the same `rn-forge-web` requirement rule.

## Choose a flow

| Application | Flow | Package guide |
| --- | --- | --- |
| Django with an interactive SAML or username/password login | Complete login with a session, or exchange a short-lived token for a SimpleJWT pair. | [Django Auth](../rn-forge-django/guides/auth.md) |
| Django API receiving externally issued bearer tokens | Use `JWKSBearerAuthentication` or supply a `PrincipalBearerAuthentication` authenticator. | [Django Auth](../rn-forge-django/guides/auth.md) |
| FastAPI receiving externally issued bearer tokens | Create one `OidcAuthenticator`, pass it to `bearer_auth`, and apply `requires` for scopes. | [FastAPI Wiring](../rn-forge-fastapi/guides/wiring.md) |

The identity provider issues externally managed access tokens. `rn-forge-commons` verifies them, `rn-forge-web` maps claims and decides the failure contract, and the framework package binds that contract to a request. An application with different claim names supplies its own claim-to-principal mapping.

Django owns its interactive login and session flow. FastAPI's binding accepts tokens and does not create a login session. API keys, mutual TLS and signed requests can use a custom `rn-forge-web` authenticator; the packages do not provide built-in flows for them.

The deferred cross-package auth review is tracked in [E8](../specs/epics/E8-django-scope-and-auth/index.md). It includes the owner's SAML-to-JWT question; this page does not decide that question.
