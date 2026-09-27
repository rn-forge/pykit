# Release 1 — the first coordinated tags

**Status:** planned

pykit's first coordinated set of package tags. The only tags that exist today are single-package tags for `rn-forge-commons` and `rn-forge-django`, up to `v0.2.2`.

[Back to releases](../index.md) · [Release runbook](../../runbooks/releasing-packages.md)

## Entry criteria

- Every scope story below is done, and the owner approves the release (S9.6.1).
- Until then, pykit stays installable outside the workspace through branch pins ([F9.7](../../specs/epics/E9-release-readiness/F9.7-interim-branch-pins.md), [ADR-0004](../../adr/ADR-0004.md)).

## Scope

### Decisions

- [S9.9.1](../../specs/epics/E9-release-readiness/F9.9-package-docs.md#s991-record-the-decision) — each package publishes its own versioned docs (done)
- [S8.1.1](../../specs/epics/E8-django-scope-and-auth/F8.1-django-split.md#s811-record-the-split-decision) — the Django package keeps all four optional areas (done)
- [S9.3.2](../../specs/epics/E9-release-readiness/F9.3-release-mechanism.md#s932-decide-how-to-handle-a-partial-run) — a failed package job blocks only its dependents (done)
- [S9.4.1](../../specs/epics/E9-release-readiness/F9.4-batch-scope.md#s941-select-the-packages) — all seven packages (done)
- [S9.4.2](../../specs/epics/E9-release-readiness/F9.4-batch-scope.md#s942-decide-the-consumer-reuse-features) — F6.1 and F6.2 left out (done)

### Work

- [S9.1.1](../../specs/epics/E9-release-readiness/F9.1-sqlalchemy-ci.md#s911-add-the-package-job) — SQLAlchemy package job (done)
- [S9.2.1](../../specs/epics/E9-release-readiness/F9.2-strict-docs-ci.md#s921-make-the-docs-job-strict) — strict docs build in CI
- [S9.3.1](../../specs/epics/E9-release-readiness/F9.3-release-mechanism.md#s931-document-current-tagging) — the release mechanism documented (done)
- [S9.3.3](../../specs/epics/E9-release-readiness/F9.3-release-mechanism.md#s933-scope-ci-jobs-to-changes-and-dependencies) — CI jobs scoped to changes and ordered by dependency
- [S9.8.1–S9.8.4](../../specs/epics/E9-release-readiness/F9.8-scaffolded-acceptance.md) — each package accepted in a scaffolded application (done)
- [S9.9.1–S9.9.3](../../specs/epics/E9-release-readiness/F9.9-package-docs.md) — package metadata, landing READMEs and changelogs (done)
- [S9.9.4](../../specs/epics/E9-release-readiness/F9.9-package-docs.md#s994-deploy-versioned-package-sites) — versioned package sites deployed (done)
- [S9.7.1](../../specs/epics/E9-release-readiness/F9.7-interim-branch-pins.md#s971-pin-internal-dependencies-to-featureupgrade) and [S9.7.2](../../specs/epics/E9-release-readiness/F9.7-interim-branch-pins.md#s972-restore-tag-pins-for-the-release) — branch pins now, tag pins at the cut
- [S9.6.1](../../specs/epics/E9-release-readiness/F9.6-tag-cut.md#s961-approve-and-cut-the-tags) — the tag cut
- [S9.5.1](../../specs/epics/E9-release-readiness/F9.5-external-installability.md#s951-verify-remote-tags-and-clean-installs) — external install check

### Packages

All seven, at their declared versions; [F9.4](../../specs/epics/E9-release-readiness/F9.4-batch-scope.md#scope) has the matrix. They carry the delivered features of [E1](../../specs/epics/E1-foundation-and-boundaries/index.md), [E2](../../specs/epics/E2-http-contract/index.md), [E3](../../specs/epics/E3-framework-adapters/index.md), [E4](../../specs/epics/E4-standards-rebaseline/index.md) and [E5](../../specs/epics/E5-tool-lifecycle/index.md), named by feature ID because those epics predate the story taxonomy.

## Exit criteria

- S9.6.1 and S9.5.1 hold: every selected package's tag and GitHub Release exist, and each installs from its tag outside the workspace.
- S9.9.4 holds: every selected package's versioned docs site is live.
- This page lists each package, its version, tag and commit, and the install result.
