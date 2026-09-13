# What kiln needs from pykit

**Date:** 2026-09-12 · **From:** `rn-forge/kiln` on `feature/v1`

kiln's standardization plan (revision 14) has been split into kiln's own spec
tree — epics, releases and ADRs under `rn-forge/kiln/docs/` — and the plan file
is retired. What this repo's plans cited from it lives here now: its §2.8
boundary table is §3.1 below, its §2.11 layout is §3.2, and its Phase C.2 steps
are in §1.

**pykit owns its own spec.** This file is only the handoff: the pykit-side work
the kiln plan carried, what is done, what kiln is waiting on, and the design kiln
assumed. Restructure it into pykit's own plans however pykit likes; kiln
references this file by path, not by heading.

On the kiln side:

- the board and the upstream table: `docs/specs/index.md`
- the decisions cited below: `docs/adr/0002-the-dependency-graphs.md` (D52),
  `docs/adr/0005-archetypes.md` (D59, D61, D73),
  `docs/adr/0011-kiln-is-modules-under-one-contract.md` (D56)
- the D-number → ADR mapping: `docs/plans/context.md` §2.2

## 1. Done

| kiln phase | What | Record |
| -- | -- | -- |
| A | Stabilize commons Part C | `commons-upgrade-plan.md`, execution status |
| C | First tooling extraction, Part D, generation engine — landed at `4624bfe`, reviewed, boundary found wrong | `commons-upgrade-plan.md` Part D, "Why this exists" |
| C.2 (pykit half) | Defect fixes F1–F6; the `rn-forge-cli` / `rn-forge-tooling` split (D52); docs policy extracted from tooling (A2); the D55 re-layout; F10–F13; F7 CI; F9 + F14 release contract and instructions — committed at `f59c40f` | `commons-upgrade-plan.md` Parts D and E |

### Phase A, as the kiln plan specified it

Repo `rn-forge/pykit`, branch `feature/upgrade`. **No release, no boundary
change.**

1. `uv sync --all-extras && uv run pytest packages/rn-forge-commons -q`; fix
   failures.
1. `uv run ruff check . && uv run ruff format --check . && uv run pyright`; fix.
1. Classify every Part C public symbol with a one-line comment block at the top
   of `commons/__init__.py`:
   `# tooling-bound (Phase C): cli, console, state, templates` so the temporary
   commons locations are visibly not a published API.
1. Update `CLAUDE.md`'s commons bullet to match reality (it still says
   `verboselogs`/`coloredlogs`).
1. Stage the result as one reviewable commit on `feature/upgrade`.

```bash
cd rn-forge/pykit
uv run pytest packages/rn-forge-commons -q
uv run ruff check . && uv run ruff format --check . && uv run pyright
grep -q 'tooling-bound' packages/rn-forge-commons/src/rn_forge/commons/__init__.py
git status --porcelain | wc -l        # 0 after the commit
```

### Phase C.2, the pykit steps as the kiln plan specified them

1. **Defect fixes, before anything moves.** **F1 + F6 together** — group staged
   changes by destination, compose block edits against one evolving buffer,
   back up and write each file once, reject incompatible whole-file and block
   ownership of one path, and preserve the unowned prefix, suffix and newline
   sequences. **F2** — roll back on `BaseException`, then re-raise interruption
   without converting it to an application failure. **F3** — fix
   `DataclassMixin` so deserialization reconstructs and validates enum fields,
   then audit every dataclass with an enum field. **F4** — normalize and
   validate artifact and stale-state paths under the repo, staging and backup
   roots *before* any mutation. **F5** — keep the intended deletion separate
   from the blocking drift classification, and execute it once approved. Tests
   for each: two inserts, two updates, removal-plus-update, CRLF and absent
   terminal newline, interruption after a replacement, JSON round trip with an
   unknown severity, absolute and `..` and symlink artifact paths.
1. **Split the development layer (D52).** New package `rn-forge-cli`, module
   `rn_forge.cli`: the Typer application class, the standard options, logging
   wiring, error-to-exit-code, the declared `[cli]` surface. (`AppConsole` went
   on to commons in Part E.) `rn-forge-tooling` keeps generation, templates,
   state, install and docs mechanics and gains a dependency on `rn-forge-cli`.
   `DirectoryLock` and `atomic_symlink` go back to commons. `ManagedBlock`
   stays. Three `.importlinter` contracts hold the layering.
