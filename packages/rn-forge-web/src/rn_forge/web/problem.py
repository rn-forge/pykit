"""RFC 9457 problem details and exception-to-problem mapping.

No RFC 9457 library is adopted: ``fastapi-problem`` 0.12.1 (checked 2026-09-23) emits no ``instance``,
sets its own ``type`` and ``title`` instead of ``about:blank`` and the status phrase, and has no
exception-to-status registry.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from types import MappingProxyType
from typing import Any, Final, Protocol, Self, cast, runtime_checkable

from pydantic import ConfigDict, model_validator

from rn_forge.web.models import WireModel
from rn_forge.web.auth import AUTH_FAILED_DETAIL, challenge_header
from rn_forge.web.tracing import TRACE_ID_KEY, current_trace_id
from rn_forge.web.exceptions import (
    AuthenticationFailed,
    ContentTooLarge,
    DomainConflict,
    IdempotencyKeyInFlight,
    IdempotencyKeyRequired,
    IdempotencyKeyReuse,
    InvalidCursor,
    InvalidOrderBy,
    MalformedPrecondition,
    PermissionDenied,
    PreconditionRequired,
    RemoteProblem,
    ServiceUnavailable,
    TooManyRequests,
    VersionConflict,
)

__all__ = [
    "BAD_GATEWAY",
    "BAD_REQUEST",
    "BLANK_TYPE",
    "CONFLICT",
    "CONTENT_TOO_LARGE",
    "FORBIDDEN",
    "GENERIC_SERVER_DETAIL",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "PRECONDITION_FAILED",
    "PRECONDITION_REQUIRED",
    "PROBLEM_MEDIA_TYPE",
    "REQUIRED_FIELD_DETAIL",
    "SERVICE_UNAVAILABLE",
    "TOO_MANY_REQUESTS",
    "UNAUTHORIZED",
    "VALIDATION_ERROR",
    "HasProblemExtensions",
    "HasResponseHeaders",
    "ProblemDetail",
    "ProblemRegistry",
    "ProblemResponse",
    "ProblemType",
    "default_registry",
    "field_error",
    "problem_from_body",
    "render_problem",
    "unmapped_exceptions",
]

PROBLEM_MEDIA_TYPE: Final = "application/problem+json"
"""The ``Content-Type`` every error response in this kit carries."""

GENERIC_SERVER_DETAIL: Final = "An unexpected error occurred."
"""What a 5xx ``detail`` says when the caller did not supply one. See :meth:`ProblemRegistry.build`."""

BLANK_TYPE: Final = "about:blank"
"""RFC 9457's prescribed ``type`` when there is no type URI to give."""

_CORE_MEMBERS: Final = frozenset({"type", "title", "status", "detail", "instance"})


@runtime_checkable
class HasProblemExtensions(Protocol):
    """An exception that contributes extension members to its own problem body.

    :meth:`ProblemRegistry.build` merges the result beneath an explicit
    ``extensions=`` argument and only for a row below 500 — a 5xx body says
    nothing about the cause, so nothing an exception carries reaches the wire
    for one. An application that wants some of ``AppException.error_data`` on
    the wire implements this and chooses the members; ``error_data`` itself is
    never published automatically, since it routinely carries credentials and
    internal identifiers.
    """

    def problem_extensions(self) -> Mapping[str, Any]: ...


@runtime_checkable
class HasResponseHeaders(Protocol):
    """An exception that contributes response headers to its own problem response.

    :func:`render_problem` merges the result beneath an explicit ``headers=``
    argument, so a caller's header always wins a collision.
    """

    def response_headers(self) -> Mapping[str, str]: ...


