"""Auth URLconf for reusable rn-forge Django auth views."""

from __future__ import annotations

from typing import Any, cast

from django.urls import path
from rest_framework.routers import DefaultRouter

from rn_forge.django.auth.drf.views import (
    GroupViewSet,
    PermissionViewSet,
    UserUpsertImportViewSet,
    UserViewSet,
)
from rn_forge.django.auth.jwt.views import UserTokenView

__all__ = [
    "router",
    "urlpatterns",
]

router = cast(Any, DefaultRouter())
router.register("permissions", PermissionViewSet, basename="rn-forge-auth-permission")
router.register("groups", GroupViewSet, basename="rn-forge-auth-group")
router.register("users", UserViewSet, basename="rn-forge-auth-user")
router.register(
    "users-import",
    UserUpsertImportViewSet,
    basename="rn-forge-auth-user-import",
)

urlpatterns = router.urls
urlpatterns += [
    path(
        "user-token/",
        cast(Any, UserTokenView).as_view(),
        name="rn-forge-auth-user-token",
    ),
]
