from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory
import pytest

from rn_forge.django.middleware import AccessLogMiddleware

pytestmark = pytest.mark.unit


def _middleware(events: list, **kwargs) -> AccessLogMiddleware:
    def view(request):
        return HttpResponse(status=204)

    return AccessLogMiddleware(
        view, log=lambda event, context: events.append((event, dict(context))), **kwargs
    )


class TestAccessLogMiddleware:
    def test_log_is_called_once_with_every_key(self) -> None:
        events = []
        request = RequestFactory().post("/orders")
        _middleware(events)(request)
        assert len(events) == 1
        event, context = events[0]
        assert event == "request.complete"
        assert set(context) == {
            "http.request.method",
            "url.path",
            "http.response.status_code",
            "duration_ms",
            "trace_id",
            "span_id",
        }
        assert (
            context["http.request.method"],
            context["url.path"],
            context["http.response.status_code"],
        ) == ("POST", "/orders", 204)
        assert context["trace_id"] is None
        assert context["span_id"] is None

    def test_default_log_does_not_raise(self) -> None:
        response = AccessLogMiddleware(lambda request: HttpResponse())(
            RequestFactory().get("/x")
        )
        assert response.status_code == 200