class ProblemDetail(WireModel):
    """An RFC 9457 problem.

    Extension members are **flattened at the top level on the wire** (RFC 9457
    §3.2): the model allows extra members, and ``ProblemDetail(...,
    extensions={...})`` merges a mapping in as extras. Core members win a
    collision with an extension of the same name.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    type: str
    title: str
    status: int
    detail: str
    instance: str

    @model_validator(mode="before")
    @classmethod
    def _merge_extensions(cls, data: Any) -> Any:
        if isinstance(data, dict) and "extensions" in data:
            merged = dict(cast("dict[str, Any]", data))
            extensions = cast("Mapping[str, Any] | None", merged.pop("extensions"))
            return {**(extensions or {}), **merged}
        return cast(Any, data)

    @property
    def extensions(self) -> dict[str, Any]:
        """The extension members, as a fresh mapping."""
        return dict(self.model_extra or {})

    def as_body(self) -> dict[str, Any]:
        """Return the wire body, extensions merged at the top level."""
        return self.model_dump()


@dataclass(frozen=True)
class ProblemType:
    """A registry row: the slug, status and title a class of failure maps to."""

    slug: str
    status: int
    title: str


# Standard problem rows. `default_registry()` binds each to an exception class;
# they remain public so applications can customize those bindings.
NOT_FOUND: Final = ProblemType("not-found", 404, "Not Found")
VALIDATION_ERROR: Final = ProblemType("validation-error", 422, "Validation Error")
INTERNAL_ERROR: Final = ProblemType("internal-error", 500, "Internal Server Error")
CONFLICT: Final = ProblemType("conflict", 409, "Conflict")
PRECONDITION_FAILED: Final = ProblemType(
    "precondition-failed", 412, "Precondition Failed"
)
PRECONDITION_REQUIRED: Final = ProblemType(
    "precondition-required", 428, "Precondition Required"
)
UNAUTHORIZED: Final = ProblemType("unauthorized", 401, "Unauthorized")
FORBIDDEN: Final = ProblemType("forbidden", 403, "Forbidden")
BAD_REQUEST: Final = ProblemType("bad-request", 400, "Bad Request")
BAD_GATEWAY: Final = ProblemType("bad-gateway", 502, "Bad Gateway")
CONTENT_TOO_LARGE: Final = ProblemType("content-too-large", 413, "Content Too Large")
TOO_MANY_REQUESTS: Final = ProblemType("too-many-requests", 429, "Too Many Requests")
SERVICE_UNAVAILABLE: Final = ProblemType(
    "service-unavailable", 503, "Service Unavailable"
)


class ProblemRegistry:
    """Maps exception classes to problem types, resolving by MRO.

    Args:
        type_base: Prefix for the ``type`` URI. When empty (the default), the
            ``type`` is ``about:blank``, which is what RFC 9457 prescribes when
            there is no type URI to give — a library must not invent a URI
            namespace. When set, ``type`` becomes ``type_base + slug``.
        fallback: The row an unregistered exception resolves to.

    Example::

        registry = ProblemRegistry(type_base="https://errors.example.com/")
        registry.register(OrderLocked, ProblemType("order-locked", 409, "Order Locked"))
        body = registry.build(exc, instance="/orders/17").as_body()
    """

    def __init__(
        self,
        *,
        type_base: str = "",
        fallback: ProblemType = INTERNAL_ERROR,
    ) -> None:
        self._type_base = type_base
        self._fallback = fallback
        self._rows: dict[type[BaseException], ProblemType] = {}

    def register(self, exc_type: type[BaseException], problem: ProblemType) -> Self:
        """Register *problem* for *exc_type*, returning ``self`` for chaining."""
        self._rows[exc_type] = problem
        return self

    @property
    def fallback(self) -> ProblemType:
        """The row an unregistered exception resolves to."""
        return self._fallback

    def rows(self) -> Mapping[type[BaseException], ProblemType]:
        """Return a read-only view of the registered rows, in registration order.

        A framework adapter needs the registered exception *types* — Starlette
        dispatches a handler per class — and an OpenAPI document needs the
        statuses they map to.
        """
        return MappingProxyType(self._rows)

    def problem_for(self, exc: BaseException) -> ProblemType:
        """Return the row for *exc*, walking its MRO before falling back.

        The MRO walk is what makes an adapter subclass resolve to its base
        class's row without anyone remembering to register it.
        """
        for cls in type(exc).__mro__:
            row = self._rows.get(cls)
            if row is not None:
                return row
        return self._fallback

    def problem_for_status(self, status: int) -> ProblemType:
        """Return the row for a bare HTTP status that carries no exception type.

        A framework raises HTTP errors no application registered — a routing
        404, a 405. The row is the **first registered row with that status**, so
        a framework 404 and a ``LookupError`` produce the same body. With no such
        row it is derived from the IANA reason phrase (405 →
        ``method-not-allowed`` / ``Method Not Allowed``); a status with no
        reason phrase resolves to the fallback.

        """
        for row in self._rows.values():
            if row.status == status:
                return row
        try:
            phrase = HTTPStatus(status).phrase
        except ValueError:
            return self._fallback
        return ProblemType(
            "-".join(re.findall(r"[a-z0-9]+", phrase.lower())), status, phrase
        )

    def type_uri(self, problem: ProblemType) -> str:
        """Return the ``type`` member for *problem*."""
        return f"{self._type_base}{problem.slug}" if self._type_base else BLANK_TYPE

    def build(
        self,
        exc: BaseException,
        *,
        instance: str,
        detail: str | None = None,
        extensions: Mapping[str, Any] | None = None,
        problem: ProblemType | None = None,
    ) -> ProblemDetail:
        """Build the problem body for *exc*.

        Args:
            exc: The exception to describe.
            instance: A URI reference identifying this occurrence — in practice
                the request path.
            detail: Overrides the derived detail. Supply it to say something
                more useful than ``str(exc)``.
            extensions: Extra members, flattened onto the wire body. Wins over
                a same-named member *exc* contributes via
                :class:`HasProblemExtensions`.
            problem: The row to build from instead of resolving one from *exc*
                — for a framework HTTP error, :meth:`problem_for_status`'s.

        Returns:
            The problem. When the status is 5xx and *detail* was not supplied,
            the detail is :data:`GENERIC_SERVER_DETAIL` rather than
            ``str(exc)`` — this is the one piece of policy in the module, and
            it is the default because getting it wrong leaks internals.

            When *exc* implements :class:`HasProblemExtensions` and the
            resolved row's status is below 500, its ``problem_extensions()``
            are merged beneath *extensions*. Nothing is merged for a 5xx row —
            a 5xx body says nothing about the cause, and that rule is not
            reachable around.

            ``title`` is *row*'s title only when :attr:`type_uri` resolves to a
            real URI (a ``type_base`` is configured, so the title describes
            it). With ``about:blank``, RFC 9457 §4.2.1 prescribes the HTTP
            status phrase instead.
        """
        row = problem if problem is not None else self.problem_for(exc)
        if detail is not None:
            resolved = detail
        elif row.status >= 500:
            resolved = GENERIC_SERVER_DETAIL
        else:
            resolved = _message_of(exc) or row.title
        merged: dict[str, Any] = {}
        if row.status < 500 and isinstance(exc, HasProblemExtensions):
            merged.update(exc.problem_extensions())
        merged.update(extensions or {})
        return ProblemDetail.model_validate(
            {
                "type": self.type_uri(row),
                "title": row.title if self._type_base else _status_phrase(row.status),
                "status": row.status,
                "detail": resolved,
                "instance": instance,
                "extensions": merged,
            }
        )


def _status_phrase(status: int) -> str:
    """Return the IANA reason phrase for *status*, or the status as a string.

    A status outside :class:`http.HTTPStatus` has no phrase; that is only
    reachable through an application-defined :class:`ProblemType` carrying a
    non-standard status.
    """
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return str(status)


def _message_of(exc: BaseException) -> str:
    """Return the human-readable message of *exc*, and nothing else.

    ``AppException.__str__`` renders ``"<error_code> | <message> | <error_data>"``,
    which is a useful log line and a terrible ``detail`` member — it would put
    the exception's whole context dict on the wire, including whatever a caller
    attached to it. So read ``.message`` when there is one.
    """
    message = getattr(exc, "message", None)
    return message if isinstance(message, str) else str(exc)


@dataclass(frozen=True)
class ProblemResponse:
    """A rendered problem response, ready for a framework to send.

    The body is :attr:`problem`'s wire form and the ``Content-Type`` is
    always :data:`PROBLEM_MEDIA_TYPE`.
    """

    problem: ProblemDetail
    headers: Mapping[str, str]

    @property
    def status(self) -> int:
        """The HTTP status."""
        return self.problem.status

    @property
    def body(self) -> dict[str, Any]:
        """The JSON body, extensions flattened (:meth:`ProblemDetail.as_body`)."""
        return self.problem.as_body()


def render_problem(
    registry: ProblemRegistry,
    exc: BaseException,
    *,
    instance: str,
    problem: ProblemType | None = None,
    detail: str | None = None,
    extensions: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    realm: str | None = None,
) -> ProblemResponse:
    """Render *exc* as a complete problem response: body and headers.

    On top of :meth:`ProblemRegistry.build`:

    - the current span's trace id is the ``traceId`` extension (``null``
      when no span is recording);
    - a 401 carries :data:`~rn_forge.web.auth.AUTH_FAILED_DETAIL` as its
      detail, whatever *detail* says, and a ``WWW-Authenticate`` challenge
      unless *headers* already carries one;
    - when *exc* implements :class:`HasResponseHeaders`, its headers are
      merged beneath *headers*, so an explicit *headers* entry wins.

    Args:
        registry: The rows to render with.
        exc: The exception being rendered.
        instance: The ``instance`` member — in practice the request path.
        problem: The row to use instead of resolving one from *exc*.
        detail: Overrides the derived detail.
        extensions: Extra members, flattened onto the body.
        headers: Response headers to carry, e.g. a framework-built challenge.
        realm: The ``realm`` of the challenge added to a 401.

    Returns:
        The response. Logging a 5xx is the caller's job.
    """
    row = problem if problem is not None else registry.problem_for(exc)
    body = registry.build(
        exc,
        instance=instance,
        detail=AUTH_FAILED_DETAIL if row.status == 401 else detail,
        problem=row,
        extensions={TRACE_ID_KEY: current_trace_id(), **(extensions or {})},
    )
    out: dict[str, str] = {}
    if isinstance(exc, HasResponseHeaders):
        out.update(exc.response_headers())
    out.update(headers or {})
    if row.status == 401 and not any(
        name.lower() == "www-authenticate" for name in out
    ):
        out["WWW-Authenticate"] = challenge_header(realm=realm)
    return ProblemResponse(problem=body, headers=out)


def default_registry(*, type_base: str = "") -> ProblemRegistry:
    """Return a **fresh** registry carrying this package's exceptions.

    A factory, never a shared module-level singleton: a consumer that mutated a
    shared registry would change every other consumer's error bodies.

    Args:
        type_base: Forwarded to :class:`ProblemRegistry`.
    """
    return (
        ProblemRegistry(type_base=type_base)
        .register(DomainConflict, CONFLICT)
        .register(VersionConflict, PRECONDITION_FAILED)
        .register(PreconditionRequired, PRECONDITION_REQUIRED)
        .register(MalformedPrecondition, BAD_REQUEST)
        .register(InvalidCursor, BAD_REQUEST)
        .register(InvalidOrderBy, BAD_REQUEST)
        .register(IdempotencyKeyRequired, BAD_REQUEST)
        .register(IdempotencyKeyReuse, VALIDATION_ERROR)
        .register(IdempotencyKeyInFlight, CONFLICT)
        .register(AuthenticationFailed, UNAUTHORIZED)
        .register(PermissionDenied, FORBIDDEN)
        .register(RemoteProblem, BAD_GATEWAY)
        .register(ContentTooLarge, CONTENT_TOO_LARGE)
        .register(TooManyRequests, TOO_MANY_REQUESTS)
        .register(ServiceUnavailable, SERVICE_UNAVAILABLE)
        .register(LookupError, NOT_FOUND)
        .register(ValueError, VALIDATION_ERROR)
    )


def unmapped_exceptions(
    registry: ProblemRegistry, *bases: type[BaseException]
) -> list[type[BaseException]]:
    """Return every subclass of *bases* that resolves to *registry*'s fallback.

    Recursively walks ``__subclasses__()`` from each base. An application
    calls this from a test or a readiness check to prove its exception table
    is total — a domain error that resolves to the fallback becomes a 500 with
    nothing to catch it.

    Args:
        registry: The registry to check resolution against.
        bases: The exception base classes to walk subclasses of.

    Returns:
        The unmapped subclasses, sorted by qualified name.
    """
    seen: set[type[BaseException]] = set()
    for base in bases:
        _collect_subclasses(base, seen)
    rows = registry.rows()
    unmapped = [
        cls
        for cls in seen
        if _resolve(cls, rows, registry.fallback) is registry.fallback
    ]
    return sorted(unmapped, key=lambda cls: f"{cls.__module__}.{cls.__qualname__}")


def _resolve(
    cls: type[BaseException],
    rows: Mapping[type[BaseException], ProblemType],
    fallback: ProblemType,
) -> ProblemType:
    """Walk *cls*'s MRO for a registered row, mirroring :meth:`ProblemRegistry.problem_for`."""
    for candidate in cls.__mro__:
        row = rows.get(candidate)
        if row is not None:
            return row
    return fallback


