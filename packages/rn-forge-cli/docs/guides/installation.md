# Installation

These packages are not published to PyPI. A release is a **git tag**, and a
consumer depends on a tag by pinned direct URL — a bare `uv add rn-forge-cli`
would not resolve, and a floating branch reference would silently change what a
build produced (kiln D46).

```toml
[project]
dependencies = [
  "rn-forge-cli @ git+https://github.com/rn-forge/pykit@rn-forge-cli-v0.1.0#subdirectory=packages/rn-forge-cli",
]
```

For a tool whose command line *is* the product, this belongs in `dependencies`.
For an application that only ships a maintenance command, put it in a `dev`
dependency group instead.

`rn-forge-commons` comes with it, pinned the same way. `rich` and `typer` are
hard dependencies: an application with a command line prints to a terminal and
parses arguments on every run, so there is nothing to gain from making either
optional. Jinja2 is **not** a dependency — that lives in `rn-forge-tooling`.

## Upgrading

Change the tag in the URL. There is no version range to widen: the pin is the
whole mechanism, and a lockfile records the resolved commit.

## The boundary, as an executable rule

The workspace's `.importlinter` contracts state it, and `uv run lint-imports`
proves it:

- `rn_forge.commons` never imports `rn_forge.cli`, `rn_forge.tooling`, Typer or
  Jinja.
- `rn_forge.cli` never imports `rn_forge.tooling` or Jinja.
- The three libraries layer strictly: tooling → cli → commons.
- `rn_forge.django`'s runtime surface never imports any of them — only
  `rn_forge.django.codegen` may, and only with the `codegen` extra installed.
