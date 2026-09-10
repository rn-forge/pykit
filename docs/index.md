# pykit

`pykit` is a personal dev-kit: a uv workspace of `rn-forge-*` Python packages.

- [rn-forge-commons](rn-forge-commons/index.md) — general Python utilities with no framework dependency:
  config loading, structured logging, collections/dict/json/yaml helpers, dataclass mixins,
  subprocess/task helpers, and optional pandas/Excel adapters.
- [rn-forge-tooling](rn-forge-tooling/index.md) — the developer-tooling surface for the
  `rn-forge-*` CLIs: Rich console, Typer wiring, local JSON state, a strict Jinja engine, the
  generation engine, installer mechanics and the documentation-tree checkers.
- [rn-forge-django](rn-forge-django/index.md) — opinionated Django/DRF integration layer:
  model base classes, a typed settings facade, basic/JWT/SAML auth, and DRF bulk/import/export
  views built on top of `rn-forge-commons`.

Pick a package above for its guides and API reference.

The `rn-forge-tooling` extraction has landed: CLI/console, local state, templates and installer
mechanics moved out of commons, with no compatibility re-exports. See the
[plan execution order](plans/README.md) for what is still open.
