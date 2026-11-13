from __future__ import annotations

import pytest

pytest.importorskip("rest_framework")

from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rn_forge.auth import Principal
from rn_forge.django.auth.drf import (
    AuthorizedAPIView,
    GroupViewSet,
    PermissionKeyPermission,
    PermissionViewSet,
    UserViewSet,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class _OrdersView(AuthorizedAPIView):
    permission_key = "orders"

    def get(self, request):
        return Response({"ok": True})


def _principal(*permissions: str) -> Principal:
    return Principal(subject="1", permissions=frozenset(permissions))


def _get(view, principal: Principal | None, **kwargs):
    request = APIRequestFactory().get("/")
    if principal is not None:
        force_authenticate(request, user=principal)
    return view(request, **kwargs)


def test_authorized_views_check_the_permission_key_permission() -> None:
    assert AuthorizedAPIView.permission_classes == [PermissionKeyPermission]
    assert UserViewSet.permission_classes == [PermissionKeyPermission]


def test_authorized_api_view_denies_a_principal_lacking_the_permission() -> None:
    view = _OrdersView.as_view()

    assert _get(view, _principal("orders.read")).status_code == 403
    assert _get(view, _principal("orders.get")).status_code == 200


@pytest.mark.parametrize(
    ("viewset", "key"),
    [
        (PermissionViewSet, "rn_forge.auth.permission"),
        (GroupViewSet, "rn_forge.auth.group"),
        (UserViewSet, "rn_forge.auth.user"),
    ],
)
def test_admin_viewsets_require_their_permission_key(viewset, key: str) -> None:
    view = viewset.as_view({"get": "list"})

    assert _get(view, _principal()).status_code == 403
    assert _get(view, _principal("other.list")).status_code == 403
    assert _get(view, _principal(f"{key}.list")).status_code == 200
