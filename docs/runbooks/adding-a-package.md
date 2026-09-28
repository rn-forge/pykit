# Adding a package

This runbook guides maintainers through adding a pykit workspace member. It covers repository integration; the package's own README and docs own its API and setup.

1. Give the package its own `packages/<name>/pyproject.toml`, `src/rn_forge/<module>/` tree, `py.typed` marker, tests, README, `CHANGELOG.md`, documentation and standalone `mkdocs.yml`. Follow the existing `uv_build` namespace package mapping and Python floor.
   Copy the published-package parts from an existing package ([ADR-0009](../adr/ADR-0009.md)): `[project.urls]`, the README's opening links line and its absolute-only links, `docs/changelog.md` with its nav entry, and the `mkdocs.yml` `site_url`, `repo_url`, `pymdownx.snippets`, `mike` plugin (`canonical_version: latest`) and `extra.version.provider: mike` settings.
2. Add the member to root `[tool.uv.workspace].members` and the root development dependency group. Add local `[tool.uv.sources]` overrides for its internal dependencies while keeping the declared dependencies pinned to intended git tags. Inspect optional extras independently.
3. Update the root `.importlinter` file with the new package's place in the graph. Keep the import rules executable before adding cross-package imports. The [workspace page](../architecture/workspace.md) describes the current boundaries.
4. Add the package to the root MkDocs includes and reader entry points. Build its standalone site and the combined site with strict link checking.
5. CI picks the member up from the workspace ([F14.1](../specs/epics/E14-workspace-ci/F14.1-discovered-pipeline.md)); the workflow needs no edit. If the package has PostgreSQL tests or extras that need an isolated install check, declare them in its `[tool.workspace-ci]` tables, as `rn-forge-django` does. The docs job publishes the package's versioned site when its first tag is cut ([F9.9](../specs/epics/E9-release-readiness/F9.9-package-docs.md)).
6. Validate the new package's tests, lint, types, import contracts and documentation. A local workspace build does not show that the package installs outside the workspace; a release proves that ([releasing packages](releasing-packages.md)).

If applications will install the package, add a scaffolded-application test for it, as [F9.8](../specs/epics/E9-release-readiness/F9.8-scaffolded-acceptance.md) does for the existing packages ([ADR-0008](../adr/ADR-0008.md)).