def _collect_subclasses(
    cls: type[BaseException], out: set[type[BaseException]]
) -> None:
    """Depth-first collection of every strict subclass of *cls*."""
    for sub in cls.__subclasses__():
        out.add(sub)
        _collect_subclasses(sub, out)


REQUIRED_FIELD_DETAIL: Final = "This field is required."
"""The ``detail`` of a validation error for a missing field, on every stack."""


def field_error(path: Iterable[object], detail: str) -> dict[str, str]:
    """Return one validation-error entry: ``{"pointer": ..., "detail": ...}``.

    The shape is RFC 9457 §3's validation example; a framework binding builds
    one per field message and puts the list under the ``errors`` extension.

    Args:
        path: The field's location, outermost first. Segments are escaped
            per RFC 6901 §3; an empty path is the document root (``""``).
        detail: The human-readable message for that field.

    Example::

        field_error(("items", 1, "qty"), "must be > 0")
        # {"pointer": "/items/1/qty", "detail": "must be > 0"}
    """
    escaped = [str(p).replace("~", "~0").replace("/", "~1") for p in path]
    return {"pointer": "/" + "/".join(escaped) if escaped else "", "detail": detail}


def problem_from_body(status: int, body: Mapping[str, Any]) -> ProblemDetail:
    """Parse an upstream ``application/problem+json`` body back into a problem.

    Missing ``type`` defaults to ``about:blank``, missing ``status`` falls back
    to *status*, and unknown members become extensions.

    Args:
        status: The HTTP status of the response the body came from.
        body: The decoded JSON object.

    Returns:
        The parsed problem.
    """
    parsed_status = body.get("status")
    return ProblemDetail.model_validate(
        {
            "type": str(body.get("type") or BLANK_TYPE),
            "title": str(body.get("title") or ""),
            "status": parsed_status if isinstance(parsed_status, int) else status,
            "detail": str(body.get("detail") or ""),
            "instance": str(body.get("instance") or ""),
            "extensions": {k: v for k, v in body.items() if k not in _CORE_MEMBERS},
        }
    )
