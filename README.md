# pykit

Development kit for Python programming. A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) containing the `rn-forge-*` package family.

Docs: [rn-forge.github.io/pykit](https://rn-forge.github.io/pykit/)

## Packages

| Package | Import path | Description |
| --- | --- | --- |
| [`rn-forge-commons`](packages/rn-forge-commons) | `rn_forge.commons` | Runtime-neutral utilities, grouped by kind of mechanism: `lang` (collections, dataclasses, reflection, values), `fs` (paths, hashing, locks, blocks, documents), `data` (Excel/pandas), `logging`, `runtime` (environment, subprocess, tasks, plugins) and `integration` (messaging/object/secret protocols, resilience), plus config, exceptions, findings and testing helpers. No web framework. |
| [`rn-forge-cli`](packages/rn-forge-cli) | `rn_forge.cli` | The shared command-line layer: `CliApp` (a `typer.Typer` subclass), the standard option set, the error-to-exit-code mapping and the declared `[cli]` surface. What an ordinary batch application wants as much as a developer tool does. Console output is not here — it is a property of the process, and lives in `rn-forge-commons`. |
| [`rn-forge-tooling`](packages/rn-forge-tooling) | `rn_forge.tooling` | The file-owning developer tooling: local JSON state, a strict Jinja engine, the generation engine, and install mechanics. Depends on `rn-forge-cli`; never a runtime dependency of a deployed app. |
| [`rn-forge-web`](packages/rn-forge-web) | `rn_forge.web` | Framework-agnostic HTTP/API primitives — the wire semantics an application promises its callers: W3C Trace Context, RFC 9457 problem details, ETag preconditions, AIP-158 pagination, idempotency, readiness, ASGI middleware, the auth contract, and a framework-free conformance table. Depends on `rn-forge-commons` and nothing else. |
| [`rn-forge-django`](packages/rn-forge-django) | `rn_forge.django` | Django/DRF integration layer built on `rn-forge-commons`: abstract model base classes, auth (basic/JWT/SAML), DRF views/serializers/exceptions, a typed settings facade. |
| [`rn-forge-fastapi`](packages/rn-forge-fastapi) | `rn_forge.fastapi` | FastAPI adapters over `rn-forge-web`: problem handlers, pydantic wire mirrors with a camelCase base, the OpenAPI error-type repair and `operationId` convention, pagination/idempotency/`If-Match` dependencies, a health router and the auth binding. Makes no wire decision of its own. |

## Import boundaries

The boundaries between these packages are executable, not conventional.
[`.importlinter`](.importlinter) states seven contracts and `uv run lint-imports` proves them; CI
gates every other job on it.

1. `rn_forge.commons` never imports `rn_forge.cli`, `rn_forge.tooling`, Typer or Jinja — it is
   runtime-neutral and ships into web servers and containers.
2. `rn_forge.cli` never imports `rn_forge.tooling` or Jinja — a batch application takes the
   command-line layer without the file-owning machinery (kiln D52, ADR-0002).
3. The three libraries layer strictly: `tooling` → `cli` → `commons`.
4. `rn_forge.django`'s runtime surface imports none of them. Only `rn_forge.django.codegen` may,
   and only with the (not yet built) `codegen` extra installed.
5. `rn_forge.web` imports no web framework (`django`, `fastapi`, `starlette`, `rest_framework`)
   and neither `rn_forge.cli` nor `rn_forge.tooling` — it ships into an ASGI server and has no
   business reaching the command-line or file-owning layers.
6. The framework packages layer on top of it: `django` → `web` → `commons` and
   `fastapi` → `web` → `commons`, as independent siblings, so neither may import the other.
7. `rn_forge.fastapi` imports neither `rn_forge.django`, `rn_forge.cli`, `rn_forge.tooling` nor
   Jinja. Only its (not yet built) `rn_forge.fastapi.codegen` may.

There are deliberately **no compatibility re-exports** in any direction: a shim would satisfy a
caller and reverse the dependency.

All packages ship a `py.typed` marker and are type-checked in strict mode.

## Design principles

1. **Don't reimplement a proven library.** If a maintained, widely-used package already does the job, depend on it. Zero dependencies is not a goal here — a small, deliberate dependency set is.
2. **Wrap for one design language.** Where a library's setup or call syntax is verbose or inconsistent with the rest of the kit, ship a thin wrapper: frozen-dataclass config, `AppException`-derived errors, injected logging, curated re-exports. The wrapper standardizes; it does not extend, fork, or vendor.
3. **Package boundaries are non-negotiable.** Framework-free packages import no web framework; heavy or situational dependencies live behind optional extras; protocols live in the lowest package that can hold them, adapters beside the technology they adapt.
4. **pykit is upstream.** Applications are built on these libraries rather than re-deriving them, so apps sharing pykit share logic and read alike.

These hold for every existing package and for every future one — new modules, new packages, new
extras. When a plan or a change conflicts with one of them, the principle wins unless the deviation
is written down with its reason.

On #1, hand-roll only when one of these is true, and say which one in the module docstring: nothing
maintained covers the concern (check PyPI before concluding this, not memory); the candidate drags
in a framework that would break a package boundary; or the needed slice is genuinely a few lines
and the candidate is unmaintained or far heavier.

On #2, a wrapper means: configuration is a frozen dataclass (or a settings-facade field), never a
kwargs soup; errors surface as `AppException` subclasses; logging is injected, never assumed;
public symbols are re-exported from the package's curated `__init__.py`. The wrapper standardizes
— it does not add features the library lacks, and the underlying object stays reachable as an
escape hatch.

On #4, surveys of existing applications are **prior art that informs the design**, not
compatibility constraints to preserve — where an application got something wrong, fix it here
rather than encoding it.

## Releases are pinned git tags, not PyPI versions

None of these packages is published to PyPI. A release is a tag (`rn-forge-commons-v0.5.0`), and
every consumer — including `rn-forge-cli` and `rn-forge-tooling` depending on `rn-forge-commons`
— declares it as a pinned direct URL (kiln D46):

```toml
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
]
```

The `[tool.uv.sources]` workspace override exists for local development only: it is what makes the
workspace resolve to this checkout, and it is not what a consumer resolves.

All packages use `uv_build` as the build backend, with `module-name` mapped to their `rn_forge.*`
namespace package.

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

Each package's own `README.md` and `docs/` carry its architecture: see
[`rn-forge-commons`](packages/rn-forge-commons), [`rn-forge-cli`](packages/rn-forge-cli),
[`rn-forge-tooling`](packages/rn-forge-tooling), [`rn-forge-web`](packages/rn-forge-web) and
[`rn-forge-django`](packages/rn-forge-django). [CLAUDE.md](CLAUDE.md) is the agent-instruction
file; it points here rather than restating any of it.
