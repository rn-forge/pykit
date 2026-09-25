# Releasing packages

This runbook describes the repository's current tag workflow for a release executor. Use the [release index](../releases/index.md) for approved scope and evidence before executing a batch.

**Status:** done

**Release scope:** The first coordinated batch remains planned.

**Owner:** pykit release executor.

## Before a merge to `main`

1. Confirm the owner has decided the Django split gate [F8.1](../specs/epics/E8-django-scope-and-auth/F8.1-django-split.md) (Q4) and the batch's package scope [F9.4](../specs/epics/E9-release-readiness/F9.4-batch-scope.md) (Q5). The outcomes remain open.
2. Check the release page's declared package versions, intended tags, direct and extra dependencies, required validation, and approval. Inspect remote tag refs; local tags do not establish remote availability.
3. Confirm each internal dependency's intended tag exists and can be installed outside the workspace. [F9.5](../specs/epics/E9-release-readiness/F9.5-external-installability.md) tracks that evidence. A local workspace build resolves source overrides and is insufficient.
4. Confirm the selected change is ready for `main`. A push to `main` can create tags and GitHub Releases automatically. The release cut [F9.6](../specs/epics/E9-release-readiness/F9.6-tag-cut.md) requires owner approval.

## What CI does

`.github/workflows/main.yml` runs import-boundary checks first. It calls `_package-ci.yml` separately for commons, CLI, tooling, web, Django and FastAPI. Each reusable job verifies the package, reads its declared version and checks whether its tag exists remotely. On a push to `main`, a missing tag causes the workflow to build, create and push the tag, and publish a GitHub Release with the build artifacts. A pull request may build artifacts but does not publish a tag.

The current job graph does not enforce dependency-ordered publication. It also has no SQLAlchemy package job. [F9.1](../specs/epics/E9-release-readiness/F9.1-sqlalchemy-ci.md) and [F9.3](../specs/epics/E9-release-readiness/F9.3-release-mechanism.md) track those gaps. The root documentation job builds without `--strict`; [F9.2](../specs/epics/E9-release-readiness/F9.2-strict-docs-ci.md) tracks that change.

After publication, record the actual package, version, remote tag and install evidence on the release page. Keep proposed packages out of the completed roster until the owner confirms scope and their refs exist. Kiln's pin flip is downstream work; whether SQLAlchemy joins its tag order remains open (Q10).
