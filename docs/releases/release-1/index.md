# Release-1 — proposed coordinated batch

This page holds the proposed first coordinated pykit release batch. Release executors use it to record approved scope, dependency prerequisites and completion evidence.

**Status:** planned

**Readiness:** not ready

**Readiness basis:** Scope is proposed, and required package-boundary and publication decisions are unresolved in the linked specs. No release action is authorized.

**Owner:** pykit release owner.

**Depends on:** Kiln E7's owner declaration that pykit is stable; the Django-scope decision [F8.1](../../specs/epics/E8-django-scope-and-auth/F8.1-django-split.md); batch selection [F9.4](../../specs/epics/E9-release-readiness/F9.4-batch-scope.md).

[Back to releases](../index.md) · [Release runbook](../../runbooks/releasing-packages.md)

## Proposed package matrix

This matrix copies the declared versions and internal dependency edges from the seven package manifests. It is a proposal for [F9.4](../../specs/epics/E9-release-readiness/F9.4-batch-scope.md), not an approved roster or evidence that the proposed tags exist.

| Candidate package | Declared version | Proposed tag | Direct internal prerequisites |
| --- | --- | --- | --- |
| `rn-forge-commons` | `0.5.0` | `rn-forge-commons-v0.5.0` | None |
| `rn-forge-cli` | `0.1.0` | `rn-forge-cli-v0.1.0` | `rn-forge-commons` |
| `rn-forge-tooling` | `0.2.0` | `rn-forge-tooling-v0.2.0` | `rn-forge-commons`, `rn-forge-cli` |
| `rn-forge-web` | `0.1.0` | `rn-forge-web-v0.1.0` | `rn-forge-commons[pydantic]` |
| `rn-forge-django` | `0.3.0` | `rn-forge-django-v0.3.0` | `rn-forge-commons`, `rn-forge-web` |
| `rn-forge-fastapi` | `0.1.0` | `rn-forge-fastapi-v0.1.0` | `rn-forge-web[security]` |
| `rn-forge-sqlalchemy` | `0.1.0` | `rn-forge-sqlalchemy-v0.1.0` | `rn-forge-web` |

Optional extras add internal edges: `rn-forge-web[auth]` adds `rn-forge-commons[auth]`; Django's `fixtures` and `oidc` extras add commons capabilities, and `oidc` and `security` add web capabilities. FastAPI's `oidc` extra adds `rn-forge-web[auth]`; its `transfer` extra adds `rn-forge-commons[excel]`. These edges come from the manifests and must be checked when approving the batch. CLI and tooling are not prerequisites of web or the framework packages.

## Scope and gates

The following are required release gates; the package roster remains proposed. Readiness is summarized from the linked specs, where decisions and acceptance remain authoritative.

| ID | Requirement | Progress | Spec readiness | Release impact |
| --- | --- | --- | --- | --- |
| [F8.1](../../specs/epics/E8-django-scope-and-auth/F8.1-django-split.md) | Decide Django package boundaries | planned | **not ready** | **Blocked:** unresolved required decision |
| [F9.1](../../specs/epics/E9-release-readiness/F9.1-sqlalchemy-ci.md) | Add SQLAlchemy CI if selected | planned | **not ready** | **Blocked if selected:** publication-policy dependency |
| [F9.2](../../specs/epics/E9-release-readiness/F9.2-strict-docs-ci.md) | Make docs CI strict | planned | ready | Implementation pending |
| [F9.3](../../specs/epics/E9-release-readiness/F9.3-release-mechanism.md) | Settle publication-order enforcement | planned | **not ready** | **Blocked:** unresolved required decision |
| [F9.4](../../specs/epics/E9-release-readiness/F9.4-batch-scope.md) | Select package and feature scope | planned | **not ready** | **Blocked:** batch scope unapproved |
| [F9.5](../../specs/epics/E9-release-readiness/F9.5-external-installability.md) | Verify external installs | planned | ready | Evidence pending; execution waits for tags |
| [F9.6](../../specs/epics/E9-release-readiness/F9.6-tag-cut.md) | Approve and cut tags | planned | **not ready** | **Blocked:** required decisions and approval pending |

The release scope will link the selected implemented work from [E1](../../specs/epics/E1-foundation-and-boundaries/index.md), [E2](../../specs/epics/E2-http-contract/index.md), [E3](../../specs/epics/E3-framework-adapters/index.md), [E4](../../specs/epics/E4-standards-rebaseline/index.md) and [E5](../../specs/epics/E5-tool-lifecycle/index.md) once the owner selects packages. [F6.1](../../specs/epics/E6-consumer-reuse/F6.1-log-redaction.md) and [F6.2](../../specs/epics/E6-consumer-reuse/F6.2-sse.md) are planned without release assignment. Kiln owns its [golden-repo acceptance](../../specs/epics/E12-kiln-acceptance/index.md).

## Completion evidence

Record each approved package's version, remote tag and commit ref, current required validation, and successful external install without a workspace source override. Record explicit release approval and the resulting GitHub Release. Until those facts are present, this page remains `planned`.

## Candidate scope readiness

These features are not assigned to this release. Their unresolved specifications become release blockers only if selected; excluding them does not block this batch.

| Candidate | Spec readiness | If selected |
| --- | --- | --- |
| [F6.1 — Log redaction](../../specs/epics/E6-consumer-reuse/F6.1-log-redaction.md) | **not ready** | **Blocked:** settle acceptance scope before implementation |
| [F6.2 — SSE](../../specs/epics/E6-consumer-reuse/F6.2-sse.md) | **not ready** | **Blocked:** settle adapter contract and acceptance before implementation |

[F9.4](../../specs/epics/E9-release-readiness/F9.4-batch-scope.md#open-questions) owns selection. [E12](../../specs/epics/E12-kiln-acceptance/index.md#open-questions) owns downstream kiln coordination; unrelated deferred kiln work and the whole-auth review are not added to this release by this table.
