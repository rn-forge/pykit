"""The examples under docs/adoption/ are executable, and this is what proves it.

Two levels of guarantee, and they are not the same:

- **`asgi_app.py` is executed.** Every case in `rn_forge.web.conformance.CASES`
  is driven through it, which makes it the first of the three independent
  proofs the table is designed to collect — and makes the table itself testable
  rather than aspirational.
- **`django_app.py` and `fastapi_app.py` are symbol-checked.** Installing
  either framework as a test dependency of this package would put a web
  framework in its dependency graph, which is the boundary the package exists
  to hold. So these are parsed, not imported, and every name they take from
  `rn_forge.web` is asserted to exist in its public API. That catches the
  realistic rot — a renamed or removed symbol. It does not catch a semantic
  change in a framework's own behaviour.
"""

import ast
import importlib.util
import json
import pathlib
import re
import sys

import pytest
from assertpy import assert_that

import rn_forge.web
from rn_forge.web.conformance import CASES, case_by_id, redact

BOUNDARY = "conformance-boundary"
EXAMPLES = pathlib.Path(__file__).parent.parent / "docs" / "adoption" / "examples"

pytestmark = pytest.mark.unit


def load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"_example_{name}", EXAMPLES / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # pydantic resolves postponed annotations here
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def asgi_app():
    """A fresh application per case — see the conformance module on isolation."""
    return load("asgi_app").app


async def call(app, case):
    """Drive one conformance case through an ASGI app and collect the response."""
    query = "&".join(f"{k}={v}" for k, v in case.request.query.items()).encode()
    headers = dict(case.request.headers)
    if case.request.body is None:
        body = b""
    elif headers.get("Content-Type") == "multipart/form-data":
        headers["Content-Type"] = f"multipart/form-data; boundary={BOUNDARY}"
        body = (
            "".join(
                f"--{BOUNDARY}\r\nContent-Disposition: form-data; "
                f'name="{name}"; filename="{name}"\r\n'
                f"Content-Type: text/csv\r\n\r\n{value}\r\n"
                for name, value in case.request.body.items()
            ).encode()
            + f"--{BOUNDARY}--\r\n".encode()
        )
    else:
        body = json.dumps(case.request.body).encode()
    scope = {
        "type": "http",
        "method": case.request.method,
        "path": case.request.path,
        "query_string": query,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }

    received = [False]

    async def receive():
        if received[0]:
            return {"type": "http.request", "body": b"", "more_body": False}
        received[0] = True
        return {"type": "http.request", "body": body, "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    payload = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    # A real client folds repeated header lines with ", " (RFC 9110 §5.3) —
    # relevant here because the OTel ASGI instrumentation adds its own
    # Access-Control-Expose-Headers line alongside the application's.
    headers: dict[str, str] = {}
    for k, v in start["headers"]:
        name, value = k.decode().lower(), v.decode()
        headers[name] = f"{headers[name]}, {value}" if name in headers else value
    is_json = "json" in headers.get("content-type", "")
    return (
        start["status"],
        headers,
        payload.decode(),
        json.loads(payload) if is_json else {},
    )


# --- the executed proof ---------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
async def test_the_asgi_example_conforms(asgi_app, case):
    """The driver every framework package ships, run against the reference app."""
    for prerequisite in case.depends_on:
        await call(asgi_app, case_by_id(prerequisite))

    status, headers, text, body = await call(asgi_app, case)

    assert_that(status).described_as("status").is_equal_to(case.expect_status)

    for name, value in case.expect_headers.items():
        assert_that(headers.get(name.lower())).described_as(name).is_equal_to(value)

    for name in case.expect_absent_headers:
        assert_that(headers).described_as(name).does_not_contain_key(name.lower())

    for name, pattern in case.expect_header_patterns.items():
        value = headers.get(name.lower())
        assert_that(value).described_as(name).is_not_none()
        assert_that(re.fullmatch(pattern, value)).described_as(
            f"{name}={value!r} ~ {pattern!r}"
        ).is_not_none()

    if case.expect_text is not None:
        assert_that(text).is_equal_to(case.expect_text)
    else:
        assert_that(redact(body)).is_equal_to(dict(case.expect_body))


def test_every_declared_prerequisite_resolves():
    """A depends_on naming a case that does not exist would silently do nothing."""
    for case in CASES:
        for prerequisite in case.depends_on:
            assert_that(case_by_id(prerequisite).id).is_equal_to(prerequisite)


def test_the_replay_cases_declare_their_prerequisite():
    """Otherwise they pass or fail by test-runner ordering."""
    for case in CASES:
        if case.area == "idempotency" and case.expect_status != 201:
            assert_that(case.depends_on).described_as(case.id).is_not_empty()
        if case.id == "idempotency.replay-returns-the-stored-response":
            assert_that(case.depends_on).contains("idempotency.first-call-executes")


@pytest.mark.asyncio
async def test_the_example_serves_every_path_the_table_uses(asgi_app):
    """A case added for an endpoint the reference app does not serve must fail here."""
    module = load("asgi_app")
    served = {path for _, path in module.ROUTES}
    used = {case.request.path for case in CASES}
    assert_that(used - served - {"/conformance/missing"}).is_empty()


# --- the symbol-checked examples ------------------------------------------


@pytest.mark.parametrize("name", ["asgi_app", "django_app", "fastapi_app"])
def test_every_imported_symbol_exists_in_the_public_api(name):
    tree = ast.parse((EXAMPLES / f"{name}.py").read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "rn_forge.web"
        for alias in node.names
    }
    assert_that(imported).described_as(
        f"{name} imports nothing from rn_forge.web"
    ).is_not_empty()
    assert_that(sorted(imported - set(rn_forge.web.__all__))).is_empty()


@pytest.mark.parametrize("name", ["asgi_app", "django_app", "fastapi_app"])
def test_every_example_parses(name):
    ast.parse((EXAMPLES / f"{name}.py").read_text())
