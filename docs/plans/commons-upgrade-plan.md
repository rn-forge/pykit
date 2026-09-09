# `rn-forge-commons` upgrade and package-boundary plan

Scope: `packages/rn-forge-commons` plus the ownership boundary with the planned
`rn-forge-tooling` package. `rn-forge-django` is explicitly **out of implementation scope** — but
it depends on commons via workspace linking, so every dependency added here ships into Django
services too, and every breaking API change here must be checked against `rn-forge-django` imports
before release.

Two sources feed this plan, and it is self-contained — it does not depend on any other document:

- A duplication survey performed 2026-08-31 across all of `packages/rn-forge-commons/src`, plus
  `/Users/rohitnarayanan/Devel/workspaces/rn-forge/agentkit` (`src/rn_forge/agentkit/core/*`,
  `commands/*`, `cli.py`) as the reference consumer for the new wrapper APIs. This produced **Part A**.
- A duplication survey performed 2026-09-04 across **two** consumers that have since been rebuilt:
  `/Users/rohitnarayanan/Devel/workspaces/rn-forge/agentkit` (~5.4k lines of source) and
  `/Users/rohitnarayanan/Devel/workspaces/rn-forge/taskkit` (~4.8k lines). These two repos have
  independently converged on the same architecture — Typer CLI → command objects → `core/`
  primitives (`io`, `state`, `paths`, `config`, `render`) → an adapter/plugin registry — and
  therefore duplicate each other extensively. This produced **Part C**, and revises Phases 2, 3 and
  5 of Part A. Note this supersedes the older single-consumer reading of agentkit that Part A was
  originally written against: `commands/common.py` no longer exists, having been replaced by
  `commands/base.py` + one class per command group.
- The commons-relevant subset of an earlier extraction survey of `cims-backend`
  (`/Users/rohitnarayanan/Devel/workspaces/walgreens/cims/backend`), performed 2026-07-22. This
  produced **Part B** and the standing conventions in "Conventions for new modules" below. Everything
  Django/DRF-shaped from that survey (RFC 7807 handler, pagination, idempotency keys, optimistic
  concurrency, OIDC/JWKS auth, outbox/inbox messaging, Celery, readiness views, sequence generators,
  request-ID middleware) is deliberately **not** here — it belongs to a future Django plan.

## Final package boundary

`rn-forge-commons` is the runtime-safe application foundation. It must be suitable for libraries,
web applications, workers, standalone applications and local tools. A capability does not belong
there merely because two local CLIs currently duplicate it; it must have runtime-neutral semantics.

| Owner | Capabilities |
| --- | --- |
| `rn-forge-commons` | Collections, dataclasses, documents, configuration, logging, exceptions, atomic file writes, content hashing, root discovery and path-containment guards |
| `rn-forge-commons` | Transport-neutral messaging/object/secret protocols, optional resilience, and generic Python entry-point discovery |
| `rn-forge-tooling` | `AppConsole`, Typer application wiring, local JSON state, configuration-template rendering, generator execution, directory locks, atomic symlink switching and archive extraction |
| agentkit/kiln | Domain models, command/result schemas, plugin policy, `$RNF_HOME` layout, product installation policy and product-specific validation |

The current `StateStore` is tooling-specific, not a general persistence abstraction: its lock is
best-effort and deliberately degrades to an unlocked write because a personal developer tool should
not fail on an unusual filesystem. A web service or shared worker must not inherit that policy.
`ContentHash` and `PathUtils.atomic_write` remain in commons because safe writes and stable hashes
are useful in every runtime.

`EntryPointLoader` remains in commons because it contains only the generic, dependency-free Python
entry-point mechanism. Plugin installation, enablement, validation, CLI mounting and lifecycle
policy stay in the consuming application or tooling layer.

Do not leave compatibility re-exports from commons to tooling: that would reverse the dependency
and create a cycle. Publish the relocation as a breaking commons change with an import migration
table. Tooling may import commons; commons must never import tooling.

The dependency graph is one-way:

```text
rn-forge-django ───────────► rn-forge-commons
rn-forge-fastapi ──────────► rn-forge-commons
rn-forge-tooling ──────────► rn-forge-commons
agentkit / kiln ───────────► rn-forge-tooling
rn-forge-django[codegen] ──► rn-forge-tooling      (extra; only rn_forge.django.codegen imports it)
```

Neither `rn-forge-django` nor `rn-forge-fastapi` may take a hard dependency on Typer, the tooling
state store or the generator engine. Production applications install only the framework runtime
package; developer environments add the `[codegen]` extra.

### Framework code generators

Nx/Angular-style generation is a tooling concern with framework-specific providers that ship
**inside the runtime package as an extra** (standardization plan D37; supersedes the separate
`rn-forge-django-codegen` / `rn-forge-fastapi-codegen` packages of revision 6):

- `rn-forge-tooling` owns a Python-callable generator contract and execution engine: option
  validation, template rendering, staged writes, conflict handling, dry-run/diff and generator
  state. The contract must not mention Typer.
- `rn-forge-django[codegen]` installs `rn-forge-tooling`; the Django templates, option schemas and
  generator implementations live in `rn_forge.django.codegen` and nowhere else. A future
  `rn-forge-fastapi[codegen]` follows the same shape. Co-versioning with the runtime is the reason:
  a generated app targets exactly the library version it was generated against.
- kiln owns the Typer command surface and discovers providers through the entry-point group
  `rn_forge.kiln.generators`, for example `kiln generate django app billing`.
- A generator must also be directly callable as Python, conceptually
  `generator.generate(options, workspace)`, so CLI parsing never becomes its API.

Three guards keep the extra out of the runtime surface, and all three exist **before** the first
codegen module is written (standardization plan Phase C.3):

1. pykit's `.importlinter` forbids `rn_forge.django` (excluding `rn_forge.django.codegen`) from
   importing `rn_forge.tooling`, `typer` or `jinja2`; `uv run lint-imports` runs in `task lint`.
2. `import rn_forge.django` succeeds with no extras installed (final checklist).
3. `rn_forge.django.__init__` never re-exports anything from `codegen`.

## Summary (read this first)

**Part A — consolidation.** Replace hand-rolled logic with proven libraries, and fix the internal
duplication found alongside it.

| Phase | What | New deps | Breaking? | Risk |
| --- | --- | --- | --- | --- |
| 0 | Internal dedup + latent-bug fixes | none | no | none |
| 1 | Rich replaces coloredlogs in `logging.py` | `rich` (hard) | no | low |
| 2 | `AppConsole` output layer, relocated to `rn-forge-tooling` | tooling depends on `rich` | **yes** | low |
| 3 | Typer application wiring, relocated to `rn-forge-tooling` | tooling depends on `typer` | **yes** | low |
| 4 | `dacite` replaces the `_coerce_*` block in `dataclasses.py` | `dacite` (hard) | no | low |
| 5 | `mergedeep` for `DictUtils.merge`; stdlib `pkgutil.resolve_name` for `import_string`; new `PathUtils.atomic_write` | `mergedeep` (hard) | no | low |
| 6 | **Gated:** OmegaConf replaces the `config.py` resolver | `omegaconf` (hard) | maybe | **medium** |

**Part B — new capability carried over from the cims survey.**

| Phase | What | New deps | Breaking? | Risk |
| --- | --- | --- | --- | --- |
| 7 | Environment fail-fast guards (`Environment.require` / `.forbid`) | none | no | none |
| 8 | New `resilience.py` — circuit breaker + retrying HTTP client | `resilience` extra | no | low |
| 8b | New `messaging.py` — `MessageBus` protocol + `InMemoryMessageBus` + `HandlerRegistry` | none | no | none |
| 8c | New `secrets.py` — `SecretStore`/`AsyncSecretStore` + `EnvSecretStore` | none | no | none |
| 8d | New `objects.py` — `ObjectStore`/`AsyncObjectStore` protocol | none | no | none |
| 9 | **Gated:** `StructLogger` — structlog front-end over `AppLogger`'s stdlib handlers | `structlog` extra | no | **medium** |
| — | Deferred: CloudEvents envelope, claim-check pattern | — | — | — |

**Part C — deduplication across agentkit and taskkit.** Every item here is implemented *twice
today*, once in each repo, and the two copies have already drifted. Ordered by lines removed.

| Phase | What | New deps | Removes (approx.) | Risk |
| --- | --- | --- | --- | --- |
| 10 | `PathUtils.atomic_write` reconciled against **both** copies (revises Phase 5.3) | none | ~120 lines | low |
| 11 | New `documents.py` — TOML/YAML/JSON serialisation + round-trip config documents | `tomlkit`, `ruamel.yaml` (base) | ~700 lines | low |
| 12 | `ContentHash` in commons; local JSON `StateStore` in tooling | none | ~200 lines | low |
| 13 | `PathUtils` repo-root discovery + path-escape guards | none | ~120 lines | low |
| 14 | `DictUtils.merge` grows layers + provenance (**replaces Phase 5.1**) | none | ~190 lines | medium |
| 15 | `DictUtils.flatten` + `TextUtils.unified_diff` | none | ~70 lines | none |
| 16 | Tooling-owned Jinja engine with strict undefined + `to_toml`/`to_yaml` | tooling depends on `jinja2` | ~80 lines | low |
| 17 | `EntryPointLoader` — failure-isolated plugin discovery | none | ~50 lines | low |
| 18 | Tooling-owned `DirectoryLock` + `atomic_symlink` + `extract_archive` | none | ~135 lines | low |
| — | **Application-owned:** `$RNF_HOME` layout, self-commands and product policy — see Phase 18 | — | — | — |

Phases 0-5 are safe and should be done in order. **Phase 6 has an explicit abort gate** — read its
section before starting it. Phase 7 is trivial and can be slotted in anywhere after Phase 0. Phase 8
is a standalone new module with no interaction with Part A, other than following the conventions
below. **Phase 9 has an explicit abort gate**, same shape as Phase 6 — read its section before
starting it.

The extraction sequence is:

1. Scaffold `rn-forge-tooling` as a typed workspace package depending on commons.
2. Move Phases 2, 3, the `StateStore` half of Phase 12, Phase 16 and Phase 18 mechanics into it,
   preserving behavior and tests.
3. agentkit is rebuilt from scratch on the tooling APIs and kiln is written against them from day
   one (standardization plan Phases D and F.3); taskkit remains a retired source of tested
   behavior, not a future consumer.
4. In the same breaking commons release, remove the relocated modules, their public re-exports,
   Typer and Jinja. Do not retain shims that make commons depend on tooling.
5. Add generator contracts only after the extraction is green; add Django/FastAPI providers as
   `[codegen]` extras of their runtime packages when their first generators are specified. The
   import-linter fence for `rn_forge.django.codegen` is added now, while the subpackage is empty.

**Phases 8b–8c–8d are added by [`web-library-plan.md`](./web-library-plan.md) §A.2** and are the
three protocol modules the rest of the workspace is blocked on: `rn-forge-azure` cannot start its
Phases 2, 3 or 4 without them, and `rn-forge-django`'s Phase 10 consumes 8b. They are small, they add
no dependencies, and they are pure protocol definitions plus in-memory/environment defaults — do them
early rather than at the end of Part B. They are numbered `8b`–`8d` rather than `9`–`11` so that
every existing cross-reference to "commons Phase 9" (the structlog gate) stays correct.

### Guiding principle for this plan

This is now a **workspace-wide design principle**, not just this plan's: see the README and CLAUDE.md
"Design principles" section — don't reimplement what a proven library does; wrap it thinly so every
`rn-forge-*` package reads the same. This plan was written under that rule and needs no change to
comply with it; new phases and future plans inherit it.

The stated requirement: *keep simple, thin, intuitive wrappers around the libraries we add, because
remembering them all while building a new application is hard.* So every phase that adds a library
also adds a commons-owned facade over it. The facade rules:

- **Thin.** A facade method should be a handful of lines. If it grows logic, that logic is a bug
  waiting to diverge from the library — push it into the library's own config instead.
- **Escape hatch, always.** Every wrapper exposes the underlying library object (`AppConsole.rich`,
  `LogLevel.to_int()`, `Config.omega`) so a consumer is never blocked by the facade.
- **Consistent with existing commons idiom.** `{}`-style message formatting (matching `AppLogger`),
  static-method utility classes, `Self` returns for chaining, curated re-export in
  `src/rn_forge/commons/__init__.py`.
- **Never re-wrap a good API.** Do not wrap `rich.table.Table` construction field-by-field; provide
  one `console.table(...)` convenience for the 90% case and let people build a `Table` directly for
  the rest.

### Conventions for new modules

These apply to every new module in Part B, and to any new file added in Part A. The first two are
standing design decisions carried over from the cims survey; the rest are existing repo conventions
restated so this document is self-contained.

1. **Logging is injected, not imported, in any module a non-pykit consumer might adopt.** cims uses
   `structlog`; commons' `AppLogger` is a stdlib-`dictConfig`/`verboselogs` design. Phase 9
   (gated) explores giving commons its own structlog-flavoured front end (`StructLogger`) that binds
   context and renders structured output while still emitting through `AppLogger`'s existing
   `dictConfig` handlers — so this is not a permanent "never unify" position, it is deferred to that
   phase's own gate. Until/unless Phase 9's gate passes, treat commons' own internal modules as
   stdlib/`AppLogger`-only: any new module that logs as part of its *observable behaviour* (a
   circuit-breaker state listener, a middleware, a relay) takes a logging callable as a
   constructor/factory parameter, defaulting to a thin `AppLogger.get_logger(__name__)` wrapper.
   Ordinary internal debug/trace logging inside commons' own utility modules stays on `AppLogger`
   directly — this rule is about *behavioural* log output that a consumer would want to route into
   their own stack.
2. **Metrics are optional hooks, never a hard dependency.** cims increments OpenTelemetry counters
   inline (`circuitbreaker_state`, `outbox_lag`). commons has an `otel` extra but no metrics module,
   and `opentelemetry-api` must not become a hard dependency. New modules accept plain callables
   (`on_state_change`, etc.) that a consumer wires to their own metrics backend.
3. **Follow the repo's module conventions.** Module docstring at the top of the file; explicit
   `__all__`; `DataclassMixin` for dataclasses that need serialization; `AppException` /
   `AppException.check(value, "msg {}", arg, error_code=...)` for validation rather than a raw
   `raise`; `AppLogger.get_logger(__name__)` at module level (subject to rule 1).
4. **Re-export from the owning package's curated public API.** Commons-owned symbols go into
   `src/rn_forge/commons/__init__.py`; tooling-owned symbols go into
   `src/rn_forge/tooling/__init__.py`. Keep imports and `__all__` sorted, and never re-export
   tooling from commons.
5. **New extras aggregate into `all`.** When adding an optional extra, add its packages to the `all`
   extra too, and gate the corresponding tests with `pytest.importorskip` following the pattern used
   by the pandas/openpyxl tests.
6. **Strict typing is a contract.** `src/` must satisfy Pyright strict mode (root `pyproject.toml`,
   `include = ["packages"]`); `tests/` is excluded. Tests are also excluded from ruff lint
   (`per-file-ignores` = `ALL`).

### Things deliberately NOT changed (decided; do not "improve" these)

- **`DictUtils.get` / `DictUtils.set`** (`collections.py:63-278`). `glom` covers this, but these are
  load-bearing across the `rn-forge-django` settings facade and `drf/views/transfer.py`. The dotted
  path + escaped-dot + list-index semantics are already tested. Leave them.
- **`DictUtils.compare`** (`collections.py:342-428`). `deepdiff` is more capable but emits a
  `root['a']['b']` DSL that would have to be translated back into the existing
  `only_in_a`/`only_in_b`/`conflicts` shape. Not worth a heavy dependency for ~60 lines. Leave it.
