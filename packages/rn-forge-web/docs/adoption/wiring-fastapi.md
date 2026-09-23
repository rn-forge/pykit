# Wiring rn-forge-web into FastAPI

**This guide moved.** It was the interim form of the FastAPI adapter layer, and
that layer now ships as the `rn-forge-fastapi` package; its "Wiring an
application" guide is the current version. (It is not linked from here: a
per-package docs build cannot link across packages.)

What the package replaced, so a reader of an older application recognises it:

| Hand-written here before | `rn-forge-fastapi` |
| --- | --- |
| the three exception handlers | `register_problem_handlers(app, registry=...)` |
| `page_params`, `require_idempotency_key`, `require_if_match` | the same names, as factories |
| the `/healthz` + `/readyz` router | `health_router(checks=..., required=..., timeout=...)` |
| the camelCase alias generator on each model | `WireModel` |
| the `ProblemDetail` injection into `components/schemas` | `FastApiApp.openapi()`, which also declares the problem responses |
| the `operationId` convention | `operation_id`, passed as `generate_unique_id_function` |

Tracing is W3C Trace Context through OpenTelemetry: `FastApiApp` calls
`FastAPIInstrumentor.instrument_app(self)` by default, which wraps the whole
middleware stack. Configure a `TracerProvider` and exporter in the
application, or run under `opentelemetry-instrument`; `rn_forge.web` and
`rn_forge.fastapi` never do either.
The [API conventions](api-conventions.md) remain the normative wire contract for
both stacks.
