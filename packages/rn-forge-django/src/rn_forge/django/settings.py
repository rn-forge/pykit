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
    "CasingSettings",
    "CasingSettingsDict",
    "DRFSettings",
    "DRFSettingsDict",
    "PaginationSettings",
    "PaginationSettingsDict",
    "RnforgeDjangoSettings",
    "RnforgeDjangoSettingsDict",
    "TransferSettings",
    "TransferSettingsDict",
    "rn_forge_django_settings",
]

_LOGGER = AppLogger.get_logger(__name__)
_SETTINGS_NAME = "RN_FORGE_DJANGO"
_DEFAULT_TRANSFER_MAX_ROWS = 10_000
_DEFAULT_PAGE_SIZE = 50
_DEFAULT_PAGE_SIZE_QUERY_PARAM = "pageSize"
_DEFAULT_MAX_PAGE_SIZE = 200
_DEFAULT_CASING_ENABLED = True


# ---------------------------------------------------------------------------
# Public Settings Shape
# ---------------------------------------------------------------------------


class TransferSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["DRF"]["TRANSFER"]``."""

    MAX_ROWS: int | None


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

    TRANSFER: TransferSettingsDict
    PAGINATION: PaginationSettingsDict
    CASING: CasingSettingsDict


class AuthSettingsDict(TypedDict, total=False):
    """Typed Django settings shape for ``RN_FORGE_DJANGO["AUTH"]``."""

    PROBLEM_TYPE_BASE: str


class RnforgeDjangoSettingsDict(TypedDict, total=False):
    """Typed Django settings shape consumed by ``RN_FORGE_DJANGO``."""

    AUTH: AuthSettingsDict
    DRF: DRFSettingsDict


# ---------------------------------------------------------------------------
# Runtime Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransferSettings:
    """Runtime settings for tabular transfer and batch operations.

    ``max_rows`` caps the rows of one export, import or batch request; ``None``
    removes the cap.
    """

    max_rows: int | None = _DEFAULT_TRANSFER_MAX_ROWS


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
    """Runtime settings for the camelCase JSON renderer and parser."""

    enabled: bool = _DEFAULT_CASING_ENABLED


@dataclass(frozen=True)
class DRFSettings:
    """Runtime settings for DRF integration helpers."""

    transfer: TransferSettings = field(default_factory=TransferSettings)
    pagination: PaginationSettings = field(default_factory=PaginationSettings)
    casing: CasingSettings = field(default_factory=CasingSettings)


@dataclass(frozen=True)
class AuthSettings:
    """Runtime settings for auth helpers."""

    problem_type_base: str = ""


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
    transfer_config = _get_mapping(config, "DRF.TRANSFER")
    pagination_config = _get_mapping(config, "DRF.PAGINATION")
    casing_config = _get_mapping(config, "DRF.CASING")

    return RnforgeDjangoSettings(
        auth=AuthSettings(
            problem_type_base=str(auth_config.get("PROBLEM_TYPE_BASE", "")),
        ),
        drf=DRFSettings(
            transfer=TransferSettings(
                max_rows=cast(
                    int | None,
                    transfer_config.get("MAX_ROWS", _DEFAULT_TRANSFER_MAX_ROWS),
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


# Built on first use: a settings module may import this package before it
# defines RN_FORGE_DJANGO.
class _LazySettings:
    """The settings facade, built on first attribute access."""

    def __init__(self) -> None:
        self._built: RnforgeDjangoSettings | None = None

    def rebuild(self) -> None:
        self._built = _build_settings()

    def __getattr__(self, name: str) -> Any:
        if self._built is None:
            self._built = _build_settings()
        return getattr(self._built, name)


_LAZY = _LazySettings()
rn_forge_django_settings = cast(RnforgeDjangoSettings, _LAZY)


def _reload_settings(*, setting: str, **kwargs: Any) -> None:
    """Reload the runtime facade when Django settings override this package."""
    del kwargs
    if setting != _SETTINGS_NAME:
        return

    _LAZY.rebuild()
    _LOGGER.debug("{} reloaded", _SETTINGS_NAME)  # noqa: PLE1205  # brace-style log format


setting_changed.connect(_reload_settings)
