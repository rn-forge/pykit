"""RFC 9457 problem details and exception-to-problem mapping."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from http import HTTPStatus
from types import MappingProxyType
from typing import Any, Final, Self, cast

from rn_forge.commons.lang.dataclasses import DataclassMixin
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
)

__all__ = [
    "BAD_GATEWAY",
    "BAD_REQUEST",
    "BLANK_TYPE",
    "CONFLICT",
    "FORBIDDEN",
    "GENERIC_SERVER_DETAIL",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "PRECONDITION_FAILED",
    "PRECONDITION_REQUIRED",
    "PROBLEM_MEDIA_TYPE",
    "UNAUTHORIZED",
    "VALIDATION_ERROR",
    "ProblemDetail",
    "ProblemRegistry",
    "ProblemType",
    "default_registry",
    "errors_from_field_map",
    "errors_from_pointer_list",
    "problem_from_body",
]

PROBLEM_MEDIA_TYPE: Final = "application/problem+json"
"""The ``Content-Type`` every error response in this kit carries."""

GENERIC_SERVER_DETAIL: Final = "An unexpected error occurred."
"""What a 5xx ``detail`` says when the caller did not supply one. See :meth:`ProblemRegistry.build`."""

BLANK_TYPE: Final = "about:blank"
"""RFC 9457's prescribed ``type`` when there is no type URI to give."""

_CORE_MEMBERS: Final = frozenset({"type", "title", "status", "detail", "instance"})


@dataclass(frozen=True)
class ProblemDetail(DataclassMixin):
    """An RFC 9457 problem, as it is modelled in Python.

    ``extensions`` is nested here and **flattened at the top level on the
    wire** — RFC 9457 §3.2 puts extension members directly on the object.
    Keeping them nested in the dataclass is what makes :meth:`as_body` the
    single place that knows the rule.
    """

    type: str
    title: str
    status: int
    detail: str
    instance: str
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])

    def as_body(self) -> dict[str, Any]:
        """Flatten to the wire body, extensions merged at the top level.

        Core members win a collision with an extension of the same name: a
        problem whose ``status`` extension disagreed with its ``status`` member
        would be unparseable by any conforming client.
        """
        body: dict[str, Any] = {
            k: v for k, v in self.extensions.items() if k not in _CORE_MEMBERS
        }
        body.update(
            {
                "type": self.type,
                "title": self.title,
                "status": self.status,
                "detail": self.detail,
                "instance": self.instance,
            }
        )
        return body


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
            extensions: Extra members, flattened onto the wire body.
            problem: The row to build from instead of resolving one from *exc*
                — for a framework HTTP error, :meth:`problem_for_status`'s.

        Returns:
            The problem. When the status is 5xx and *detail* was not supplied,
            the detail is :data:`GENERIC_SERVER_DETAIL` rather than
            ``str(exc)`` — this is the one piece of policy in the module, and
            it is the default because getting it wrong leaks internals.
        """
        row = problem if problem is not None else self.problem_for(exc)
        if detail is not None:
            resolved = detail
        elif row.status >= 500:
            resolved = GENERIC_SERVER_DETAIL
        else:
            resolved = _message_of(exc) or row.title
        return ProblemDetail(
            type=self.type_uri(row),
            title=row.title,
            status=row.status,
            detail=resolved,
            instance=instance,
            extensions=dict(extensions or {}),
        )


def _message_of(exc: BaseException) -> str:
    """Return the human-readable message of *exc*, and nothing else.

    ``AppException.__str__`` renders ``"<error_code> | <message> | <error_data>"``,
    which is a useful log line and a terrible ``detail`` member — it would put
    the exception's whole context dict on the wire, including whatever a caller
    attached to it. So read ``.message`` when there is one.
    """
    message = getattr(exc, "message", None)
    return message if isinstance(message, str) else str(exc)


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
        .register(IdempotencyKeyRequired, BAD_REQUEST)
        .register(IdempotencyKeyReuse, CONFLICT)
        .register(AuthenticationFailed, UNAUTHORIZED)
        .register(PermissionDenied, FORBIDDEN)
        .register(RemoteProblem, BAD_GATEWAY)
        .register(LookupError, NOT_FOUND)
        .register(ValueError, VALIDATION_ERROR)
    )


_REQUIRED_FIELD_MESSAGE: Final = "This field is required."
"""The normalized validation message for a missing field."""


def errors_from_pointer_list(raw: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Normalize a FastAPI/pydantic error list into pointer/message pairs.

    Leading ``body`` locations are removed and missing-field messages are
    normalized. Other location prefixes and messages are preserved.

    Args:
        raw: The ``errors()`` output of a pydantic validation error.

    Returns:
        ``[{"pointer": "/field", "message": "..."}, ...]``.
    """
    return [
        {
            "pointer": _pointer(_body_relative(entry.get("loc") or ())),
            "message": _REQUIRED_FIELD_MESSAGE
            if entry.get("type") == "missing"
            else str(entry.get("msg", "")),
        }
        for entry in raw
    ]


def _body_relative(loc: Sequence[Any]) -> Sequence[Any]:
    """Drop FastAPI's leading ``"body"`` location segment, if there is one."""
    return loc[1:] if loc and loc[0] == "body" else loc


def errors_from_field_map(raw: Mapping[str, Any]) -> list[dict[str, str]]:
    """Normalize a DRF-style ``{field: [messages]}`` map into pointer/message pairs.

    Nested mappings and lists are traversed recursively.

    Args:
        raw: A DRF ``serializer.errors`` mapping.

    Returns:
        ``[{"pointer": "/field", "message": "..."}, ...]``, one entry per
        message, in traversal order.
    """
    errors: list[dict[str, str]] = []
    _walk_field_map(raw, (), errors)
    return errors


def _walk_field_map(
    node: Any, path: tuple[str, ...], out: list[dict[str, str]]
) -> None:
    """Depth-first walk of a DRF error tree, appending pointer/message pairs."""
    if isinstance(node, Mapping):
        for key, value in cast("Mapping[Any, Any]", node).items():
            _walk_field_map(value, (*path, str(key)), out)
    elif isinstance(node, (list, tuple)):
        items: list[Any] = list(cast("Sequence[Any]", node))
        # A list of scalars is a field's messages; a list of mappings is a
        # nested serializer, and the index is part of the pointer.
        scalars = all(not isinstance(item, (Mapping, list, tuple)) for item in items)
        for index, item in enumerate(items):
            _walk_field_map(item, path if scalars else (*path, str(index)), out)
    else:
        out.append({"pointer": _pointer(path), "message": str(node)})


def _pointer(parts: Iterable[Any]) -> str:
    """Build an RFC 6901 JSON pointer, escaping ``~`` and ``/`` per §3."""
    escaped = [str(p).replace("~", "~0").replace("/", "~1") for p in parts]
    return "/" + "/".join(escaped) if escaped else ""


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
    return ProblemDetail(
        type=str(body.get("type") or BLANK_TYPE),
        title=str(body.get("title") or ""),
        status=parsed_status if isinstance(parsed_status, int) else status,
        detail=str(body.get("detail") or ""),
        instance=str(body.get("instance") or ""),
        extensions={k: v for k, v in body.items() if k not in _CORE_MEMBERS},
    )
