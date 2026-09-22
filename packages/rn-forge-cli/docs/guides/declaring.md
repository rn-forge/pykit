# Declaring a CLI

`CliApp.from_config` builds a Typer application from a `[cli]` table in a
TOML, YAML or JSON document. You write the command functions; the table names
them, and `CliApp` supplies the app, the standard options and exit-code
handling.

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

| Key | Meaning |
| --- | --- |
| `name` | application name, also the root logger name |
| `help` | the application's `--help` text |
| `default_log_level` | default value of `--log-level` (default `verbose`) |
| `commands[].name` | the name the command is invoked by |
| `commands[].target` | import path, as `module:attribute` or a dotted path |
| `commands[].help` | help text; defaults to the target's docstring |

A `target` that is a `typer.Typer` becomes a subcommand group; a target that is
a function becomes a single command.

## The whole of `cli.py`

```python
from pathlib import Path

from rn_forge.cli import CliApp

app = CliApp.from_config(Path(__file__).parent / "cli.toml")
```

with `golden-app = "golden_app.cli:app"` under `[project.scripts]`. There is no
`main()` — the generated console script is `sys.exit(app())`, and `CliApp`
returns an exit code.

## Validation

The table is validated when it is loaded. A value of the wrong type is rejected
with the offending key named:

```text
AppException: Invalid CliSurface: wrong value type for field "commands.target"
              - should be "str" instead of value "1" of type "int"
```

A missing `[cli]` table, a blank name, duplicate command names and a target
that cannot be imported are rejected the same way.

## Loading from a mapping

`CliSurface.load` also accepts an already-parsed mapping, for a test or an
application with its own config loader. Loading and building are separate
steps, so a configuration can be validated without building the app:

```python
from rn_forge.cli import CliApp, CliSurface

surface = CliSurface.load({"name": "demo", "commands": [...]})   # validates
app = CliApp.from_surface(surface)                                # builds
```

## Building the app in code

When a table is not enough, construct `CliApp` directly, or use a plain
`typer.Typer` and wrap it in [`run`](cli.md#exit-codes) to get the same
exit-code handling.
