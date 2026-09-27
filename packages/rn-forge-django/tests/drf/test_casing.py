from __future__ import annotations

import io
import json

import pytest

rest_framework = pytest.importorskip("rest_framework")

from django.test import override_settings  # noqa: E402
from rest_framework import serializers  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from rn_forge.django.drf.casing import (  # noqa: E402
    CamelCaseJSONParser,
    CamelCaseJSONRenderer,
    RawDict,
    camelize,
    camelize_key,
    underscore_key,
    underscoreize,
)
from rn_forge.django.drf.serializers import RawPassthroughField  # noqa: E402

pytestmark = pytest.mark.unit


class TestKeyTransforms:
    @pytest.mark.parametrize(
        ("snake", "camel"),
        [("page_size", "pageSize"), ("next_page_token", "nextPageToken"), ("id", "id")],
    )
    def test_round_trip(self, snake, camel) -> None:
        assert camelize_key(snake) == camel
        assert underscore_key(camel) == snake

    def test_snake_input_is_unchanged_by_underscore(self) -> None:
        assert underscore_key("page_size") == "page_size"

    def test_leading_underscore_is_kept(self) -> None:
        assert camelize_key("_private_key") == "_privateKey"


class TestRecursion:
    def test_camelize_recurses_into_mappings_and_lists(self) -> None:
        assert camelize({"order_lines": [{"unit_price": 1}]}) == {
            "orderLines": [{"unitPrice": 1}]
        }

    def test_camelize_leaves_raw_values_alone(self) -> None:
        data = {"vendor_payload": RawDict({"sku_id": 1})}
        assert camelize(data) == {"vendorPayload": {"sku_id": 1}}

    def test_underscoreize_skips_opaque_names(self) -> None:
        data = {"vendorPayload": {"skuId": 1}, "lineItems": [{"unitPrice": 2}]}
        assert underscoreize(data, opaque=frozenset({"vendor_payload"})) == {
            "vendor_payload": {"skuId": 1},
            "line_items": [{"unit_price": 2}],
        }


class TestRendererAndParser:
    def test_renderer_camelizes(self) -> None:
        assert json.loads(CamelCaseJSONRenderer().render({"page_size": 2})) == {
            "pageSize": 2
        }

    def test_parser_accepts_both_spellings(self) -> None:
        parsed = CamelCaseJSONParser().parse(
            io.BytesIO(b'{"pageSize": 1, "page_token": "t"}')
        )
        assert parsed == {"page_size": 1, "page_token": "t"}

    def test_disabled_casing_is_plain_json(self) -> None:
        with override_settings(RN_FORGE_DJANGO={"DRF": {"CASING": {"ENABLED": False}}}):
            assert json.loads(CamelCaseJSONRenderer().render({"page_size": 2})) == {
                "page_size": 2
            }
            parsed = CamelCaseJSONParser().parse(io.BytesIO(b'{"pageSize": 1}'))
        assert parsed == {"pageSize": 1}


class _LineSerializer(serializers.Serializer):
    unit_price = serializers.IntegerField()


class _OrderSerializer(serializers.Serializer):
    order_ref = serializers.CharField()
    vendor_payload = RawPassthroughField()
    lines = _LineSerializer(many=True)


class _OrderView(APIView):
    authentication_classes: list = []
    permission_classes: list = []
    parser_classes = [CamelCaseJSONParser]
    renderer_classes = [CamelCaseJSONRenderer]
    serializer_class = _OrderSerializer

    def get_serializer_class(self):
        return self.serializer_class

    def post(self, request):
        serializer = _OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(_OrderSerializer(serializer.validated_data).data)


class TestRawPassthroughField:
    def test_nested_dict_keys_survive_both_directions(self) -> None:
        body = {
            "orderRef": "PO-1",
            "vendorPayload": {"SKU_ID": 1, "lineNo": 2},
            "lines": [{"unitPrice": 3}],
        }
        request = APIRequestFactory().post("/orders", body, format="json")
        response = _OrderView.as_view()(request)
        response.render()
        assert json.loads(response.content) == body
