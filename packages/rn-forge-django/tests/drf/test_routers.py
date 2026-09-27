from __future__ import annotations

import pytest
from django.urls import Resolver404, resolve, reverse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from rn_forge.django.drf.routers import CustomMethodRouter

pytestmark = pytest.mark.unit


class _Orders(ViewSet):
    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({"pk": pk})

    @action(
        detail=False, methods=["post"], url_path="batchCreate", url_name="batch-create"
    )
    def batch_create(self, request):
        return Response({})

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        return Response({"cancelled": pk})


class _Slugs(ViewSet):
    lookup_value_regex = "[a-z:]+"

    def retrieve(self, request, pk=None):
        return Response({"pk": pk})


router = CustomMethodRouter(trailing_slash=False)
router.register("orders", _Orders, basename="orders")
router.register("slugs", _Slugs, basename="slugs")
urlpatterns = router.urls


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = __name__


class TestCustomMethodRouter:
    def test_collection_custom_method_has_no_slash(self) -> None:
        match = resolve("/orders:batchCreate")
        assert match.url_name == "orders-batch-create"
        assert reverse("orders-batch-create") == "/orders:batchCreate"

    def test_detail_custom_method_carries_the_lookup(self) -> None:
        match = resolve("/orders/12:cancel")
        assert match.kwargs["pk"] == "12"
        assert reverse("orders-cancel", kwargs={"pk": "12"}) == "/orders/12:cancel"

    def test_detail_still_resolves(self) -> None:
        assert resolve("/orders/12").url_name == "orders-detail"

    def test_the_lookup_does_not_swallow_an_unknown_verb(self) -> None:
        with pytest.raises(Resolver404):
            resolve("/orders/12:nope")

    def test_a_viewset_regex_overrides_the_default(self) -> None:
        assert resolve("/slugs/a:b").kwargs["pk"] == "a:b"

    def test_a_wrong_method_on_a_custom_method_is_405(self, client) -> None:
        assert client.get("/orders/12:cancel").status_code == 405
        assert client.post("/orders/12:cancel").json() == {"cancelled": "12"}
