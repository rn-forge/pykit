"""Typed settings facade for ``rn-forge-django``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TypedDict, cast

from django.conf import settings
from django.core.signals import setting_changed
from rn_forge.commons.lang.collections import DictUtils
from rn_forge.commons.logging import AppLogger

__all__ = [
    "AuthSettings",
    "AuthSettingsDict",
    "AuthSAMLSettings",
    "AuthSAMLSettingsDict",
    "CasingSettings",
    "CasingSettingsDict",
    "DRFSettings",
    "DRFSettingsDict",
    "DRFViewsSettings",
    "DRFViewsSettingsDict",
    "PaginationSettings",
    "PaginationSettingsDict",
    "RnforgeDjangoSettings",
    "RnforgeDjangoSettingsDict",
    "rn_forge_django_settings",
]

_LOGGER = AppLogger.get_logger(__name__)
_SETTINGS_NAME = "RN_FORGE_DJANGO"
_DEFAULT_TRANSFER_FORMAT = "xlsx"
_DEFAULT_EXPORT_MAX_ROWS = 10_000
_DEFAULT_IMPORT_MAX_ROWS = 10_000
_DEFAULT_PAGE_SIZE = 50
_DEFAULT_PAGE_SIZE_QUERY_PARAM = "pageSize"
_DEFAULT_MAX_PAGE_SIZE = 200
_DEFAULT_CASING_ENABLED = True


# ---------------------------------------------------------------------------
# Public Settings Shape
# ---------------------------------------------------------------------------


class DRFViewsSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["DRF"]["VIEWS"]``."""

    DEFAULT_TRANSFER_FORMAT: str
    EXPORT_MAX_ROWS: int | None
    IMPORT_MAX_ROWS: int | None
    PERMISSION_ACTION_MAP: Mapping[str, str]


class PaginationSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["DRF"]["PAGINATION"]``."""

    PAGE_SIZE: int
    PAGE_SIZE_QUERY_PARAM: str
    MAX_PAGE_SIZE: int


class CasingSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["DRF"]["CASING"]``."""

    ENABLED: bool


class DRFSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["DRF"]``."""

    VIEWS: DRFViewsSettingsDict
    PAGINATION: PaginationSettingsDict
    CASING: CasingSettingsDict


class AuthSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["AUTH"]``."""

    SAML: "AuthSAMLSettingsDict"


class AuthSAMLSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["AUTH"]["SAML"]``."""

    SETTINGS: Mapping[str, Any]
    RETURN_TO: str | None


class RnforgeDjangoSettingsDict(TypedDict, total=False):
    """Typed Django settings shape consumed by ``RN_FORGE_DJANGO``."""

    AUTH: AuthSettingsDict
    DRF: DRFSettingsDict


# ---------------------------------------------------------------------------
# Runtime Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DRFViewsSettings:
    """Runtime settings for DRF view helpers."""

    default_transfer_format: str = _DEFAULT_TRANSFER_FORMAT
    export_max_rows: int | None = _DEFAULT_EXPORT_MAX_ROWS
    import_max_rows: int | None = _DEFAULT_IMPORT_MAX_ROWS
    permission_action_map: Mapping[str, str] = field(
        default_factory=lambda: cast(Mapping[str, str], {})
    )


@dataclass(frozen=True)
class PaginationSettings:
    """Runtime settings for the DRF pagination classes.

    Read at request time by both pagination classes, so ``override_settings``
    takes effect without a re-import.
    """

    page_size: int = _DEFAULT_PAGE_SIZE
    page_size_query_param: str = _DEFAULT_PAGE_SIZE_QUERY_PARAM
    max_page_size: int = _DEFAULT_MAX_PAGE_SIZE


@dataclass(frozen=True)
class CasingSettings:
    """Runtime settings for the camelCase JSON renderer and parser.

    ``enabled`` defaults to ``True``: camelCase on the wire is the kit's
    contract. Switching it off makes both classes behave as DRF's plain JSON
    renderer and parser.
    """

    enabled: bool = _DEFAULT_CASING_ENABLED


@dataclass(frozen=True)
class DRFSettings:
    """Runtime settings for DRF integration helpers."""

    views: DRFViewsSettings = field(default_factory=DRFViewsSettings)
    pagination: PaginationSettings = field(default_factory=PaginationSettings)
    casing: CasingSettings = field(default_factory=CasingSettings)


@dataclass(frozen=True)
class AuthSettings:
    """Runtime settings for auth helpers."""

    saml: "AuthSAMLSettings" = field(default_factory=lambda: AuthSAMLSettings())


@dataclass(frozen=True)
class AuthSAMLSettings:
    """Runtime settings for SAML auth helpers."""

    settings: Mapping[str, Any] = field(
        default_factory=lambda: cast(Mapping[str, Any], {})
    )
    return_to: str | None = None


@dataclass(frozen=True)
class RnforgeDjangoSettings:
    """Runtime settings facade for ``rn-forge-django``."""

    auth: AuthSettings = field(default_factory=AuthSettings)
    drf: DRFSettings = field(default_factory=DRFSettings)


def _settings_dict() -> Mapping[str, Any]:
    raw = getattr(settings, _SETTINGS_NAME, {})
    if not isinstance(raw, Mapping):
        raise TypeError(f"{_SETTINGS_NAME} must be a mapping")
    return cast(Mapping[str, Any], raw)


def _get_mapping(data: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    value = DictUtils.get(data, path)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{_SETTINGS_NAME}.{path} must be a mapping")
    return cast(Mapping[str, Any], value)


def _build_settings() -> RnforgeDjangoSettings:
    config = _settings_dict()
    auth_config = _get_mapping(config, "AUTH")
    views_config = _get_mapping(config, "DRF.VIEWS")
    pagination_config = _get_mapping(config, "DRF.PAGINATION")
    casing_config = _get_mapping(config, "DRF.CASING")

    return RnforgeDjangoSettings(
        auth=AuthSettings(
            saml=AuthSAMLSettings(
                settings=cast(
                    Mapping[str, Any],
                    _get_mapping(auth_config, "SAML").get("SETTINGS", {}),
                ),
                return_to=cast(
                    str | None,
                    _get_mapping(auth_config, "SAML").get("RETURN_TO"),
                ),
            ),
        ),
        drf=DRFSettings(
            views=DRFViewsSettings(
                default_transfer_format=str(
                    views_config.get(
                        "DEFAULT_TRANSFER_FORMAT",
                        _DEFAULT_TRANSFER_FORMAT,
                    )
                ),
                export_max_rows=cast(
                    int | None,
                    views_config.get(
                        "EXPORT_MAX_ROWS",
                        _DEFAULT_EXPORT_MAX_ROWS,
                    ),
                ),
                import_max_rows=cast(
                    int | None,
                    views_config.get(
                        "IMPORT_MAX_ROWS",
                        _DEFAULT_IMPORT_MAX_ROWS,
                    ),
                ),
                permission_action_map=cast(
                    Mapping[str, str],
                    views_config.get(
                        "PERMISSION_ACTION_MAP",
                        {},
                    ),
                ),
            ),
            pagination=PaginationSettings(
                page_size=cast(
                    int, pagination_config.get("PAGE_SIZE", _DEFAULT_PAGE_SIZE)
                ),
                page_size_query_param=str(
                    pagination_config.get(
                        "PAGE_SIZE_QUERY_PARAM", _DEFAULT_PAGE_SIZE_QUERY_PARAM
                    )
                ),
                max_page_size=cast(
                    int, pagination_config.get("MAX_PAGE_SIZE", _DEFAULT_MAX_PAGE_SIZE)
                ),
            ),
            casing=CasingSettings(
                enabled=bool(casing_config.get("ENABLED", _DEFAULT_CASING_ENABLED)),
            ),
        ),
    )


rn_forge_django_settings = _build_settings()


def _reload_settings(*, setting: str, **kwargs: Any) -> None:
    """Reload the runtime facade when Django settings override this package."""
    del kwargs
    if setting != _SETTINGS_NAME:
        return

    global rn_forge_django_settings
    rn_forge_django_settings = _build_settings()
    _LOGGER.debug("{} reloaded", _SETTINGS_NAME)


setting_changed.connect(_reload_settings)  # pyright: ignore[reportUnknownMemberType]  # Django signal stubs are incomplete
