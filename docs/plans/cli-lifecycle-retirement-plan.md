# Retiring `[cli.lifecycle]` from `rn-forge-cli`

**Status:** implemented, 2026-09-21. Supersedes
[`cli-lifecycle-namespace-plan.md`](cli-lifecycle-namespace-plan.md), whose
`namespace` design carries over unchanged. Owner decision — kiln is also the
owner's, so kiln's generator template updates in the same change rather than
waiting for a separate handoff.

## Problem

Commons Part F ([`commons-upgrade-plan.md`](commons-upgrade-plan.md#part-f--the-tool-lifecycle-surface-kiln-phase-c3))
gave `rn-forge-cli` a second declared table, `[cli.lifecycle]`, alongside the
generic `[cli]` table: `LifecycleSurface`, a fixed six-verb vocabulary
(`LIFECYCLE_VERBS`), and `CliApp.add_lifecycle`. The stated reason `rn-forge-cli`
needed to know about lifecycle at all — rather than tooling declaring itself
as an ordinary `[[cli.commands]]` entry — was that `rn-forge-cli` must not
import `rn_forge.tooling`, and a repository's `[cli]` document is parsed by
`rn-forge-cli` alone. So mounting had to happen there, and `target` was kept a
required string (never a default naming `rn_forge.tooling...`) specifically so
that module path never appeared in `rn-forge-cli`'s own source.

Revisiting that: `rn-forge-cli` never needed to know the verb names, the
namespace-collision rule, or anything else lifecycle-specific to do the
mounting. `CliApp.add_typer` (inherited from `typer.Typer`, and already public
— see `CliApp`'s own docstring) is generic enough to mount *any* pre-built
`Typer`, including one tooling builds from its own factory. The only reason
`[cli.lifecycle]` existed as a table `rn-forge-cli` parsed was to parameterize
a factory call (`factory(product, verbs)`) that a plain `CommandSurface`
(`name` + `target`, imported and mounted as-is) cannot express. That parameter
threading does not require `rn-forge-cli` to know it is for "lifecycle" — it
only required somewhere to hold `product`/`verbs`/`namespace` and call
`add_typer` after the fact, and that somewhere can be `rn-forge-tooling`
itself, calling `rn-forge-cli`'s existing public API.

## Decision

`rn-forge-cli` returns to knowing only the generic `[cli]` shape: `name`,
`help`, `default_log_level`, and `commands` (`name`/`target`/`help`). It has no
concept of a lifecycle verb, a product, or a namespace.

`rn-forge-tooling` owns the whole lifecycle-on-a-command-line concern:

- `LifecycleSurface` (`rn_forge.tooling.cli.lifecycle`) — `product`, `verbs`,
  `namespace` — parsed from a `[lifecycle]` table, a sibling of `[cli]` in the
  same document, not nested under it.
- `build_tool_app(source, ...) -> CliApp` — reads the document once, builds
  the generic application through `rn-forge-cli`'s own public
  `CliSurface.load` / `CliApp.from_surface`, then mounts this package's
  `lifecycle_commands(product, verbs)` through `CliApp.add_typer`, at the root
  or under `namespace`.

The `target` key is gone. It only existed to route around `rn-forge-cli` not
being allowed to know tooling's module path; now that tooling calls its own
factory directly, there is no string to route through.

```toml
[cli]
name = "golden-tool"

[lifecycle]
product = "golden_tool.product:PRODUCT"
verbs = ["status", "doctor"]    # optional; default: all six
namespace = "self"              # optional; default: mounted at the root
```

```python
from rn_forge.tooling.cli.lifecycle import build_tool_app

app = build_tool_app(Path(__file__).parent.parent / ".rn-forge/kiln/config.toml")
```

A repository that declares `[lifecycle]` now depends on `rn-forge-tooling`
*visibly*, in its own `cli.py` import, rather than only inside a TOML string
that `rn-forge-cli` resolved on its behalf. A repository with only `[cli]`
never imports `rn-forge-tooling`.

## Changes made

**`rn-forge-cli`** (`packages/rn-forge-cli`):

- `surface.py` — removed `LifecycleSurface`, `LIFECYCLE_VERBS`, the `lifecycle`
  field on `CliSurface`, and the lifecycle branch of the duplicate-name check.
- `app.py` — removed `CliApp.add_lifecycle`; `from_surface` no longer calls it.
- `__init__.py` — `LifecycleSurface` dropped from the public facade.
- `docs/guides/declaring.md` — the "Lifecycle verbs" section replaced with a
  short pointer: this package knows only the generic shape; lifecycle is a
  `rn-forge-tooling` concept, documented in that package's own guide.
- `tests/test_surface.py` — `TestLifecycle` and its fixtures removed.

**`rn-forge-tooling`** (`packages/rn-forge-tooling`):

- `cli/lifecycle.py` — added `LifecycleSurface` (verb whitelist, duplicate and
  namespace validation, same rules the old `rn-forge-cli` version had) and
  `build_tool_app`.
- `README.md` and `docs/guides/lifecycle.md` — describe the `[lifecycle]`
  table and `build_tool_app`, replacing the `[cli.lifecycle]`/`target`
  description.
- `tests/cli/test_lifecycle_commands.py` — rebuilt around `build_tool_app`
  (root mount, namespaced mount, a namespaced verb sharing a root command
  name, both collision rejections, blank-namespace rejection, an unimportable
  product, and a document with no `[lifecycle]` table building a plain app).

## Validation

```bash
uv run pytest -q packages/rn-forge-cli packages/rn-forge-tooling
uv run ruff check packages/rn-forge-cli packages/rn-forge-tooling
uv run pyright packages/rn-forge-cli packages/rn-forge-tooling
uv run lint-imports
! rg -q 'rn_forge\.tooling' packages/rn-forge-cli/src
uv run --group docs mkdocs build --strict   # from each package directory
```

All pass. `rn-forge-cli` still does not import `rn_forge.tooling` (7 import
contracts kept, unchanged).

## Handoff to kiln

kiln is the owner's own tool, so this lands as a direct instruction rather
than a cross-team handoff:

1. `[archetype.python-tool]`'s rendered `cli.py` for a tool with
   `lifecycle = true` changes its import and call from
   `CliApp.from_config(...)` to
   `rn_forge.tooling.cli.lifecycle.build_tool_app(...)`.
2. The rendered `.rn-forge/kiln/config.toml` (and any golden repo's) moves its
   lifecycle declaration from a nested `[cli.lifecycle]` table with a `target`
   key to a sibling `[lifecycle]` table without one.
3. kiln S4.5.5's `namespace = "self"` design is unaffected — it is the same
   key, same validation, just declared and mounted by `rn-forge-tooling` now.
4. `golden/python-tool` (kiln F3.3) and its `kiln self status`/`kiln self
   doctor` acceptance update their fixture accordingly once kiln's session
   picks this up.
