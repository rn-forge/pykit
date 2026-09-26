# Releasing packages

How to take a coordinated release from an approved page to verified tags. A push to `main` creates the tags, so everything that must be true of the tags is settled before the merge, and everything that proves them happens after it.

## How CI tags

`.github/workflows/main.yml` runs the import-boundary check first, then one reusable `_package-ci.yml` job per package, all in parallel from the same commit. Each package job verifies the package (ruff, pyright, pytest), reads its declared version and checks whether `<package>-v<version>` exists on the remote. On a push to `main`, a missing tag makes the job build the package, create and push the tag, and publish a GitHub Release with the build artifacts. A pull request builds but never tags.

Three consequences:

- **Order hardly matters.** Every tag points at the same commit and is pushed within one run.
- **A partial run is the risk.** If one package's job fails, packages that depend on it can still be tagged, pinning a tag that does not exist. [S9.3.3](../specs/epics/E9-release-readiness/F9.3-release-mechanism.md) removes it: each package job waits for its prerequisites' jobs, so a failure blocks only its dependents, and CI runs only the packages a change affects plus their dependents. Until S9.3.3 lands, treat any failed package job as blocking the whole release.
- **CI never proves external resolution.** Every job syncs with `--all-packages`, so internal dependencies resolve from the workspace, not from their pins. The install check after tagging is separate ([F9.5](../specs/epics/E9-release-readiness/F9.5-external-installability.md)).

`rn-forge-sqlalchemy` has no package job yet ([F9.1](../specs/epics/E9-release-readiness/F9.1-sqlalchemy-ci.md)), and the docs job builds without `--strict` ([F9.2](../specs/epics/E9-release-readiness/F9.2-strict-docs-ci.md)).

## Steps

### Before the merge

1. Confirm the release page's decisions are recorded and its scope stories are done.
1. Confirm every package in scope has the version it should be tagged at, and that no tag for that version exists on the remote (`git ls-remote --tags origin`). A local tag proves nothing.
1. Move each package's `[Unreleased]` changelog entries under a heading for the version being tagged, dated with the merge day.
1. Restore tag pins: every internal requirement names the tag this release creates (S9.7.2). A pin to `feature/upgrade` must not be tagged.
1. Run the workspace validation from the [development guide](../guides/development.md), and get the owner's approval to release.

### Merge and watch

1. Merge to `main`.
1. Watch every package job to completion. If one fails, fix it forward on `main`; nobody consumes a dependent's tag until its prerequisites' tags exist.

### After the merge

1. Confirm each tag and GitHub Release exists on the remote.
1. Check the external install job ([F9.5](../specs/epics/E9-release-readiness/F9.5-external-installability.md)) passed for each new tag.
1. Check each tagged package's docs at `https://rn-forge.github.io/pykit/packages/<package>/latest/` show the new version ([F9.9](../specs/epics/E9-release-readiness/F9.9-package-docs.md); until S9.9.4 lands, no versioned site is deployed).
1. Record each package's version, tag, commit and install result on the release page, and set it to `shipped` with the date once its exit criteria hold.
