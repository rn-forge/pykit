# E9 — Release readiness

**Status:** in progress · **Owner:** pykit · **Release:** [release-1](../../../releases/release-1/index.md)

What pykit must decide, fix and prove before its first coordinated set of tags, and the interim that keeps pykit installable outside the workspace until then.

[Back to the work index](../../index.md)

| Feature | Status | Work |
| --- | --- | --- |
| [F9.1 — SQLAlchemy CI](F9.1-sqlalchemy-ci.md) | planned | Add the missing package job. |
| [F9.2 — Strict docs CI](F9.2-strict-docs-ci.md) | in progress | Build the documentation with `--strict` in CI. |
| [F9.3 — Release mechanism](F9.3-release-mechanism.md) | in progress | Tagging is documented and the partial-run decision made; scope CI jobs to changes and dependencies. |
| [F9.4 — Batch scope](F9.4-batch-scope.md) | done | All seven packages; F6.1 and F6.2 deferred. |
| [F9.5 — External installability](F9.5-external-installability.md) | planned | A CI job proves each new tag installs outside the workspace. |
| [F9.6 — Tag cut](F9.6-tag-cut.md) | planned | Approve and cut the tags. |
| [F9.7 — Interim branch pins](F9.7-interim-branch-pins.md) | in progress | Internal pins name `feature/upgrade`; restore tag pins at the cut. |
| [F9.8 — Scaffolded acceptance](F9.8-scaffolded-acceptance.md) | planned | Prove each package in an application scaffolded from built wheels. |
| [F9.9 — Package docs](F9.9-package-docs.md) | in progress | Metadata, READMEs and changelogs done; deploy versioned package sites. |

**Next step:** F9.1, F9.8 and S9.9.4; F9.2 is confirmed by the first merge run.

**Order:** F9.1, F9.2, F9.8 and S9.9.4 can land at any time. S9.7.2 and S9.6.1 follow them; F9.5 verifies after S9.6.1.

The [release runbook](../../../runbooks/releasing-packages.md) describes the workflow.
