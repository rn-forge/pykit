"""Public API for ``rn_forge.fastapi``.

FastAPI adapters over :mod:`rn_forge.web`: the plumbing that turns the web
package's wire decisions into exception handlers, ``Depends`` factories, a
router and an OpenAPI repair — and that makes no wire decision of its own::

    from fastapi import FastAPI
    from rn_forge.web import CorrelationIdMiddleware, default_registry
    from rn_forge.fastapi import (
        install_problem_schema,
        operation_id,
        register_problem_handlers,
    )

    registry = default_registry()          # register domain exceptions first
    app = FastAPI(generate_unique_id_function=operation_id)
    app.add_middleware(CorrelationIdMiddleware)
    register_problem_handlers(app, registry=registry)
    install_problem_schema(app, registry=registry)

Six flat modules, all one kind of mechanism — FastAPI adapters over web
primitives — so the package stays flat (kiln D55). There is deliberately **no
``middleware`` module**: ``rn_forge.web.CorrelationIdMiddleware`` is pure ASGI
and installs with ``app.add_middleware(...)`` unchanged, and a one-line wrapper
would exist only to make a table row.

Where the boundaries are
------------------------

- This package imports ``rn-forge-web`` and FastAPI, and never
  ``rn_forge.django``, ``rn_forge.cli`` or ``rn_forge.tooling``.
  ``uv run lint-imports`` proves it.
- **The framework is always imported fully qualified** —
  ``from fastapi import APIRouter``, never ``import fastapi`` — because this
  package is itself named ``fastapi`` one level down.
- **No application factory, no container, no store, no settings.** An
  application passes configuration as arguments; see the wiring guide.
- **Logging is injected, always.** Anything that logs takes a ``log`` callable
  and stays silent when it is ``None``.

There are deliberately no compatibility re-exports in any direction.
"""

from rn_forge.fastapi.auth import basic_auth, bearer_auth, requires
from rn_forge.fastapi.dependencies import (
    page_params,
    require_idempotency_key,
    require_if_match,
)
from rn_forge.fastapi.health import health_router
from rn_forge.fastapi.openapi import (
    OPENAPI_VERSION,
    install_problem_schema,
    operation_id,
)
from rn_forge.fastapi.problem import Log, register_problem_handlers
from rn_forge.fastapi.schemas import (
    CheckResult,
    HealthReport,
    Page,
    ProblemDetail,
    WireModel,
)

__all__ = [
    "OPENAPI_VERSION",
    "CheckResult",
    "HealthReport",
    "Log",
    "Page",
    "ProblemDetail",
    "WireModel",
    "basic_auth",
    "bearer_auth",
    "health_router",
    "install_problem_schema",
    "operation_id",
    "page_params",
    "register_problem_handlers",
    "require_idempotency_key",
    "require_if_match",
    "requires",
]
