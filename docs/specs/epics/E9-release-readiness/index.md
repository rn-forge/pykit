# E9 — Release readiness

This epic holds pykit's release evidence and tag work. Kiln owns the trigger and downstream golden-repo acceptance.

**Status:** planned

**Readiness:** not ready

**Readiness basis:** Release scope and publication-order decisions remain unresolved. Independently ready features are identified below.

**Owner:** pykit release owner.

**Depends on:** Kiln E7's owner declaration that pykit is stable; [F8.1](../E8-django-scope-and-auth/F8.1-django-split.md) before tags.

[Back to the work index](../../index.md)

| Feature | Status | Readiness | Work |
| --- | --- | --- | --- |
| [F9.1 — SQLAlchemy CI](F9.1-sqlalchemy-ci.md) | planned | not ready | Add package validation job. |
| [F9.2 — Strict docs CI](F9.2-strict-docs-ci.md) | planned | ready | Build documentation strictly in CI. |
| [F9.3 — Release mechanism](F9.3-release-mechanism.md) | planned | not ready | Document actual tagging and decide order enforcement. |
| [F9.4 — Batch scope](F9.4-batch-scope.md) | planned | not ready | Confirm selected packages. |
| [F9.5 — External installability](F9.5-external-installability.md) | planned | ready | Prove remote refs and external installs. |
| [F9.6 — Tag cut](F9.6-tag-cut.md) | planned | not ready | Owner-approved release action. |

The [release runbook](../../../runbooks/releasing-packages.md) describes the current workflow. A release assignment will live in `releases/` after the owner settles scope. [E12](../E12-kiln-acceptance/index.md) tracks kiln's separate work.

## Readiness dependencies

The owning specs hold the unresolved decisions: [F8.1](../E8-django-scope-and-auth/F8.1-django-split.md#open-questions) for package boundaries, [F9.3](F9.3-release-mechanism.md#open-questions) for publication policy and [F9.4](F9.4-batch-scope.md#open-questions) for batch scope. [E12](../E12-kiln-acceptance/index.md#open-questions) owns the downstream tag-order decision. Feature readiness above is separate from progress and release approval.
