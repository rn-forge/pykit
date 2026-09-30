# E9 — Release readiness

| | |
| --- | --- |
| **State** | Closed |
| **Start Date** | 2026-09-24 |
| **Closed Date** | 2026-09-28 |

What pykit must decide, fix and prove before its first coordinated set of tags, and the interim that keeps pykit installable outside the workspace until then.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| --- | --- | --- |
| [F9.1 — SQLAlchemy CI](F9.1-sqlalchemy-ci.md) | Add the missing package job. | Closed |
| [F9.2 — Strict docs CI](F9.2-strict-docs-ci.md) | Build the documentation with `--strict` in CI. | Closed |
| [F9.3 — Release mechanism](F9.3-release-mechanism.md) | Tagging is documented; CI jobs are scoped to changes and wait on their prerequisites, so a partial run cannot tag a dependent. | Closed |
| [F9.4 — Batch scope](F9.4-batch-scope.md) | All seven packages; F6.1 and F6.2 deferred. | Closed |
| [F9.5 — External installability](F9.5-external-installability.md) | A CI job proves each new tag installs outside the workspace. | Closed |
| [F9.6 — Tag cut](F9.6-tag-cut.md) | Approve and cut the tags. | Closed |
| [F9.7 — Interim branch pins](F9.7-interim-branch-pins.md) | Internal pins named `feature/upgrade` until S9.7.2 restored tag pins. | Closed |
| [F9.8 — Scaffolded acceptance](F9.8-scaffolded-acceptance.md) | Prove each package in an application scaffolded from built wheels. | Closed |
| [F9.9 — Package docs](F9.9-package-docs.md) | Metadata, READMEs, changelogs and versioned package sites; live pages confirmed after the tag cut. | Closed |

All nine features are closed; release-1's exit criteria are met.

The [release runbook](../../../runbooks/releasing-packages.md) describes the workflow.
