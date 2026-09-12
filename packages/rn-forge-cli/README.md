# rn-forge-cli

The shared command-line layer for `rn-forge-*` applications: the Typer
application class, the standard option set and the error-to-exit-code mapping.

Where [`rn-forge-commons`](../rn-forge-commons/README.md) is runtime-neutral —
safe in a web server, a worker or a container — this package is the
*command-line shape*. An ordinary batch application wants it just as much as
a developer tool does, which is why it is separate from
[`rn-forge-tooling`](../rn-forge-tooling/README.md), the package that owns
files, installs and rendering. It owns:

- `app` — `CliApp`, a `typer.Typer` subclass wiring the standard options into
  logging and the console; `ExitCode`; and `run`, which applies the mapping to
  any Typer app. Calling a `CliApp` returns an exit code, so `[project.scripts]`
  points straight at the app object.
- `options` — `--log-level`, `--log-file`, `--quiet`, `--json`, `--dry-run`,
  `--yes`, `--set`, `CliOptions` and `parse_overrides`.
- `surface` — `CliSurface`/`CommandSurface`, the records behind a declared
  `[cli]` table, so a repository describes its command line instead of writing
  it (kiln ADR-0009). Validated on load: a wrong type names the offending key.

Console output is **not** here — `AppConsole` lives in `rn-forge-commons`,
because it is a property of the process rather than of the command-line parser,
and `rn_forge.django` may not import this package to reach one. This package
drives it: `--quiet`/`--json` set its mode.

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
from rn_forge.cli import CliApp
from rn_forge.commons import console

app = CliApp("golden-app", "Do the thing.")


@app.command()
def greet(name: str) -> None:
    """Greet someone."""
    console.success("Hello, {}", name)
```

```toml
[project.scripts]
golden-app = "golden_app.cli:app"
```

There is no `main()`: a generated console script is `sys.exit(app())`, and
`CliApp.__call__` returns the mapped exit code.

Or declare the whole surface in configuration instead (kiln ADR-0009):

```python
app = CliApp.from_config(".rn-forge/kiln/config.toml")
```
