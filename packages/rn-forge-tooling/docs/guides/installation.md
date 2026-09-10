# Installation

```bash
uv add rn-forge-tooling
```

It is a **development** dependency. Add it to a `dev` group, or to a CLI's own
`dependencies` when the CLI *is* the developer tool:

```toml
[dependency-groups]
dev = ["rn-forge-tooling"]
```

`rich`, `typer` and `jinja2` are hard dependencies: a tool that generates files
renders templates and prints to a terminal on every run, so there is nothing to
gain from making either optional. `rn-forge-commons` comes with it.

## What moved here from `rn-forge-commons`

These modules lived in `rn_forge.commons` while their runtime boundary was
still under review. There are deliberately **no compatibility re-exports** —
commons re-exporting from tooling would reverse the dependency and create a
cycle.

| Was | Now |
| --- | --- |
| `rn_forge.commons.console` | [`rn_forge.tooling.console`](../api/console.md) |
| `rn_forge.commons.cli` | [`rn_forge.tooling.cli`](../api/cli.md) |
| `rn_forge.commons.state` | [`rn_forge.tooling.state`](../api/state.md) |
| `rn_forge.commons.templates` (`templates` extra) | [`rn_forge.tooling.templates`](../api/templates.md) |
| `DirectoryLock`, `PathUtils.atomic_symlink`, `PathUtils.extract_archive` | [`rn_forge.tooling.install`](../api/install.md) |

`ContentHash`, `PathUtils.atomic_write`, `PathUtils.backup`, the path guards,
`DocumentUtils` and `EntryPointLoader` stayed in commons: safe writes and stable
hashes are useful in every runtime, not only on a workstation.

## The boundary, as an executable rule

The workspace's `.importlinter` contracts state it, and `uv run lint-imports`
proves it:

- `rn_forge.commons` never imports `rn_forge.tooling`, Typer or Jinja.
- `rn_forge.django`'s runtime surface never imports `rn_forge.tooling`, Typer or
  Jinja — only `rn_forge.django.codegen` may, and only with the `codegen` extra
  installed.