- **`excel.py`, `pandas.py`, `tasks.py`, `testing.py`.** Already appropriately thin wrappers over
  openpyxl / pandas / `concurrent.futures` / assertpy.
- **`DataclassMixin`'s serialization side** (`as_dict`, `to_json`, `to_yaml`, `__str__`, `__repr__`).
  Only the *deserialization* coercion helpers are replaced in Phase 4.
- **structlog support is no longer a closed question — see Phase 9's gate.** Note that Phase 1
  changes the *rendering* backend from coloredlogs to Rich; that neither moves commons toward
  structlog nor away from it and does not affect Phase 9's outcome either way.

### Python-version note (read before touching `logging.py`)

`logging.py:991` uses PEP 758 parenthesis-free `except TypeError, ValueError:`, which only parses on
Python 3.14+. Phase 0 changes it to the parenthesized form: valid on every Python version, costs
nothing, and keeps `rn-forge-commons` compatible with the latest stack without pinning to it.

### Dependency changes (apply incrementally, one phase at a time)

`packages/rn-forge-commons/pyproject.toml`:

```toml
dependencies = [
  "ruamel.yaml>=0.19.1",  # phase 11 (11.4) — replaces pyyaml outright
  "tomlkit>=0.15.0",      # phase 11 (11.4)
  "verboselogs>=1.7",
  "rich>=15.0.0",        # phase 1 — matches the floor already used by rn-forge-agentkit
  "dacite>=1.9.2",       # phase 4
  "mergedeep>=1.3.4",    # phase 5
  # "omegaconf>=2.3.0",  # phase 6 ONLY IF the gate passes
]

[project.optional-dependencies]
# coloredlogs = [...]  <-- DELETE in phase 1
json = ["python-json-logger>=4.0.0"]                                # phase 0
resilience = ["pybreaker>=1.2.0", "tenacity>=9.0.0", "httpx>=0.28"] # phase 8
# structlog = ["structlog>=25.1.0"]  # phase 9 ONLY IF the gate passes
# documents = [...]  <-- NOT created; see 11.4, both deps are base deps
excel = ["openpyxl>=3.1.5", "pandas>=3.0.3"]
otel = ["opentelemetry-instrumentation-logging>=0.64b0"]
pandas = ["pandas>=3.0.3"]
testing = ["assertpy>=1.1", "pytest>=9.1.1"]
all = [
  "httpx>=0.28",
  "openpyxl>=3.1.5",
  "opentelemetry-instrumentation-logging>=0.64b0",
  "pandas>=3.0.3",
  "pybreaker>=1.2.0",
  "python-json-logger>=4.0.0",
  "ruamel.yaml>=0.19.1",
  "tenacity>=9.0.0",
  "tomlkit>=0.15.0",
]
```

`rn-forge-tooling` declares its dependencies directly rather than relying on commons' transitive
dependencies:

```toml
dependencies = [
  "jinja2>=3.1.6",
  "rn-forge-commons",
  "rich>=15.0.0",
  "typer>=0.26.8",
]
```

Also remove `coloredlogs` from the `all` extra and from any `dev`/`docs` group that references it.

**Versioning:** the original argparse removal requires `rn-forge-commons` **`0.3.0`**. Relocating
the already-exposed CLI/tooling APIs requires the next breaking commons release; release
`rn-forge-tooling` independently so subsequent tooling changes do not force runtime-library bumps.

### Validation commands

Run from the repo root after each phase. Include tooling once it is scaffolded. Do not proceed with
any of these red:

```bash
uv sync --all-extras
uv run pytest packages/rn-forge-commons packages/rn-forge-tooling
uv run ruff check packages/rn-forge-commons packages/rn-forge-tooling
uv run ruff format --check packages/rn-forge-commons packages/rn-forge-tooling
uv run pyright                       # strict mode; src/ must be clean, tests are excluded
uv run --directory packages/rn-forge-commons --group docs mkdocs build --strict
uv run --directory packages/rn-forge-tooling --group docs mkdocs build --strict
```

Note `pyright` is configured `include = ["packages"]`, so it type-checks `rn-forge-django` too — a
breaking commons change that Django imports will surface here. That is intentional; fix the Django
call sites minimally (import-path updates only, no redesign) if any break.

---

## Part A — Consolidation

### Phase 0 — Internal dedup and latent-bug fixes

No new dependencies. Nothing here is user-visible except the `json` extra. Do this first; it makes
the later phases smaller.

#### 0.1 — Collapse the duplicated reflection helpers

**Problem.** `ReflectUtils.inspect_method_arguments` and `ReflectUtils.inspect_variables`
(`reflection.py:94-208`) have **zero call sites** anywhere in the workspace. `logging.py:976-1046`
independently implements the same two operations as `_format_arguments`, `_resolve_variables`, and
`_resolve_dotted_variable`. The two copies have diverged: the `logging.py` versions also search
`frame.f_globals` and catch `AttributeError` on dotted traversal; the `ReflectUtils` versions look
only at `f_locals` and will propagate an `AttributeError` from `attrgetter` on a bad path.

**The `logging.py` implementations are the correct ones.** Keep their behavior.

Steps:

1. In `reflection.py`, replace the bodies of `ReflectUtils.inspect_variables`,
   `_resolve_variable`, and `_resolve_dotted_variable` with the `logging.py` logic — i.e. search
   `f_locals` then `f_globals`, use `!r` formatting for values, and return `"<name>=<undefined>"`
   on a missing root *or* on an `AttributeError` during dotted traversal. Keep the existing
   public signature `inspect_variables(var_names: str, source_frame: FrameType | None = None)`.
   Keep the `frame is None -> []` early return and its trace log.
2. In `reflection.py`, replace the body of `ReflectUtils.inspect_method_arguments` with the
   `_format_arguments` logic — specifically, wrap `sig.bind(...)` in
   `except (TypeError, ValueError): return [repr(args), repr(kwargs)]`. The current version lets a
   bind failure propagate, which can crash an audit-logged call. Keep the existing signature and the
   `include` overriding the default `self`/`cls` exclusion. Use `!r` for values.
3. In `logging.py`, delete `_format_arguments`, `_resolve_variables`, and `_resolve_dotted_variable`
   entirely. Delete the now-unused `from operator import attrgetter as _attrgetter` import at
   `logging.py:17`.
4. Update the two call sites: `logging.py:704` becomes
   `ReflectUtils.inspect_method_arguments(func, args, kwargs, exclude=exclude, include=include)`,
   and `logging.py:825` becomes `ReflectUtils.inspect_variables(var_names, _f)`.
   `ReflectUtils` is already imported at `logging.py:31`.

**Import-cycle warning.** `reflection.py` deliberately does not import `AppLogger` at module scope —
it uses a lazy `_logger()` function (`reflection.py:25-28`) because `logging.py` imports
`reflection.py`. **Do not "clean up" that lazy import.** Any logging you add inside the moved code
must go through `_logger()`.

**Tests.** `tests/test_reflection.py` (255 lines) and `tests/test_logging.py` (938 lines) both
already cover these paths from opposite ends. Reconcile them: the reflection tests must gain the
globals-lookup and bind-failure cases that only the logging tests currently assert; the logging
tests that poke `_resolve_variables` directly must be repointed at `ReflectUtils`. Net line count
across the two files should go *down*.

#### 0.2 — Unify boolean parsing

**Problem.** `AppUtils.parse_bool` (`utils.py:245`) accepts `true/yes/enabled` and
`false/no/disabled/none`. `console.BooleanAction` (`console.py:59-61`) accepts `true/yes/1` and
`false/no/0`. So `--dry-run enabled` fails on the CLI while `Environment.is_enabled` accepts it, and
`--dry-run 1` fails in `parse_bool`.

**Fix.** Make `AppUtils.parse_bool` the single source of truth and widen its token set to the union:

- Truthy: `true`, `yes`, `y`, `on`, `1`, `enabled`
- Falsy: `false`, `no`, `n`, `off`, `0`, `disabled`, `none`

Then have `BooleanAction.__call__` delegate: `AppUtils.parse_bool(values, strict=False)`, raising
`argparse.ArgumentTypeError` when it returns `None`. Keep `BooleanAction`'s error message wording.

Note `console.py` is deleted in Phase 2 — so this delegation is short-lived, but do it anyway so
Phase 0 is independently correct and the widened token set is covered by the existing
`tests/test_console.py` boolean cases before they're deleted.

**Tests.** Extend `tests/test_utils.py::parse_bool` cases with the newly-accepted tokens. Extend
`tests/test_console.py` to assert `--flag enabled` and `--flag 1` both work.

#### 0.3 — Declare the JSON-logging dependency

**Problem.** `logging.py:866` wires `"()": "pythonjsonlogger.jsonlogger.JsonFormatter"` into
`dictConfig`, but `python-json-logger` is declared nowhere in `pyproject.toml`. Any consumer calling
`AppLogger.initialize(use_json=True)` gets a `dictConfig` `ValueError` at runtime. The path is never
exercised in CI because `tests/test_logging.py:344` does
`pytest.importorskip("pythonjsonlogger", ...)`.

**Fix.**

1. Add the `json` extra shown in the dependency block above, and add `python-json-logger>=4.0.0` to
   the `all` extra and to the `dev` dependency group (the `dev` group self-references
   `rn-forge-commons[excel]` today — change that to `rn-forge-commons[all]` so a `--group dev` sync
   exercises every optional path, per the convention stated in `CLAUDE.md`).
2. **Check the import path against the installed version.** `python-json-logger` 3.x moved the
   canonical module from `pythonjsonlogger.jsonlogger` to `pythonjsonlogger.json`, and
   `pythonjsonlogger.jsonlogger` now emits a `DeprecationWarning`. After syncing, verify which path
   4.x exposes and use the non-deprecated one in the dictConfig string.
3. Delete the `importorskip` at `tests/test_logging.py:344` — the dependency is now guaranteed
   present in `dev`, so the JSON formatter path must actually run in CI.

#### 0.4 — Parenthesize the except clause

`logging.py:991`: `except TypeError, ValueError:` → `except (TypeError, ValueError):`. See the
Python-version note above. (This line moves into `reflection.py` as part of 0.1 — apply the
parenthesized form there.)

**Phase 0 exit criteria:** validation suite green; `grep -rn "_format_arguments\|_resolve_variables"
packages/` returns nothing; `AppLogger.initialize(use_json=True)` works in a test without an
`importorskip`.

---

### Phase 1 — Rich replaces coloredlogs

**Motivation (why this is more than a colour swap).** The current integration is architecturally
wrong: `AppLogger.initialize` builds a full `dictConfig`, and then `_try_enable_coloredlogs`
(`logging.py:937-956`) calls `coloredlogs.install()`, which *installs its own handler on the root
logger*, partially overriding the config that was just applied. Rich's `RichHandler` is an ordinary
`logging.Handler` and goes **inside** the dictConfig, so there is exactly one place that decides
handler wiring. Rich additionally gives you `rich.traceback` (exception rendering with source
context), correct non-TTY degradation, and markup in log messages.

#### 1.1 — Handler selection

Console handler is chosen by the **already-existing** `config.enable_color and config.isatty`
signal (`LoggingConfig.defaults()`, `logging.py:199-236`). No new switch is introduced.

- `use_json=True` → JSON formatter on a plain `StreamHandler`. **JSON wins over Rich** — machine
  output must never be decorated. Assert this precedence in a test.
- else `enable_color and isatty` → `RichHandler`
- else → plain `StreamHandler` with the existing `config.fmt` format string

The **file handler is never a RichHandler.** It keeps `logging.FileHandler` with the full
`_DEFAULT_FORMAT`/`_OTEL_FORMAT` string. ANSI codes and Rich's column wrapping in a log file are a
regression. This is the single most important detail in this phase.

#### 1.2 — Format strings

`RichHandler` renders its own time, level, and path columns and uses the formatter's output as the
*message body only*. So the console handler needs a **new, shorter** format that omits everything
Rich already provides. Add alongside the existing constants in `logging.py`:

```python
_RICH_FORMAT = "%(caller)s [svc=%(service)s env=%(env)s] %(message)s"
_RICH_OTEL_FORMAT = (
    "%(caller)s [svc=%(service)s env=%(env)s "
    "trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s"
)
```

`_DEFAULT_FORMAT` and `_OTEL_FORMAT` stay exactly as they are for the file and plain-stream
handlers. `LoggingConfig.build()` currently derives `fmt` from `enable_otel_correlation`
(`logging.py:238-260`); extend that derivation so the *rich* variant is selected on the same
condition. Do not add a new public `LoggingConfig` field for this if it can be derived — but if
derivation makes `build()` convoluted, add `rich_fmt: str` as a proper field and document it.

An explicit user-supplied `fmt=` override must still win for all handler types.

#### 1.3 — Custom log levels need a Rich theme

`RichHandler` styles the level column by looking up `logging.level.<levelname.lower()>` in the
console's theme. commons registers **five levels Rich has never heard of**: `TRACE` (1), `SPAM` (5),
`VERBOSE` (15), `NOTICE` (25), `SUCCESS` (35) — see `AppLogger._register_levels_and_class()`
(`logging.py:836`) and `verboselogs`. Without theme entries they render unstyled.

Define a module-level theme in `logging.py` and pass it to the `Console` that `RichHandler` wraps:

```python
_RICH_THEME = Theme({
    "logging.level.trace":    "dim cyan",
    "logging.level.spam":     "dim",
    "logging.level.debug":    "green",
    "logging.level.verbose":  "blue",
    "logging.level.info":     "bright_white",
    "logging.level.notice":   "bright_blue",
    "logging.level.success":  "bold green",
    "logging.level.warning":  "yellow",
    "logging.level.error":    "bold red",
    "logging.level.critical": "bold white on red",
})
```

This replaces `LoggingConfig.field_styles` / `level_styles`, which are coloredlogs-shaped dicts.
**Decision to make:** either (a) delete those two fields and add a single `theme: Theme | None`
field, or (b) keep them as `dict[str, str]` level→style overrides merged over `_RICH_THEME`. Prefer
**(b)** — it keeps `LoggingConfig` free of a Rich type in its public signature, which matters
because `LoggingConfig` is re-exported from `rn_forge.commons`. Rename `level_styles` semantics in
the docstring accordingly, and drop `field_styles` (Rich has no per-field styling equivalent; the
current default only styles the injected `caller` field, which is now part of the message body).

#### 1.4 — Wiring

In `AppLogger._configure_logging` (`logging.py:847`), the console handler becomes:

```python
handlers["console"] = {
    "()": "rich.logging.RichHandler",
    "level": config.level,
    "formatter": "rich",
    "filters": ["enrich"],
    "console": _build_rich_console(config),   # module-level factory, applies the theme
    "rich_tracebacks": True,
    "markup": False,        # log messages are not trusted markup — see below
    "show_path": True,
    "show_time": True,
    "omit_repeated_times": False,
    "log_time_format": "[%Y-%m-%d %H:%M:%S]",
}
```

**`markup=False` is deliberate.** Log messages interpolate arbitrary values via `BraceLogRecord`
(`logging.py:61-93`); a value containing `[/]` or `[red]` would either crash Rich's markup parser or
inject styling. Keep markup off in the logging path. Markup belongs in `AppConsole` (Phase 2), where
the caller controls the string.

Delete `_try_enable_coloredlogs` and the `import coloredlogs` entirely. Remove the `coloredlogs`
extra from `pyproject.toml`.

#### 1.5 — Traceback installation

