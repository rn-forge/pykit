# rn-forge-tooling

[Documentation](https://rn-forge.github.io/pykit/packages/rn-forge-tooling/latest/)
·
[Changelog](https://github.com/rn-forge/pykit/blob/main/packages/rn-forge-tooling/CHANGELOG.md)
·
[Source](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-tooling)
· [All pykit packages](https://rn-forge.github.io/pykit/)

The lifecycle and install layer of the developer-tooling stack: for command-line
tools that install themselves and manage their own versions. File generation,
local state and templates live in `rn-forge-commons`.

Where
[`rn-forge-commons`](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-commons)
is runtime-neutral — safe in a web server, a worker or a container — and
[`rn-forge-cli`](https://github.com/rn-forge/pykit/tree/main/packages/rn-forge-cli)
is the command-line shape every application wants, this package is deliberately
workstation-shaped: it assumes a developer's filesystem and a tool that owns
files in it. It owns:

- `install` — the tool lifecycle: `$RNF_HOME` layout (`ToolHome`), release
  sources and verification, archive extraction, the `ToolProduct` seam, and
  the transactional
  `install`/`upgrade`/`uninstall`/`cleanup`/`status`/`doctor` verbs.
- `cli` — `build_tool_app`, which builds an `rn-forge-cli` application from a
  `[cli]` table and adds the lifecycle verbs declared in a `[lifecycle]`
  table.

A repository that only needs a command line takes `rn-forge-cli` and stops
there. A package that ships into a deployed runtime (`rn-forge-django`,
`rn-forge-fastapi`) must never depend on this package outside a `codegen` extra.
Tooling may import cli and commons; neither may import tooling, and `task lint`
proves it.

## Install

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-tooling>=0.3,<0.4"]
```

`rn-forge-cli` and `rn-forge-commons` come with it, as version ranges. The
`testing` extra installs `assertpy` and `pytest`.

## Minimum example

```toml
# cli.toml
[cli]
name = "golden-tool"
help = "A tool that manages its own install."

[lifecycle]
product = "golden_tool.product:PRODUCT"
```

```python
from pathlib import Path

from rn_forge.tooling.cli.lifecycle import build_tool_app

app = build_tool_app(Path(__file__).parent / "cli.toml")
```

## Errors

`install` and `upgrade` roll back on failure and re-raise as an `AppException`
whose message says "rolled back" only when every undo step succeeded; otherwise
it names each failed step. An interruption is re-raised as is after recovery.

Maintainer commands are in the
[development guide](https://rn-forge.github.io/pykit/guides/development/).
