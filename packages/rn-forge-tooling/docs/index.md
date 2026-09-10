# rn-forge-tooling

`rn-forge-tooling` is the file-owning half of the developer-tooling stack for
the `rn-forge-*` command-line tools — `kiln`, `agentkit`, and the framework code
generators that ship as `[codegen]` extras.

It provides:

- a locked, atomically-written JSON state store
- a strict Jinja render engine
- a generation engine: artifact kinds, action classification, transactional apply
- install mechanics: archive extraction for a release bundle
- the documentation-tree checkers, and the `rn-forge-docs` command that runs them

Where `rn-forge-commons` is runtime-neutral — safe in a web server, a worker or
a container — and `rn-forge-cli` is the command-line shape every application
wants, this package is deliberately workstation-shaped: it assumes a
developer's filesystem and a tool that owns files in it. A repository that only
needs a command line takes `rn-forge-cli` and stops there. A package that ships
into a deployed runtime must not depend on this one outside a `codegen` extra;
`uv run lint-imports` enforces that.

Use the guides for common workflows and the API reference for module details.
