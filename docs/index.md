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
- [rn-forge-web](rn-forge-web/index.md) — framework-agnostic HTTP/API primitives: the correlation
  ID, RFC 9457 problem details and the exception registry, ETag preconditions, AIP-158 cursor
  pagination, the idempotency-store protocol, readiness aggregation, a pure-ASGI correlation
  middleware, the authentication contract, and the conformance table both framework packages are
  tested against. Depends on `rn-forge-commons` and imports no web framework.
- [rn-forge-django](rn-forge-django/index.md) — opinionated Django/DRF integration layer:
  model base classes, a typed settings facade, basic/JWT/SAML auth, and DRF bulk/import/export
  views built on top of `rn-forge-commons`.
- [rn-forge-fastapi](rn-forge-fastapi/index.md) — FastAPI adapters over `rn-forge-web`: problem
  handlers, pydantic mirrors of the wire shapes with a camelCase base model, the OpenAPI error-type
  repair and `operationId` convention, pagination/idempotency/`If-Match` dependencies, a health
  router and the auth binding. Makes no wire decision of its own.

Pick a package above for its guides and API reference.

The development layer is **two** packages, not one: `rn-forge-cli` is what any program with a command
line takes, and `rn-forge-tooling` is what a program that installs itself, owns files in someone
else's repo or renders templates takes. `rn-forge-web` is on the other side of the graph entirely:
`web → commons`, with `django → web → commons` and `fastapi → web → commons` as independent
siblings, so a package that ships into an ASGI server never
reaches the command-line or file-owning layers. There are no compatibility re-exports in any
direction, and `.importlinter` proves the layering. See the [plan execution order](plans/README.md) for what is
still open.
