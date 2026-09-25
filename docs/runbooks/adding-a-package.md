# Adding a package

This runbook guides maintainers through adding a pykit workspace member. It covers repository integration; the package's own README and docs own its API and setup.

**Status:** done

**Owner:** pykit maintainers.

1. Give the package its own `packages/<name>/pyproject.toml`, `src/rn_forge/<module>/` tree, `py.typed` marker, tests, README, documentation and standalone `mkdocs.yml`. Follow the existing `uv_build` namespace package mapping and Python floor.
2. Add the member to root `[tool.uv.workspace].members` and the root development dependency group. Add local `[tool.uv.sources]` overrides for its internal dependencies while keeping the declared dependencies pinned to intended git tags. Inspect optional extras independently.
3. Update the root `.importlinter` file with the new package's place in the graph. Keep the import rules executable before adding cross-package imports. The [workspace page](../architecture/workspace.md) describes the current boundaries.
4. Add the package to the root MkDocs includes and reader entry points. Build its standalone site and the combined site with strict link checking.
5. Add package verification and any separate service tests to `.github/workflows/main.yml`. Its reusable package job must receive the package name and directory. Check coverage, release and documentation jobs for the new member; the current CI list does not update itself.
6. Validate the new package's tests, lint, types, import contracts and documentation. Record release readiness separately. A local workspace build does not establish external installability.

Kiln owns generated repository shape and golden-repo acceptance. Its planned `[archetype.python-lib] packages` entry and `state.json` re-seed require the kiln cutover; the corresponding files are absent from this checkout. Track that downstream integration in [E12](../specs/epics/E12-kiln-acceptance/index.md) when kiln schedules it.
