"""Configuration guards for Django."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.utils import AppUtils
from rn_forge.commons.runtime.environment import Environment

__all__ = [
    "require_environment",
    "require_settings",
]

# ---------------------------------------------------------------------------
# Startup guards
# ---------------------------------------------------------------------------


def require_settings(*names: str) -> None:
    """Raise ``ImproperlyConfigured`` if any named Django setting is unset or blank.

    All missing names are reported together. Empty values follow
    :meth:`rn_forge.commons.lang.utils.AppUtils.is_empty`.

    Raises:
        ImproperlyConfigured: One or more settings are missing.
    """
    missing = sorted(
        name for name in names if AppUtils.is_empty(getattr(settings, name, None))
    )
    if missing:
        raise ImproperlyConfigured(
            f"Missing required Django setting(s): {', '.join(missing)}"
        )


def require_environment(*names: str) -> dict[str, str]:
    """Return the named environment variables, raising if any is unset or blank.

    Raises:
        ImproperlyConfigured: One or more variables are missing; the message
            names all of them.
    """
    try:
        return Environment.require(*names)
    except AppException as exc:
        raise ImproperlyConfigured(exc.message) from exc
