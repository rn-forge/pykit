# pykit

Development kit for Python programming. A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
containing the `rn-forge-*` package family.

Docs: [rn-forge.github.io/pykit](https://rn-forge.github.io/pykit/)

## Packages

| Package | Import path | Description |
| --- | --- | --- |
| [`rn-forge-commons`](packages/rn-forge-commons) | `rn_forge.commons` | General-purpose utilities: config loading, collections/dict/json/yaml helpers, structured logging, dataclass mixins, subprocess/task helpers, Excel/pandas helpers, CLI argument parsing. No Django dependency. |
| [`rn-forge-django`](packages/rn-forge-django) | `rn_forge.django` | Django/DRF integration layer built on `rn-forge-commons`: abstract model base classes, auth (basic/JWT/SAML), DRF views/serializers/exceptions, a typed settings facade. |

Both packages ship a `py.typed` marker and are type-checked in strict mode.

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
```

See [`packages/rn-forge-commons`](packages/rn-forge-commons) and [`packages/rn-forge-django`](packages/rn-forge-django)
for package-specific details, and [CLAUDE.md](CLAUDE.md) for architecture notes.
