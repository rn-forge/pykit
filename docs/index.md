# pykit

`pykit` is a personal dev-kit: a uv workspace of `rn-forge-*` Python packages.

- [rn-forge-commons](rn-forge-commons/index.md) — runtime-neutral Python utilities with no
  web-framework dependency, grouped by kind of mechanism: config loading and structured logging,
  `lang/` (collections, dataclass mixins, reflection), `fs/` (atomic writes, hashing, locks, fenced
  blocks, round-trip documents), `runtime/` (environment guards, subprocess and task helpers, plugin
  loading), `integration/` (messaging, secrets, object-store protocols and resilience), and optional
  pandas/Excel adapters.
- [rn-forge-cli](rn-forge-cli/index.md) — the shared command-line layer for every `rn-forge-*`
  application, developer tool or not: a Rich console facade, the Typer application factory, the
  standard option set, the error-to-exit-code mapping, and the declared `[cli]` surface.
- [rn-forge-tooling](rn-forge-tooling/index.md) — the file-owning developer tooling: a locked JSON
  state store, a strict Jinja engine, the generation engine, release-bundle extraction and the
  documentation-tree checkers. Depends on `rn-forge-cli`.
- [rn-forge-django](rn-forge-django/index.md) — opinionated Django/DRF integration layer:
  model base classes, a typed settings facade, basic/JWT/SAML auth, and DRF bulk/import/export
  views built on top of `rn-forge-commons`.

Pick a package above for its guides and API reference.

The development layer is **two** packages, not one: `rn-forge-cli` is what any program with a command
line takes, and `rn-forge-tooling` is what a program that installs itself, owns files in someone
else's repo or renders templates takes. There are no compatibility re-exports in any direction, and
`.importlinter` proves the layering. See the [plan execution order](plans/README.md) for what is
still open.
