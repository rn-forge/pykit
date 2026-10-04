"""A Django project, installed from built wheels, served over HTTP and run through the conformance table."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# The service is the fixture application `test_conformance.py` already wires from this package's
# adapters: everything above its fixtures (imports, models, views, urlpatterns, `WIRING`).
_CONFORMANCE = Path(__file__).with_name("test_conformance.py")

DRIVER = """\
import json
import re
import sys
import threading
from pathlib import Path
from wsgiref.simple_server import make_server

import django
import httpx
from django.conf import settings

settings.configure(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "scaffold.sqlite3"}},
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "rn_forge.django.auth",
        "rn_forge.django.messaging",
    ],
    ALLOWED_HOSTS=["127.0.0.1", "localhost"],
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    USE_TZ=False,
)
django.setup()

from django.core.cache import cache
from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.test import override_settings
from opentelemetry import trace
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    set_global_response_propagator,
)
from opentelemetry.sdk.trace import TracerProvider

from rn_forge.web.conformance import CASES, case_by_id, redact
import service

# The application instruments itself; the process supplies the SDK, as any service does.
trace.set_tracer_provider(TracerProvider())
set_global_response_propagator(TraceResponsePropagator())
override_settings(**service.WIRING).enable()


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def reset_rows():
    connection.close()
    Path("scaffold.sqlite3").unlink(missing_ok=True)
    with connection.schema_editor() as editor:
        editor.create_model(service._ConformanceItem)
        editor.create_model(service._Order)
        editor.create_model(service._ConformanceDocument)
    for pk in ("1", "2", "3"):
        service._ConformanceItem.objects.create(pk=pk)
    service._Order.objects.create(pk="1", name="widget")
    service._ConformanceDocument.objects.create(
        pk="1",
        name="widget",
        note="fragile",
        tags=["a", "b"],
        settings={"color": "red", "size": "L"},
    )
    connection.close()
    cache.clear()


def issue(client, case):
    spec = case.request
    headers = dict(spec.headers)
    if headers.get("Content-Type") == "multipart/form-data":
        del headers["Content-Type"]
        return client.request(
            spec.method,
            spec.path,
            headers=headers,
            params=dict(spec.query),
            files={name: ("file.csv", value, "text/csv") for name, value in spec.body.items()},
        )
    return client.request(
        spec.method, spec.path, headers=headers, params=dict(spec.query), json=spec.body
    )


def check(case):
    reset_rows()
    server = make_server(
        "127.0.0.1", 0, get_wsgi_application(), server_class=WSGIServer, handler_class=QuietHandler
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
            for prerequisite in case.depends_on:
                issue(client, case_by_id(prerequisite))
            response = issue(client, case)
    finally:
        server.shutdown()
        server.server_close()
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
    body = json.loads(response.content) if response.content else {}
    if redact(body) != dict(case.expect_body):
        problems.append(f"body {redact(body)!r} != {dict(case.expect_body)!r}")
    if service.casing_violations(body):
        problems.append(f"casing {service.casing_violations(body)}")
    return problems


failed = {case.id: found for case in CASES if (found := check(case))}
for case_id, found in failed.items():
    print(case_id, *found, sep="\\n  ")
print(f"{len(CASES) - len(failed)}/{len(CASES)} cases conform")
sys.exit(1 if failed else 0)
"""


@pytest.mark.scaffold
def test_a_served_project_passes_every_conformance_case(scaffold_venv, tmp_path: Path):
    source = _CONFORMANCE.read_text()
    project = tmp_path / "project"
    project.mkdir()
    # `casing_violations` is kept: it sits between the fixtures and the parametrized test.
    service = source[: source.index('@pytest.fixture(scope="module", autouse=True)')]
    helpers = source[
        source.index("def casing_violations") : source.index("@pytest.mark.parametrize")
    ]
    (project / "service.py").write_text(service + "\n\n" + helpers)
    (project / "driver.py").write_text(DRIVER)
    bin_dir = scaffold_venv(
        "rn-forge-commons[excel,pydantic]",
        "rn-forge-web[security]",
        "rn-forge-django[drf,transfer,openapi,security,cors,otel]",
        "assertpy",
        "httpx",
        "opentelemetry-sdk",
        "pytest",
    )

    result = subprocess.run(
        [str(bin_dir / "python"), "driver.py"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
