"""RFC 9457 problem details, and the exception-to-problem registry.

The highest-value module in the package: it is what makes two applications on
two frameworks return the *same* error body for the same situation.

Four pieces:

1. :class:`ProblemDetail` — the wire shape, with ``as_body()`` as the single
   place that knows extensions flatten to the top level (RFC 9457 §3.2).
2. :class:`ProblemRegistry` — exception class → :class:`ProblemType`, resolved
   by MRO so an adapter subclass inherits its base's row automatically.
3. :func:`errors_from_field_map` / :func:`errors_from_pointer_list` — the two
   frameworks' validation-error shapes normalized to one RFC 6901 pointer list.
4. :func:`problem_from_body` — the client-side direction: parse an upstream's
   problem body back into a :class:`ProblemDetail`.

Why this is hand-written
------------------------

``rfc9457`` (0.4.1) was evaluated as the Phase 0.2 candidate and rejected: its
``Problem`` is an ``Exception`` with its own constructor, ``__str__`` and
``__repr__``, which cannot compose with :class:`~rn_forge.commons.exceptions.AppException`
without one of the two losing its contract. It also models no ``instance``
member, carries no registry, and has no parse direction. See
"Dependencies and why" in the package README.

RFC 9457 obsoletes RFC 7807; the media type and the member names are unchanged,
so this shape is correct under either number.
"""

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


# The rows both surveyed implementations converged on, plus the two the
# precondition contract (§3.1) needs. `default_registry()` binds each of them
# to an exception class; they are public so a consumer can re-bind one.
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

    An *instantiable* registry rather than a module-level dict: two
    applications in one process, and a test that wants a clean registry, both
    need instances.

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

        Both framework packages call this rather than keeping a status table of
        their own: a status-to-slug mapping is a wire decision, and two tables
        are two decisions.
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
"""The message a missing field carries, on both stacks. It is DRF's wording."""


def errors_from_pointer_list(raw: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Normalize a FastAPI/pydantic error list into pointer/message pairs.

    pydantic reports ``[{"loc": ("body", "field"), "msg": "...", "type": "..."}, ...]``.
    Each ``loc`` becomes an RFC 6901 JSON pointer, with the two normalizations
    that make the list identical to :func:`errors_from_field_map`'s for the
    same failure — which the conformance table asserts:

    - **A leading ``"body"`` segment is dropped.** FastAPI prefixes the part of
      the request a field came from; the pointer is into the body document,
      which is what DRF's field map already describes. ``query``, ``header``
      and ``path`` locations keep their prefix, being outside the body.
    - **A missing field says** ``"This field is required."`` rather than
      pydantic's ``"Field required"``. Only this one message is translated: it
      is the failure the table pins, and a vocabulary for every validator
      would be a translation layer nobody asked for.

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

    **Recurses.** Nested serializers produce nested dicts, and lists of
    serializers produce lists of dicts; a non-recursive version silently drops
    every nested error. (cims's handler does not recurse — that is a bug fixed
    on the way through, not a behaviour preserved.)

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

    **Tolerant on the way in, strict on the way out.** RFC 9457 requires only
    that the body be a JSON object, every member is optional in practice, and
    upstreams get this wrong — a parser that raised on a slightly-wrong body
    would convert an upstream 404 into a local 500. Missing ``type`` defaults to
    ``about:blank``, missing ``status`` falls back to *status*, and every
    unknown member lands in ``extensions``.

    It takes a parsed mapping and a status, not a response object: no ``httpx``
    or ``requests`` import, so it is usable from a commons ``ResilientHttpClient``
    call site, a Django test, or an async client without any of them becoming a
    dependency of this package.

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