1. **Extract the docs policy (A2).** `docs/structure.py` keeps link, Markdown
   and nav mechanics and takes a policy object; the ADR numbering, epic /
   feature / release naming and instruction filenames become the caller's. kiln
   supplies them (kiln F4.1); until then a default policy lives in kiln's
   fixtures, not in tooling.
1. **Re-layout all three packages (D55).** Modules move; public class names do
   not; no compatibility re-exports.
1. **F10, F11, F12, F13 while the code is open.** Diagnostic logging to stderr
   from initialization so `--json` is parseable wherever the flag sits; nav
   values serialized with the YAML library; the anchor checker calling
   Python-Markdown's own slug and unique-id logic instead of reimplementing it,
   plus reference links and fenced-code awareness; `docs nav --json` emitting a
   result.
1. **F7 — CI.** Add `rn-forge-cli` and `rn-forge-tooling` to package
   verification, build, release and coverage in pykit's `main.yml`, and run
   `lint-imports` as a required gate.
1. **F9 + F14 — the release contract and the instructions.** `rn-forge-cli` and
   `rn-forge-tooling` declare their commons dependency as a pinned direct URL,
   and the installation guides describe that model rather than `uv add`.
   Smoke-test an install outside the workspace. Reconcile pykit's `AGENTS.md` to
   be a pointer to `CLAUDE.md`.

## 2. Open — what kiln is waiting on

### 2.1 The tool lifecycle surface (kiln Phase C.3) — not started

**Blocks:** kiln F3.3 (`golden/python-tool` becomes a tool), and through it
kiln's release-1. `rn_forge/tooling/install/` holds only `archive.py`.

Repo `rn-forge/pykit`, branch `feature/upgrade`. Mechanism only; no kiln change.
Follow pykit's own conventions (no compatibility re-exports, `.importlinter`
contracts kept). Estimate: 3 days.

1. **`rn_forge/tooling/install/`**: `home.py` (`$RNF_HOME`, the
   `<home>/<product>/versions/<v>/` tree, the `current` symlink via commons
   `atomic_symlink` + `DirectoryLock`), `release.py` (resolve latest tag,
   download, verify, extract with `archive.py`), `product.py` (`ToolProduct`,
   every member defaulted), `lifecycle.py` (`install`, `upgrade`, `uninstall`,
   `cleanup`, `status`, `doctor`). Transactional in the shape of
   `generation/apply.py`: stage, back up, swap `current` last, restore on
   failure. Tests: failed download, failed migration, interrupted swap,
   `uninstall` over an install that never completed.
1. **`[cli.lifecycle]`** — a `CliSurface` record (on `StrictDataclassMixin`, like
   the rest of the surface) listing the verbs, and `CliApp.from_config`
   mounting them against a product object named in the table. `rn-forge-cli`
   must not import tooling (contract), so the mount resolves the product and the
   lifecycle functions by import string, the same way `[[cli.commands]]` targets
   already are.
1. Docs: tooling's guide gains a lifecycle page; cli's surface page documents the
   table.

```bash
cd rn-forge/pykit
uv run pytest -q packages/rn-forge-tooling packages/rn-forge-cli
uv run lint-imports && uv run pyright && uv run ruff check .
! rg -q 'rn_forge\.tooling' packages/rn-forge-cli/src
```

#### The design kiln assumed

The seam is an adapter, and it is the one kiln's own modules already use —
`artifacts()` + `checks()`, nothing else. A product implements a protocol;
`rn-forge-tooling` owns every algorithm around it.

```python
class ToolProduct(Protocol):
    name: str                 # "agentkit"; $RNF_HOME/<name>/
    version: str
    release_source: ReleaseSource        # default: GitHub releases of `repo`
    state_schema_version: int

    def artifacts(self) -> Sequence[Artifact]: ...   # what `install` puts in place
    def checks(self) -> Sequence[Check]: ...         # product-specific doctor rows
    def migrate(self, frm: str, to: str) -> None: ...  # default: no-op
```

Every member is defaulted, so a trivial tool implements none of them and still
gets the verbs.

| Module | Owns |
| -- | -- |
| `install/home.py` | `$RNF_HOME` resolution, `<home>/<product>/versions/<v>/`, the `current` symlink (commons `atomic_symlink`, `DirectoryLock`) |
| `install/release.py` | resolve the latest tag, download, verify, extract (`archive.py`) |
| `install/lifecycle.py` | `install`, `upgrade`, `uninstall`, `cleanup`, `status`, `doctor` as transactional sequences over the protocol |

