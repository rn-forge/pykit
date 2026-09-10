# CLI

`build_app` returns a `typer.Typer` app whose root callback wires the standard options into
`AppLogger` and `console`:

```python
import typer
from rn_forge.cli import build_app

app = build_app("my-tool", help="Do the thing.")

@app.command()
def run() -> None:
    print("running")

if __name__ == "__main__":
    app()
```

This gives `my-tool` four options for free: `--log-level`/`--log-file` (feeding
`AppLogger.initialize`) and `--quiet`/`--json` (feeding the `console` singleton from
[the console guide](console.md)). Pass `add_log_options=False`/`add_output_options=False` to omit
either pair.

## Reading the resolved flags in a command

```python
from rn_forge.cli import options

@app.command()
def run(ctx: typer.Context) -> None:
    opts = options(ctx)
    if opts.json_output:
        ...
```

Typer allows `--quiet`/`--json` both before and after the subcommand name
(`my-tool --quiet run` and `my-tool run --quiet`). The root callback only sees the former; a command
that wants to accept its own `--quiet`/`--json` too should declare them and merge with
`command_options`:

```python
from rn_forge.cli import JsonOption, QuietOption, command_options

@app.command()
def run(ctx: typer.Context, quiet: QuietOption = False, json_output: JsonOption = False) -> None:
    opts = command_options(ctx, quiet=quiet, json_output=json_output)
```

## CLI overrides

`parse_key_values` collects flat `KEY=VALUE` pairs; `parse_overrides` is its dotted-path, typed
sibling for `--set` style config overrides, producing a nested mapping meant to be merged as the
highest-precedence layer over a loaded config (see `DictUtils.merge` in `rn-forge-commons`):

```python
from rn_forge.cli import parse_overrides

parse_overrides(["database.port=5432", "feature_flags=[\"a\", \"b\"]"])
# {"database": {"port": 5432}, "feature_flags": ["a", "b"]}
```

Each value is parsed first as JSON, then as a TOML scalar, falling back to the raw string.

Typer's native `bool` handling (`--flag`/`--no-flag`) covers plain boolean options directly — no
wrapper needed.
