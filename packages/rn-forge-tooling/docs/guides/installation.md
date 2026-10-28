# Installation

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-tooling>=0.3,<0.4"]
```

It is a **development** dependency. Add it to a `dev` group, or to a CLI's own
`dependencies` when the CLI *is* the developer tool.

`rn-forge-cli` and `rn-forge-commons` come with it, as version ranges.

## Upgrading

Raise the version range. A lockfile records the resolved version.

## What lives where

The three libraries split by what an API's signature *contains*, not by who
calls it today:

| Concern | Package |
| -- | -- |
| Typer app factory, standard options, `AppConsole`, exit codes, the `[cli]` surface | `rn-forge-cli` |
| Lifecycle verbs, install | `rn-forge-tooling` |
| Paths, hashes, locks, managed blocks, documents, findings, logging, integration protocols, generation, state, templates (`templates` extra) | `rn-forge-commons` |

There are deliberately **no compatibility re-exports** in any direction: a shim
would satisfy a caller and reverse the dependency.

## The boundary, as an executable rule

The workspace's `.importlinter` contracts state it, and `uv run lint-imports`
proves it:

- `rn_forge.commons` never reaches into `rn_forge.cli` or `rn_forge.tooling` and
  never imports Typer. Jinja and the Markdown parsers enter only through
  `rn_forge.commons.text`, and `rn_forge.commons.generation` and `text` are
  imported directly, never by commons' core or facade.
- `rn_forge.cli` never imports `rn_forge.tooling` or Jinja.
- The three libraries layer strictly: tooling → cli → commons.
- `rn_forge.django`'s runtime surface never imports any of them — only
  `rn_forge.django.codegen` may, and only with the `codegen` extra installed.
