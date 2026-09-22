# Lifecycle verbs under a namespace

**Status:** superseded, 2026-09-21, by
[`cli-lifecycle-retirement-plan.md`](cli-lifecycle-retirement-plan.md). The
`namespace` key landed as designed below, then the review that followed it
found the larger `[cli.lifecycle]` mechanism itself misplaced: it put a
tooling-specific vocabulary (the six verb names, the lifecycle table's shape)
into `rn-forge-cli`, which is supposed to know only the generic
name/target/help shape of a declared command. The retirement plan moves the
whole mechanism into `rn-forge-tooling` — `LifecycleSurface` and
`build_tool_app` — and this plan's `namespace` design carries over unchanged
as part of it. Kept for the `namespace` design record; do not implement
against this version.

**Status (original):** planned, 2026-09-21. Requested by kiln
[S4.5.5](https://github.com/rn-forge/kiln/blob/main/docs/specs/epics/E4-generator/F4.5-cli.md#s455--lifecycle-wiring),
which waits on this plan to close. Scope: `rn-forge-cli` only.

## Problem

`[cli.lifecycle]` always mounts its verbs at the root of the application
(`CliApp.add_lifecycle` calls `self.add_typer(commands)` with no name). For
kiln, that puts verbs about the tool's own install next to commands about the
repository it manages:

| Root verb | Collides or is confused with |
| --- | --- |
| `kiln doctor` | kiln's own `doctor`, which inspects a generated repository (a hard collision: `CliSurface` rejects the duplicate) |
| `kiln upgrade` | `kiln config-upgrade`, which upgrades a repository's config schema |
| `kiln status` | reads as "status of this repository" |

S4.5.5 worked around the hard collision by leaving `doctor` out of `verbs` and
adding a hand-written `kiln self-doctor` command. That special-cases one verb
and leaves the other two confusions in place. kiln cannot build the group
itself: its import contract forbids importing Typer.

## Decision

`[cli.lifecycle]` gains an optional `namespace` key. When it is set, the verbs
are mounted under that name as a sub-command group instead of at the root:

```toml
[cli.lifecycle]
product = "rn_forge.kiln.product:PRODUCT"
target = "rn_forge.tooling.cli.lifecycle:lifecycle_commands"
namespace = "self"          # optional; default: mounted at the root
```

This gives `kiln self install|upgrade|uninstall|cleanup|status|doctor`, the
same shape as `uv self update`, `rustup self update` and `poetry self`.

The default stays the root, so every existing declaration (`golden-tool doctor`)
behaves exactly as it does now. Whether the python-tool canon should set
`namespace = "self"` for every tool is kiln's decision and is not part of this
plan.

## Changes

All in `packages/rn-forge-cli`. `rn-forge-tooling` does not change:
`lifecycle_commands` already returns an unnamed `typer.Typer`, and naming it is
the mounting side's job.

1. **`surface.py` — `LifecycleSurface`.** Add the field
   `namespace: str | None = None`, documented in the `Args:` block. In
   `__post_init__`, reject a namespace that is empty or whitespace-only, or that
   contains whitespace, with an `AppException` naming the value.
2. **`surface.py` — `CliSurface.__post_init__`.** The duplicate-name check uses
   the names the lifecycle table actually takes up at the root: `[namespace]`
   when a namespace is set, `verbs` otherwise. So `[[cli.commands]] name =
   "doctor"` next to `namespace = "self"` with `doctor` in `verbs` is accepted,
   and a command named `self` next to `namespace = "self"` is rejected as a
   duplicate.
3. **`app.py` — `CliApp.add_lifecycle`.** Mount with
   `self.add_typer(commands, name=lifecycle.namespace)`. When a namespace is
   set, also pass a fixed group help, `"Install, upgrade and check this tool
   itself."`, so `--help` doesn't show an empty description. Update the docstring,
   which currently says the verbs are mounted "at the root".
4. **Docs.**
   - `docs/guides/declaring.md`, section "Lifecycle verbs: `[cli.lifecycle]`":
     add `namespace` to the example and the key table. Replace the sentence
     "The verbs are mounted at the root of the application" with the two cases,
     and say how the collision rule depends on the namespace.
   - `packages/rn-forge-tooling/docs/guides/lifecycle.md` (line 119, "mounts the
     verbs at the root"): add "unless the table sets `namespace`" and a link to
     the cli guide.
   - `docs/plans/README.md`: move this plan's status row to implemented.

## Tests

In `packages/rn-forge-cli/tests/test_surface.py`, next to the existing
lifecycle tests (`test_verbs_are_mounted_at_the_root_against_the_product` and
the others):

- `test_namespace_defaults_to_none`: an existing table parses with
  `namespace is None`, and `run(app, ["doctor"])` still reaches the verb at the
  root (the existing root test already covers this; assert the field too).
- `test_verbs_are_mounted_under_the_namespace`: with `namespace = "self"` and
  `verbs = ["status", "doctor"]`, `run(app, ["self", "doctor"])` returns
  `ExitCode.OK` and prints `doctor ran for True`, and `run(app, ["doctor"])`
  returns `ExitCode.USAGE`.
- `test_a_namespaced_verb_may_share_a_command_name`: a `[[cli.commands]]`
  entry named `doctor` next to `namespace = "self"` with `doctor` in `verbs`
  loads without error, and both `app doctor` and `app self doctor` run their own
  targets.
- `test_a_namespace_colliding_with_a_command_is_rejected`: a command named
  `self` next to `namespace = "self"` raises `AppException` matching
  `Duplicate`.
- `test_a_blank_namespace_is_rejected`: `namespace = ""`, `"  "` and `"a b"`
  each raise `AppException`.

## Validation

```bash
uv run pytest -q packages/rn-forge-cli packages/rn-forge-tooling
uv run ruff check packages/rn-forge-cli
uv run pyright packages/rn-forge-cli
uv run lint-imports
! rg -q 'rn_forge\.tooling' packages/rn-forge-cli/src
```

and the strict docs build for `rn-forge-cli` and `rn-forge-tooling`.

## Acceptance

- A declaration without `namespace` builds the same application as today,
  and every existing `rn-forge-cli` and `rn-forge-tooling` test passes
  unchanged.
- With `namespace = "self"`, `<app> --help` lists `self` and none of the verbs,
  and `<app> self --help` lists every declared verb.
- A root command may share a verb's name when the verbs are namespaced. A root
  command may not share the namespace's name.
- `rn-forge-cli` still does not import `rn_forge.tooling`.

## Handoff to kiln

Once this lands on a commit kiln can pin, kiln's S4.5.5 follow-up:

1. Bumps the pin.
2. Sets `namespace = "self"` and adds `doctor` to `verbs` in both
   `src/rn_forge/kiln/cli.toml` and `.rn-forge/kiln/config.toml`.
3. Deletes `commands.self_doctor` and its `[[cli.commands]]` row.
4. Changes its tests to `kiln self status --json` and `kiln self doctor`.

The owner confirms availability to kiln. kiln does not pick this up on its own.
