# Wiring rn-forge-web into FastAPI

**This guide moved.** The adapter layer now ships in `rn-forge-fastapi`.
Use that package's "Wiring an application" guide for current setup and its
API reference for the adapter calls. (It is not linked from here: a
per-package docs build cannot link across packages.)

The [API conventions](api-conventions.md) remain the shared wire contract for
both framework adapters.

## If your application predates rn-forge-fastapi

An older application may still carry the hand-written layer this page used to
describe. Each piece maps to one `rn-forge-fastapi` call:

| Hand-written here before | `rn-forge-fastapi` |
| --- | --- |
| the three exception handlers | `register_problem_handlers(app, registry=...)` |
| `page_params`, `require_idempotency_key`, `require_if_match` | the same names, as factories |
| the `/healthz` + `/readyz` router | `health_router(checks=..., required=..., timeout=...)` |
| the camelCase alias generator on each model | `rn_forge.web.WireModel` |
| the `ProblemDetail` injection into `components/schemas` | `FastApiApp.openapi()`, which also declares the problem responses |
| the `operationId` convention | `operation_id`, passed as `generate_unique_id_function` |

Tracing is W3C Trace Context through OpenTelemetry: `FastApiApp` calls
`FastAPIInstrumentor.instrument_app(self)` by default, which wraps the whole
middleware stack. Configure a `TracerProvider` and exporter in the
application, or run under `opentelemetry-instrument`; `rn_forge.web` and
`rn_forge.fastapi` never do either.
