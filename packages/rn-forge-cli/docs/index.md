# rn-forge-cli

`rn-forge-cli` is the shared command-line layer for `rn-forge-*` applications.

It provides:

- a Rich output facade with RICH/PLAIN/QUIET/JSON modes
- a Typer application factory wiring the standard options every tool takes
- `--log-level`, `--log-file`, `--quiet`, `--json`, `--dry-run`, `--yes`, and
  the `CliOptions` a command reads them from
- the error-to-exit-code mapping, and the `run` wrapper a `main()` uses
- `declare`: an application built from a declared `[cli]` surface, so a
  repository describes its command line instead of writing it

Where `rn-forge-commons` is runtime-neutral — safe in a web server, a worker or
a container — this package is the *process and command-line shape*. An ordinary
batch application wants it as much as a developer tool does, which is why it is
separate from `rn-forge-tooling`: that package owns files, installs and
rendering, and a repository that only needs a command line should not have to
install Jinja to get one.

`rn_forge.cli` never imports `rn_forge.tooling`, and `rn_forge.commons` never
imports either; `uv run lint-imports` proves it.

Use the guides for common workflows and the API reference for module details.
