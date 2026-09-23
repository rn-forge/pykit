# Standard FastAPI application layer

**Status:** implemented, 2026-09-18. Follow-up to the
[FastAPI library plan](fastapi-library-plan.md), prompted by kiln's first
FastAPI + Angular application trial.

## Problem and decision to revisit

`rn-forge-fastapi` already supplies health/readiness routes, problem handlers,
OpenAPI conventions and operation IDs; `rn-forge-web` supplies correlation
middleware. Each application repeats their assembly in its composition root.

The package [README](../../packages/rn-forge-fastapi/README.md) explicitly
excludes an application factory, and its
[wiring guide](../../packages/rn-forge-fastapi/docs/guides/wiring.md) treats
that assembly as application-owned. Revisit this exclusion against pykit's
"wrap for one design language" principle. Standard adapter wiring belongs in
pykit; product routes, settings and infrastructure remain application-owned.
This adds the supported ``AppConfig`` and ``create_app`` API.

## Scope

Add a thin `create_app` factory to `rn-forge-fastapi`, with a typed, frozen
configuration object, injected logging and a normal FastAPI instance as its
result. Final public names and signature are settled during implementation.
Use the existing adapters and wire conventions:

- Install correlation middleware, problem handlers, matching OpenAPI schemas
  and operation IDs, and mount `/healthz` and `/readyz` through `health_router`.
- Accept a configured problem registry, readiness checks and required check
  names, with a finite configurable check timeout. Register domain exceptions
  before installing handlers; use the same registry for OpenAPI.
- Accept application routers and a lifespan hook. Preserve access to normal
  FastAPI APIs for extension; avoid a parallel router or dependency framework.
- Keep settings loading, authentication policy, CORS, database clients and
  other infrastructure explicit and application-owned. No import-time global
  app, environment reads, network calls or implicit resource creation.
- Keep wire decisions in `rn-forge-web` and framework assembly in
  `rn-forge-fastapi`; introduce no runtime dependency on CLI, tooling or kiln.

Health and readiness are the initial shared utility endpoints. Additional
utility endpoints require their own contract and are outside this scope.
Application-file generation and a `[codegen]` extra are also outside scope.

**Superseded, 2026-09-19:** `create_app` was replaced by the `FastApiApp`
subclass — see [web-api-reuse-plan.md, Phase 0](web-api-reuse-plan.md#phase-0--fastapiapp-rn-forge-fastapi).
This section stays as the historical record of the factory it replaced.

## Implementation surface

- Add the factory and configuration in the package's flat module layout and
  export public symbols through its curated `__init__.py` facade.
- Add focused package tests and exercise factory-created apps through the
  existing web conformance cases; preserve coverage of the standalone adapters.
- Revise the package README's factory exclusion, quickstart and wiring guide.
  Document ownership of configuration, registries, checks and lifespan.
- Add API documentation and its package MkDocs navigation entry. Update the
  original library plan to record the revised decision when implemented.

## Acceptance

**Completed, 2026-09-18:** `rn_forge.fastapi.AppConfig` is a frozen, typed
configuration for the shared wiring, and `create_app` returns a normal
`FastAPI` instance. Factory tests cover health semantics, domain problems,
OpenAPI, custom routers, lifespan and per-instance isolation; the existing
web conformance driver now creates its fixture through the factory.

- A minimal caller creates an ASGI app with standard health, readiness, problem
  handling and OpenAPI wiring without repeating adapter installation.
- Liveness does not run dependency checks. Required-check failure and timeout
  yield the established readiness response; optional failures retain the
  existing web semantics.
- Existing conformance cases pass through the factory. Problem responses,
  correlation headers (including server errors) and OpenAPI remain consistent.
- Custom routers and lifespan startup/shutdown work. Separately supplied
  registries, checks and configuration do not leak between app instances.
- Factory construction performs no environment lookup or network access and
  starts no infrastructure. Runtime import boundaries remain intact.
- Package tests, scoped lint/type checks, import contracts and the package's
  strict documentation build pass.

## Downstream handoff to kiln

Once the API is implemented and available through a resolvable pykit ref, kiln
can use it in its web acceptance fixture and generated README. The repo-owned
`app.py` exports the resulting `app` for the existing `task api:dev` target.

The factory does not create `app.py`. Automatic bootstrap-file generation
remains separate framework codegen work under kiln ADR-0011/E10. Until adoption,
kiln's manually composed fixture remains supported; this proposal adds no new
E5 shipping dependency. Kiln owns its task, template and acceptance changes;
this document owns the pykit runtime scope.
