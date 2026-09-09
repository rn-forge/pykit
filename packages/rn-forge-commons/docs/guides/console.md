# Console output

`AppConsole` is a thin facade over `rich.console.Console` with four output modes:

```python
from rn_forge.commons.console import console, OutputMode

console.info("Starting {}", "job")
console.success("Done in {}s", 1.2)
console.table("name", "status", rows=[("alpha", "ok"), ("beta", "failed")])
```

## The quiet/JSON tri-mode pattern

A CLI typically needs three output personalities: normal (styled, human-readable), `--quiet`
(suppress everything but an optional one-line summary), and `--json` (machine-readable only). Model
that by switching `console`'s mode instead of writing separate code paths:

```python
from rn_forge.commons.console import console, OutputMode

def run(*, quiet: bool = False, json_output: bool = False) -> None:
    if json_output:
        console.set_mode(OutputMode.JSON)
    elif quiet:
        console.set_mode(OutputMode.QUIET)

    result = do_work()

    # One call, three behaviours:
    # - RICH:  prints `result` as Rich would (a Table, a str, ...)
    # - QUIET: prints only quiet_text, or nothing
    # - JSON:  serializes `result` via JsonUtils.serialize
    console.emit(result, quiet_text="ok")
```

`table()` follows the same pattern — it renders a Rich table normally, and emits
`[{column: cell, ...}, ...]` in JSON mode, so call sites never need an `if json: ...` branch:

```python
console.table("name", "status", rows=rows)
```

`warning()`/`error()` always go to stderr; `fail()` calls `error()` then raises `SystemExit` — no
Typer dependency, so it works the same from a plain script as from a Typer command (see the
[CLI guide](cli.md) for the Typer-specific layer built on top of this one).

The underlying `rich.console.Console` is always reachable via `console.rich` for anything this
facade doesn't cover — a `Progress` bar, a `Live` display, or a custom renderable.
