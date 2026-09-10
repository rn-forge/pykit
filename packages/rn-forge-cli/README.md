# rn-forge-cli

The shared command-line layer for `rn-forge-*` applications: the Typer
application factory, the standard option set, the console conventions and the
error-to-exit-code mapping.

Where [`rn-forge-commons`](../rn-forge-commons/README.md) is runtime-neutral —
safe in a web server, a worker or a container — this package is the *process
and command-line shape*. An ordinary batch application wants it just as much as
a developer tool does, which is why it is separate from
[`rn-forge-tooling`](../rn-forge-tooling/README.md), the package that owns
files, installs and rendering. It owns:

- `console` — the Rich output facade (`AppConsole`, `OutputMode`, `console`).
- `app` — `build_app`, the Typer application factory and its root callback.
- `options` — `--log-level`, `--log-file`, `--quiet`, `--json`, `--dry-run`,
  `--yes`, `CliOptions`, `command_options` and the CLI value parsers.
- `errors` — `ExitCode`, `exit_code_for` and the `run` wrapper a `main()` uses.
- `declare` — builds an application from a declared `[cli]` surface, so a
  repository describes its command line instead of writing it (kiln ADR-0009).

`rn_forge.cli` may import `rn_forge.commons`. It must never import
`rn_forge.tooling`, and `rn_forge.commons` must never import either —
`.importlinter` proves all three.

## Installation

These packages are not published to PyPI; a release is a tag. Depend on this
one by pinned direct URL:

```toml
dependencies = [
  "rn-forge-cli @ git+https://github.com/rn-forge/pykit@rn-forge-cli-v0.1.0#subdirectory=packages/rn-forge-cli",
]
```

## Usage

```python
from rn_forge.cli import build_app, console, run

app = build_app("golden-app", "Do the thing.")


@app.command()
def greet(name: str) -> None:
    """Greet someone."""
    console.success("Hello, {}", name)


def main() -> int:
    return run(app)
```