Add an `AppLogger.initialize(...)` keyword `rich_tracebacks: bool = True` that, when the RichHandler
path is selected, calls `rich.traceback.install(show_locals=False, suppress=[...])` once (guard with
the existing initialization idempotency lock — `AppLogger.initialize` is already documented as
idempotent, and `traceback.install` must not be called repeatedly). `show_locals=False` by default:
locals in a traceback routinely contain credentials.

#### 1.6 — Tests

`tests/test_logging.py` (938 lines) is the largest test file and has coloredlogs-specific
assertions. Rework:

- Delete every coloredlogs assertion and the `importorskip("coloredlogs")` guards.
- Add: handler-selection matrix — assert the concrete handler class on the root logger for each of
  the four combinations of `(use_json, enable_color and isatty)`, including the
  **`use_json=True` beats colour** precedence case.
- Add: file handler is `logging.FileHandler` (never `RichHandler`) even when colour is on, and its
  formatter's `_fmt` is the full `_DEFAULT_FORMAT`.
- Add: every custom level name has a `logging.level.*` key in the resolved theme. Drive this from
  the level list rather than hardcoding, so a future level addition fails the test.
- Add: a log record whose interpolated message contains `[red]` is emitted literally, not styled
  (guards the `markup=False` decision).
- Keep all existing `BraceLogRecord`, `EnrichFilter`, audit-decorator, and OTel-correlation tests
  unchanged — Phase 1 must not alter them.

#### 1.7 — Docs

Rewrite `packages/rn-forge-commons/docs/guides/logging.md` for the Rich backend. Docstrings in
`logging.py` are the mkdocstrings source (`mkdocs.yml` autogenerates `api/logging.md`) — update
`LoggingConfig`'s field docstrings, `AppLogger.initialize`'s Args section, and the module docstring's
bullet list, which currently names coloredlogs.

**Phase 1 exit criteria:** validation suite green; `grep -rn coloredlogs packages/` returns nothing;
running any example from `docs/guides/logging.md` in a terminal shows Rich-formatted output, and
piping it to a file shows clean unstyled text.

---

### Phase 2 — `AppConsole` becomes the tooling output layer

**This phase deletes the entire current contents of `console.py`** (`CLIArgumentParser`,
`BooleanAction`, `KeyValueAction`) and replaces the module with an output facade. The argparse
functionality is not lost — it is superseded by Phase 3's Typer module. Relocate the resulting
facade from commons to tooling before the next commons release. Do Phases 2 and 3 plus relocation
as one migration so consumers never have two canonical import paths.

#### 2.1 — Why this module is the highest-value addition

`rn-forge-agentkit` is the reference consumer and it currently hand-rolls this entire layer in
`/Users/rohitnarayanan/Devel/workspaces/rn-forge/agentkit/src/rn_forge/agentkit/commands/common.py`:
a module-level `Console()` singleton, `emit()` (tri-mode rich/quiet/JSON dispatch), `fail()` (red
error + exit), `_jsonable()` (dataclass/`Path`/nested coercion to JSON-safe values), and three
separate hand-built `rich.table.Table` construction sites
(`global_cmds.py:177`, `project_cmds.py:~208`, `shared_cmds.py:~180` and `~265`). Design the API
below so agentkit can delete `commands/common.py` almost entirely and import from tooling instead.

#### 2.2 — API

New `packages/rn-forge-tooling/src/rn_forge/tooling/console.py`:

```python
class OutputMode(StrEnum):
    RICH  = "rich"    # default: styled, tables, colour
    PLAIN = "plain"   # no styling (explicit override; also what a non-TTY gets)
    QUIET = "quiet"   # suppress everything except explicit quiet_text
    JSON  = "json"    # machine-readable only


class AppConsole:
    """Thin facade over ``rich.console.Console`` with quiet/JSON output modes."""

    def __init__(self, *, mode: OutputMode | None = None, stderr: bool = False,
                 theme: Theme | None = None) -> None: ...
        # mode=None -> RICH when stdout isatty, else PLAIN

    # -- mode -------------------------------------------------------------
    @property
    def mode(self) -> OutputMode: ...
    def set_mode(self, mode: OutputMode) -> Self: ...
    @property
    def rich(self) -> Console: ...        # escape hatch — the underlying Console

    # -- core -------------------------------------------------------------
    def print(self, msg: Any = "", *args: Any, style: str | None = None,
              markup: bool = True) -> None: ...
        # {}-formats msg with args (AppLogger idiom). No-op in QUIET and JSON.

    def emit(self, value: Any, *, quiet_text: str | None = None) -> None: ...
        # JSON  -> self.json(value)
        # QUIET -> print quiet_text unstyled if given, else nothing
        # else  -> self.rich.print(value)   (renders Table/Panel/str/renderables)

    def json(self, value: Any) -> None: ...
        # always emits, even in QUIET; uses JsonUtils.serialize (see 2.3)

    # -- semantic (all {}-formatting, all no-op in QUIET/JSON) -------------
    def success(self, msg: str, *args: Any) -> None: ...   # green
    def info(self, msg: str, *args: Any) -> None: ...
    def detail(self, msg: str, *args: Any) -> None: ...    # dim
    def warning(self, msg: str, *args: Any) -> None: ...   # yellow, -> stderr
    def error(self, msg: str, *args: Any) -> None: ...     # red,    -> stderr
    def fail(self, msg: str, *args: Any, code: int = 1) -> NoReturn: ...
        # error(...) then raise SystemExit(code)

    # -- structures -------------------------------------------------------
    def table(self, *columns: str, rows: Iterable[Sequence[Any]],
              title: str | None = None, **table_kwargs: Any) -> None: ...
        # one-call build+print; non-str cells go through str(). No-op in QUIET.
        # In JSON mode, emits [{column: cell, ...}, ...] instead of a table.

    def diff(self, text: str, *, title: str | None = None) -> None: ...
        # unified-diff text with syntax highlighting; markup disabled

    def rule(self, title: str = "") -> None: ...

    # -- interaction (always uses the real stdin/stdout, ignores QUIET) ----
    def confirm(self, msg: str, *, default: bool = False) -> bool: ...
    def prompt(self, msg: str, *, default: str | None = None,
               password: bool = False) -> str: ...
    def status(self, msg: str) -> AbstractContextManager[None]: ...
        # spinner in RICH mode; a no-op context manager otherwise


console: AppConsole = AppConsole()   # module-level default singleton
```

#### 2.3 — `emit`'s JSON serialization must be fixed, not reused as-is

`AppConsole.json` should route through `JsonUtils.serialize`, but `_json_default`
(`collections.py:895-899`) currently falls back to **`repr(obj)`** for anything non-dataclass. That
turns `Path("/x")` into the string `"PosixPath('/x')"` — which is exactly why agentkit wrote its own
`_jsonable()`. Fix `_json_default` in `collections.py` as part of this phase:

```python
def _json_default(obj: object) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, PurePath):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=repr)
    if isinstance(obj, Decimal):
        return float(obj)
    return repr(obj)          # keep repr as the final fallback
```

Add cases to `tests/test_collections.py` for each. This is a behaviour change to `JsonUtils.serialize`
for `Path`/`Enum`/`datetime` values — it is a strict improvement and no current test asserts the
`repr` form for those types, but confirm that with a grep before committing.

**Confirmed by a second consumer.** agentkit's `commands/base.py::_jsonable` is an independent
reimplementation of exactly this coercion (dataclass → `asdict`, recurse into dict/list/tuple,
`Path` → `str`), written for the same reason. Two consumers landing on the same fix is the
strongest evidence this belongs in commons; `_jsonable` is deleted outright when agentkit adopts
`AppConsole`.

#### 2.4 — Design notes

- **`fail` raises `SystemExit`, not `typer.Exit`.** This keeps `console.py` free of any Typer
  import, so the output layer is usable from a plain script, a Django management command, or a
  pytest run. Typer/Click handle a bare `SystemExit` correctly.
- **`warning`/`error` go to stderr.** Construct a second lazily-initialized
  `Console(stderr=True)` internally rather than making callers manage two `AppConsole` instances.
- **`markup=True` is the default here** (unlike the logging handler) because the caller controls the
  format string. But `diff()` and `table()` cell rendering must force `markup=False` — diff text and
  data values are untrusted.
- **`table()` in JSON mode emits rows, not a table.** This is what makes agentkit's
  `if options(ctx)["json"]: emit(ctx, rows); return` boilerplate disappear at all four call sites.
- **Do not** add a `Progress` wrapper beyond `status()`. Rich's `Progress` API is good and varied;
  wrapping it thinly loses more than it saves. Point people at `console.rich` in the docstring.

#### 2.5 — Tests

New `packages/rn-forge-tooling/tests/test_console.py`:

- Mode dispatch matrix: for each of the four `OutputMode` values, assert what `print`, `emit`,
  `json`, `success`, `table` do and do not write. Use `Console(file=StringIO(), width=...)` via the
  `AppConsole(...)` constructor or by monkeypatching `console.rich.file` — pin an explicit `width`
  so wrapping is deterministic across terminals.
- `emit(value, quiet_text=...)` in QUIET emits only `quiet_text`; in QUIET with no `quiet_text`,
  emits nothing.
- `table()` in JSON mode emits a JSON array of objects keyed by column name.
- `fail()` raises `SystemExit` with the given code and writes to stderr.
- `{}`-formatting works and a value containing `[red]` in `diff()`/`table()` is not styled.
- `json()` handles `Path`, `Enum`, `datetime`, `set`, `Decimal`, and a nested dataclass.

#### 2.6 — Docs

- Add tooling `docs/api/console.md` content pointing mkdocstrings at the new symbols.
- Add a tooling guide `docs/guides/console.md` and a nav entry under Guides, covering the
  quiet/JSON tri-mode pattern with a worked example.

---

### Phase 3 — Tooling `cli.py`: Typer replaces `CLIArgumentParser`

#### 3.1 — API

New `packages/rn-forge-tooling/src/rn_forge/tooling/cli.py`:

```python
class LogLevel(StrEnum):
    """CLI-facing log level names. Values are lowercase for clean --help output."""
    CRITICAL = "critical"; ERROR = "error"; SUCCESS = "success"
    WARNING  = "warning";  NOTICE = "notice"; INFO = "info"
    VERBOSE  = "verbose";  DEBUG  = "debug";  SPAM = "spam"; TRACE = "trace"

    def to_int(self) -> int: ...   # -> AppLogger.<LEVEL>, replaces the _LOG_LEVELS dict


# Reusable Annotated option types — the point of the module.
LogLevelOption = Annotated[LogLevel, typer.Option("--log-level", "-ll", ...)]
LogFileOption  = Annotated[Path | None, typer.Option("--log-file", "-lf", ...)]
QuietOption    = Annotated[bool, typer.Option("--quiet", "-q", ...)]
JsonOption     = Annotated[bool, typer.Option("--json", ...)]


def build_app(
    name: str,
    help: str | None = None,
    *,
    add_log_options: bool = True,
    add_output_options: bool = True,
    default_log_level: LogLevel = LogLevel.VERBOSE,
    **typer_kwargs: Any,
) -> typer.Typer:
    """Return a Typer app whose root callback wires --log-level/--log-file into
    AppLogger.initialize() and --quiet/--json into the AppConsole singleton."""


def parse_key_values(values: Sequence[str] | None) -> dict[str, str]:
    """Parse ``["a=1", "b=2"]`` into ``{"a": "1", "b": "2"}``.

    Raises typer.BadParameter on a pair without '='. Replaces KeyValueAction;
    use with ``Annotated[list[str], typer.Option("--env")]``.
    """


def parse_overrides(values: Sequence[str] | None) -> dict[str, Any]:
    """Parse ``["a.b=1", "c=[1,2]"]`` into a NESTED mapping with typed scalars.

    The dotted-path, JSON-or-TOML-scalar sibling of parse_key_values, for
    ``--set dotted.key=value`` CLI overrides that feed a config merge layer.
    """
```

**`parse_overrides` is required by both agentkit and taskkit** — agentkit's
`core/config.py::parse_cli_overrides` is the reference implementation (dotted-path nesting, JSON
scalar parse falling back to a TOML scalar parse, falling back to the raw string; raises on a
missing `=`, an empty key, or a path that collides with an existing scalar). Port it here, keep
`parse_key_values` as the flat/untyped variant, and make the docstrings cross-reference each other
so the next reader picks the right one. `parse_overrides` pairs with `DictUtils.merge`'s
`overrides` layer (Phase 14).

#### 3.2 — What `build_app`'s root callback must do

Mirror agentkit's `cli.py:23-38` and `commands/common.py:26-46`, which is the proven shape:

1. Reject `--quiet` together with `--json` via `typer.BadParameter` (they are contradictory).
2. `console.set_mode(OutputMode.JSON if json else OutputMode.QUIET if quiet else None)`.
3. `AppLogger.initialize(root_logger_name=name.replace(" ", "_").lower(), level=log_level.to_int(), file=log_file)`.
4. Store the resolved flags on `ctx.obj` as a small frozen dataclass (`CliOptions`) — **not** a bare
   dict, so it types cleanly under strict Pyright. agentkit uses `dict[str, bool]` and pays for it
   with casts. Expose `def options(ctx: typer.Context) -> CliOptions` that reads
   `ctx.find_root().obj`.
5. Set `no_args_is_help=True` and `pretty_exceptions_show_locals=False` as defaults in
   `typer_kwargs` (overridable). `show_locals=False` for the same credential-leak reason as Phase 1.

Also provide `command_options(ctx, *, quiet=False, json_output=False)` — agentkit needs the flags to
work both before and after the subcommand name, which the root callback alone cannot do. Port it.

#### 3.3 — Removals

Delete `CLIArgumentParser`, `BooleanAction`, `KeyValueAction`, and the `_LOG_LEVELS` dict. Update
`src/rn_forge/commons/__init__.py`: drop the removed argparse names and do not expose their Typer
replacements. Add `AppConsole`, `OutputMode`, `console`, `LogLevel`, `build_app`,
`parse_key_values`, `parse_overrides` and `CliOptions` to
`src/rn_forge/tooling/__init__.py` instead.

Typer's native `bool` parameter handling (`--flag` / `--no-flag`) fully replaces `BooleanAction`; no
wrapper is needed. Say so in the module docstring so the next person doesn't re-add one.

**Bump the version to `0.3.0` here** and note the removals in the README / docs index.

#### 3.4 — Tests

New `packages/rn-forge-tooling/tests/test_cli.py`, using `typer.testing.CliRunner`:

- `LogLevel.to_int()` maps every member to the right `AppLogger` constant (drive from the enum, not
  a hardcoded list).
- `build_app` produces an app whose `--help` lists the log and output options; `add_log_options=False`
  and `add_output_options=False` omit them.
- `--quiet --json` together exits non-zero with a usage error.
- A command reading `options(ctx)` sees the right `CliOptions` for flags given before *and* after
  the subcommand name.
- `--log-level debug` results in the root logger being at `DEBUG` (assert on
  `logging.getLogger().level`, and reset logging state between tests — `tests/conftest.py` is only
  10 lines today and will likely need a logging-reset fixture; check whether
  `tests/test_logging.py` already has one to reuse).
- `parse_key_values` happy path, empty input, and the missing-`=` error.

#### 3.5 — Docs

New tooling `docs/api/cli.md` + nav entry and `docs/guides/cli.md` + nav entry. Update the commons
quickstart to remove `CLIArgumentParser` and direct CLI users to `rn-forge-tooling`.

---

### Phase 4 — `dacite` replaces the coercion block in `dataclasses.py`

#### 4.1 — What is being replaced

`_coerce_field_value`, `_coerce_sequence`, `_coerce_dict`, `_coerce_union`, and
`_coerce_nested_dataclass` (`dataclasses.py:319-405`, ~90 lines). Only these. `as_dict`, `to_json`,
`to_yaml`, `from_json`, `from_yaml`, `__init_subclass__`, `__str__`, `__repr__`, and
`_dataclass_to_dict`/`_convert_value` are untouched.

