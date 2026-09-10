# Declaring a CLI

A repository can describe its command line rather than construct it. The
description lives in whatever configuration document the repository already
has, and `rn_forge.cli.declare` builds the Typer application from it. The
repository writes command functions; it never writes app construction, flag
plumbing or exit-code handling (kiln ADR-0009).

## The `[cli]` table

```toml
[cli]
name = "golden-app"
help = "Do the thing."
log_options = true      # --log-level, --log-file
output_options = true   # --quiet, --json

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
by name, so this module never learns what a command does.

## The whole of `main.py`

```python
from pathlib import Path

from rn_forge.cli import run
from rn_forge.cli.declare import declare

app = declare(Path(__file__).parent.parent / ".rn-forge/kiln/config.toml")


def main() -> int:
    return run(app)
```

## Reading a surface without a file

`load_surface` also accepts an already-parsed mapping, which is what a test or
an application with its own config loader passes:

```python
from rn_forge.cli.declare import build_declared_app, load_surface

app = build_declared_app(load_surface({"name": "demo", "commands": [...]}))
```

## The escape hatch

A repository whose application this cannot describe calls
[`build_app`](cli.md) and constructs its own, using the same primitives.
Dropping down costs nothing and is not a fork — no generated file is involved
either way.
