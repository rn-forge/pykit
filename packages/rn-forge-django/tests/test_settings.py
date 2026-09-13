from __future__ import annotations

import pytest
from django.test import override_settings

from rn_forge.django import settings as rnf_settings
from rn_forge.django.settings import (
    CasingSettings,
    DRFViewsSettings,
    PaginationSettings,
)

pytestmark = pytest.mark.unit


def _current():
    return rnf_settings.rn_forge_django_settings


class TestDefaults:
    def test_empty_setting_yields_every_default(self) -> None:
        with override_settings(RN_FORGE_DJANGO={}):
            conf = _current()
        assert conf.drf.views == DRFViewsSettings()
        assert conf.drf.pagination == PaginationSettings()
        assert conf.drf.casing == CasingSettings()
        assert conf.auth.saml.return_to is None

    def test_pagination_defaults(self) -> None:
        assert PaginationSettings() == PaginationSettings(
            page_size=50, page_size_query_param="pageSize", max_page_size=200
        )

    def test_casing_is_on_by_default(self) -> None:
        assert CasingSettings().enabled is True


class TestOverrideAndReload:
    def test_override_rebuilds_the_facade(self) -> None:
        with override_settings(
            RN_FORGE_DJANGO={
                "DRF": {
                    "VIEWS": {"EXPORT_MAX_ROWS": 5},
                    "PAGINATION": {"PAGE_SIZE": 10},
                    "CASING": {"ENABLED": False},
                },
                "AUTH": {"SAML": {"RETURN_TO": "/home"}},
            }
        ):
            conf = _current()
            assert conf.drf.views.export_max_rows == 5
            assert conf.drf.pagination.page_size == 10
            assert conf.drf.pagination.max_page_size == 200
            assert conf.drf.casing.enabled is False
            assert conf.auth.saml.return_to == "/home"

    def test_leaving_the_override_restores_the_previous_values(self) -> None:
        before = _current()
        with override_settings(
            RN_FORGE_DJANGO={"DRF": {"PAGINATION": {"PAGE_SIZE": 1}}}
        ):
            assert _current().drf.pagination.page_size == 1
        assert _current() == before

    def test_unrelated_setting_change_does_not_rebuild(self) -> None:
        before = _current()
        with override_settings(USE_TZ=True):
            assert _current() is before

    def test_non_mapping_section_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            with override_settings(RN_FORGE_DJANGO={"DRF": {"PAGINATION": 3}}):
                pass