The command line stays declared, not written (kiln ADR-0009). A
`[cli.lifecycle]` table lists which verbs the tool exposes, and
`CliApp.from_config` mounts them. The table is gated by `lifecycle = true`, a
capability flag orthogonal to the archetype (kiln ADR-0005) — which is why kiln
itself, a `python-lib`, gets these verbs without being a `python-tool`. Two
doctors, deliberately: `kiln doctor` inspects a repository; a tool's `doctor`
inspects its own install. Both emit commons `Finding`, neither knows about the
other.

Prior art is agentkit's `commands/self_command.py` and `core/doctor.py`; read
them, port nothing.

**Risk, and its guard:** this grows into an installer framework. Every
`ToolProduct` member is defaulted, the only acceptance on the kiln side is
`golden-tool doctor` and `golden-tool status`, and nothing in v1 self-installs
except kiln.

### 2.2 `rn-forge-fastapi` — in progress

**Blocks:** kiln E5 (the web archetypes), release-2. kiln starts E5 when
`fastapi-library-plan.md` reaches its acceptance.

**Alignment needed in pykit:** the owner decided on 2026-09-12 that intellibuild
is `python-web-app` (`fastapi + angular`), with a separately built frontend
package. This repo's plan index and `fastapi-library-plan.md` still say
`python-web-api`. intellibuild is now a standalone plan in kiln
(`docs/plans/intellibuild.md`) and does not gate kiln's releases.

### 2.3 Releases — triggered, not scheduled

**Unblocks:** kiln E7 (the pin flip). Under kiln ADR-0005, kiln consumes pykit
from `feature/upgrade` (or a local path) until the owner declares pykit stable;
no release gates kiln. When that happens: cut the tags in the order commons →
cli → tooling → web → django/fastapi (`commons-upgrade-plan.md` D.8), and kiln
flips its default source from branch to tag.

This suspends the "releases are pinned git tags" rule this repo's plan index
states (kiln D46); it does not reverse it.

## 3. Design the kiln plan recorded for pykit

Kept here because kiln no longer carries it and pykit's plans cite it.

### 3.1 The boundary, as corrected by the Phase C review (D52)

The first pass moved one set out of commons; C.2 moves it into two packages and
moves two things back:

| API | Home | Reason |
| -- | -- | -- |
| Typer helpers, `AppConsole`, standard options, logging wiring, error-to-exit-code, the `[cli]` surface | **`rn-forge-cli`** (`AppConsole` later moved to commons in Part E) | the process and command-line shape; every CLI wants it, including batches |
| `generation`, `TemplateEngine`, `StateStore`, `install`, `extract_archive`, docs *mechanics* | **`rn-forge-tooling`** | owns files, installs, or renders; only `python-tool` and kiln/agentkit need it |
| `DirectoryLock`, `atomic_symlink` | **back to commons** (`fs/locks.py`) | no installer policy in the signature; a local worker can serialize filesystem work or publish a snapshot atomically |
| `ManagedBlock` | **stays in commons** (`fs/blocks.py`) | a byte-preserving fenced-span edit; the current callers are all dev tools because they are the only current callers |
| `Finding`, `Severity`, `JsonValue`, `utils.py`, `EntryPointLoader`, `PathUtils`, `ContentHash`, documents, integration protocols, resilience | **commons** | unchanged; generalize `Finding`'s wording so paths need not be repo-relative and severity need not dictate exit policy |
| ADR numbering, epic/feature/release naming, instruction filenames in `docs/structure.py` | **kiln** (its checks, kiln F4.1) | rn-forge policy, which kiln ADR-0001 says is kiln's; tooling takes an explicit policy object instead (A2) |

Do not leave compatibility re-exports in either direction: commons must never
import cli or tooling, and cli must never import tooling. `.importlinter` holds
all three contracts.

**Kiln-owned:** `$RNF_HOME`, the `.rn-forge/` layout, `config.toml` schemas,
archetypes, golden repos and product policy. The generic template and generator
engines are tooling-owned; kiln owns their repo-standardization inputs and
command surface.

The Part C/D shared capabilities as originally placed:

