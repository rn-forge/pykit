# Installation

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-cli>=0.1,<0.2"]
```

For a tool whose command line *is* the product, this belongs in `dependencies`.
For an application that only ships a maintenance command, put it in a `dev`
dependency group instead.

`rn-forge-commons` comes with it, as a version range. `rich` and `typer` are
hard dependencies: an application with a command line prints to a terminal and
parses arguments on every run, so there is nothing to gain from making either
optional. Jinja2 is **not** a dependency — that lives in `rn-forge-tooling`.

## Upgrading

Raise the version range. A lockfile records the resolved version.

## The boundary, as an executable rule

The workspace's `.importlinter` contracts state it, and `uv run lint-imports`
proves it:

- `rn_forge.commons` never imports `rn_forge.cli`, `rn_forge.tooling`, Typer or
  Jinja.
- `rn_forge.cli` never imports `rn_forge.tooling` or Jinja.
- The three libraries layer strictly: tooling → cli → commons.
- `rn_forge.django`'s runtime surface never imports any of them — only
  `rn_forge.django.codegen` may, and only with the `codegen` extra installed.
