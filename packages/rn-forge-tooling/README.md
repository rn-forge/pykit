# rn-forge-tooling

The shared developer-tooling surface for the `rn-forge-*` command-line tools
(`kiln`, `agentkit`) and for framework code generators shipped as `[codegen]`
extras.

Where [`rn-forge-commons`](../rn-forge-commons/README.md) is runtime-neutral —
safe in a web server, a worker or a container — this package is deliberately
workstation-shaped. It owns:

- `console` — the Rich output facade (`AppConsole`, `OutputMode`, `console`).
- `cli` — Typer application wiring, reusable options and CLI parsers.
- `state` — a locked, atomically-written JSON state store.
- `templates` — a strict Jinja2 render engine.
- `generation` — artifact kinds, action classification and transactional apply.
- `install` — directory locks, atomic symlink flips and archive extraction.
- `docs` — the documentation-tree checkers (structure, links, nav generation).

A package that ships into a deployed runtime (`rn-forge-django`,
`rn-forge-fastapi`) must never depend on this package outside a `codegen`
extra. Tooling may import commons; commons must never import tooling.
