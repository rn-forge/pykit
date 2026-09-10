# rn-forge-tooling

`rn-forge-tooling` is the shared developer-tooling surface for the `rn-forge-*`
command-line tools — `kiln`, `agentkit`, and the framework code generators that
ship as `[codegen]` extras.

It provides:

- a Rich output facade with RICH/PLAIN/QUIET/JSON modes
- Typer application wiring for the standard options every tool takes
- a locked, atomically-written JSON state store
- a strict Jinja render engine
- a generation engine: artifact kinds, action classification, transactional apply
- workstation install mechanics: directory locks, atomic symlinks, archive extraction
- the documentation-tree checkers, and the `rn-forge-docs` command that runs them

Where `rn-forge-commons` is runtime-neutral — safe
in a web server, a worker or a container — this package is deliberately
workstation-shaped. A package that ships into a deployed runtime must not depend
on it outside a `codegen` extra; `uv run lint-imports` enforces that.

Use the guides for common workflows and the API reference for module details.
