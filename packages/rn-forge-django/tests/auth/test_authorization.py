from __future__ import annotations

import json

import pytest

pytest.importorskip("rest_framework")

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group, Permission  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from rest_framework.pagination import PageNumberPagination  # noqa: E402
from rest_framework.request import Request  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.serializers import ModelSerializer  # noqa: E402
from rest_framework.test import APIRequestFactory, force_authenticate  # noqa: E402
from rest_framework.viewsets import ModelViewSet  # noqa: E402

from rn_forge.auth import AuthorizationContextCache, Principal  # noqa: E402
from rn_forge.django.auth.authorization import (  # noqa: E402
    DjangoAuthorizationContextProvider,
    connect_authorization_signals,
    permission_keys,
)
from rn_forge.django.auth.drf import (  # noqa: E402
    GroupViewSet,
    PermissionKeyPermission,
    ResourcePolicyViewMixin,
    UserViewSet,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

User = get_user_model()


def _perm(codename: str) -> Permission:
    return Permission.objects.get(codename=codename)


def test_permission_keys_map_default_and_custom_codenames() -> None:
    assert permission_keys(_perm("change_group")) == {"auth.group.update"}
    assert permission_keys(_perm("view_group")) == {
        "auth.group.read",
        "auth.group.list",
    }
    custom = Permission.objects.create(
        codename="Adjust_Stock",
        name="adjust",
        content_type=ContentType.objects.get_for_model(Group),
    )
    assert permission_keys(custom) == {"auth.adjust_stock"}


def test_provider_builds_keys_from_user_and_group_permissions() -> None:
    user = User.objects.create_user("u", password="x")
    group = Group.objects.create(name="editors")
    group.permissions.add(_perm("add_group"))
    user.groups.add(group)
    user.user_permissions.add(_perm("view_group"))

    ctx = DjangoAuthorizationContextProvider().resolve(str(user.pk))

    assert ctx.active
    assert ctx.roles == {"editors"}
    assert ctx.permissions == {
        "auth.group.create",
        "auth.group.read",
        "auth.group.list",
    }


@pytest.mark.parametrize(
    ("flag", "role"), [("is_staff", "staff"), ("is_superuser", "superuser")]
)
def test_staff_and_superuser_bypass_is_a_role_granting_everything(
    flag: str, role: str
) -> None:
    user = User.objects.create_user("b", password="x", **{flag: True})

    ctx = DjangoAuthorizationContextProvider(catalog=["orders.read"]).resolve(
        str(user.pk)
    )

    assert role in ctx.roles
    assert {"orders.read", "auth.group.update", "auth.user.delete"} <= ctx.permissions


def test_provider_inactive_or_unknown_user_has_no_permissions() -> None:
    user = User.objects.create_user(
        "i", password="x", is_active=False, is_superuser=True
    )
    provider = DjangoAuthorizationContextProvider()
    for account_id in (str(user.pk), "99999"):
        ctx = provider.resolve(account_id)
        assert not ctx.active
        assert ctx.permissions == frozenset()


@pytest.fixture
def cache() -> object:
    cache = AuthorizationContextCache(DjangoAuthorizationContextProvider())
    disconnect = connect_authorization_signals(cache)
    yield cache
    disconnect()


def test_signals_bump_affected_versions(cache: AuthorizationContextCache) -> None:
    a = User.objects.create_user("a", password="x")
    b = User.objects.create_user("b", password="x")
    group = Group.objects.create(name="g")
    a.groups.add(group)
    assert cache.resolve(str(a.pk)).permissions == frozenset()

    a.user_permissions.add(_perm("view_group"))
    assert "auth.group.read" in cache.resolve(str(a.pk)).permissions

    group.permissions.add(_perm("add_group"))
    assert "auth.group.create" in cache.resolve(str(a.pk)).permissions

    group.user_set.add(b)  # reverse side
    assert "auth.group.create" in cache.resolve(str(b.pk)).permissions

    a.is_active = False
    a.save()
    assert not cache.resolve(str(a.pk)).active

    group.delete()
    assert "auth.group.create" not in cache.resolve(str(b.pk)).permissions


def test_viewset_changes_bump_authorization(cache: AuthorizationContextCache) -> None:
    target = User.objects.create_user("t", password="x")
    group = Group.objects.create(name="g")
    assert cache.resolve(str(target.pk)).active
    # The viewset's own authentication is not under test, only its writes.
    open_user_view = UserViewSet.as_view(
        {"patch": "partial_update"}, permission_classes=[]
    )
    request = APIRequestFactory().patch(
        f"/users/{target.pk}/",
        json.dumps({"is_active": False}),
        content_type="application/merge-patch+json",
    )
    response = open_user_view(request, pk=target.pk)

    assert response.status_code == 200
    assert not cache.resolve(str(target.pk)).active

    open_group_view = GroupViewSet.as_view(
        {"patch": "partial_update"}, permission_classes=[]
    )
    response = open_group_view(
        APIRequestFactory().patch(
            f"/groups/{group.pk}/",
            json.dumps({"name": "h"}),
            content_type="application/merge-patch+json",
        ),
        pk=group.pk,
    )
    assert response.status_code == 200


class _View:
    permission_key = "orders"
    permission_action_map = {"archive": "delete"}

    def __init__(self, action: str | None = None) -> None:
        self.action = action


def _request(principal: object) -> Request:
    request = Request(APIRequestFactory().get("/"))
    request.user = principal  # pyright: ignore[reportAttributeAccessIssue]
    return request


def test_permission_class_checks_requirement_for_action() -> None:
    principal = Principal(
        subject="1", permissions=frozenset({"orders.update", "orders.delete"})
    )
    permission = PermissionKeyPermission()
    assert permission.has_permission(_request(principal), _View("partial_update"))
    assert permission.has_permission(_request(principal), _View("archive"))
    assert not permission.has_permission(_request(principal), _View("list"))
    assert not permission.has_permission(_request(object()), _View("list"))


class _Policy:
    def allows(self, principal: Principal, action: str, resource: Group) -> bool:
        return resource.name.startswith(str(principal.attributes["prefix"]))

    def scope(self, principal: Principal, action: str, query):  # noqa: ANN001, ANN201
        return query.filter(name__startswith=principal.attributes["prefix"])


class _GroupSerializer(ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "name"]


class _Page(PageNumberPagination):
    page_size = 2


class _GroupView(ResourcePolicyViewMixin, ModelViewSet):
    queryset = Group.objects.order_by("name")
    serializer_class = _GroupSerializer
    pagination_class = _Page
    resource_policy = _Policy()


class _HiddenGroupView(_GroupView):
    policy_hides_existence = True

    def get_queryset(self):  # noqa: ANN201
        # Bypass scoping so the object-level check is the one exercised.
        return Group.objects.all()


def _call(view, method: str, path: str, **kwargs) -> Response:  # noqa: ANN001
    request = getattr(APIRequestFactory(), method)(path)
    force_authenticate(
        request, user=Principal(subject="1", attributes={"prefix": "a-"})
    )
    return view(request, **kwargs)


def test_scoped_list_paginates_only_permitted_rows() -> None:
    for name in ("a-1", "a-2", "a-3", "b-1", "b-2"):
        Group.objects.create(name=name)
    view = _GroupView.as_view({"get": "list"})

    first = _call(view, "get", "/groups/")
    second = _call(view, "get", "/groups/?page=2")

    assert first.data["count"] == 3
    assert [g["name"] for g in first.data["results"]] == ["a-1", "a-2"]
    assert [g["name"] for g in second.data["results"]] == ["a-3"]
    assert second.data["next"] is None


def test_out_of_scope_detail_is_404_and_denied_object_follows_setting() -> None:
    allowed = Group.objects.create(name="a-1")
    other = Group.objects.create(name="b-1")

    assert (
        _call(
            _GroupView.as_view({"get": "retrieve"}), "get", "/", pk=allowed.pk
        ).status_code
        == 200
    )
    assert (
        _call(
            _GroupView.as_view({"get": "retrieve"}), "get", "/", pk=other.pk
        ).status_code
        == 404
    )
    assert (
        _call(
            _HiddenGroupView.as_view({"get": "retrieve"}), "get", "/", pk=other.pk
        ).status_code
        == 404
    )

    class Visible(_GroupView):
        def get_queryset(self):  # noqa: ANN201
            return Group.objects.all()

    assert (
        _call(Visible.as_view({"get": "retrieve"}), "get", "/", pk=other.pk).status_code
        == 403
    )
