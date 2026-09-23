from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory
import pytest

from rn_forge.django.middleware import CorrelationIdMiddleware
from rn_forge.web import get_correlation_id

pytestmark = pytest.mark.unit


def _middleware(seen: list, events: list, **kwargs) -> CorrelationIdMiddleware:
    def view(request):
        seen.append((get_correlation_id(), request.correlation_id))
        return HttpResponse(status=204)

    return CorrelationIdMiddleware(
        view, log=lambda event, context: events.append((event, dict(context))), **kwargs
    )


class TestCorrelationIdMiddleware:
    def test_inbound_header_is_preserved_and_echoed(self) -> None:
        seen, events = [], []
        request = RequestFactory().get("/x", headers={"X-Correlation-ID": "abc123"})
        response = _middleware(seen, events)(request)
        assert response["X-Correlation-ID"] == "abc123"
        assert seen == [("abc123", "abc123")]

    def test_absent_header_is_generated(self) -> None:
        seen, events = [], []
        response = _middleware(seen, events)(RequestFactory().get("/x"))
        generated = response["X-Correlation-ID"]
        assert len(generated) == 32
        assert seen == [(generated, generated)]

    def test_blank_header_is_treated_as_absent(self) -> None:
        seen, events = [], []
        request = RequestFactory().get("/x", headers={"X-Correlation-ID": ""})
        response = _middleware(seen, events)(request)
        assert response["X-Correlation-ID"]

    def test_log_is_called_once_with_every_key(self) -> None:
        seen, events = [], []
        request = RequestFactory().post("/orders", headers={"X-Correlation-ID": "c1"})
        _middleware(seen, events)(request)
        assert len(events) == 1
        event, context = events[0]
        assert event == "request.complete"
        assert set(context) == {
            "http.request.method",
            "url.path",
            "http.response.status_code",
            "duration_ms",
            "correlation_id",
        }
        assert (
            context["http.request.method"],
            context["url.path"],
            context["http.response.status_code"],
        ) == ("POST", "/orders", 204)
        assert context["correlation_id"] == "c1"

    def test_binding_is_reset_after_the_request(self) -> None:
        _middleware([], [])(
            RequestFactory().get("/x", headers={"X-Correlation-ID": "c1"})
        )
        assert get_correlation_id() is None

    def test_sequential_requests_are_isolated(self) -> None:
        seen, events = [], []
        middleware = _middleware(seen, events)
        middleware(RequestFactory().get("/a", headers={"X-Correlation-ID": "first"}))
        middleware(RequestFactory().get("/b"))
        assert seen[0][0] == "first"
        assert seen[1][0] not in (None, "first")

    def test_custom_header_is_honoured_on_read_and_echo(self) -> None:
        seen, events = [], []
        request = RequestFactory().get("/x", headers={"X-Request-ID": "r-9"})
        response = _middleware(seen, events, header="X-Request-ID")(request)
        assert response["X-Request-ID"] == "r-9"
        assert not response.has_header("X-Correlation-ID")

    def test_subclass_header_attribute_is_honoured(self) -> None:
        class Custom(CorrelationIdMiddleware):
            header = "X-Trace"

        response = Custom(lambda request: HttpResponse())(
            RequestFactory().get("/x", headers={"X-Trace": "t-1"})
        )
        assert response["X-Trace"] == "t-1"

    def test_default_log_does_not_raise(self) -> None:
        response = CorrelationIdMiddleware(lambda request: HttpResponse())(
            RequestFactory().get("/x")
        )
        assert response.status_code == 200


def test_a_malformed_inbound_id_is_replaced() -> None:
    seen, events = [], []
    request = RequestFactory().get("/x", headers={"X-Correlation-ID": "bad id!"})
    response = _middleware(seen, events)(request)
    assert response["X-Correlation-ID"] != "bad id!"
    assert seen[0][0] == response["X-Correlation-ID"]
