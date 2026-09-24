"""A DRF router that spells extra actions as AIP-136 custom methods."""

from __future__ import annotations

from typing import Any, cast

from rest_framework.routers import DefaultRouter, DynamicRoute, Route

__all__ = ["CustomMethodRouter"]


class CustomMethodRouter(DefaultRouter):
    """A :class:`~rest_framework.routers.DefaultRouter` with colon-form custom methods.

    An ``@action(detail=False, url_path="batchCreate")`` is served at
    ``/orders:batchCreate`` and an ``@action(detail=True, url_path="cancel")``
    at ``/orders/12:cancel``. Custom methods never take a trailing slash. The
    default lookup pattern excludes ``:``, so ``GET /orders/12:nope`` is a 404
    rather than a ``retrieve`` of ``"12:nope"``; a viewset's own
    ``lookup_value_regex`` overrides it.

    Example::

        router = CustomMethodRouter()
        router.register("orders", OrderViewSet, basename="orders")
        urlpatterns = router.urls
    """

    routes = [
        Route(
            url=r"^{prefix}{trailing_slash}$",
            mapping={"get": "list", "post": "create"},
            name="{basename}-list",
            detail=False,
            initkwargs={"suffix": "List"},
        ),
        DynamicRoute(
            url=r"^{prefix}:{url_path}$",
            name="{basename}-{url_name}",
            detail=False,
            initkwargs={},
        ),
        # Before the detail route, so `/orders/12:cancel` is never a `retrieve`.
        DynamicRoute(
            url=r"^{prefix}/{lookup}:{url_path}$",
            name="{basename}-{url_name}",
            detail=True,
            initkwargs={},
        ),
        Route(
            url=r"^{prefix}/{lookup}{trailing_slash}$",
            mapping={
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            },
            name="{basename}-detail",
            detail=True,
            initkwargs={"suffix": "Instance"},
        ),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        cast(Any, super()).__init__(*args, **kwargs)
        if self._use_regex:
            # DRF reads this in get_lookup_regex whenever a viewset sets no lookup_value_regex.
            self._default_value_pattern = "[^/.:]+"