| Item | Owner/module | Replaces |
| -- | -- | -- |
| `ManagedBlock(name, *, comment="#")` with `render(text, body) -> str`, `remove(text) -> str`, `extract(text) -> str \| None`; supports `#` and `<!-- -->` fences | commons `blocks.py` | agentkit `project_command._scaffold_gitignore`, taskkit `io.update_gitignore_block`, `gen_nav.py` marker logic |
| `Finding(code, severity, message, path=None, line=None, details=field(default_factory=dict))` + `Severity` StrEnum; `DataclassMixin` for `--json` | commons `findings.py` | taskkit `validator.Finding`, agentkit `doctor.CheckResult` |
| Recursive `JsonValue` alias | commons `_typing.py` | duplicated JSON metadata annotations |
| `DryRunOption`, `YesOption`; `CliOptions.dry_run`, `.yes` | tooling `cli.py` (now `rn-forge-cli`) | both kits' per-command flags |
| `StateStore(..., metadata: Mapping[str, JsonValue] \| None)` written beside `schema_version`/`entries`; `metadata` property on load; canonical JSON output with sorted mapping keys | tooling `state.py` | taskkit's `taskkit_version`/`config_hash` envelope fields |
| `generation.py` — artifact kinds, action classification, staged/backed-up/atomic transactional execution, Typer-free generator protocol | tooling `generation.py` | agentkit `project_command` apply loop, taskkit `planner` write path |

**Codegen (D37):** `rn-forge-tooling` owns the generator engine;
`rn-forge-django[codegen]` owns Django templates and option schemas under
`rn_forge.django.codegen`, registered in the `rn_forge.kiln.generators`
entry-point group; kiln discovers them and supplies Typer commands. The runtime
surface of `rn_forge.django` never imports `codegen`, tooling, Typer or Jinja —
enforced by import-linter in pykit. A FastAPI runtime package follows the same
shape. Guard against the extra leaking into the runtime surface: the
import-linter contract exists before the first codegen module, and
`import rn_forge.django` with no extras is a checklist item.

### 3.2 Package layout inside the three libraries (D55)

Commons was 7,274 lines across 23 flat modules, and the flatness was the
problem: `utils.py`, `objects.py`, `tasks.py` and `collections.py` sat at the
same level and meant four unrelated things. Grouping by *kind of mechanism*
makes the answer to "where does this go" readable off the tree.

**Rule: modules are grouped; public class names do not move.** `PathUtils`,
`DictUtils`, `AppLogger`, `Finding` and the rest keep their names and stay
re-exported from the package facade, so `from rn_forge.commons import PathUtils`
is unaffected. What changes is the submodule path. There are no compatibility
shims.

```text
rn_forge/commons/
  __init__.py        facade — the cheap, always-available symbols
  exceptions.py      AppException
  findings.py        Finding, Severity
  config.py          Config
  testing.py         assert_that, soft_assertions, output_path
  lang/              collections.py  dataclasses.py  reflection.py
                     types.py (was _typing)  utils.py (AppUtils, Base64)
  fs/                paths.py (PathUtils)  hashing.py (ContentHash)
                     locks.py (DirectoryLock, atomic_symlink)  ← back from tooling
                     blocks.py (ManagedBlock)  documents.py
  data/              pandas.py  excel.py
  logging/           __init__.py (AppLogger, LoggingConfig, TRACE)  structlog.py
  runtime/           environment.py  subprocess.py (Process)  tasks.py (Task, TaskPool)
                     plugins.py (EntryPointLoader)
  integration/       messaging.py  objects.py  secrets.py  resilience.py

rn_forge/cli/
  __init__.py        facade
  app.py             CliApp (typer.Typer subclass) + ExitCode + run
  options.py         --json --dry-run --yes --log-level --set; CliOptions
  surface.py         the [cli] surface records (ADR-0009)
                     (AppConsole lives in rn_forge.commons.runtime.console)

rn_forge/tooling/
  __init__.py        lazy facade — no eager import of jinja2
  generation/        artifacts.py  plan.py  apply.py
  templates.py       TemplateEngine
  state.py           StateStore
  install/           archive.py (extract_archive)  home.py ($RNF_HOME)
                     release.py  lifecycle.py  product.py (ToolProduct)
  docs/              markdown.py  links.py  nav.py  areas.py  site.py
                     policy.py    ← the injected policy protocol (A2)
                     structure.py ← mechanics only
  cli/               tooling's own command surfaces (rn-forge-docs)
```

Two things this layout does not pretend to fix. `AppUtils` remains a genuine
grab bag (`parse_bool`, `is_empty`, `get_or_default`, `import_string`,
`null_safe_attrgetter`, `join_string`, `unified_diff`); splitting it would break
a public class name for little gain, so it stays whole in `lang/utils.py` and new
helpers must justify not going into a named module instead. And several
submodule names shadow stdlib ones — `collections`, `dataclasses`, `logging`,
`subprocess`, `pandas` — which the flat layout already did; Python 3's absolute
imports handle it, and the intuitive name is worth more than the shadow costs.
