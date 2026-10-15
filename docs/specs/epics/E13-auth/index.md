# E13 — Authentication and authorization

| | |
| --- | --- |
| **State** | New |

Standards-based authentication and authorization for new pykit web applications: SSO through OIDC and SAML, social login, optional local passwords, server-side sessions for browsers, bearer tokens for machine clients, and authorization computed from the application's own data. Django and FastAPI follow one pattern. The framework-neutral code moves to a new `rn-forge-auth` package, and each framework package binds it.

Every feature here builds on [the design](design.md), which [F13.1](F13.1-auth-design.md) settles. [Auth patterns](patterns.md) is the background reference on the industry patterns. The browser client is ngkit's work, tracked in ngkit's own epic against the same design.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| --- | --- | --- |
| [F13.1 — Auth design](F13.1-auth-design.md) | Settle the design and record its decisions. | New |

Once F13.1 settles, the design's [What this replaces](design.md#what-this-replaces) and [Package placement](design.md#package-placement) sections become numbered features here. Creating the `rn-forge-auth` package and moving the existing code into it is [E15's F15.2](../E15-package-boundaries/F15.2-auth-package.md). The features here cover the login adapters, the session and HTTP surface for each framework, authorization context and resource policy, and the removal of the locally issued JWT flows.
