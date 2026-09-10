# Installation

These packages are not published to PyPI. A release is a **git tag**, and a
consumer depends on a tag by pinned direct URL — a bare `uv add
rn-forge-tooling` would not resolve, and a floating branch reference would
silently change what a build produced (kiln D46).

```toml
[project]
dependencies = [
  "rn-forge-tooling @ git+https://github.com/rn-forge/pykit@rn-forge-tooling-v0.2.0#subdirectory=packages/rn-forge-tooling",
]
```

It is a **development** dependency. Add it to a `dev` group, or to a CLI's own
`dependencies` when the CLI *is* the developer tool.

`rn-forge-cli` and `rn-forge-commons` come with it, pinned the same way.
`jinja2` and `markdown` are hard dependencies: a tool that generates files
renders templates on every run, and the docs checkers ask Python-Markdown what
anchor a heading gets rather than guessing.

## Upgrading

Change the tag in the URL. There is no version range to widen: the pin is the
whole mechanism, and a lockfile records the resolved commit.

## What lives where

The three libraries split by what an API's signature *contains*, not by who
calls it today:

| Concern | Package |
| --- | --- |
| Typer app factory, standard options, `AppConsole`, exit codes, the `[cli]` surface | `rn-forge-cli` |
| Generation, templates, state, install, docs checkers | `rn-forge-tooling` |
| Paths, hashes, locks, managed blocks, documents, findings, logging, integration protocols | `rn-forge-commons` |

There are deliberately **no compatibility re-exports** in any direction: a shim
would satisfy a caller and reverse the dependency.

## The boundary, as an executable rule

The workspace's `.importlinter` contracts state it, and `uv run lint-imports`
proves it:

- `rn_forge.commons` never imports `rn_forge.cli`, `rn_forge.tooling`, Typer or
  Jinja.
- `rn_forge.cli` never imports `rn_forge.tooling` or Jinja.
- The three libraries layer strictly: tooling → cli → commons.
- `rn_forge.django`'s runtime surface never imports any of them — only
  `rn_forge.django.codegen` may, and only with the `codegen` extra installed.
