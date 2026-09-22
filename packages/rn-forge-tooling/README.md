# rn-forge-tooling

The file-owning half of the developer-tooling stack: for command-line tools
that install themselves and write files into a repository, and for framework
code generators shipped as `[codegen]` extras.

Where [`rn-forge-commons`](../rn-forge-commons/README.md) is runtime-neutral —
safe in a web server, a worker or a container — and
[`rn-forge-cli`](../rn-forge-cli/README.md) is the command-line shape every
application wants, this package is deliberately workstation-shaped: it assumes
a developer's filesystem and a tool that owns files in it. It owns:

- `state` — a locked, atomically-written JSON state store.
- `templates` — a strict Jinja2 render engine.
- `generation` — artifact kinds, action classification and transactional apply,
  split into `artifacts` (the vocabulary), `plan` (what a write would do) and
  `apply` (making a batch of writes all-or-nothing).
- `install` — the tool lifecycle: `$RNF_HOME` layout (`ToolHome`), release
  sources and verification, archive extraction, the `ToolProduct` seam, and the
  transactional `install`/`upgrade`/`uninstall`/`cleanup`/`status`/`doctor`
  verbs.
- `cli` — `build_tool_app`, which builds an `rn-forge-cli` application from a
  `[cli]` table and adds the lifecycle verbs declared in a `[lifecycle]` table.

A repository that only needs a command line takes `rn-forge-cli` and stops
there. A package that ships into a deployed runtime (`rn-forge-django`,
`rn-forge-fastapi`) must never depend on this package outside a `codegen`
extra. Tooling may import cli and commons; neither may import tooling, and
`uv run lint-imports` proves it.

## Install

Not published to PyPI: a release is a git tag, and a consumer pins one by
direct URL.

```toml
[project]
dependencies = [
  "rn-forge-tooling @ git+https://github.com/rn-forge/pykit@rn-forge-tooling-v0.2.0#subdirectory=packages/rn-forge-tooling",
]
```

`rn-forge-cli` and `rn-forge-commons` come with it, pinned the same way.

## Docs

Full API reference and guides are built with mkdocs:

```bash
uv run --group docs mkdocs serve   # or `mkdocs build`
```

Source lives in [`docs/`](docs), configured via [`mkdocs.yml`](mkdocs.yml).

## Development

From the repo root or this directory:

```bash
uv run pytest packages/rn-forge-tooling
uv run ruff check packages/rn-forge-tooling
uv run pyright
```
