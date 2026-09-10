# pykit

Development kit for Python programming. A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) containing the `rn-forge-*` package family.

Docs: [rn-forge.github.io/pykit](https://rn-forge.github.io/pykit/)

## Packages

| Package | Import path | Description |
| --- | --- | --- |
| [`rn-forge-commons`](packages/rn-forge-commons) | `rn_forge.commons` | Runtime-neutral utilities, grouped by kind of mechanism: `lang` (collections, dataclasses, reflection, values), `fs` (paths, hashing, locks, blocks, documents), `data` (Excel/pandas), `logging`, `runtime` (environment, subprocess, tasks, plugins) and `integration` (messaging/object/secret protocols, resilience), plus config, exceptions, findings and testing helpers. No web framework. |
| [`rn-forge-cli`](packages/rn-forge-cli) | `rn_forge.cli` | The shared command-line layer: Rich console, the Typer application factory, the standard option set, the error-to-exit-code mapping and the declared `[cli]` surface. What an ordinary batch application wants as much as a developer tool does. |
| [`rn-forge-tooling`](packages/rn-forge-tooling) | `rn_forge.tooling` | The file-owning developer tooling: local JSON state, a strict Jinja engine, the generation engine, install mechanics and the docs checkers. Depends on `rn-forge-cli`; never a runtime dependency of a deployed app. |
| [`rn-forge-django`](packages/rn-forge-django) | `rn_forge.django` | Django/DRF integration layer built on `rn-forge-commons`: abstract model base classes, auth (basic/JWT/SAML), DRF views/serializers/exceptions, a typed settings facade. |

The import boundaries between these are executable. [`.importlinter`](.importlinter) states four
contracts — `rn_forge.commons` imports neither `cli` nor `tooling`, `rn_forge.cli` never imports
`tooling`, the three libraries layer strictly (tooling → cli → commons), and `rn_forge.django`'s
runtime surface imports none of them outside a future `codegen` extra. `uv run lint-imports` proves
them, and CI gates every other job on it.

There are deliberately **no compatibility re-exports** in any direction: a shim would satisfy a
caller and reverse the dependency.

All packages ship a `py.typed` marker and are type-checked in strict mode.

## Design principles

1. **Don't reimplement a proven library.** If a maintained, widely-used package already does the job, depend on it. Zero dependencies is not a goal here — a small, deliberate dependency set is.
2. **Wrap for one design language.** Where a library's setup or call syntax is verbose or inconsistent with the rest of the kit, ship a thin wrapper: frozen-dataclass config, `AppException`-derived errors, injected logging, curated re-exports. The wrapper standardizes; it does not extend, fork, or vendor.
3. **Package boundaries are non-negotiable.** Framework-free packages import no web framework; heavy or situational dependencies live behind optional extras; protocols live in the lowest package that can hold them, adapters beside the technology they adapt.
4. **pykit is upstream.** Applications are built on these libraries rather than re-deriving them, so apps sharing pykit share logic and read alike.

See [CLAUDE.md](CLAUDE.md) for the full statement of these.

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync --all-extras
```

## Development

```bash
uv run pytest                 # run tests across the workspace
uv run ruff check .           # lint
uv run ruff format .          # format
uv run pyright                # type check (strict mode, packages/ only)
uv run lint-imports           # enforce package import boundaries
```

See [`packages/rn-forge-commons`](packages/rn-forge-commons), [`packages/rn-forge-cli`](packages/rn-forge-cli), [`packages/rn-forge-tooling`](packages/rn-forge-tooling) and [`packages/rn-forge-django`](packages/rn-forge-django) for package-specific details, and [CLAUDE.md](CLAUDE.md) for architecture notes.
