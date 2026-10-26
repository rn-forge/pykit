# E13 — Authentication and authorization

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-10-26 |

Standards-based authentication and authorization for new pykit web applications:
SSO through OIDC and SAML, social login, optional local passwords, server-side
sessions for browsers, bearer tokens for machine clients, and authorization
computed from the application's own data. Django and FastAPI follow one pattern.
The framework-neutral code moves to a new `rn-forge-auth` package, and each
framework package binds it. The package and the framework adapters ship
together, in one release.

Every feature here builds on [the design](design.md), which
[F13.1](F13.1-auth-design.md) settles. [Auth patterns](patterns.md) is the
background reference on the industry patterns. The browser client is ngkit's
work, tracked in ngkit's own epic against the same design.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| -- | -- | -- |
| [F13.1 — Auth design](F13.1-auth-design.md) | Settle the design, evaluate the libraries and record the decisions. | Active |
| [F13.2 — rn-forge-auth package](F13.2-auth-package.md) | Create the package and move the existing token, `Principal` and OIDC code into it. | New |

`rn-forge-auth` follows the package rule and adapter structure that
[E15](../E15-package-boundaries/index.md) sets
([ADR-0011](../../../adr/ADR-0011.md)).

Once F13.1 settles, the design's
[What this replaces](design.md#what-this-replaces) and
[Package placement](design.md#package-placement) sections become numbered
features here. F13.2 creates the `rn-forge-auth` package and moves the existing
code into it. The features that follow it cover the login adapters, the session
and HTTP surface for each framework, authorization context and resource policy,
and the removal of the locally issued JWT flows, and are written inside
`rn-forge-auth`.
