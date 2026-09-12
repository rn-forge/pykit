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

`CliSurface` is a
`StrictDataclassMixin`, so a value whose type does not match its field is
rejected by name rather than surfacing later as an attribute error:

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