#### 4.2 — Two behavioural details that will break tests if missed

Read `dataclasses.py:319-405` before writing any code. The existing coercion is:

1. **Structural, not scalar.** It rebuilds nested dataclasses and recurses into
   `list`/`set`/`tuple`/`dict`/union annotations. It never converts `"5"` to `5`. dacite matches
   this — it structures, it does not coerce scalars. Good.
2. **Lenient.** `_coerce_field_value`'s final `return value` passes an unmatched value through
   *unchanged*, and `_coerce_union` falls through to `return cast(Any, value)`. So today, putting a
   `str` in an `int`-annotated field silently succeeds. **dacite type-checks by default and would
   raise `WrongTypeError`.** To preserve behaviour you must pass
   `dacite.Config(check_types=False)`.

**Decision required, flag it rather than deciding silently:** `check_types=False` preserves today's
semantics exactly (recommended for this migration — it keeps the phase a pure refactor).
`check_types=True` is arguably *better* behaviour and would catch real config bugs, but it will fail
existing tests in `tests/test_dataclasses.py` and is a breaking change for consumers.
**Default to `check_types=False`**, and expose it so a subclass can opt in:

```python
class DataclassMixin:
    #: dacite configuration; override in a subclass to enable strict type checking.
    __dacite_config__: ClassVar[dacite.Config] = dacite.Config(check_types=False)
```

#### 4.3 — The `from_dict` hook regression

`_coerce_nested_dataclass` (`dataclasses.py:395-405`) calls a nested dataclass's own
`from_dict` classmethod when one exists, falling back to `annotation(**value)`. dacite structures
nested dataclasses itself and will **not** call a subclass's overridden `from_dict`.

Before switching, `grep -rn "def from_dict" packages/` to find any subclass that overrides it. If
none exists (likely), proceed and add a test asserting a nested override is *not* called, documenting
the intentional change. If one does exist, register a dacite `type_hooks` entry for that type.

#### 4.4 — Implementation

`DataclassMixin.from_dict` becomes roughly:

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> Self:
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls.__name__} is not a dataclass — DataclassMixin requires @dataclass")
    try:
        return dacite.from_dict(data_class=cls, data=data, config=cls.__dacite_config__)
    except dacite.DaciteError:
        _LOGGER.exception("DataclassMixin.from_dict failed | cls={} | keys={}",
                          cls.__name__, sorted(data))
        raise
```

Keep the existing debug log of ignored unknown keys — dacite ignores extras silently (matching
today's behaviour), but that log line is useful. Compute it as
`sorted(set(data) - {f.name for f in dataclasses.fields(cls)})` before the call.

Keep the `TypeError` for a non-dataclass `cls`: it is asserted by an existing test and dacite would
raise a different error type.

Delete all five `_coerce_*` functions and the now-unused `get_origin`/`get_args`/`get_type_hints`/
`UnionType`/`Union` imports.

#### 4.5 — Tests

`tests/test_dataclasses.py` (396 lines) is the specification here. **Do not rewrite it — run it
against the dacite implementation and fix only what genuinely changed.** Then add:

- A field typed `int` receiving `"5"` still passes through unchanged (locks in `check_types=False`).
- `__dacite_config__ = dacite.Config(check_types=True)` on a subclass makes that case raise.
- `Optional[NestedDataclass]` from `None` and from a dict.
- `dict[str, NestedDataclass]` and `list[NestedDataclass]` round-trip via `to_dict`/`from_dict`.
- A `frozen=True` nested dataclass (the `rn-forge-django` settings facade uses frozen dataclasses;
  even though Django is out of scope, `Process` in `subprocess.py` is a `DataclassMixin` and its
  round-trip must keep working — `tests/test_subprocess.py` covers that, so run it too).

---

### Phase 5 — Small, high-certainty swaps

Three independent changes; each can be its own commit.

#### 5.1 — `mergedeep` for `DictUtils.merge` — **SUPERSEDED BY PHASE 14, DO NOT DO THIS**

> The agentkit/taskkit survey (2026-09-04) found that agentkit's `ConfigMerger` needs two things
> `mergedeep` cannot express: **per-key provenance** (which layer supplied each dotted key) and
> **per-path append-vs-replace list strategy**. Swapping in `mergedeep` here and then re-growing
> those features in Phase 14 would be churn. **Skip 5.1 entirely; go straight to Phase 14**, which
> keeps the hand-rolled merge and extends it. The deep-copy analysis below is still accurate and is
> the reason Phase 14 keeps `copy.deepcopy` — read it, then read Phase 14.

Original 5.1 analysis follows, retained because Phase 14 depends on its deep-copy reasoning:

Replace the bodies of `DictUtils.merge`, `_merge_override`, and `_merge_key`
(`collections.py:280-340`) with `mergedeep.merge(target, *overrides, strategy=Strategy.REPLACE)`.

**Preserve three behaviours the current code has** — assert each in a test:

1. `merge` mutates and returns `target` (chained by `Config.__init__`, `collections.py`, and
   `config.py:120`). `mergedeep.merge` also mutates-and-returns the destination — verify.
2. Empty/`None` override dicts are skipped, not merged. Filter before the call.
3. **Override values are deep-copied** (`_merge_key`'s `copy.deepcopy(value)`), so the merged result
   shares no references with the overrides. `mergedeep` does **not** deep-copy. This matters:
   `Config` merges parsed YAML documents and then mutates the result during reference resolution.
   Either `copy.deepcopy` each override before passing it to `mergedeep`, or drop the guarantee and
   prove nothing depends on it. **Deep-copy — do not drop the guarantee.** Add a test that mutating
   a nested value in the merged result leaves the override dict untouched.

Given (3), the honest cost/benefit is thinner than it first looks. If preserving deep-copy semantics
makes the wrapper as long as the code it replaces, **skip 5.1 and say so** — that is an acceptable
outcome, not a failure. (The 2026-09-04 survey settled this: it *is* skipped. See Phase 14.)

#### 5.2 — `pkgutil.resolve_name` for `AppUtils.import_string`

`AppUtils.import_string` (`utils.py:326-395`, ~50 lines) reimplements stdlib
`pkgutil.resolve_name` (3.9+). Replace the body; keep the signature, the `ImportError` contract, and
the logging.

Two differences to handle:

- `resolve_name` supports both `pkg.mod:attr` and `pkg.mod.attr`. That is a superset — fine, and
  worth documenting in the docstring as a new capability.
- **`resolve_name` has no `package` parameter and does not support relative imports.** The current
  function accepts `package` and handles a leading `"."`. Keep the relative branch on the existing
  `importlib.import_module(module_path, package)` path and delegate to `resolve_name` only for the
  absolute case. Do not silently drop the relative-import support — `tests/test_utils.py` covers it.

Normalize the raised exceptions: `resolve_name` raises `ImportError` for a bad module and
`AttributeError` for a missing attribute; the current contract is `ImportError` for both. Wrap.

#### 5.3 — New `PathUtils.atomic_write` — **see Phase 10 before implementing**

Not a swap — a gap. agentkit implements atomic write-and-replace in
`/Users/rohitnarayanan/Devel/workspaces/rn-forge/agentkit/src/rn_forge/agentkit/core/io.py::atomic_write`
(mkstemp in the destination directory, `fsync`, permission preservation or explicit mode,
`os.replace`, temp cleanup on failure). `PathUtils.write_file` (`utils.py:157`) does a plain
non-atomic write.

**Do not port agentkit's copy verbatim** — taskkit has a second, subtly different implementation of
the same function, and the correct commons version is the union of the two. Phase 10 specifies it.
The signature stays as below:
`PathUtils.atomic_write(content: str | bytes, path: str | Path, *, mode: int | None = None, encoding: str = "utf-8") -> Path`.
Keep `write_file` as-is; do not make it atomic by default (a surprising behaviour change, and
atomic write fails on cross-device temp dirs in ways plain write does not).

Tests: bytes and str content; parent directories created; existing file's permission bits preserved;
explicit `mode` applied; no `.tmp` leftovers in the directory after a simulated mid-write failure.

---

### Phase 6 — GATED: OmegaConf for `config.py`

> **Outcome (2026-09-07): gate failed, abandoned.** No `ConfigOmega` branch was written — the
> structural analysis below made the outcome clear without needing to build and then discard a
> prototype. Estimated cost of the four non-negotiable pieces: an `__extends__` pre-merge pass
> handling transitive extends (~40-60 lines), a syntax-translation pass rewriting `@{}`/`#{}` into
> OmegaConf's `${}` form since OmegaConf only understands the latter (~20-30 lines), a **post**-pass
> to flatten `#{}`'s list-splice semantics back in — OmegaConf has no equivalent, it would substitute
> the referenced list as a single nested element rather than splicing it inline, so a sentinel-tagged
> pre-pass plus a post-resolution walk is needed (~30-50 lines), and dotted-index path translation
> between `DictUtils.get`'s `"a.0.b"` form and OmegaConf's `.`/`[0]` form (~15-20 lines). That is
> 100-160+ lines of pre/post glue on top of the `antlr4-python3-runtime` dependency risk already
> flagged — well past the ~80-line threshold, and no simplification over the ~245-line hand-rolled
> resolver it would replace. The hand-rolled resolver in `config.py` is unchanged.

**Do not start this phase without re-reading this gate.** Phases 0-5 stand on their own; this one
can be abandoned with no loss.

#### 6.1 — The gate

`config.py` is 441 lines with 453 lines of passing tests. OmegaConf genuinely subsumes the `${}`
interpolation machinery (`_expand_value_placeholders`, `_substitute_value_ref`,
`_resolve_whole_string_ref`, the depth guards). But it does **not** provide:

- **`__extends__` inheritance** (`config.py:196-215`). Needs a pre-merge pass over the raw dicts.
- **`@{path}` / `#{path}`** dict and list references. These map onto ordinary OmegaConf
  interpolation *except* for `#{}`'s **list flattening** — a `#{}` reference inside a list splices
  the referenced list's elements into the parent (`config.py:229-233`). OmegaConf has no equivalent;
  it needs a post-resolution pass.
- **`dict` return types.** OmegaConf works in `DictConfig`, so `Config.get()` must
  `OmegaConf.to_container(...)` on the way out to keep the current contract, and strict Pyright
  around `DictConfig` is `Any`-ish.

It also pins `antlr4-python3-runtime`, which has historically caused resolution conflicts in
workspaces that pull antlr transitively.

**Procedure — follow this order:**

1. **First**, port `tests/test_config.py` to run against a new `ConfigOmega` implementation *without
   deleting the existing `Config`*. Every one of the 453 lines must pass unmodified. The test file is
   the behavioural contract; changing a test to make the new implementation pass is the failure mode
   to avoid.
2. If `__extends__` + `#{}` flattening + the `dict` return contract can all be satisfied with
   pre/post passes totalling **under ~80 lines**, the migration is a win: swap `Config`'s internals,
   delete `ConfigOmega`, delete the old resolver, done.
3. **If it takes more than that, stop.** Delete the branch, keep the hand-rolled resolver, and
   report back that the gate failed and why. That is the correct outcome, not a shortfall.

#### 6.2 — If the gate passes

- `Config.__init__` keeps its exact signature (`*paths`, `config_type`, `resolve`). File discovery
  (`rglob`, sorted, deep-merge) stays as-is — OmegaConf replaces only `resolve_references()` and
  everything under `# -- reference resolution (private)`.
- `Config.get(key_path, default=...)` → `OmegaConf.select(cfg, key_path, default=default)`, then
  `to_container` if the result is a container. Note OmegaConf uses `.` for paths and `[0]` for list
  indices, whereas `DictUtils.get` uses `.0` — **the existing dotted-index form must keep working**;
  translate the path before selecting.
- `Config.set` can stay on `DictUtils.set` against the plain-dict backing store.
- Keep the `RecursionError` on circular references. OmegaConf raises
  `InterpolationResolutionError`/`GrammarParseError` for cycles — catch and re-raise as
  `RecursionError` with the current message so the contract holds.
- Escape-hatch property: `Config.omega -> DictConfig`.

#### 6.3 — Docs

`docs/guides/config.md` documents the `${}`/`@{}`/`#{}`/`__extends__` syntax. If the gate passes,
note which forms are now OmegaConf-native and which remain commons extensions — future readers need
to know which half of the syntax has upstream documentation.

---

## Part B — New capability carried over from the cims survey

Two items from the cims-backend extraction survey are genuinely framework-agnostic and belong in
commons. Everything else in that survey was Django/DRF-shaped and is out of scope here.

### Phase 7 — Environment fail-fast guards

No new dependencies. Small, self-contained; slot it in anywhere after Phase 0.

**Source pattern.** cims's `config/settings/production.py` declares a `required_environment` set and
fails fast at import time with `ImproperlyConfigured` if anything is unset, plus explicit
"this variable must not still be the insecure default" checks. That shape is generic and worth
having; the Django exception type is not.

**Destination — a decision that differs from the original survey.** The cims survey proposed putting
these in `config.py`. **Put them on the existing `Environment` class in `utils.py` instead.** They
are environment-variable helpers, `Environment` already owns `get`/`set`/`is_enabled`/`get_all`, and
`config.py` may be rewritten wholesale by Phase 6 — keeping these out of that file avoids a
needless collision.

```python
class Environment:
    ...
    @staticmethod
    def require(*names: str) -> dict[str, str]:
        """Return the values of *names*, raising if any is unset or blank.

        Raises:
            AppException: One or more variables are unset or empty. The message
                lists every missing name at once (not just the first), so a
                misconfigured deployment surfaces all problems in one run.
        """

    @staticmethod
    def forbid(name: str, *forbidden: str, message: str | None = None) -> None:
        """Raise if the value of *name* equals any of *forbidden*.

        Intended for "the insecure default is still in place" guards, e.g.
        ``Environment.forbid("SECRET_KEY", "change-me")``.
        """
```

Design notes:

- **`AppException`, never `ImproperlyConfigured`** — commons stays Django-free. A Django-flavoured
  wrapper that re-raises as `ImproperlyConfigured` belongs in `rn-forge-django`, not here.
- Use `AppException.check(...)` per convention 3, or raise directly if the aggregated-message
  requirement makes `check` awkward — aggregating all missing names matters more than the idiom.
- `require` returning the resolved values (rather than `None`) lets a caller write
  `cfg = Environment.require("DB_URL", "SECRET_KEY")` and use the result, which is strictly more
  useful than a bare assertion.
- Treat a set-but-empty/whitespace-only variable as missing — reuse `AppUtils.is_empty`.

**Tests.** `tests/test_utils.py` additions, using `monkeypatch.setenv`/`delenv`: all-present returns
the mapping; one missing raises; **several missing all appear in one message**; empty-string counts
as missing; `forbid` matches and does not match; custom `message` is used.

### Phase 8 — `resilience.py`: circuit breaker + retrying HTTP client

