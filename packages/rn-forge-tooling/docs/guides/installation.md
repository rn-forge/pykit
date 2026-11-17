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

## The boundary

`rn_forge.tooling` may import `rn_forge.cli` and `rn_forge.commons`; neither may
import it; `task lint` proves it. The
[workspace boundaries](https://rn-forge.github.io/pykit/architecture/workspace/)
page explains the rest.
