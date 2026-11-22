"""Typed settings loaded from prefixed environment variables.

Provides:

- :class:`EnvSettings` — a frozen ``pydantic_settings.BaseSettings`` that an
  application subclasses, with :meth:`EnvSettings.load` as its entry point.
- :class:`SettingsError` — every invalid or missing variable at once, each
  named by its environment variable.

Requires the ``settings`` extra. Not imported by ``rn_forge.commons``'s curated
``__init__.py``; import this module directly.

Example::

    from pydantic_settings import SettingsConfigDict
    from rn_forge.commons.lang.settings import EnvSettings

    class AppSettings(EnvSettings):
        model_config = SettingsConfigDict(env_prefix="APP_")

        workers: int = 1
        enabled: bool = False

    AppSettings.load({"APP_WORKERS": "x"})
    # SettingsError: Invalid settings: APP_WORKERS: Input should be a valid integer...
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any, ClassVar, Self

from pydantic import ValidationError, field_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources.utils import parse_env_vars
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.utils import AppUtils

__all__ = ["EnvSettings", "SettingsError"]

_environ: ContextVar[Mapping[str, str] | None] = ContextVar(
    "rn_forge_env_settings_environ", default=None
)


class SettingsError(AppException):
    """Settings failed validation; :attr:`variables` names every culprit.

    Args:
        errors: ``(variable, message)`` pairs, one per failure.
    """

    variables: tuple[str, ...]

    def __init__(self, errors: tuple[tuple[str, str], ...]) -> None:
        ordered = sorted(errors)
        self.variables = tuple(sorted({variable for variable, _ in ordered}))
        super().__init__(
            "Invalid settings: {}",
            "; ".join(f"{variable}: {message}" for variable, message in ordered),
            variables=list(self.variables),
        )


class _MappingEnvSource(EnvSettingsSource):
    # The base class reads os.environ inside _load_env_vars; swapping that one
    # method is the narrowest way to feed it another mapping.
    def _load_env_vars(self) -> Mapping[str, str | None]:
        environ = _environ.get()
        if environ is None:
            return super()._load_env_vars()
        return parse_env_vars(
            environ,
            self.case_sensitive,
            self.env_ignore_empty,
            self.env_parse_none_str,
        )


class EnvSettings(BaseSettings):
    """Frozen settings read from environment variables.

    Subclass it and set ``env_prefix`` in ``model_config``; the subclass's
    config is merged with this one. No ``.env`` file or secrets directory is
    read unless the subclass sets ``env_file`` or ``secrets_dir``. A ``bool``
    field takes the tokens :meth:`AppUtils.parse_bool` takes.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        case_sensitive=False,
        env_file=None,
        secrets_dir=None,
        extra="ignore",
    )

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Build the settings from *environ*, or ``os.environ`` when ``None``.

        ``os.environ`` is never modified.

        Args:
            environ: The variables to read.

        Returns:
            The validated settings.

        Raises:
            SettingsError: A variable is invalid or a required one is missing.
        """
        token = _environ.set(environ)
        try:
            return cls()
        except ValidationError as error:
            raise SettingsError(_variable_errors(cls, error)) from error
        finally:
            _environ.reset(token)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Replace the environment source with one that honours :meth:`load`."""
        return (
            init_settings,
            _MappingEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("*", mode="before")
    @classmethod
    def _parse_bool_tokens(cls, value: Any, info: Any) -> Any:
        field = cls.model_fields.get(info.field_name)
        if field is None or field.annotation is not bool or not isinstance(value, str):
            return value
        return AppUtils.parse_bool(value)


def _variable_errors(
    settings: type[EnvSettings], error: ValidationError
) -> tuple[tuple[str, str], ...]:
    prefix = settings.model_config.get("env_prefix") or ""
    return tuple(
        ((prefix + str(detail["loc"][0])).upper(), detail["msg"])
        for detail in error.errors()
    )
