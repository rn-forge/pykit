# CLI

`CliApp` is a `typer.Typer` subclass whose root callback wires the standard options into
`AppLogger` and the `console` singleton from `rn-forge-commons`:

```python
from rn_forge.cli import CliApp

app = CliApp("my-tool", help="Do the thing.")

@app.command()
def run() -> None:
    print("running")
```

and in `pyproject.toml`:

```toml
[project.scripts]
my-tool = "my_tool.cli:app"
```

That is the whole wiring. A generated console script is `sys.exit(app())`, and `CliApp.__call__`
returns a mapped exit code, so the repository writes no `main()` and no exit-code handling.

`my-tool` gets four options for free: `--log-level`/`--log-file` (feeding `AppLogger.initialize`)
and `--quiet`/`--json` (feeding `console`, whose modes are described in the console guide in
`rn-forge-commons`).

Because `CliApp` *is* a `typer.Typer`, every Typer facility works unchanged — `@app.command()`,
`app.add_typer(...)`, and the constructor's full keyword set via `**typer_kwargs`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | `ExitCode.OK` — the command succeeded |
| `1` | `ExitCode.FAILURE` — an `AppException`, or an unexpected error |
| `2` | `ExitCode.USAGE` — a bad command line (Click's own convention) |
| `130` | `ExitCode.INTERRUPTED` — `Ctrl-C` (`128 + SIGINT`) |

An `AppException` is a diagnosed failure: it prints as one line, with its traceback logged at debug
level. Anything else is a defect, and its traceback is logged in full. A command that raises
`typer.Exit(3)` exits `3` — an explicit code is honoured as given.

To apply the same mapping to a hand-built `typer.Typer`, call the free function:

```python
from rn_forge.cli import run

def main() -> int:
    return run(my_plain_typer_app)
```

## Reading the resolved flags in a command

Typer allows `--quiet`/`--json` both before and after the subcommand name (`my-tool --quiet run`
and `my-tool run --quiet`). The root callback only sees the former, so a command that declares its
own copies merges them with `CliOptions.from_context`:

```python
import typer
from rn_forge.cli import CliOptions, JsonOption, QuietOption

@app.command()
def run(ctx: typer.Context, quiet: QuietOption = False, json_output: JsonOption = False) -> None:
    opts = CliOptions.from_context(ctx, quiet=quiet, json_output=json_output).apply(ctx)
    if opts.json_output:
        ...
```

The two steps are separate because they do different things. `from_context` is pure: it reads what
the root callback resolved and merges the command-level flags over it. `apply` is not: it rejects
the mutually-exclusive `--quiet --json` pair, switches `console` into the requested mode, and writes
the merged result back onto the root context. A caller that only wants to *know* the options — a
test, or a command driving its own `AppConsole` — stops after `from_context`.

`dry_run` and `yes` ride along on the same object, so a command that writes anything reads both off
the context instead of threading them through.

## CLI overrides

`SetOption` and `parse_overrides` are the two halves of `--set dotted.key=value`:

```python
from rn_forge.cli import SetOption, parse_overrides

@app.command()
def deploy(overrides: SetOption = None) -> None:
    values = parse_overrides(overrides)
    # --set database.port=5432 --set 'feature_flags=["a", "b"]'
    # {"database": {"port": 5432}, "feature_flags": ["a", "b"]}
```

Each value is parsed first as JSON, then as a TOML scalar, falling back to the raw string. The
nested mapping is exactly the shape `DictUtils.merge_layers` in `rn-forge-commons` takes as its
highest-precedence layer, so an override lands in a layered configuration with its provenance
tracked.

Typer's native `bool` handling (`--flag`/`--no-flag`) covers plain boolean options directly — no
wrapper needed.
