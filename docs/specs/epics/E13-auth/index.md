# E13 — Authentication and authorization

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-10-26 |

Standards-based authentication and authorization for new pykit web applications:
SSO through OIDC (with SAML IdPs through a broker), social login, optional local
passwords, server-side sessions for browsers, bearer tokens for machine clients,
and authorization computed from the application's own data. Django and FastAPI
follow one pattern. The framework-neutral code moves to a new `rn-forge-auth`
package, and each framework package binds it. The package and the framework
adapters ship together, in one release.

Every feature here builds on [the design](design.md), which
[F13.1](F13.1-auth-design.md) settles. [Auth patterns](patterns.md) is the
background reference on the industry patterns. The browser client is ngkit's
work, tracked in ngkit's own epic against the same design.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| -- | -- | -- |
| [F13.1 — Auth design](F13.1-auth-design.md) | Settle the design, evaluate the libraries and record the decisions. | Active |
| [F13.2 — rn-forge-auth package](F13.2-auth-package.md) | Create the package and move the existing token, `Principal` and OIDC code into it. | New |
| [F13.3 — Core contracts and token profiles](F13.3-core-contracts.md) | The neutral contracts, the three token profiles, the stores and the offline fake IdPs. | New |
| [F13.4 — Protocol adapters](F13.4-protocol-adapters.md) | OIDC and OAuth 2.0, local-password and development logins. | New |
| [F13.5 — Django binding](F13.5-django-binding.md) | The shared HTTP surface, sessions, CSRF and authorization on Django. | New |
| [F13.6 — FastAPI binding](F13.6-fastapi-binding.md) | The same surface and defaults on FastAPI. | New |
| [F13.7 — Remove the legacy auth flows](F13.7-legacy-removal.md) | Remove the locally issued JWT flows and the auth code the new surface replaces. | New |

`rn-forge-auth` follows the package rule and adapter structure that
[E15](../E15-package-boundaries/index.md) sets
([ADR-0011](../../../adr/ADR-0011.md)).

F13.1 records the design as ADRs and evaluates the libraries, then writes the
stories of F13.3 to F13.7, which all ship in Release 7. F13.2 creates the
`rn-forge-auth` package and moves the existing code into it. F13.3 to F13.7
follow it, in order, and are written inside `rn-forge-auth` and the framework
packages.
