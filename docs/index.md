# pykit

`pykit` is a personal dev-kit: a uv workspace of `rn-forge-*` Python packages.

- [rn-forge-commons](rn-forge-commons/index.md) — general Python utilities with no framework dependency:
  config loading, structured logging, collections/dict/json/yaml helpers, dataclass mixins,
  subprocess/task helpers, and optional pandas/Excel adapters.
- [rn-forge-django](rn-forge-django/index.md) — opinionated Django/DRF integration layer:
  model base classes, a typed settings facade, basic/JWT/SAML auth, and DRF bulk/import/export
  views built on top of `rn-forge-commons`.

Pick a package above for its guides and API reference.

The planned `rn-forge-tooling` extraction will move CLI/console, local state, templates and
installer mechanics out of commons. It remains blocked on owner-reviewed kiln golden repositories;
see the [plan execution order](plans/README.md).
