"""A settings fragment for ``django-cors-headers``.

**Requires the ``cors`` extra.** Not re-exported from any facade; import it
directly.

**The application owns its CORS policy** — which origins, and whether there
is one at all. What this module adds is not a policy but the one default only
this kit can supply: a browser cannot read ``ETag``, ``Link`` or the
correlation header unless they are named in
``Access-Control-Expose-Headers``, and an application-owned CORS block does
not know what headers the kit emits.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rn_forge.web import EXPOSED_HEADERS

__all__ = ["cors_settings"]


def cors_settings(allowed_origins: Sequence[str]) -> dict[str, Any]:
    """Return a ``django-cors-headers`` settings fragment.

    Add ``"corsheaders"`` to ``INSTALLED_APPS`` and
    ``"corsheaders.middleware.CorsMiddleware"`` to ``MIDDLEWARE`` (above
    ``CommonMiddleware``) — this fragment carries only the settings values.

    Args:
        allowed_origins: The origins this API allows. No default — naming
            them is the application's decision.

    Returns:
        ``CORS_ALLOWED_ORIGINS`` and ``CORS_EXPOSE_HEADERS`` (from
        :data:`rn_forge.web.EXPOSED_HEADERS`).
    """
    return {
        "CORS_ALLOWED_ORIGINS": list(allowed_origins),
        "CORS_EXPOSE_HEADERS": list(EXPOSED_HEADERS),
    }
