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
| the `/healthz` + `/readyz` router | `health_router(checks=..., required=...)` |
| the camelCase alias generator on each model | `WireModel` |
| the `ProblemDetail` injection into `components/schemas` | `install_problem_schema(app)` |
| the `operationId` convention | `operation_id`, passed as `generate_unique_id_function` |

Two rules still apply to any ASGI application, framework or not, and they are
this package's: install `CorrelationIdMiddleware` directly rather than inside a
`BaseHTTPMiddleware`, and never reset the correlation ContextVar on the way out.
The [API conventions](api-conventions.md) remain the normative wire contract for
both stacks.
