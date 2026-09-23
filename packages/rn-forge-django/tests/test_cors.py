from __future__ import annotations

import pytest

from rn_forge.django.cors import cors_settings
from rn_forge.web import EXPOSED_HEADERS

pytestmark = pytest.mark.unit


def test_cors_settings_carries_the_allowed_origins() -> None:
    settings = cors_settings(["https://example.com", "https://other.example.com"])
    assert settings["CORS_ALLOWED_ORIGINS"] == [
        "https://example.com",
        "https://other.example.com",
    ]


def test_cors_settings_exposes_the_kits_own_headers() -> None:
    settings = cors_settings(["https://example.com"])
    assert settings["CORS_EXPOSE_HEADERS"] == list(EXPOSED_HEADERS)
