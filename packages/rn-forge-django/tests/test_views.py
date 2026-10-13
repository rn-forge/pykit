from __future__ import annotations

import json

import pytest

django = pytest.importorskip("django")

from django.http import HttpRequest  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from rn_forge.django.views import (  # noqa: E402
    debug_request,
    debug_request_view,
    health_urlpatterns,
    index_view,
    liveness_view,
    readiness_view,
)
from rn_forge.web import CheckResult, WebError  # noqa: E402

pytestmark = pytest.mark.unit


class TestHelperViews:
    def test_liveness_view(self) -> None:
        request = HttpRequest()
        request.method = "GET"
        response = liveness_view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"status": "pass"}

    def test_debug_request_view(self) -> None:
        request = HttpRequest()
        request.path = "/debug/"
        request.path_info = "/debug/"
        request.method = "GET"
        request.META = {"SERVER_NAME": "localhost", "SERVER_PORT": "80"}
        response = debug_request_view(request)
        assert response.status_code == 200
        assert json.loads(response.content)["path"] == "/debug/"

    def test_index_view_renders_html(self) -> None:
        request = HttpRequest()
        request.path = "/"
        request.path_info = "/"
        request.method = "GET"
        request.META = {"SERVER_NAME": "localhost", "SERVER_PORT": "80"}
        response = index_view(request)
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]
        assert b"rn-forge-django" in response.content


def _ready(checks, **kwargs):
    response = readiness_view(checks, **kwargs)(RequestFactory().get("/readyz"))
    return response.status_code, json.loads(response.content)


def _boom():
    raise RuntimeError("db unreachable")


class TestReadinessView:
    def test_all_pass_is_200(self) -> None:
        status, body = _ready({"db": lambda: True}, required=["db"])
        assert status == 200
        assert body["status"] == "pass"

    def test_optional_failure_is_200_and_recorded(self) -> None:
        status, body = _ready(
            {"db": lambda: True, "queue": lambda: False}, required=["db"]
        )
        assert status == 200
        assert body["status"] == "fail"
        assert body["checks"]["queue"]["status"] == "fail"

    def test_required_failure_is_503(self) -> None:
        status, _ = _ready({"db": lambda: False}, required=["db"])
        assert status == 503

    def test_raising_check_is_captured_not_500(self) -> None:
        status, body = _ready({"db": _boom})
        assert status == 200
        assert body["checks"]["db"]["reason"] == "db unreachable"

    def test_warn_and_skipped_are_200(self) -> None:
        status, body = _ready(
            {
                "cache": lambda: CheckResult(status="warn"),
                "search": lambda: CheckResult(
                    status="skipped", reason="not configured"
                ),
            }
        )
        assert status == 200
        assert body["checks"]["search"]["status"] == "skipped"

    def test_async_check_raises(self) -> None:
        async def check():
            return True

        with pytest.raises(WebError):
            _ready({"db": check})

    def test_empty_checks_is_200(self) -> None:
        assert _ready({}) == (200, {"status": "pass", "checks": {}})

    def test_only_get_is_allowed(self) -> None:
        response = readiness_view({})(RequestFactory().post("/readyz"))
        assert response.status_code == 405


class TestHealthUrlpatterns:
    def test_default_paths_have_no_trailing_slash(self) -> None:
        patterns = health_urlpatterns(checks={})
        names = [str(p.pattern) for p in patterns]
        assert "livez" in names
        assert "readyz" in names
        assert "healthz" in names

    def test_legacy_alias_can_be_dropped(self) -> None:
        patterns = health_urlpatterns(checks={}, legacy_liveness_path=None)
        names = [str(p.pattern) for p in patterns]
        assert "healthz" not in names


# ---------------------------------------------------------------------------
# debug_request
# ---------------------------------------------------------------------------


class TestDebugRequest:
    def _make_request(self, path: str = "/test/", method: str = "GET") -> HttpRequest:
        factory = RequestFactory()
        maker = getattr(factory, method.lower())
        return maker(path)

    def test_contains_expected_top_level_keys(self) -> None:
        req = self._make_request()
        result = debug_request(req)
        assert set(result.keys()) == {
            "path",
            "path_info",
            "method",
            "content_type",
            "scheme",
            "absolute_uri",
            "full_path",
            "host",
            "port",
            "headers",
            "meta",
        }

    def test_path_matches_request(self) -> None:
        req = self._make_request("/api/v1/items/")
        result = debug_request(req)
        assert result["path"] == "/api/v1/items/"
        assert result["full_path"] == "/api/v1/items/"

    def test_method_is_uppercased(self) -> None:
        req = self._make_request(method="POST")
        result = debug_request(req)
        assert result["method"] == "POST"

    def test_headers_is_dict(self) -> None:
        req = self._make_request()
        result = debug_request(req)
        assert isinstance(result["headers"], dict)

    def test_meta_contains_remote_addr(self) -> None:
        req = self._make_request()
        req.META["REMOTE_ADDR"] = "127.0.0.1"
        result = debug_request(req)
        assert result["meta"]["REMOTE_ADDR"] == "127.0.0.1"

    def test_meta_http_headers_are_included(self) -> None:
        req = self._make_request()
        req.META["HTTP_ACCEPT"] = "application/json"
        result = debug_request(req)
        assert result["meta"]["HTTP_ACCEPT"] == "application/json"

    def test_sensitive_http_headers_are_redacted(self) -> None:
        req = self._make_request()
        req.META["HTTP_AUTHORIZATION"] = "Bearer secret-token"
        req.META["HTTP_COOKIE"] = "sessionid=secret"
        result = debug_request(req)
        assert result["meta"]["HTTP_AUTHORIZATION"] == "<redacted>"
        assert result["meta"]["HTTP_COOKIE"] == "<redacted>"

    def test_meta_non_http_keys_excluded(self) -> None:
        req = self._make_request()
        req.META["wsgi.input"] = object()
        result = debug_request(req)
        # wsgi.input does not start with HTTP_; should not be in meta HTTP keys
        assert "wsgi.input" not in result["meta"]

    def test_no_external_calls_made(self) -> None:
        # Ensure debug_request does not contain an external IP field
        req = self._make_request()
        result = debug_request(req)
        assert "internalIP" not in result
        assert "externalIP" not in result
