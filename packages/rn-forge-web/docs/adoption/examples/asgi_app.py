"""A complete application over `rn_forge.web`, on bare ASGI and nothing else.

This is the reference implementation of the conformance fixture surface, and
this package's own test suite runs every case in
`rn_forge.web.conformance.CASES` through it — so it is executable proof that
the primitives compose into the contract, and the first of the three
independent proofs the table is designed to collect.

Deliberately no framework: no routing library, no serialization library, no
dependency injection. Everything below is either `rn_forge.web` or the standard
library, which is what makes it a fair test of the package boundary. A real
application would use a framework for the parts that are tedious here — routing
and body parsing — and would keep this shape for everything else.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qs

from rn_forge.web import (
    AUTH_FAILED_DETAIL,
    PROBLEM_MEDIA_TYPE,
    AuthenticationFailed,
    CheckResult,
    CorrelationIdMiddleware,
    DomainConflict,
    EntityVersionETagCodec,
    InMemoryIdempotencyStore,
    Message,
    Page,
    Principal,
    ProblemType,
    Receive,
    Requirement,
    Scope,
    ScopeAuthorizer,
    Send,
    challenge_header,
    check_precondition,
    clamp_page_size,
    decode_cursor,
    default_registry,
    encode_cursor,
    errors_from_field_map,
    get_correlation_id,
    run_checks,
)

# --- application state, all of it a fixture -------------------------------

REGISTRY = default_registry()
REGISTRY.register(
    RequestValidationError := type("RequestValidationError", (ValueError,), {}),
    ProblemType("validation-error", 422, "Validation Error"),
)

CODEC = EntityVersionETagCodec()
IDEMPOTENCY = InMemoryIdempotencyStore()
AUTHORIZER = ScopeAuthorizer()

ROWS = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
ITEM_VERSION = 7
PAGE_DEFAULT, PAGE_CAP = 2, 2
REALM = "conformance"


# --- the handlers ---------------------------------------------------------


def boom(request: Request) -> Response:
    """An exception with no registry row: 500, and the detail must not leak."""
    raise RuntimeError("connection to db-primary.internal failed: password=hunter2")


def conflict(request: Request) -> Response:
    """A registered exception: 409, with the message as the detail."""
    raise DomainConflict("Order already dispatched")


def validate(request: Request) -> Response:
    """Validation errors normalized to RFC 6901 pointers."""
    body = request.json()
    if not isinstance(body, dict) or "name" not in body:
        raise RequestValidationError("Validation Error")
    return Response(200, {"name": body["name"]})


def patch_item(request: Request) -> Response:
    """`If-Match` preconditions: required, so absent is 428."""
    check_precondition(
        request.header("If-Match"),
        current_version=ITEM_VERSION,
        entity_id="1",
        required=True,
    )
    return Response(
        200,
        {"id": "1", "version": ITEM_VERSION},
        headers={"ETag": CODEC.format(entity_id="1", version=ITEM_VERSION)},
    )


def list_items(request: Request) -> Response:
    """AIP-158 pagination. Note what is *not* here: any rejection of pageSize."""
    raw_size = request.query("pageSize")
    size = clamp_page_size(
        int(raw_size) if raw_size and raw_size.lstrip("-").isdigit() else None,
        default=PAGE_DEFAULT,
        cap=PAGE_CAP,
    )

    start = 0
    if (token := request.query("pageToken")) is not None:
        cursor = decode_cursor(token)  # raises InvalidCursor → 400
        start = next(
            (i + 1 for i, row in enumerate(ROWS) if row["id"] == cursor.entity_id), 0
        )

    window = ROWS[start : start + size]
    has_more = start + size < len(ROWS)
    page = Page(
        items=window,
        next_page_token=(
            encode_cursor(window[-1]["id"], window[-1]["id"]) if has_more else None
        ),
    )
    return Response(200, page.as_body())


def create_charge(request: Request) -> Response:
    """An idempotent unsafe endpoint."""
    key = request.header("Idempotency-Key")
    if key is None:
        raise ValueError("Idempotency-Key is required")

    body = request.json()
    stored = IDEMPOTENCY.record_or_replay(  # raises IdempotencyKeyReuse → 409
        scope="charges", key=key, request_body=body
    )
    if stored is not None:
        return Response(stored.status, {**stored.body, "replayed": True})

    payload = {"charged": body["amount"], "replayed": False}
    IDEMPOTENCY.complete(
        scope="charges", key=key, status=201, response_body={"charged": body["amount"]}
    )
    return Response(201, payload)


async def readyz(request: Request) -> Response:
    """Readiness. `db` is required, `queue` is not — hence 503 versus 200."""
    failing = request.query("fail")

    def make(name: str) -> Callable[[], CheckResult]:
        return lambda: CheckResult(
            status="fail" if name == failing else "pass",
            reason="unreachable" if name == failing else None,
        )

    report = await run_checks(
        {"db": make("db"), "queue": make("queue")}, required=["db"]
    )
    return Response(report.http_status, report.as_body())


def private(request: Request) -> Response:
    """The 401/403 boundary — the two failures must not look alike."""
    header = request.header("Authorization")
    if header is None or not header.startswith("Bearer "):
        raise AuthenticationFailed("No credentials were supplied")

    # A real application verifies the token here, through the commons module,
    # and never reports *why* verification failed.
    principal = Principal(subject="u1", scopes=frozenset())
    AUTHORIZER.authorize(
        principal, requires=Requirement(all_scopes=frozenset({"read"}))
    )
    return Response(200, {"subject": principal.subject})


def echo(request: Request) -> Response:
    """Nothing but the correlation contract, which the middleware already served."""
    return Response(200, {})


ROUTES: dict[tuple[str, str], Callable[..., Any]] = {
    ("GET", "/conformance/boom"): boom,
    ("GET", "/conformance/conflict"): conflict,
    ("POST", "/conformance/validate"): validate,
    ("PATCH", "/conformance/items/1"): patch_item,
    ("GET", "/conformance/items"): list_items,
    ("POST", "/conformance/charges"): create_charge,
    ("GET", "/conformance/readyz"): readyz,
    ("GET", "/conformance/private"): private,
    ("GET", "/conformance/echo"): echo,
}


# --- the plumbing ---------------------------------------------------------


class Request:
    """The three things a handler above needs off the wire."""

    def __init__(self, scope: Scope, body: bytes) -> None:
        self._scope = scope
        self._body = body
        self._query = parse_qs(scope.get("query_string", b"").decode())

    def header(self, name: str) -> str | None:
        wanted = name.lower().encode()
        return next(
            (
                v.decode()
                for k, v in self._scope.get("headers", [])
                if k.lower() == wanted
            ),
            None,
        )

    def query(self, name: str) -> str | None:
        values = self._query.get(name)
        return values[0] if values else None

    def json(self) -> Any:
        return json.loads(self._body) if self._body else None

    @property
    def path(self) -> str:
        return self._scope.get("path", "")


class Response:
    """A status, a JSON body and any extra headers."""

    def __init__(
        self,
        status: int,
        body: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        media_type: str = "application/json",
    ) -> None:
        self.status = status
        self.body = body
        self.headers = dict(headers or {})
        self.media_type = media_type


async def application(scope: Scope, receive: Receive, send: Send) -> None:
    """Route, invoke, and turn anything raised into a problem body."""
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body"):
            break

    request = Request(scope, body)
    handler = ROUTES.get((scope.get("method", "GET"), request.path))

    try:
        if handler is None:
            raise LookupError("Not Found")
        result = handler(request)
        response = await result if hasattr(result, "__await__") else result
    except Exception as exc:  # noqa: BLE001 - every failure becomes a problem body
        response = _problem_response(exc, request)

    await _send(send, response)


def _problem_response(exc: BaseException, request: Request) -> Response:
    """The single place an exception becomes a response. There is no other."""
    row = REGISTRY.problem_for(exc)
    problem = REGISTRY.build(
        exc,
        instance=request.path,
        # A 401 says only that authentication failed. Expired, bad signature
        # and unknown key must be indistinguishable on the wire.
        detail=AUTH_FAILED_DETAIL if row.status == 401 else None,
        extensions=_error_extensions(exc),
    )
    # 401 carries a challenge; 403 must not. See the API conventions, §7.
    headers = (
        {"WWW-Authenticate": challenge_header(realm=REALM)}
        if problem.status == 401
        else {}
    )
    return Response(
        problem.status,
        problem.as_body(),
        headers=headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _error_extensions(exc: BaseException) -> dict[str, Any]:
    """Correlation always; field errors when there are any."""
    extensions: dict[str, Any] = {"correlation_id": get_correlation_id()}
    if isinstance(exc, RequestValidationError):
        extensions["errors"] = errors_from_field_map(
            {"name": ["This field is required."]}
        )
    return extensions


async def _send(send: Send, response: Response) -> None:
    """Serialize one response onto the ASGI send channel."""
    payload = json.dumps(response.body).encode()
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", response.media_type.encode()),
        (b"content-length", str(len(payload)).encode()),
    ]
    headers += [(k.lower().encode(), v.encode()) for k, v in response.headers.items()]
    start: Message = {
        "type": "http.response.start",
        "status": response.status,
        "headers": headers,
    }
    await send(start)
    await send({"type": "http.response.body", "body": payload})


app = CorrelationIdMiddleware(application)
"""The application, with correlation bound and stamped. This is what a server runs."""
