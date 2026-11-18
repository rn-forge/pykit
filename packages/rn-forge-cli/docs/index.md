# rn-forge-cli

`rn-forge-cli` is the shared command-line layer for `rn-forge-*` applications.

It provides:

- `CliApp`, a `typer.Typer` subclass wiring the standard options every tool
  takes, and returning an exit code when called so `[project.scripts]` needs
  nothing but `mypkg.cli:app`
- `--log-level`, `--log-file`, `--quiet`, `--json`, `--dry-run`, `--yes`,
  `--set`, and the `CliOptions` a command reads them from
- `ExitCode` and `run`: the error-to-exit-code mapping, applicable to a
  hand-built Typer app too
- `CliSurface`: an application built from a declared `[cli]` table, so a
  repository describes its command line instead of writing it

Where `rn-forge-commons` is runtime-neutral — safe in a web server, a worker or
a container — this package is the *command-line shape*. An ordinary batch
application wants it as much as a developer tool does, which is why it is
separate from `rn-forge-tooling`: that package owns files, installs and
rendering, and a repository that only needs a command line should not have to
install Jinja to get one.

Console output lives one layer down, in `rn-forge-commons`: it is a property of
the process rather than of the command-line parser, and a Django management
command or a worker entry point needs it without taking a Typer dependency. This
package drives it — `--quiet`/`--json` set its mode.

`rn_forge.cli` never imports `rn_forge.tooling`, and `rn_forge.commons` never
imports either; `task lint` proves it.

## Install

```toml
dependencies = ["rn-forge-cli>=0.1,<0.2"]
```

No extras; `testing` installs `assertpy` and `pytest`. Minimum example:
[CLI](guides/cli.md). An `AppException` exits 1 as one line; a bad command line
exits 2; `Ctrl-C` exits 130; any other exception exits 1 with its traceback
logged. See [Exit codes](guides/cli.md#exit-codes).

Use the guides for common workflows and the API reference for module details.