> **Outcome (2026-09-07): built per the §A.3 redesign, not the original sync spec below.** The
> library search §A.3 asked for: `purgatory` (async-native, per-key named circuits, event hooks —
> the maintained successor to `aiobreaker`, which itself only exists because `pybreaker`'s
> threading-based model doesn't fit async) for the breaker, and `stamina` for retry — its *backoff
> hook* callable (`(exc) -> bool | float | timedelta`) turned out to be exactly the shape
> `Retry-After` support needs, confirmed by prototype. The token-bucket rate limiter is hand-rolled,
> as anticipated — nothing on PyPI clamps from `X-RateLimit-Remaining`/`X-RateLimit-Reset` headers.
> See `src/rn_forge/commons/resilience.py`'s module docstring for the full record and
> `tests/test_resilience.py` (20 cases, `httpx.MockTransport`) for validation. Concretely this means:
> `ResilientAsyncHttpClient` (async throughout, not the sync client speced below), breakers keyed by
> an optional `key=` argument to `request`/`get`/`post`/... (falling back to the client's `name`),
> `clock`/`sleep` constructor-injectable on the rate limiter for deterministic tests, and
> `CircuitOpenError` (an `AppException`) wrapping purgatory's `OpenedState`. The `resilience` extra is
> `purgatory>=3.0.1`, `stamina>=25.2.0`, `httpx>=0.28` — `pybreaker`/`tenacity` were never added. The
> sync-client spec in 8.1-8.4 below is retained for its still-accurate design notes (the metrics seam,
> the optional-import guard, "don't build async speculatively" — inverted here since async *is* the
> real requirement) but is not what got built.
>
> **Amended by [`web-library-plan.md`](./web-library-plan.md) §A.3 — read that first.** A second
> independent implementation (intellibench's async Azure DevOps client) shows this design misses five
> things: it is async, breakers are per-key rather than per-client, `clock`/`sleep` must be injectable
> for testable timing, retry must honour `Retry-After`, and a token-bucket limiter clamped from
> `X-RateLimit-Remaining` belongs beside it. `pybreaker`'s model does not fit an async call path
> cleanly, so the library choice below is reopened: evaluate maintained async-capable breakers, and
> consider `stamina` (over `tenacity`) for retry, before writing anything by hand. Whatever survives
> that search still gets the thin facade specified here.
>
> **This phase stays in commons.** "It is HTTP, so it belongs in `rn-forge-web`" was considered and
> rejected: breakers and retries are transport-agnostic (workers, CLIs and the Azure adapters need
> them without serving HTTP), and `rn-forge-azure` depends on commons only — moving resilience to web
> would make an Azure Blob adapter depend on an ASGI/problem-details package. `parse_retry_after` and
> transient-status classification land here too. The one HTTP concern that goes the other way is
> parsing an upstream `application/problem+json` body, which is `rn-forge-web` §2.5 and is a pure
> function over a mapping, so this module can call it without a dependency arrow being created.

New optional extra. This was flagged in the cims survey as the single highest-value extraction from
that codebase: ~50 lines, zero domain coupling, and used consistently by every integration client
in cims.

**Why this isn't just stdlib.** The Python standard library has no circuit breaker and no
retry-with-backoff primitive — `urllib3.util.Retry` covers static retry counts for its own transport
only, and nothing in stdlib tracks failure-rate state across calls to trip/reset a breaker. `tenacity`
(retry policies, backoff/jitter strategies, stop conditions) and `pybreaker` (breaker state machine,
listeners) are real capability, not a stdlib feature reinvented behind a wrapper — which is why this
phase is a thin facade over both rather than a "does stdlib already do this" swap like Phases 4/5.

**Source:** cims `apps/common/resiliency.py` (`retryable`, `breaker`, `BreakerListener`,
`ResilientHttpClient`). **Destination:** new
`packages/rn-forge-commons/src/rn_forge/commons/resilience.py`. **Extra:** `resilience` =
`pybreaker`, `tenacity`, `httpx`.

#### 8.1 — API

```python
def retryable(exc: BaseException) -> bool:
    """Return True for transient httpx failures (connect errors, timeouts, 5xx)."""


def breaker(
    name: str,
    *,
    fail_max: int = 5,
    reset_timeout: int = 60,
    on_state_change: Callable[[str, str, str], None] | None = None,
) -> pybreaker.CircuitBreaker:
    """Build a named circuit breaker.

    ``on_state_change(name, old_state, new_state)`` replaces cims's hardcoded
    OTel-counter listener. Defaults to logging via AppLogger only.
    """


class ResilientHttpClient:
    """httpx client wrapped in a per-instance circuit breaker and tenacity retry."""

    def __init__(
        self,
        base_url: str,
        *,
        name: str,
        stop_after_attempt: int = 3,
        wait_initial: float = 0.5,
        wait_max: float = 8.0,
        fail_max: int = 5,
        reset_timeout: int = 60,
        on_state_change: Callable[[str, str, str], None] | None = None,
        **httpx_kwargs: Any,
    ) -> None: ...

    @property
    def client(self) -> httpx.Client: ...      # escape hatch
    @property
    def breaker(self) -> pybreaker.CircuitBreaker: ...
    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response: ...
    def get / post / put / patch / delete(...)  # thin passthroughs
    def close(self) -> None
    def __enter__ / __exit__                    # context-manager support
```

#### 8.2 — Design notes

- **Keep `retryable` httpx-specific for v1.** The cims version is, and generalizing across HTTP
  clients from one example produces the wrong abstraction. Expose the exception-type tuple as a
  module-level constant consumers can extend, rather than burying it in the function body.
- **`on_state_change` is the metrics seam** (convention 2). Default it to an `AppLogger` warning on
  every transition; do not import OpenTelemetry.
- **Optional-import guard.** `resilience.py` must not be imported by
  `src/rn_forge/commons/__init__.py` at module scope, or `import rn_forge.commons` breaks for anyone
  without the `resilience` extra. Follow whatever pattern `excel.py`/`pandas.py` already use for
  their optional dependencies — check those two files first and match them exactly rather than
  inventing a third convention.
- Add a `ResilientHttpClient` **async** variant only if a consumer needs one. Do not build it
  speculatively.

#### 8.3 — Tests

New `tests/test_resilience.py`, gated with `pytest.importorskip` like the pandas/openpyxl tests. Use
`httpx.MockTransport` (preferred — no extra dependency) or `respx`:

- A 500 followed by a 200 retries once and returns the 200.
- A connect timeout retries up to `stop_after_attempt` then raises.
- A 4xx does **not** retry (it is not transient) — this is the case most likely to be got wrong.
- `fail_max` consecutive failures open the breaker; the next call raises
  `pybreaker.CircuitBreakerError` **without** issuing an HTTP request (assert on the mock transport's
  call count).
- `on_state_change` is invoked with `(name, "closed", "open")` on trip.
- Context-manager use closes the underlying httpx client.

#### 8.4 — Docs

New `docs/api/resilience.md` + nav entry; a section in `docs/guides/` (either a new
`guides/resilience.md` or an addition to an existing guide) showing the breaker + retry wiring and
the `on_state_change` metrics seam.

### Phase 8b — `messaging.py`: the `MessageBus` protocol

> **Added by [`web-library-plan.md`](./web-library-plan.md) §A.2**, moved out of the django plan's
> Phase 10 so that `rn-forge-azure` can implement a Service Bus adapter without depending on Django,
> and so a worker or CLI can publish without importing a web framework. Messaging is not HTTP-shaped,
> which is why this is commons and not `rn-forge-web`.

**Sources.** cims `apps/messaging/bus.py` (`MessageBus`, `AzureServiceBus`, `InMemoryMessageBus`) and
its `HANDLERS` registry in `apps/messaging/consumer.py`. **Destination:** new
`src/rn_forge/commons/messaging.py`. **No new dependency** — protocols, a dict and a list.

```python
class MessageBus(Protocol):
    def publish(self, destination: str, event: Mapping[str, Any]) -> None: ...


class AsyncMessageBus(Protocol):
    async def publish(self, destination: str, event: Mapping[str, Any]) -> None: ...


class InMemoryMessageBus:
    """Records published events in memory. The test double, and the local default."""

    @property
    def published(self) -> Sequence[tuple[str, Mapping[str, Any]]]: ...
    def clear(self) -> None: ...


class HandlerRegistry:
    """Maps a message type to its handler. Instantiable — no module-level registry."""

    def register(self, message_type: str, handler: Callable[[Mapping[str, Any]], None]) -> Self: ...
    def handler_for(self, message_type: str) -> Callable[[Mapping[str, Any]], None] | None: ...
```

**Design notes.**

- **Both a sync and an async protocol**, for the same reason the web package ships two idempotency
  protocols: a Service Bus adapter over the async SDK and a Django-side sync publisher are both real,
  and a single protocol returning `Awaitable[None] | None` is a lie in the type system.
- **`HandlerRegistry` is instantiable**, replacing cims's module-level `HANDLERS` dict and `@register`
  decorator — two registries must be able to coexist in one process, and a test needs a clean one.
  `register` returns `Self` for chaining, matching the commons idiom.
- **No cloud implementation here, and no envelope format.** `rn-forge-azure` Phase 4 implements Service
  Bus; the CloudEvents envelope builder stays deferred (it has no consumer until the django plan's
  Phase 10 gate passes). This module is the protocol plus the in-memory double, nothing more.
- **No delivery guarantees are implied.** `publish` is fire-and-forget from the protocol's point of
  view; transactional-outbox semantics belong to the caller (the django plan's Phase 10). Say so in the
  module docstring, or someone will assume this interface is exactly-once.
- Curated re-export in `src/rn_forge/commons/__init__.py`, per repo convention. No optional-import
  guard needed — there is no optional dependency.

**Tests.** New `tests/test_messaging.py` (`unit`): `InMemoryMessageBus` records destination and event
in order; `clear` empties it; the published sequence is a copy, not the live list; `HandlerRegistry`
round-trip, unknown type returns `None`, re-registering the same type (decide and test whether it
raises or replaces — pick raise), chaining returns the same instance; two registries are independent;
both protocols are satisfied by the in-memory bus (`isinstance` if `runtime_checkable`, else a Pyright
assignment test).

**Docs.** New `docs/api/messaging.md` + nav entry.

---

### Phase 8c — `secrets.py`: the `SecretStore` protocol

> **Added by [`web-library-plan.md`](./web-library-plan.md) §A.2.** `rn-forge-azure` Phase 2 (Key
> Vault) is blocked on this module. Commons rather than web, because a CLI or a worker needs secrets
> and neither serves HTTP.

**Source.** intellibench `libs/backend/ports/src/intellibuild_ports/secrets.py` — 15 lines, whose
`EnvSecretPort` docstring says outright that "a managed-identity or key-vault-backed adapter replaces
this one, not the port". **Destination:** new `src/rn_forge/commons/secrets.py`. **No new dependency.**

```python
class SecretNotFound(AppException):
    """The named secret does not exist in the backing store."""


class SecretStore(Protocol):
    def get_secret(self, key: str) -> str: ...


class AsyncSecretStore(Protocol):
    async def get_secret(self, key: str) -> str: ...


class EnvSecretStore:
    """Reads secrets from the process environment. The local/dev default."""

    def __init__(self, *, prefix: str = "") -> None: ...
```

**Design notes.**

- **A `Protocol`, not an ABC.** intellibench's is an ABC; a library must not require adapters to
  inherit from it — an Azure Key Vault client wrapper should satisfy the protocol structurally.
- **Raise `SecretNotFound`, never return `None`.** A missing secret is a configuration failure that
  should fail fast and loudly at startup; an `Optional` return invites `or "default"`, which is how a
  service silently starts up unauthenticated. Pair this with Phase 7's `Environment.require` in the
  docs — they are the same fail-fast argument.
- **Never cache in the protocol.** Caching policy (TTL, refresh-on-rotation) belongs to the adapter;
  Key Vault charges per call and rotation semantics differ per backend.
- **No `set_secret`.** Nothing in the workspace writes secrets, and an interface that can write is one
  a compromised process can use. Add it when a real consumer needs it.
- `EnvSecretStore(prefix=...)` maps `get_secret("db-password")` to `DB_PASSWORD` — document the exact
  transformation (upper-case, `-` → `_`, prefix prepended), because a guessed mapping is a debugging
  session.

**Tests.** New `tests/test_secrets.py` (`unit`): `EnvSecretStore` hit and miss (miss raises
`SecretNotFound` with the key in the message); prefix applied; the name transformation exactly as
documented; empty-string value counts as missing (same rule as Phase 7's guards); protocol
satisfaction.

**Docs.** New `docs/api/secrets.md` + nav entry, cross-linked from the resilience/config guides.

---

### Phase 8d — `objects.py`: the `ObjectStore` protocol

> **Added by [`web-library-plan.md`](./web-library-plan.md) §A.2.** `rn-forge-azure` Phase 3 (Blob
> Storage) implements it, and the deferred claim-check pattern needs it.

**Source.** intellibench's specified `BlobPort` (`put`/`get`/`delete`/`url_for`) plus cims's Azure Blob
usage. **Destination:** new `src/rn_forge/commons/objects.py`. **No new dependency.**

```python
class ObjectNotFound(AppException):
    """No object exists at the given key."""


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def url_for(self, key: str, *, expires_in: timedelta) -> str: ...


class AsyncObjectStore(Protocol):
    ...  # same five members, async


class InMemoryObjectStore:
    """Dict-backed store for tests. ``url_for`` raises NotImplementedError."""
```

**Design notes.**

- **`url_for` is the member worth arguing about, and it stays.** It returns a time-limited pre-signed
  URL so a client downloads directly instead of streaming bytes through the application — Azure calls
  it a SAS URL, S3 a presigned URL. The concept is portable; the alternative is every consumer
  reinventing a download proxy.
- **`expires_in` is required, not defaulted.** A pre-signed URL with a forgotten expiry is a leak with
  a long tail. Forcing the caller to state it is the whole point.
- **`bytes`, not file objects or paths.** A streaming interface can be added when something needs to
  move a file too large to hold in memory; guessing that shape now, from zero consumers, is how a
  protocol acquires an unusable `IO[bytes]` member.
- **`InMemoryObjectStore.url_for` raises `NotImplementedError`** rather than returning a fake URL — a
  test that passes against a fabricated URL proves nothing.
- Include `exists` even though `get` + catch would do: the claim-check pattern polls for presence, and
  fetching a payload to discover it exists is wasteful on a blob store.

**Tests.** New `tests/test_objects.py` (`unit`): put/get round-trip preserves bytes exactly; `get` on a
missing key raises `ObjectNotFound`; `delete` removes; `delete` on a missing key (decide and test —
idempotent no-op is the better contract for a store); `exists` both ways; `url_for` raises on the
in-memory store; protocol satisfaction for both sync and async.

**Docs.** New `docs/api/objects.md` + nav entry.

---

### Phase 9 — GATED: `StructLogger`, a structlog front-end over `AppLogger`

> **Outcome (2026-09-07): gate passed, built.** All four conditions in 9.1 were validated with a
> working prototype before committing to the module (see `src/rn_forge/commons/structlogger.py`,
> `tests/test_structlogger.py`):
>
> 1. **Custom levels survive.** The blocker found: `structlog.stdlib.LoggerFactory` calls
>    `logging.setLoggerClass()` in its own `__init__`, clobbering `AppLogger`'s registration —
>    confirmed by prototype (a logger obtained afterward was `structlog`'s internal
>    `_FixedFindCallerLogger`, not `AppLogger`). Fix: a custom `logger_factory` calling
>    `AppLogger.get_logger()` directly, never touching `setLoggerClass`. Once that's in place,
>    `structlog.stdlib.BoundLogger._proxy_to_logger(method_name, ...)` calls
>    `getattr(self._logger, method_name)(...)` — i.e. it calls the underlying `AppLogger`'s own
>    `.trace()`/`.spam()`/`.verbose()`/`.notice()`/`.success()` methods by name, which already exist.
>    A `_AppBoundLogger` subclass adding those five one-line methods (mirroring `.info()`'s own
>    definition) was all that was needed — no forking of structlog internals.
> 2. **Facade stays thin.** The processor chain is `[merge_contextvars, _render_event]` — no
>    `ProcessorFormatter`. `_render_event` is the final processor and renders the event dict into a
>    plain `{}`-joined string *before* it reaches `AppLogger`, so the handler's formatter (Rich/JSON/
>    file) never needs to change — a record from `StructLogger` is indistinguishable from one a plain
>    `AppLogger.get_logger(__name__)` call would produce, confirmed by test
>    (`TestSameSink::test_lands_in_same_handler_as_applogger_call`) and by prototype with `use_json=True`
>    and a file handler.
> 3. **Prototyped for real**, not just synthetic: verified against `AppLogger.initialize(use_json=True,
>    file=...)` with the JSON formatter and file handler both active, confirming identical output shape
>    for `StructLogger`- and `AppLogger`-originated records.
> 4. **Not a hard dependency** — `structlog.py` is not imported by `__init__.py`; `import
>    rn_forge.commons` succeeds with the extra absent (test:
>    `test_import_rn_forge_commons_succeeds_without_structlog_named_module`).
>
> One documented constraint survives into the API: call `AppLogger.initialize()` before the *first*
> `StructLogger` log call (not before constructing one — the underlying logger is resolved lazily, on
> first use via `cache_logger_on_first_use=True`), so construction order does not matter, only which
> one logs first.

**Do not start this phase without re-reading this gate.** Phases 0-8 stand on their own; this one
can be abandoned with no loss, same as Phase 6.

#### 9.1 — The gate

`structlog` is not architecturally incompatible with stdlib `logging` — `structlog.stdlib` is
explicitly designed to sit in front of it: `structlog.configure(logger_factory=...)` binds
structlog's context/processor machinery to stdlib `Logger` instances, and
`structlog.stdlib.ProcessorFormatter` lets the *final* rendering step still be an ordinary
`logging.Formatter` on an ordinary `logging.Handler`. So a `StructLogger` facade can give CIMS
context-binding (`log = log.bind(request_id=...)`) and structured key-value/JSON output while every
record still flows through `AppLogger`'s existing `dictConfig` — Rich console, plain file handler,
JSON formatter, `EnrichFilter`'s caller/service/env/OTel fields — unchanged. One sink, structlog
ergonomics on top.

What has to be proven before committing to this, in order:

1. **The verboselogs levels survive the handoff.** `TRACE`/`SPAM`/`VERBOSE`/`NOTICE`/`SUCCESS` are
   not stdlib levels; structlog's `add_log_level` processor and `structlog.stdlib`'s level filtering
   assume the stdlib set. Prototype logging at each custom level through `StructLogger` and confirm
   the level name, numeric value, and Rich theme styling all still land correctly end to end. If this
   requires forking `structlog.stdlib`'s level-handling internals, that is the gate failing.
2. **The facade stays thin.** The point of `StructLogger` is context binding
   (`bind`/`unbind`/`new`) plus `{}`-or-kwarg-style structured fields, delegating rendering entirely
   to `AppLogger`'s configured handlers. If making structlog's processor chain cooperate with
   `dictConfig` needs a non-trivial custom processor chain (beyond `merge_contextvars`,
   `add_log_level`, and a final `ProcessorFormatter` handoff), that is scope creep — stop and report
   back rather than building it.
3. **Prototype against one real CIMS call site**, not synthetic examples. Pick a call site cims
   currently does `structlog.get_logger(__name__).bind(...)`-style logging at (check the cims
   extraction survey for a concrete file/line), and confirm the `StructLogger` version produces
   equivalent output through `AppLogger`'s handlers, including the file sink and JSON mode.
4. **`structlog` must not become a hard dependency.** Follow the same optional-import pattern as
   Phase 8 (`resilience.py`) and `excel.py`/`pandas.py` — `structlog.py` (or wherever this lives) is
   never imported at module scope from `src/rn_forge/commons/__init__.py`, and
   `import rn_forge.commons` must keep succeeding with no optional extras installed.

**If all four hold with a facade that stays in the "handful of lines per method" range set by the
guiding principle at the top of this doc, build it.** If any one requires nontrivial custom glue,
**stop, delete the prototype, and report back that the gate failed and why** — that is a correct
outcome, not a shortfall, exactly as Phase 6 treats its own gate.

#### 9.2 — API (draft — confirm against the Phase 9.1 prototype before finalizing)

```python
class StructLogger:
    """Thin structlog front-end over AppLogger's stdlib handlers.

    Every record still flows through whatever AppLogger.initialize() configured
    (Rich console, file, JSON) — this only adds context binding and structured
    key-value fields on top. Use AppLogger.get_logger(__name__) directly for
    ordinary unstructured logging; use StructLogger when you want persistent
    bound context (request_id, tenant, etc.) across a chain of log calls.
    """

    def __init__(self, name: str, **initial_context: Any) -> None: ...

    def bind(self, **new_context: Any) -> Self: ...      # returns a new bound logger
    def unbind(self, *keys: str) -> Self: ...
    def new(self, **context: Any) -> Self: ...            # reset context, then bind

    @property
    def structlog(self) -> structlog.stdlib.BoundLogger: ...   # escape hatch

    def trace / spam / debug / verbose / info / notice / success / warning / error / critical(
        self, event: str, **kwargs: Any
    ) -> None: ...
```

#### 9.3 — Design notes

- **`AppLogger.initialize()` remains the single configuration entrypoint.** `StructLogger` does not
  call `dictConfig` itself; it calls `structlog.configure(...)` once, wired to route through whatever
  stdlib handlers `AppLogger.initialize()` already set up. Calling `AppLogger.initialize()` after
  constructing a `StructLogger` must not silently orphan it — document the required call order (or
  make `StructLogger` re-check config on first use) once the prototype settles the mechanics.
- **Optional-import guard**, per convention 2/the Phase 8 pattern: `import rn_forge.commons` must not
  require `structlog` to be installed.
- **Re-export from the curated public API only if the gate passes** (convention 4).

#### 9.4 — Tests

New `tests/test_structlogger.py`, gated with `pytest.importorskip("structlog")`:

- Every verboselogs level (`trace`/`spam`/`verbose`/`notice`/`success`) round-trips through
  `StructLogger` with the correct stdlib level number.
- `bind`/`unbind`/`new` context semantics: bound fields appear in every subsequent call until
  unbound; `new()` clears prior context.
- A `StructLogger` call lands in the same file handler / Rich console / JSON output as an equivalent
  `AppLogger.get_logger(__name__)` call — assert on the same sink, not just "it doesn't crash."
- `import rn_forge.commons` succeeds with `structlog` not installed.

#### 9.5 — Docs

If the gate passes: new `docs/api/structlogger.md` + nav entry, and a section in
`docs/guides/logging.md` explaining when to reach for `StructLogger` vs. `AppLogger.get_logger`
directly (bound context vs. one-off structured calls) — this is exactly the kind of "how do the
logging pieces fit together" question this plan should answer for the next reader, not just the
resilience/console pieces.

---

## Part C — Deduplication across agentkit and taskkit

Source: the 2026-09-04 survey of `rn-forge/agentkit` and `rn-forge/taskkit`. Unlike Parts A and B,
**nothing here is speculative** — every item below exists twice today, and several pairs have
already drifted in ways that are latent bugs. Neither repo currently depends on
`rn-forge-commons`; adopting it is what collects the payoff.

### How the two repos line up

Both converged independently on the same five-layer architecture, which is why the duplication is
so systematic:

| Layer | agentkit | taskkit |
| --- | --- | --- |
| Typer surface | `cli.py` (350) | `cli.py` (302) |
| Command objects | `commands/base.py` (183) + 4 command classes | `commands/base.py` (174) + 3 command modules |
| Atomic file IO | `core/io.py` (233) | `core/io.py` (167) |
| State (hash → artifact) | `core/state.py` (208) | `core/state.py` (84) |
| Path/root discovery | `core/paths.py` (66) | `core/paths.py` (89) |
| Layered config | `core/config.py` (201) | `core/config.py` (153) |
| Templating | `core/render.py` (82) | `core/renderer.py` (96) |
| Plugin/adapter registry | `agents/registry.py` (172) | `adapters/registry.py` (101) |
| `$RNF_HOME` self-install | `commands/self_command.py` (342) | `core/install.py` (390) |

**Ordering.** Phases 10-17 are independent of each other and of Parts A/B, with two exceptions:
Phase 14 must come after Phase 0 (it touches `DictUtils`), and Phase 16's `to_toml` filter needs
Phase 11. Do Phase 10 first regardless — several other phases call `atomic_write`.

**Adoption is a separate step.** As with the rest of this plan, *do not modify agentkit or taskkit
here.* Design each API against both repos' call sites, ship it in commons, and leave adoption to a
follow-up plan in each repo (see "Not in this plan" at the end).

---

### Phase 10 — `PathUtils.atomic_write`, reconciled against both copies

Supersedes Phase 5.3's "port it verbatim" instruction. There are two implementations and **each has
something the other lacks**:

| Behaviour | agentkit `io.atomic_write` | taskkit `io.atomic_write_bytes` |
| --- | --- | --- |
| Accepts `str` and `bytes` | yes | bytes only |
| Explicit `mode=` override | yes | no |
| Preserves existing file's mode | yes | yes |
| `fsync`s the file | yes | yes |
| **`fsync`s the parent directory** | yes | yes |
| Temp cleanup catches | `except Exception` | `except BaseException` |
| `mkstemp` suffix | none | `.tmp` |

**The commons version takes the union**: `str | bytes` content, optional explicit `mode`, existing
mode preserved when `mode` is `None`, file fsync, best-effort parent-directory fsync (silently
skipped on filesystems that refuse to open a directory), and a `.tmp` suffix on the temp file so a
stray temp is recognizable.

**Use taskkit's `except BaseException`, not agentkit's `except Exception`.** A `KeyboardInterrupt`
or `SystemExit` between `mkstemp` and `os.replace` leaves an orphaned temp file under agentkit's
version. This is the drift-becomes-a-bug case that justifies one shared copy.

Both repos' docstrings independently explain *why* the parent directory is fsynced (the rename
lives in the directory, so fsyncing only the file can still lose the new name after a crash). Keep
that explanation in the commons docstring — it is the non-obvious part.

Tests are as specified in Phase 5.3, plus: parent-directory fsync failure is swallowed, not raised;
a `KeyboardInterrupt` mid-write leaves no temp file behind.

---

### Phase 11 — New `documents.py`: round-trip TOML/YAML/JSON configuration documents

**Dependencies:** `tomlkit`, `ruamel.yaml` — planned as a `documents` extra, shipped as base
dependencies instead ([11.4](#114--superseded-one-yaml-backend-one-serialisation-module)).

**The gap** (as originally written; superseded in part by 11.4). commons handles YAML via `pyyaml` and JSON via `JsonUtils`, and has **no TOML support
at all**. Both consumers need TOML, and — more importantly — both need *comment-preserving
round-trip* editing, which `pyyaml` structurally cannot do and `tomlkit`/`ruamel.yaml` exist
specifically to provide. agentkit's `core/io.py` is the fuller implementation; taskkit's
`core/config.py` has the TOML-only subset plus an array-of-tables append helper.

#### 11.1 — API

```python
class ConfigFormat(StrEnum):
    TOML = "toml"; YAML = "yaml"; JSON = "json"

    @classmethod
    def of(cls, path: Path, override: str | None = None) -> Self: ...
        # suffix-driven, with the yml -> yaml alias


class DocumentError(AppException):
    """A configuration document cannot be read, parsed, or encoded."""


class DocumentUtils:
    """Round-trip config documents that keep their comments and formatting."""

    # -- plain mappings (comments discarded) ------------------------------
    @staticmethod
    def loads(text: str, fmt: ConfigFormat | str) -> dict[str, Any]: ...
    @staticmethod
    def dumps(data: Mapping[str, Any], fmt: ConfigFormat | str) -> str: ...
    @staticmethod
    def read(path: str | Path, *, missing_ok: bool = False) -> dict[str, Any]: ...
    @staticmethod
    def write(path: str | Path, data: Mapping[str, Any]) -> None: ...   # atomic

    # -- round-trip documents (comments and style preserved) --------------
    @staticmethod
    def read_document(path: str | Path) -> Any: ...
    @staticmethod
    def write_document(path: str | Path, document: Any) -> None: ...    # atomic
    @staticmethod
    def update(path: str | Path, updates: Mapping[str, Any]) -> None: ...
        # deep-update in place, preserving comments; creates the file if absent
```

#### 11.2 — Design notes

- **Both `write` and `write_document` go through `PathUtils.atomic_write`** (Phase 10). Both repos
  already do this; it is the single most valuable property of this module and must not be lost.
- **`DocumentError` subclasses `AppException`** per convention 3 — not agentkit's bare
  `ConfigIOError(ValueError)`. Callers that catch `ValueError` still work, since `AppException`
  should keep whatever base commons already gives it; verify before assuming.
- **~~Keep `pyyaml` for the existing `YamlUtils`.~~ SUPERSEDED — see 11.4.** The original decision
  was to leave `collections.py` on `pyyaml` and confine `ruamel.yaml` to `documents.py`'s
  round-trip path. That was reversed once the module landed: see [11.4](#114--superseded-one-yaml-backend-one-serialisation-module).
- **JSON has no comments**, so its round-trip and plain paths are the same code. Keep
  `indent=2, sort_keys=True` + trailing newline — both repos already agree on that, and it is what
  makes their state/config files diff cleanly.
- **Port taskkit's `append_table` too**, generalized as
  `DocumentUtils.append_to_array(document, key, fields)` — appending one table to a TOML
  array-of-tables without disturbing surrounding comments is genuinely fiddly and taskkit has
  already solved it.
- **Do not port taskkit's `parse_config`/`ConfigFinding`.** That is Pydantic validation of
  taskkit's own schema; commons must not take a Pydantic dependency for it. The *pattern* (report
  every validation failure with a dotted field path, not just the first) is worth keeping in
  taskkit.

#### 11.4 — SUPERSEDED: one YAML backend, one serialisation module

The Phase 11 plan assumed `documents.py` would sit *beside* `collections.py`'s `JsonUtils` and
`YamlUtils`. In practice that left two YAML parsers with divergent behaviour in one package, and
the "plain" path in `documents.py` never used `pyyaml` at all — it parsed with `ruamel` and
flattened. Both were consolidated:

- **`ruamel.yaml` is the only YAML backend.** `pyyaml` and `types-pyyaml` are dropped. `YamlUtils`
  uses `typ="safe"`; `DocumentUtils`'s round-trip methods use `typ="rt"`. ruamel is a functional
  superset of pyyaml, so this is a swap, not an addition. `YamlUtils.serialize`'s `**kwargs` now
  set attributes on the `ruamel.yaml.YAML` instance rather than passing through to `yaml.dump`;
  `sort_keys` and `default_flow_style` behave as before.
- **`JsonUtils` and `YamlUtils` moved from `collections.py` to `documents.py`.** `collections.py`
  is now `DictUtils` + `ListUtils` only, matching its name. `documents.py` owns every
  serialisation concern. Both are re-exported from the curated `__init__.py`, so
  `from rn_forge.commons import JsonUtils` is unchanged; only direct
  `rn_forge.commons.collections` imports had to move.
- **The `documents` extra is gone.** `ruamel.yaml` and `tomlkit` are base dependencies. Keeping
  core serialisation behind an optional extra was untenable once `config.py`, `console.py` and
  `dataclasses.py` all depended on it. `tomlkit` rather than stdlib `tomllib` because `tomllib`
  cannot write TOML, let alone preserve comments.
- **`_deep_update_document` stays separate from `DictUtils.merge`**, and now says why in its
  docstring: `merge` is `dict`-typed and deep-copies override values, which would replace the
  tomlkit/ruamel containers and discard their attached comments.

#### 11.3 — Tests

New `tests/test_documents.py`, gated with `pytest.importorskip`:

- Round-trip a TOML file with comments and a YAML file with comments through
  `read_document`/`write_document`: comments and key order survive byte-for-byte.
- `update()` deep-merges nested tables and preserves comments on untouched keys.
- `update()` on a missing file creates it.
- Suffix dispatch including the `.yml` → yaml alias, and an unsupported suffix raising
  `DocumentError`.
- A non-mapping document root raises `DocumentError` (both repos enforce this).
- `read(missing_ok=True)` returns `{}`.

---

### Phase 12 — Commons `ContentHash` and tooling `StateStore`

**No new dependencies.** Both repos maintain a JSON "what did I last write where" state file keyed
by path, and both hash file contents with SHA-256 to detect drift.

#### 12.1 — Hashing

Trivial and identical in both (`state.content_hash` / `state.file_hash` in agentkit; inlined in
taskkit). Add to `utils.py` alongside `PathUtils`:

```python
class ContentHash:
    @staticmethod
    def of(content: str | bytes, *, algorithm: str = "sha256") -> str: ...
    @staticmethod
    def of_file(path: str | Path, *, algorithm: str = "sha256") -> str | None: ...
        # None when the path is not a file — both repos rely on this exact contract
```

#### 12.2 — `StateStore`

Place this class in `packages/rn-forge-tooling/src/rn_forge/tooling/state.py`; it imports
`ContentHash`, `PathUtils`, `DataclassMixin` and `AppException` from commons.

agentkit's `StateStore` (208 lines) is far more developed than taskkit's `load_state`/`save_state`
(84 lines) and is the right starting point. It contributes:

- `flock`-based advisory locking around read-modify-write, **degrading to unlocked** rather than
  failing on a filesystem without `flock` support.
- One write per *operation* rather than per entry (`record_many`), keeping the clobber window small.
- Aggressive validation on load, with a documented rationale: a hand-edited or truncated state file
  that happens to parse would otherwise surface as an `AttributeError` deep inside a later apply.

taskkit contributes the shape that makes it reusable: a **typed entry** (`ArtifactState`) and
top-level metadata (`schema_version`, a producing-tool version, a config hash) rather than agentkit's
free-form `dict[str, Any]`.

**Tooling version — generic over the entry type but intentionally local in its locking policy:**

```python
E = TypeVar("E", bound=DataclassMixin)

class StateStore(Generic[E]):
    """A locked, atomically-written, JSON-backed key → entry store.

    Args:
        path: The state file.
        entry_type: A DataclassMixin subclass; entries round-trip through
            its from_dict/as_dict, so validation is the dataclass's job.
        schema_version: Written to the file and checked on load.
    """

    def load(self) -> dict[str, E]: ...
    def get(self, key: str) -> E | None: ...
    def record(self, key: str, entry: E) -> None: ...
    def record_many(self, entries: Mapping[str, E]) -> None: ...
    def remove(self, key: str) -> None: ...
    def stale_keys(self, exists: Callable[[str], bool] = ...) -> list[str]: ...
    def locked(self) -> AbstractContextManager[None]: ...   # exposed, both repos need it
```

Design notes:

- **`entry_type` being a `DataclassMixin` is what removes agentkit's 60-line hand-rolled
  validation block** — Phase 4's dacite-backed `from_dict` does that work, and with
  `__dacite_config__ = dacite.Config(check_types=True)` on the entry class it does it *better*
  than the current hand-rolled checks. This is a genuine payoff from Phase 4; call it out in the
  docstring. It also means Phase 12 should land after Phase 4.
- **Keep agentkit's `flock` degradation and its comment.** Silently proceeding unlocked is a
  deliberate local-tool choice (a personal dev tool must not fail a command because `/tmp` is on a
  weird filesystem). This is also why `StateStore` must not be exposed as commons persistence for
  web services or shared workers.
- **Key normalization is the caller's job, not the store's.** agentkit resolves paths to canonical
  absolute strings (`_resolved`); taskkit uses repo-relative POSIX strings. Both are correct for
  their scope, so the store must not impose one — take `str` keys and let the caller normalize with
  Phase 13's helpers.
- **`stale_keys` takes an existence predicate** rather than assuming keys are filesystem paths,
  since taskkit's keys are artifact ids, not paths.

#### 12.3 — Backups are *not* part of this

Both repos also have a timestamped backup helper (`state.backup_file` / `io.backup_file`), and they
differ in a way that is not reconcilable into one function: agentkit lays backups out relative to
`$HOME` under a per-run timestamp resolved lazily via a **module-level global**; taskkit lays them
out relative to the repo root under a caller-supplied timestamp. taskkit's is the better design
(no global). Port **only** the small generic piece into `PathUtils`:

```python
PathUtils.backup(path, destination_root, *, relative_to: Path | None = None) -> Path | None
```

— copy with `shutil.copy2`, create parents, return `None` when the source is not a file. Leave
per-run timestamp policy in each application; agentkit's `start_backup_run()` global is exactly the
kind of thing that must not migrate into a shared library.

#### 12.4 — Tests

- Round-trip typed entries; `record_many` writes once (assert with a write counter or mtime).
- A corrupt/truncated state file raises with a message naming the file.
- A state file with an unexpected `schema_version` is rejected.
- Concurrent `record` from two threads does not lose entries.
- `of_file` returns `None` for a missing path and for a directory.

---

### Phase 13 — Repository-root discovery and path-escape guards in `PathUtils`

**No new dependencies.** Small, but security-relevant: these are the functions that stop a config
value or a third-party plugin from writing outside the tree it was given.

Three related pieces, all currently duplicated or divergent:

```python
class PathUtils:
    @staticmethod
    def find_root(
        start: str | Path | None = None,
        *,
        markers: Sequence[str | Path] = (".git",),
        fallback: Literal["start", "raise"] = "start",
    ) -> Path:
        """Walk up from *start* to the nearest ancestor containing any marker."""

    @staticmethod
    def normalize_relative(raw: str) -> str:
        """Normalize to a POSIX relative path, rejecting absolute paths and
        any '..' that would escape the root. '.' means the root itself."""

    @staticmethod
    def assert_within(root: str | Path, target: str | Path) -> Path:
        """Resolve *target* and raise unless it stays inside *root*.
        Covers the symlink-escape case, not just lexical '..'."""
```

Reconciliation notes:

- **`markers` and `fallback` are what make one function serve both.** agentkit's `project_root()`
  looks only for `.git` and falls back to the start directory; taskkit's `find_repository_root()`
  takes an ordered marker list (`.rn-forge/taskkit/config.toml`, then `Taskfile.yml`, then `.git`,
  each behind its own flag) and *raises* when nothing matches. Ordered markers + a fallback policy
  expresses both without a flag per marker.
- **`normalize_relative` is taskkit's `normalize_repo_path` verbatim** — agentkit has no equivalent
  and validates ad hoc inside `Artifact.__post_init__` instead (rejecting absolute paths and `..`
  segments there). Once this exists, that validation becomes a one-line call, which is the point.
- **`assert_within` merges taskkit's `reject_escaping_symlink` with agentkit's `Artifact` checks.**
  Note the two catch *different* attacks: agentkit's is lexical (a declared `../../.ssh/config`),
  taskkit's is resolution-based (a symlink pointing outside the repo). A correct guard needs both,
  and neither repo currently has both. **This is the most consequential drift the survey found** —
  say so in the docstring and test both cases explicitly.
- **`AppException` for the failures**, per convention 3. Both repos' bespoke error types
  (`PathEscapeError`, `RepositoryRootNotFoundError`, `SymlinkEscapeError`) become subclasses in
  commons or plain `AppException`s with distinct error codes — prefer distinct codes over a type
  per failure.

Tests: marker precedence order; `fallback="raise"` vs `"start"`; a `..` escape rejected; an
absolute path rejected; `"."` accepted as the root; a symlink resolving *inside* the root allowed;
a symlink resolving outside rejected; a non-symlink path outside the root rejected.

---

### Phase 14 — `DictUtils.merge` grows layers and provenance

**Replaces Phase 5.1** (see the superseded note there). **No new dependencies** — this is the phase
that explains why `mergedeep` was the wrong call.

**What agentkit's `ConfigMerger` does that a plain deep-merge cannot:**

1. **Per-key provenance.** Every dotted key path maps to the name of the highest-precedence layer
   that supplied it (`defaults` / `global` / `local` / `overrides` / `layer-N`). This drives
   agentkit's `diff` command, its `doctor` output, and `highest_source()` in
   `core/operations/result.py`. Nothing off-the-shelf does this.
2. **Per-path list strategy.** Lists *replace* by default, but paths marked
   `merge_strategy=append` concatenate instead. agentkit infers those paths from Pydantic
   `json_schema_extra`; commons must not depend on Pydantic, so it takes them as an explicit
   `append_paths` argument and leaves the schema-introspection adapter in agentkit.

#### 14.1 — API

```python
@dataclass(frozen=True, slots=True)
class MergeResult(DataclassMixin):
    config: dict[str, Any]
    provenance: dict[str, str]      # dotted path -> layer name


class DictUtils:
    @staticmethod
    def merge(target, *overrides) -> dict[str, Any]:
        """Unchanged. Existing callers keep working."""

    @staticmethod
    def merge_layers(
        *layers: Mapping[str, Any] | tuple[str, Mapping[str, Any]],
        layer_names: Sequence[str] | None = None,
        append_paths: Collection[str] = (),
    ) -> MergeResult:
        """Deep-merge in increasing precedence order, tracking provenance."""
```

#### 14.2 — Constraints

- **`DictUtils.merge` keeps its exact current signature and semantics.** It is load-bearing across
  the `rn-forge-django` settings facade, `collections.py`, and `config.py:120`. `merge_layers` is
  additive; it does not replace `merge`, and `merge` must not start returning a `MergeResult`.
- **Deep-copy every value taken from a layer** — the same guarantee Phase 5.1 analyzed and the
  reason `mergedeep` was rejected. agentkit's `_deep_merge` already does this. Assert it: mutating
  a nested value in the merged result must leave every input layer untouched.
- **Unnamed layers get conventional names** (`defaults`, `global`, `local`, `overrides`, then
  `layer-N`) — port agentkit's convention exactly; its `diff` output depends on those literals.
- **`_mark_provenance` recurses into mappings** so a whole subtree introduced by one layer gets an
  entry per leaf, not just at the subtree root. This is subtle and easy to drop when reimplementing;
  it is why agentkit's provenance map is useful at all.

#### 14.3 — Tests

Port agentkit's `tests/core/test_config.py` merge cases as the contract, plus: precedence across
three layers; provenance for a key overridden twice reports the *last* layer; an append-path list
concatenates while a normal list replaces; a subtree introduced wholesale gets provenance on every
leaf; deep-copy isolation; `merge`'s existing tests still pass unchanged.

---

### Phase 15 — `DictUtils.flatten` and `TextUtils.unified_diff`

**No new dependencies.** Small, obvious, and used by both repos.

```python
DictUtils.flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]
    # nested mappings -> dotted paths; the inverse of the dotted DictUtils.get/set

TextUtils.unified_diff(
    expected: str, actual: str, *,
    expected_name: str = "expected", actual_name: str = "actual",
) -> str
    # "" when equal; a conventional unified diff otherwise
```

Notes:

- `flatten` is the natural completion of `DictUtils`'s existing dotted-path `get`/`set` and is a
  prerequisite for anything that wants to diff two config trees by key. agentkit has it in
  `core/diff.py`; commons does not.
- `unified_diff` returning **`""` for equal inputs** (rather than an empty-ish diff header) is the
  contract both repos rely on to decide "did anything change" — keep it and test it.
- **`TextUtils` may not exist yet** — check `utils.py` first. If it doesn't, putting these two
  functions on `AppUtils` is fine; do not create a new module for two functions.
- Leave `layered_changes()` in agentkit. It is a presentation concern over `flatten` + provenance,
  and taskkit has no use for it.
- This pairs with Phase 2's `AppConsole.diff()`, which renders exactly this output.

---

### Phase 16 — Tooling `templates.py`: a strict Jinja render engine

**New tooling dependency:** `jinja2>=3.1.6`. Template rendering is a core part of generator
execution, so Jinja is not optional in the development-only tooling distribution. The tooling
package depends on commons Phase 11 for `DocumentUtils` and the `to_toml`/`to_yaml` filters.

Both repos render generated configuration from packaged templates; agentkit's `RenderEngine` is the
fuller version. Put this API in
`packages/rn-forge-tooling/src/rn_forge/tooling/templates.py`, not in either web runtime package.

```python
class RenderError(AppException): ...

class TemplateEngine:
    def __init__(
        self,
        *,
        directory: str | Path | None = None,
        package: str | None = None,
        package_path: str = "templates",
        strict: bool = True,
        **environment_kwargs: Any,
    ) -> None: ...

    @property
    def environment(self) -> jinja2.Environment: ...   # escape hatch
    def render_string(self, template: str, context: Mapping[str, Any]) -> str: ...
    def render(self, name: str, context: Mapping[str, Any]) -> str: ...
    def validate(self) -> list[str]: ...   # compile every visible template
```

Notes:

- **Support both loaders.** agentkit uses `FileSystemLoader`, taskkit uses `PackageLoader`; one
  engine that accepts either (`directory=` or `package=`) serves both. Raise if both or neither are
  given.
- **`StrictUndefined` by default** (agentkit's choice) — a silently-empty variable in a generated
  config file is a bug that surfaces far from its cause. `strict=False` is the escape hatch.
- **`keep_trailing_newline=True` in both repos; `trim_blocks`/`lstrip_blocks` only in taskkit.**
  Default `keep_trailing_newline=True` (both agree) and pass the rest through
  `environment_kwargs` rather than inventing a parameter per Jinja option.
- **`to_toml`/`to_yaml` filters come from Phase 11's `DocumentUtils.dumps`.** Documents are part of
  the commons base install, so tooling registers them directly.
- **`validate()` is the non-obvious value here** — compiling every template the loader can see is
  what lets `doctor`-style commands catch a broken template before a user hits it. agentkit's
  version swallows a `TypeError` from `list_templates()` on a loaderless environment; keep that.
- **Do not wrap async rendering, sandboxing, or bytecode caching.** Point at `.environment`.

Tooling tests: strict undefined raises `RenderError`; both loader styles; `to_toml`/`to_yaml`
round-trip through a rendered template; `validate()` reports a broken template by name and returns
`[]` for a loaderless engine.

---

### Phase 17 — `EntryPointLoader`: failure-isolated plugin discovery

**No new dependencies.** The smallest phase, and the one to skip if time is short — but the
isolation logic is genuinely subtle and currently exists only in agentkit.

**Only agentkit does entry-point discovery today** (taskkit's registry is an explicit dict populated
by `default_registry()`, with no plugin surface). Per this repo's own "don't design a Protocol from
one example" rule, extract **only** the generic mechanical part and leave the adapter contract in
agentkit:

```python
@dataclass(frozen=True, slots=True)
class PluginError(DataclassMixin):
    entry_point: str
    reason: str


class EntryPointLoader(Generic[T]):
    """Load an entry-point group, isolating each plugin's failures.

    A third-party entry point runs arbitrary code at import time. One broken
    plugin must never take down the host CLI, so each is loaded in isolation
    and its failure recorded rather than raised.
    """

    def __init__(self, group: str, *, expected_type: type[T]) -> None: ...
    def load(self, *, refresh: bool = False) -> tuple[list[T], list[PluginError]]: ...
        # entry points sorted by name so behaviour never depends on install order
```

What stays in agentkit: `_VALID_NAME` adapter-name validation, the builtins-are-reserved rule, and
`_validate_artifacts` (duplicate keys/destinations, exactly-one-`config` checks). Those are
agentkit's domain contract, not a generic plugin concern.

Two details worth carrying into the commons docstring because both are deliberate and non-obvious:
sorting entry points by name so discovery order does not depend on install order, and instantiating
a loaded object when it is a class or callable but accepting an already-constructed instance.

Note agentkit also isolates `cli_extension` mounting the same way in `cli.py:695-710` — that stays
in agentkit, but the loader's docstring should mention the pattern generalizes.

---

### Phase 18 — The self-install layer: put reusable mechanics in tooling

This is the **largest single duplication in the survey** — agentkit's `commands/self_command.py`
(342 lines) and taskkit's `core/install.py` (390 lines) are two implementations of one design:

- `$RNF_HOME/<product>/v<version>/` versioned install directories, `$RNF_HOME/bin/<product>` shim.
- A **portable `mkdir`-based install lock** — both repos independently rejected `flock` here, and
  both say so in a comment.
- Build an environment by shelling out to `uv sync` in a staged source tree.
- **Atomic `current` symlink flip** (write `.current.tmp.<pid>`, then `replace`).
- `cleanup` retaining the active version (+N rollbacks in taskkit), `doctor` reporting PATH
  resolution and symlink health, `upgrade` from a GitHub release tag, a local archive, or a local
  source checkout.
- `$RNF_HOME` resolution honouring the env var with a `~/.rn-forge` default (agentkit
  `paths.rnf_home()`, taskkit `install.resolve_rnf_home()`) — trivially duplicated, and it stays
  that way; see 18.3 for why commons is the wrong home for it.

**The `$RNF_HOME` layout and the self-commands do not belong in commons or the generic generator
engine.** It is not a general
Python utility but the rn-forge toolchain's product installer: it knows about `uv`, GitHub release
tarballs, a `current` symlink convention, and a `$RNF_HOME` directory layout. Putting it behind a
commons extra would make `rn-forge-commons` the home of a distribution mechanism that
`rn-forge-django` — a library that ships into deployed runtime servers and containers — will never
use. **This includes `$RNF_HOME` resolution itself** (see 18.3).

The reusable workstation mechanics belong in `rn-forge-tooling`; product coordinates and policy
remain in agentkit and kiln. Taskkit is a reference donor only. Section 18.1 defines that boundary.

#### 18.1 — What tooling can absorb: ~135 of 732 lines (~18%)

Decomposition of both files, by what a commons utility could replace:

| Concern | agentkit | taskkit | Generic? |
| --- | --- | --- | --- |
| Portable `mkdir` install lock (timeout + poll) | ~25 | ~30 | **yes** |
| Atomic symlink flip | ~5 | ~12 | **yes** |
| Release download + safe tarball extract | ~25 | — | **yes** |
| Version parsing/sorting | ~8 | ~15 | **yes — but use `packaging`, see 18.2** |
| Retention planning (keep active + N newest) | ~12 | ~45 | borderline — policy, not mechanism |
| `uv sync` invocation + failure mapping | ~30 | ~35 | no — uv/product policy |
| `$RNF_HOME` layout one-liners | ~10 | ~30 | no — umbrella-specific (18.3) |
| Install orchestration (lock→build→verify→flip→cleanup) | ~18 | ~35 | no — but it *is* shared between the two repos |
| `doctor` health checks | — | ~75 | partly (symlink status, PATH mismatch) |
| CLI reporting / Typer wiring / confirmations | ~55 | — | no |
| agentkit's `uninstall()` — hook stripping, owned artifacts | ~90 | — | no — pure agentkit domain |
| Docstrings, imports, `__all__` | ~35 | ~45 | no |

The residue is not mostly Typer config — agentkit only has ~55 lines of that, and taskkit has none
(its Typer surface lives in `cli.py`, already counted separately). It is mostly **three things a
shared mechanism cannot remove**:
agentkit's 90-line `uninstall()`, which is domain logic that was never install-layer at all; ~65
lines of `uv`-specific build invocation; and ~80 lines of docstrings/imports. Extracting the four
"yes" rows removes roughly **135 lines across both repos**, and no more.

The remaining ~250 lines of genuinely-shared install *orchestration* can only be deduplicated by the
two repos sharing an implementation. `rn-forge-tooling` is now that shared package, but it must keep
product coordinates and product-specific validation behind injected callbacks or application-owned
commands.

Concretely, add to tooling:

```python
# rn_forge/tooling/install.py
class DirectoryLock:
    """A portable advisory lock backed by mkdir, for cross-process serialization.

    mkdir is atomic on every filesystem this runs on; flock is not available
    everywhere. Use this when the lock must hold across processes on unknown
    filesystems; use tooling StateStore's flock-based locking (Phase 12) when a failed
    lock should degrade to unlocked rather than raise.
    """
    def __init__(self, path, *, timeout: float = 30.0, poll_interval: float = 0.05,
                 on_wait: Callable[[Path], None] | None = None) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *exc: object) -> None: ...


atomic_symlink(link: str | Path, target: str | Path) -> None
    # write .<name>.tmp-<pid> then os.replace; never unlink-then-recreate,
    # which leaves a window where the link does not exist at all.

extract_archive(archive, destination, *, filter: str = "data") -> Path
    # tarfile/zipfile with the data filter set, returning the single root dir.
```

`on_wait` on `DirectoryLock` is what lets agentkit keep printing "waiting for install lock ..."
without coupling the lock to a console. `extract_archive` defaulting to `filter="data"` is the point of
having it once: agentkit sets it correctly today, and a hand-rolled second copy is exactly how a
tar-slip vulnerability gets introduced.

**Not in commons: the download.** `urllib.request.urlopen` against a GitHub releases API is 25 lines
of product-specific coordinates, and a generic "download a file" wrapper adds nothing over the
stdlib. Leave it.

#### 18.2 — A real bug this decomposition surfaces

taskkit's `_version_sort_key` (`core/install.py:118-122`) splits on `.` and maps digit-only chunks
to `int`, leaving others as `str`. **Any prerelease installed alongside a normal version crashes
`installed_versions()`**, and with it `cleanup` and `doctor`:

```python
sorted(["0.2.0", "0.10.0", "0.2.0rc1"], key=_version_sort_key)
# TypeError: '<' not supported between instances of 'str' and 'int'
```

(Verified 2026-09-04.) agentkit avoids this only by never sorting versions semantically — it sorts
directory names lexically, which mis-orders `v0.10.0` before `v0.2.0`.

**The fix is not a commons `VersionUtils`** — it is `packaging.version.Version`, which is maintained,
ubiquitous, and already in every environment that has `pip`. This is design principle 1 working as
intended: the right move is a dependency, not an extraction. Record it here so whoever fixes taskkit
does not hand-roll a third copy.

#### 18.3 — `$RNF_HOME` resolution stays out of commons

An earlier draft of this plan proposed `Environment.rnf_home()` in commons "since both repos have
it." **That was wrong and is withdrawn.** `rn-forge-commons` is consumed by `rn-forge-django`, which
ships into deployed runtime servers and containers; `$RNF_HOME` is developer-workstation
configuration for someone running several tools under the rn-forge umbrella locally. A library that
runs in production has no business carrying a developer-machine path convention, and a three-line
saving is not a reason to leak one environment's assumptions into every consumer.

Keep it in each product while their layouts differ. If the layouts converge, tooling may own a
parameterized layout value object, but commons must never expose `$RNF_HOME`.

#### 18.4 — Shared orchestration decision

Use `rn-forge-tooling`; do not create a separate `rn-forge-selfkit`. Tooling owns the reusable
installer state machine and mechanics, parameterized by product callbacks. It may expose a
`ProductInstaller` that accepts product name, resolved install root, environment builder, artifact
source and verification hooks. It must not select `$RNF_HOME`, call a particular GitHub repository,
or define a product's retention/uninstall policy by default.

Start from taskkit's richer seams (`--keep N` planning, structured `DoctorFinding`, explicit
`build_environment`) and agentkit's stronger source/archive resolution, but keep those policies in
the product adapter until both products use the same contract.

---

### What Part C deliberately leaves in the applications

Recorded so a later reader does not "finish the job" by hoisting these too:

- **Domain models.** taskkit's `TaskkitConfig`/`WorkspaceConfig`/`Capability`/`TaskSpec` and
  agentkit's `Artifact`/`AgentAdapter`/`Scope` are each repo's core vocabulary. They are Pydantic-
  or domain-shaped and must not migrate.
- **The `Envelope` / `OperationResult` result types.** Both are output *schemas* with committed
  JSON contracts (taskkit's carries `schema`, `exit_code`, `findings`; agentkit's carries
  per-artifact actions and diffs). A shared envelope would couple two independent CLI contracts to
  one version number. Phase 2's `AppConsole` gives them a shared *renderer*; the schemas stay put.
- **`BaseCommand`.** Once `AppConsole` (Phase 2) and `build_app`/`CliOptions` (Phase 3) exist, what
  remains of both repos' `commands/base.py` is domain glue — adapter selection, root resolution,
  envelope construction. That is the right amount to keep local.
- **Both registries' resolution policy.** agentkit resolves by adapter name, taskkit by
  `(language, runner)` capability tuples. Only the entry-point loading mechanism is shared
  (Phase 17).
- **taskkit's validator/planner/discovery** (`core/validator.py` 657, `core/planner.py` 574,
  `core/discovery.py` 557 — a third of the repo). Entirely taskkit's domain; no agentkit analogue.
- **agentkit's `doctor.py`** (436 lines). Its checks are agentkit-specific; the *pattern* of a
  structured finding list is already shared by taskkit's `Finding`, but two similar dataclasses do
  not justify a shared abstraction yet. Revisit only if a third consumer appears.

---

## Deferred — do not build these yet

- **CloudEvents envelope builder** (cims `apps/messaging/cloudevents.py::envelope()`). A
  `build_cloudevent(*, id, type, source, subject=None, time=None, data=None, extra=None) -> dict`
  helper for the CloudEvents 1.0 envelope. It is genuinely framework-agnostic and would live in
  `rn_forge/commons/cloudevents.py`, but on its own it is a ~15-line dict builder with no consumer
  in this workspace — it only earns its place alongside the outbox/inbox messaging subsystem, which
  is Django-scoped and deferred. If built later: `source` stays a required parameter (no hardcoded
  default), and W3C `traceparent` injection goes through the caller-supplied `extra` dict rather
  than pulling OTel spans into commons.
- **Claim-check pattern** (cims `apps/messaging/claim_check.py`). Threshold-based payload
  externalization plus a SHA-256 integrity check. The logic is generic but the only concrete storage
  backend is Azure Blob, and designing a storage `Protocol` from a single example reliably produces
  the wrong abstraction. Revisit when a second backend (S3, GCS, or a second Azure consumer with
  different requirements) is actually in view.

---

## Final checklist before calling this done

- [ ] `packages/rn-forge-tooling` exists and declares a direct dependency on `rn-forge-commons`
- [ ] `uv sync --all-extras && uv run pytest packages/rn-forge-commons packages/rn-forge-tooling` green
- [ ] `uv run pyright` clean (covers `rn-forge-django` and tooling too)
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run --directory packages/rn-forge-commons --group docs mkdocs build --strict` clean
- [ ] Tooling docs build clean
- [ ] `grep -rn "coloredlogs\|CLIArgumentParser\|BooleanAction\|KeyValueAction\|_coerce_field_value" packages/` returns nothing
- [ ] Commons has no Typer/Jinja dependency and does not expose `cli`, `console`, `state` or `templates`
- [ ] Django/FastAPI runtime packages have no Typer or tooling dependency outside the `codegen` extra;
      `uv run lint-imports` proves `rn_forge.django` minus `rn_forge.django.codegen` never imports them
- [ ] Each package's curated `__init__.py` exposes only symbols it owns; `__all__` is sorted
- [ ] `import rn_forge.commons` succeeds in an environment with **no** optional extras installed
      (guards the Phase 8 optional-import rule)
- [ ] Breaking commons relocation and the new tooling package are listed in the docs index / README
- [ ] `CLAUDE.md`'s `rn-forge-commons` bullet updated — it currently describes logging as "built on
      `verboselogs`/`coloredlogs`" and lists `console.py` as "CLI argument parsing"
- [ ] Commons nav contains resilience/messaging/secrets/objects; tooling nav contains CLI/console
- [ ] Phases 8b/8c/8d landed — `rn-forge-azure` Phases 2/3/4 and `rn-forge-django` Phase 10 are
      blocked on them (see [`README.md`](./README.md) for the cross-plan order)
- [ ] Phase 6 and Phase 9 gate outcomes recorded (built, or abandoned with the reason written down)
- [ ] Phase 18.4 uses tooling for shared mechanics while product layout and policy remain local
- [ ] Generator contract is Python-callable without Typer; framework providers are `[codegen]` extras
- [ ] No developer-workstation path convention (`$RNF_HOME` and friends) leaked into commons — see 18.3
- [ ] Every Part C API checked against **both** agentkit and taskkit call sites, not just one
- [ ] Nothing committed or pushed — leave the working tree for review

## Not in this plan (deliberately deferred)

- **agentkit and kiln consuming these wrappers.** Both depend on `rn-forge-tooling`, which supplies
  their shared development surface and depends on commons. kiln is written against tooling from the
  start; agentkit is **rebuilt from scratch** on it (standardization plan D39, Phase F.3) — there is
  no in-place adoption. Design each migrated API against agentkit and taskkit's tested call sites,
  but do not modify either repo as part of this plan. The mapping below is the donor mapping for the
  agentkit rewrite:
  - **agentkit:** `commands/base.py`'s `_jsonable`/`console`/`fail`/`emit` → `AppConsole`;
    `core/io.py` → `PathUtils.atomic_write` + `DocumentUtils`; `core/config.py`'s merge half →
    `DictUtils.merge_layers`, its `parse_cli_overrides` → `rn_forge.tooling.cli.parse_overrides`;
    `core/diff.py` → `DictUtils.flatten` + `TextUtils.unified_diff`; `core/render.py` → tooling
    `TemplateEngine`; `core/state.py` → tooling `StateStore` + commons `ContentHash`;
    `core/paths.py::project_root` →
    `PathUtils.find_root`; `agents/registry.py`'s discovery half → `EntryPointLoader`.
  - **taskkit reference mapping (the repo is retired, so do not add a dependency):**
    `core/io.py`'s `atomic_write_bytes` → `PathUtils.atomic_write`; `core/config.py`'s
    document half → `DocumentUtils`; `core/state.py` → tooling `StateStore`; `core/paths.py` →
    `PathUtils.find_root`/`normalize_relative`/`assert_within`; `core/renderer.py`'s `_ENV` →
    tooling `TemplateEngine`; `commands/base.py`'s console pair → tooling `AppConsole`.
  - Both keep their domain models, result envelopes, and resolution policies — see "What Part C
    deliberately leaves in the applications."
- **`rn-forge-django`.** Out of scope. Recorded here so they are not lost when the older plan
  documents are deleted: `drf/views/transfer.py` (~1,200 lines) substantially overlaps
  `django-import-export`+`tablib`; there is a `RequestUtils` name collision between
  `django/utils.py:40` and `django/drf/utils.py:49` (different APIs, no shared logic); and the
  Django-shaped half of the cims survey — RFC 7807 problem-details handler, pagination,
  Idempotency-Key helper, optimistic-concurrency and immutability mixins, `OmitEmptyMixin`,
  `PermissionByMethodMixin`, readiness-view factory, sequence-backed code generator, request-ID
  middleware, OIDC/JWKS bearer auth, outbox/inbox messaging, Celery integration, and the
  drf-spectacular/camelCase settings recipes — all belong to a future Django plan.
