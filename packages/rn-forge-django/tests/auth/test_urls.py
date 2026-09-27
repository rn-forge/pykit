from __future__ import annotations

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from rn_forge.django.auth.urls import router, urlpatterns  # noqa: E402

pytestmark = pytest.mark.unit


class TestAuthUrls:
    def test_registers_expected_routes(self) -> None:
        names = {
            pattern.name
            for pattern in list(router.urls) + list(urlpatterns)
            if pattern.name
        }

        assert "rn-forge-auth-permission-list" in names
        assert "rn-forge-auth-group-list" in names
        assert "rn-forge-auth-user-list" in names
        assert "rn-forge-auth-user-token" in names

    def test_exposes_urlpatterns(self) -> None:
        assert urlpatterns
