# Releasing packages

How to take a coordinated release from an approved page to verified tags. A push
to `main` creates the tags, so everything that must be true of the tags is
settled before the merge, and everything that proves them happens after it.

## How CI tags

`.github/workflows/main.yml` names no package; the `rn-forge-devops` package
(`uv run rn-forge-devops`) reads them from the workspace manifests
([F14.1](../specs/epics/E14-workspace-automation/F14.1-discovered-pipeline.md)).
The import-boundary check and a `plan` job run first.

`plan` selects the packages whose files changed plus every package that depends
on one, read from the manifests' internal requirements; a change outside the
packages and `docs/`, or a manual run, selects all of them. It emits the
matrices for the check jobs, which run in parallel: `verify` (ruff, pyright,
pytest) for each selected package; `postgres`, `redis` and `smoke` for packages
that declare them in `[tool.workspace-ci]` (today `rn-forge-django`: its tests
against PostgreSQL, and each extra installed alone from the built wheels); and
each root suite, such as `scaffold`.

On a push to `main`, the baseline is the last successful push run of this
workflow on `main`, so failed or superseded runs' changes are included again.
Pull requests use their base SHA. A missing or non-ancestor baseline selects all
packages.

Each passing check leaves a marker. The single `release` job then walks the
selected packages in dependency order and takes the ones whose checks all passed
and whose selected prerequisites were taken too. A published GitHub Release, not
a tag alone, marks `<package>-v<version>` as shipped. On a push to `main`, an
already published release is skipped; a missing tag is built from the pushed
commit; an existing tag without a published release is rebuilt from its original
source in a detached worktree. A leftover draft is deleted after the build
succeeds, preserving its tag.

Every build, including a pull request's, runs `twine check --strict`, so a
package with broken metadata fails CI. On a push to `main`, `release` then
uploads the package to PyPI by trusted publishing, unless PyPI already has that
version. Each uploaded file carries a PEP 740 attestation, which the job signs
beforehand with `astral-sh/attest-action`; the GitHub release attaches only the
wheel, the sdist and the SBOM. Only after the upload does `gh release create`
attach the artifacts and publish the release, creating a missing tag at the
pushed commit
([GitHub CLI release creation](https://cli.github.com/manual/gh_release_create)).
A published release therefore implies the version is on PyPI. Its notes are the
package's changelog section for the version, and it is never marked "Latest". A
separate reusable workflow creates the umbrella `release-<n>` release, marked
"Latest", from the newest release page whose status is `shipped`, unless that
tag exists. A pull request builds but never publishes. `ci-ok` fails if any job
failed; it is the required status check.

Three consequences:

- **Fresh tags share a commit.** New tags point at the pushed commit; resumed
  releases keep their original tag and source.
- **A partial run is the risk.** If one package's checks fail, packages that
  depend on it could be tagged ahead of it. `release` withholds a package with
  a failed check and every selected package that depends on it, and releases
  the rest
  ([S9.3.2](../specs/epics/E9-release-readiness/F9.3-release-mechanism.md)). A
  package that was not selected is not re-tagged, and its existing tag still
  satisfies its dependents' ranges.
- **CI never proves external resolution.** Every job syncs with
  `--all-packages`, so internal dependencies resolve from the workspace, not
  from their ranges. The install check after tagging is separate
  ([F9.5](../specs/epics/E9-release-readiness/F9.5-external-installability.md)).

The docs job runs after `release` and builds with `--strict`, so a broken link
fails the run before deploy
([F9.2](../specs/epics/E9-release-readiness/F9.2-strict-docs-ci.md)). Before it
builds the root site, it finds the `<package>-v<version>` tags that point at the
pushed commit and deploys each package's site with `mike` to `gh-pages` under
`packages/<package>/<major>.<minor>/`, moving `latest` to it. It then copies
that tree into the root site's Pages artifact
([S9.9.4](../specs/epics/E9-release-readiness/F9.9-package-docs.md)). A failed
docs job leaves the tags in place; rerun the original `main` push run.

A failed release is fixed by rerunning the original `main` push run; it skips
what PyPI and GitHub already have. A manual dispatch builds only and does not
publish releases or deploy Pages. Dispatching it with `testpypi` set uploads
every package to TestPyPI instead, skipping versions already there, and creates
no tags or releases; use it from the release branch to prove the uploads before
the merge. The workflow's token cannot create a PyPI project, so before a
package's first upload the owner creates the empty project from the `rn-forge`
organization's *Projects* page and attaches the trusted publisher (owner
`rn-forge`, repository `pykit`, workflow `main.yml`, environment `pypi`). That
page allows the organization 10 new projects a day. Do not create a project by
uploading with a user token: that path has a lower personal limit, and Release 7
hit `429 Too many new projects created` after four projects, still in force 90
minutes later. The limits cover new projects only, so uploading a version to an
existing project is unaffected. An empty project has no JSON API page, so check
it at `https://pypi.org/simple/<name>/`
([F21.3](../specs/epics/E21-pypi-distribution/F21.3-publish-from-release.md#registering-the-publishers)).
A resumed tag at an older commit is outside that run's automatic
external-install and docs checks. Verify its published assets and package docs,
then check its install and import by hand, substituting the package, version and
import module:

```bash
package=rn-forge-web
version=0.1.0
module=rn_forge.web
tmp=$(mktemp -d)
uv venv -q "$tmp/venv"
VIRTUAL_ENV="$tmp/venv" uv pip install "$package==$version"
"$tmp/venv/bin/python" -c "import $module"
```

## Yanking a bad version

PyPI never accepts a version twice, even after a delete, so a bad release is
fixed forward:

1. Yank the version on pypi.org (the project's *Manage* page, then *Options*).
   Installers stop choosing it unless a requirement pins it exactly.
1. Fix the problem on `main` and release the next patch version of the package.

## Steps

### Before the merge

1. Confirm the release page's decisions are recorded and its scope stories are
   done.
1. Confirm every package in scope has the version it should be tagged at, and
   that no tag for that version exists on the remote
   (`git ls-remote --tags origin`). A local tag proves nothing. The version
   follows the bump rule ([ADR-0004](../adr/ADR-0004.md)): before 1.0, minor
   for a breaking change and patch otherwise.
1. Move each package's `[Unreleased]` changelog entries under a heading for the
   version being tagged, dated with the merge day.
1. Run `rn-forge-devops requirements`. A package's ceiling must admit each
   dependency version this release tags. A breaking release of a dependency
   needs each dependent to widen its ceiling, after its tests pass on the new
   version, and to be released with it.
1. Run the workspace validation from the
   [development guide](../guides/development.md), and get the owner's approval
   to release.

### Merge and watch

1. Merge to `main`.
1. Watch the run to completion. If a check fails, fix it forward on `main`;
   nobody consumes a dependent's tag until its prerequisites' tags exist.

### After the merge

1. Confirm each tag and GitHub Release exists on the remote.
1. Check the external install job
   ([F9.5](../specs/epics/E9-release-readiness/F9.5-external-installability.md))
   passed for each new tag.
1. Check each tagged package's docs at
   `https://rn-forge.github.io/pykit/packages/<package>/latest/` show the new
   version ([F9.9](../specs/epics/E9-release-readiness/F9.9-package-docs.md)).
1. Once the `docs` job has deployed, install the released packages by name from
   PyPI, as the `external-install` job does.
1. Fill the release's `security.md` with each control's result and evidence.
1. Record each package's version, tag, commit and install result on the release
   page, and set it to `shipped` with the date once its exit criteria hold.
