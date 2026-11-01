"""A FastAPI service, installed from built wheels, served over HTTP and run through the conformance table."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# The service is the fixture application `test_conformance.py` already wires from this package's
# adapters: everything above its parametrized test (imports, models, `build_app`, `issue`).
_CONFORMANCE = Path(__file__).with_name("test_conformance.py")

DRIVER = """\
import re
import socket
import sys
import threading
import time

import httpx
import uvicorn
from opentelemetry import trace
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    set_global_response_propagator,
)
from opentelemetry.sdk.trace import TracerProvider

from rn_forge.web.conformance import CASES, case_by_id, redact
from service import build_app, casing_violations, issue

# The application instruments itself; the process supplies the SDK, as any service does.
trace.set_tracer_provider(TracerProvider())
set_global_response_propagator(TraceResponsePropagator())


def serve(app):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.01)
    return server, f"http://127.0.0.1:{port}"


def check(case):
    server, url = serve(build_app(failing=case.request.query.get("fail")))
    try:
        with httpx.Client(base_url=url) as client:
            for prerequisite in case.depends_on:
                issue(client, case_by_id(prerequisite))
            response = issue(client, case)
    finally:
        server.should_exit = True
    problems = []
    if response.status_code != case.expect_status:
        problems.append(f"status {response.status_code} != {case.expect_status}")
    for name, value in case.expect_headers.items():
        if response.headers.get(name) != value:
            problems.append(f"header {name}={response.headers.get(name)!r} != {value!r}")
    for name in case.expect_absent_headers:
        if name in response.headers:
            problems.append(f"header {name} present")
    for name, pattern in case.expect_header_patterns.items():
        value = response.headers.get(name)
        if value is None or not re.fullmatch(pattern, value):
            problems.append(f"header {name}={value!r} !~ {pattern!r}")
    if case.expect_text is not None:
        if response.text != case.expect_text:
            problems.append("text differs")
        return problems
    body = response.json() if response.content else {}
    if redact(body) != dict(case.expect_body):
        problems.append(f"body {redact(body)!r} != {dict(case.expect_body)!r}")
    if casing_violations(body):
        problems.append(f"casing {casing_violations(body)}")
    return problems


failed = {case.id: found for case in CASES if (found := check(case))}
for case_id, found in failed.items():
    print(case_id, *found, sep="\\n  ")
print(f"{len(CASES) - len(failed)}/{len(CASES)} cases conform")
sys.exit(1 if failed else 0)
"""


@pytest.mark.scaffold
def test_a_served_service_passes_every_conformance_case(scaffold_venv, tmp_path: Path):
    source = _CONFORMANCE.read_text()
    service = tmp_path / "service"
    service.mkdir()
    (service / "service.py").write_text(
        source[: source.index("@pytest.mark.parametrize")]
    )
    (service / "driver.py").write_text(DRIVER)
    bin_dir = scaffold_venv(
        "rn-forge-data",
        "rn-forge-web[security]",
        "rn-forge-fastapi[transfer]",
        "assertpy",
        "httpx",
        "opentelemetry-sdk",
        "pytest",
        "uvicorn",
    )

    result = subprocess.run(
        [str(bin_dir / "python"), "driver.py"],
        cwd=service,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


SSE_DRIVER = """\
import asyncio
import socket
import threading
import time
from collections.abc import AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI
from sse_starlette import ServerSentEvent

from rn_forge.fastapi.sse import sse_response
from rn_forge.web import ProblemDetail

app = FastAPI()


@app.get("/events")
async def events():
    async def source() -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent("one", id="1")
        yield ServerSentEvent("two", id="2")
        await asyncio.sleep(0.5)
        raise RuntimeError("secret")

    return sse_response(source(), ping=0.1, instance="/events")


with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.01)

try:
    with httpx.stream("GET", f"http://127.0.0.1:{port}/events", timeout=5) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
finally:
    server.should_exit = True

frames = [frame.splitlines() for frame in body.split("\\r\\n\\r\\n") if frame]
assert frames[0] == ["retry: 5000"], frames
assert frames[1:3] == [["id: 1", "data: one"], ["id: 2", "data: two"]], frames
assert any(frame[0].startswith(": ping") for frame in frames[3:-1]), frames
event, data = frames[-1]
assert event == "event: error", frames
problem = ProblemDetail.model_validate_json(data.removeprefix("data: "))
assert problem.status == 500 and problem.instance == "/events", problem
assert "secret" not in body
print("sse ok")
"""


@pytest.mark.scaffold
def test_a_served_sse_endpoint_streams_frames_a_heartbeat_and_a_problem(
    scaffold_venv, tmp_path: Path
):
    (tmp_path / "sse_driver.py").write_text(SSE_DRIVER)
    bin_dir = scaffold_venv(
        "rn-forge-web[security]",
        "rn-forge-fastapi[sse]",
        "httpx",
        "uvicorn",
    )

    result = subprocess.run(
        [str(bin_dir / "python"), "sse_driver.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
