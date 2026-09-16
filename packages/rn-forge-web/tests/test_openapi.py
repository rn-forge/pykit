"""Tests for rn_forge.web.openapi — the naming rules both bindings read."""

import pytest
from assertpy import assert_that

from rn_forge.web.openapi import operation_id, page_component_name

pytestmark = pytest.mark.unit


class TestOperationIdForCrud:
    @pytest.mark.parametrize(
        ("path", "method", "expected"),
        [
            ("/api/v1/work-items", "GET", "workItemsList"),
            ("/api/v1/work-items/{id}", "GET", "workItemsGet"),
            ("/orders", "POST", "ordersCreate"),
            ("/orders/{id}", "PUT", "ordersUpdate"),
            ("/orders/{id}", "PATCH", "ordersPartialUpdate"),
            ("/orders/{id}", "DELETE", "ordersDelete"),
            ("/orders/{id}/items", "GET", "itemsList"),
            ("/", "GET", "rootList"),
        ],
    )
    def test_resource_verb(self, path, method, expected) -> None:
        assert_that(operation_id(path, method)).is_equal_to(expected)

    def test_put_and_patch_on_one_resource_differ(self) -> None:
        assert operation_id("/orders/{id}", "PUT") != operation_id(
            "/orders/{id}", "PATCH"
        )

    def test_method_case_does_not_matter(self) -> None:
        assert_that(operation_id("/orders", "post")).is_equal_to("ordersCreate")


class TestOperationIdForCustomMethods:
    """AIP-136: an action is `:action` on the resource it acts on."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/orders/{orderId}:cancel", "ordersCancel"),
            ("/api/v1/orders/{orderId}:cancel", "ordersCancel"),
            ("/orders:batchCreate", "ordersBatchCreate"),
            ("/work-items/{id}:archive", "workItemsArchive"),
        ],
    )
    def test_resource_action(self, path, expected) -> None:
        assert_that(operation_id(path, "POST")).is_equal_to(expected)

    def test_the_http_method_does_not_change_a_custom_method_name(self) -> None:
        assert_that(operation_id("/orders/{id}:cancel", "GET")).is_equal_to(
            operation_id("/orders/{id}:cancel", "POST")
        )

    def test_the_same_action_on_two_resources_does_not_collide(self) -> None:
        """The collision the plain-segment spelling produces; OpenAPI forbids it."""
        assert operation_id("/orders/{id}:cancel", "POST") != operation_id(
            "/invoices/{id}:cancel", "POST"
        )

    def test_an_action_as_a_plain_segment_is_mechanical_and_needs_an_override(
        self,
    ) -> None:
        """Documented, not desired: nothing in the path marks it as an action."""
        assert_that(operation_id("/orders/{id}/cancel", "POST")).is_equal_to(
            "cancelCreate"
        )


class TestPageComponentName:
    def test_prefixes_the_item_name(self) -> None:
        assert_that(page_component_name("OrderOut")).is_equal_to("PageOrderOut")
