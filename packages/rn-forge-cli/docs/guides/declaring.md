# Declaring a CLI

A repository can describe its command line rather than construct it. The
description lives in whatever configuration document the repository already
has, and `CliApp.from_config` builds the application from it. The repository
writes command functions; it never writes app construction, flag plumbing or
exit-code handling (kiln ADR-0009).

## The `[cli]` table

```toml
[cli]
name = "golden-app"
help = "Do the thing."
default_log_level = "verbose"

[[cli.commands]]
name = "sync"
target = "golden_app.commands.sync:sync"

[[cli.commands]]
name = "db"
help = "Database maintenance."
target = "golden_app.commands.db:app"
```

A `target` naming a `typer.Typer` becomes a subcommand namespace; a target
naming a function becomes a single command. Either way the target is imported
by name, so nothing here learns what a command does.

## Lifecycle verbs: `[cli.lifecycle]`

An installable tool also declares its lifecycle verbs. The table names the
product object the verbs act on and the factory that builds them:

```toml
[cli.lifecycle]
product = "golden_tool.product:PRODUCT"
target = "rn_forge.tooling.cli.lifecycle:lifecycle_commands"
verbs = ["status", "doctor"]    # optional; default: all six
```

| Key | Meaning |
| --- | --- |
| `product` | import path of the product object |
| `target` | import path of a factory called as `factory(product, verbs)` that returns a `typer.Typer` |
| `verbs` | any of `install`, `upgrade`, `uninstall`, `cleanup`, `status`, `doctor` |

The verbs are mounted at the root of the application: `golden-tool doctor`,
not `golden-tool lifecycle doctor`. A verb that repeats a `[[cli.commands]]`
name, an unknown verb, or a factory that does not return a Typer app is
rejected when the application is built.

`target` is a string, not a default, on purpose. The factory and the product
protocol live in `rn-forge-tooling`, the file-owning layer, and this package
may not import it. A repository that declares lifecycle verbs depends on
`rn-forge-tooling`; one that does not never loads it. Whether a repository has
the table at all is its manager's decision — kiln renders it for a repository
whose config sets `lifecycle = true`.

## The whole of `cli.py`

```python
from pathlib import Path

from rn_forge.cli import CliApp

app = CliApp.from_config(Path(__file__).parent.parent / ".rn-forge/kiln/config.toml")
```

with `my-tool = "golden_app.cli:app"` under `[project.scripts]`. There is no
`main()` — the generated console script is `sys.exit(app())`, and `CliApp`
returns an exit code.

## The table is validated

`CliSurface` is parsed strictly, as every `DataclassMixin` is, so a value whose
type does not match its field is rejected by name rather than surfacing later
as an attribute error:

```text
AppException: Invalid CliSurface: wrong value type for field "commands.target"
              - should be "str" instead of value "1" of type "int"
```

A missing `[cli]` table, a blank name and duplicate command names are rejected
the same way. This matters because the table is written by hand.

## Reading a surface without a file

`CliSurface.load` also accepts an already-parsed mapping, which is what a test
or an application with its own config loader passes. Because the record and the
application are separate, a configuration can be *checked* without building a
Typer app to do it:

```python
from rn_forge.cli import CliApp, CliSurface

surface = CliSurface.load({"name": "demo", "commands": [...]})   # validates
app = CliApp.from_surface(surface)                                # builds
```

## The escape hatch

A repository whose application this cannot describe constructs `CliApp`
directly — or drops to a plain `typer.Typer` and wraps it in
[`run`](cli.md#exit-codes), using the same primitives. Dropping down costs
nothing and is not a fork; no generated file is involved either way.
