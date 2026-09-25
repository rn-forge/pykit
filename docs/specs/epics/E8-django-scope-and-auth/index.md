# E8 — Django scope and auth

This epic keeps the pre-release Django package decision and the later whole-auth review together. It is for the owner deciding scope, not an authorization to change auth behavior.

**Status:** deferred

**Readiness:** not ready

**Readiness basis:** The package-scope decision and whole-auth design remain unsettled; feature readiness is listed below.

**Owner:** pykit owner.

**Entry criteria:** Decide the split before a tag cut; schedule the auth review when a consumer needs it.

[Back to the work index](../../index.md)

| Feature | Status | Readiness | Decision needed |
| --- | --- | --- | --- |
| [F8.1 — Django package split](F8.1-django-split.md) | planned release gate | not ready | Whether SAML, Celery, fixtures and messaging leave `rn-forge-django`. |
| [F8.2 — Whole-auth review](F8.2-auth-review.md) | deferred | not ready | Review Django and the web/FastAPI auth surfaces as one piece. |

## Readiness dependencies

[F8.1](F8.1-django-split.md#open-questions) owns the package-split decision required before tags. [F8.2](F8.2-auth-review.md#open-questions) owns the deferred auth-design question; it is not included in the release.

**Source:** `docs/plans/README.md`, Backlog; `standards-rebaseline-plan.md`, R6; `docs/auth-overview.md`, “My followup thoughts.”
