# pykit

Development kit for Python programming. A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) containing the `rn-forge-*` package family.

Docs: [rn-forge.github.io/pykit](https://rn-forge.github.io/pykit/)

## Packages

| Package | Import path | Description |
| --- | --- | --- |
| [`rn-forge-commons`](packages/rn-forge-commons) | `rn_forge.commons` | General-purpose utilities: config loading, collections/dict/json/yaml helpers, structured logging, dataclass mixins, subprocess/task helpers, Excel/pandas helpers, round-trip documents, integration protocols, managed blocks and structured findings. No Django dependency. |
| [`rn-forge-tooling`](packages/rn-forge-tooling) | `rn_forge.tooling` | The developer-tooling surface for the `rn-forge-*` CLIs: Rich console, Typer wiring, local JSON state, a strict Jinja engine, the generation engine, installer mechanics and the docs checkers. Depends on `rn-forge-commons`; never a runtime dependency of a deployed app. |
| [`rn-forge-django`](packages/rn-forge-django) | `rn_forge.django` | Django/DRF integration layer built on `rn-forge-commons`: abstract model base classes, auth (basic/JWT/SAML), DRF views/serializers/exceptions, a typed settings facade. |

The import boundaries between these are executable: [`.importlinter`](.importlinter) forbids
`rn_forge.commons` from importing tooling, Typer or Jinja, and forbids `rn_forge.django`'s runtime
surface from doing the same outside a future `codegen` extra. `uv run lint-imports` proves it.

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

See [`packages/rn-forge-commons`](packages/rn-forge-commons), [`packages/rn-forge-tooling`](packages/rn-forge-tooling) and [`packages/rn-forge-django`](packages/rn-forge-django) for package-specific details, and [CLAUDE.md](CLAUDE.md) for architecture notes.
