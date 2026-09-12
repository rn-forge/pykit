"""Public API for ``rn_forge.web``.

Framework-agnostic HTTP/API primitives: the wire semantics an application
*promises its callers*, shared by Django/DRF, FastAPI/Starlette and anything
else that speaks HTTP::

    from rn_forge.web import (
        CorrelationIdMiddleware,
        ProblemDetail,
        check_precondition,
        default_registry,
    )

    registry = default_registry()
    body = registry.build(exc, instance=request.path).as_body()

Nine modules, all one kind of mechanism — inbound HTTP wire semantics — which
is why the package stays flat rather than grouping by sub-package the way
``rn_forge.commons`` does. That is a decision, not an accident (kiln D55): this
curated ``__init__`` is what would make a later regrouping cheap, because
moving a module would not move a public name.

Where the boundaries are
------------------------

- This package imports **``rn-forge-commons`` and nothing else in the
  workspace**, and no web framework: not ``django``, not ``fastapi``, not
  ``starlette``, not ``rest_framework``. Nor ``rn_forge.cli`` or
  ``rn_forge.tooling`` — a package that ships into an ASGI server has no
  business reaching the command-line or file-owning layers.
  ``uv run lint-imports`` proves all of it.
- **Inbound, not outbound.** A circuit breaker, a retry policy and a token
  bucket are transport-agnostic and live in ``rn_forge.commons.integration.resilience``
  — a worker retrying a database call needs them and serves no HTTP. The one
  concern that runs the other way is :func:`~rn_forge.web.problem.problem_from_body`,
  which parses an *upstream's* problem body; it is a pure function over a
  mapping precisely so no client library is pulled in either direction.
- **Protocols here, adapters elsewhere.** This package declares
  :class:`~rn_forge.web.idempotency.IdempotencyStore` and implements only an
  in-memory test double. Django implements it over the cache; a SQLAlchemy app
  over its outbox table.
- **Logging is injected, always.** Nothing here imports ``AppLogger``. Anything
  that logs takes a ``log`` callable and stays silent when it is ``None``.

There are deliberately no compatibility re-exports in any direction.
"""

from rn_forge.web.asgi import (
    ASGIApp,
    CorrelationIdMiddleware,
    Message,
    Receive,
    Scope,
    Send,
)
from rn_forge.web.auth import (
    AUTH_FAILED_DETAIL,
    AsyncAuthenticator,
    Authenticator,
    Authorizer,
    BearerErrorCode,
    Credentials,
    Principal,
    Requirement,
    ScopeAuthorizer,
    challenge_header,
)
from rn_forge.web.concurrency import (
    ANY_ETAG,
    EntityVersionETagCodec,
    ETagCodec,
    VersionETagCodec,
    check_precondition,
)
from rn_forge.web.conformance import (
    CASES,
    REDACTED,
    VARIABLE_MEMBERS,
    ConformanceArea,
    ConformanceCase,
    RequestSpec,
    case_by_id,
    cases_for,
    redact,
)
from rn_forge.web.context import (
    DEFAULT_CORRELATION_HEADER,
    bind_correlation_id,
    correlation_id_var,
    correlation_log_processor,
    get_correlation_id,
    new_correlation_id,
    require_correlation_id,
    set_correlation_id,
)
from rn_forge.web.exceptions import (
    AuthenticationFailed,
    DomainConflict,
    IdempotencyKeyRequired,
    IdempotencyKeyReuse,
    InvalidCursor,
    MalformedPrecondition,
    PermissionDenied,
    PreconditionRequired,
    RemoteProblem,
    VersionConflict,
    WebError,
)
from rn_forge.web.health import (
    Check,
    CheckResult,
    CheckStatus,
    HealthReport,
    run_checks,
    run_checks_sync,
)
from rn_forge.web.idempotency import (
    AsyncIdempotencyStore,
    IdempotencyStore,
    InMemoryAsyncIdempotencyStore,
    InMemoryIdempotencyStore,
    StoredResponse,
    request_hash,
)
from rn_forge.web.pagination import (
    DEFAULT_PAGE_SIZE_PARAM,
    DEFAULT_PAGE_TOKEN_PARAM,
    Cursor,
    Page,
    clamp_page_size,
    decode_cursor,
    encode_cursor,
    next_link_header,
)
from rn_forge.web.problem import (
    BAD_GATEWAY,
    BAD_REQUEST,
    BLANK_TYPE,
    CONFLICT,
    FORBIDDEN,
    GENERIC_SERVER_DETAIL,
    INTERNAL_ERROR,
    NOT_FOUND,
    PRECONDITION_FAILED,
    PRECONDITION_REQUIRED,
    PROBLEM_MEDIA_TYPE,
    UNAUTHORIZED,
    VALIDATION_ERROR,
    ProblemDetail,
    ProblemRegistry,
    ProblemType,
    default_registry,
    errors_from_field_map,
    errors_from_pointer_list,
    problem_from_body,
)

__all__ = [
    "ANY_ETAG",
    "ASGIApp",
    "AUTH_FAILED_DETAIL",
    "BAD_GATEWAY",
    "BAD_REQUEST",
    "BLANK_TYPE",
    "CASES",
    "CONFLICT",
    "DEFAULT_CORRELATION_HEADER",
    "DEFAULT_PAGE_SIZE_PARAM",
    "DEFAULT_PAGE_TOKEN_PARAM",
    "FORBIDDEN",
    "GENERIC_SERVER_DETAIL",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "PRECONDITION_FAILED",
    "PRECONDITION_REQUIRED",
    "PROBLEM_MEDIA_TYPE",
    "REDACTED",
    "UNAUTHORIZED",
    "VALIDATION_ERROR",
    "VARIABLE_MEMBERS",
    "AsyncAuthenticator",
    "AsyncIdempotencyStore",
    "AuthenticationFailed",
    "Authenticator",
    "Authorizer",
    "BearerErrorCode",
    "Check",
    "CheckResult",
    "CheckStatus",
    "ConformanceArea",
    "ConformanceCase",
    "CorrelationIdMiddleware",
    "Credentials",
    "Cursor",
    "DomainConflict",
    "ETagCodec",
    "EntityVersionETagCodec",
    "HealthReport",
    "IdempotencyKeyRequired",
    "IdempotencyKeyReuse",
    "IdempotencyStore",
    "InMemoryAsyncIdempotencyStore",
    "InMemoryIdempotencyStore",
    "InvalidCursor",
    "MalformedPrecondition",
    "Message",
    "Page",
    "PermissionDenied",
    "PreconditionRequired",
    "Principal",
    "ProblemDetail",
    "ProblemRegistry",
    "ProblemType",
    "Receive",
    "RemoteProblem",
    "RequestSpec",
    "Requirement",
    "Scope",
    "ScopeAuthorizer",
    "Send",
    "StoredResponse",
    "VersionConflict",
    "VersionETagCodec",
    "WebError",
    "bind_correlation_id",
    "case_by_id",
    "cases_for",
    "challenge_header",
    "check_precondition",
    "clamp_page_size",
    "correlation_id_var",
    "correlation_log_processor",
    "decode_cursor",
    "default_registry",
    "encode_cursor",
    "errors_from_field_map",
    "errors_from_pointer_list",
    "get_correlation_id",
    "new_correlation_id",
    "next_link_header",
    "problem_from_body",
    "redact",
    "request_hash",
    "require_correlation_id",
    "run_checks",
    "run_checks_sync",
    "set_correlation_id",
]
