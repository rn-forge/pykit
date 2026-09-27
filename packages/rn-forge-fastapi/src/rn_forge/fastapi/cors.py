"""An opt-in CORS module over Starlette's own ``CORSMiddleware``.

**The application owns its CORS policy** — which origins, and whether there is
one at all. What this module adds is not a policy but the one default only
this kit can supply: a browser cannot read ``ETag`` or ``Link`` unless they
are named in ``Access-Control-Expose-Headers``, and an application-owned CORS
block does not know what headers the kit emits. ``traceresponse`` needs no
entry here — the OpenTelemetry response propagator exposes it itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from rn_forge.web import EXPOSED_HEADERS, WebError

__all__ = ["CorsPolicy", "apply_cors"]


@dataclass(frozen=True, slots=True, kw_only=True)
class CorsPolicy:
    """A CORS policy: the application's origins, and this kit's own defaults.

    Args:
        allow_origins: The origins this API allows. No default — naming them
            is the application's decision.
        allow_credentials: Whether to allow cookies/credentials.
        allow_methods: The methods a preflight may approve.
        allow_headers: The request headers a preflight may approve.
        expose_headers: The response headers a browser may read. Defaults to
            :data:`rn_forge.web.EXPOSED_HEADERS`.
        max_age: How long, in seconds, a preflight result may be cached.

    Raises:
        WebError: *allow_credentials* is set and *allow_origins* contains
            ``"*"`` — a combination browsers reject outright.
    """

    allow_origins: tuple[str, ...]
    allow_credentials: bool = False
    allow_methods: tuple[str, ...] = (
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    )
    allow_headers: tuple[str, ...] = (
        "Authorization",
        "Content-Type",
        "If-Match",
        "Idempotency-Key",
    )
    expose_headers: tuple[str, ...] = field(default_factory=lambda: EXPOSED_HEADERS)
    max_age: int = 600

    def __post_init__(self) -> None:
        if self.allow_credentials and "*" in self.allow_origins:
            raise WebError("CorsPolicy cannot allow credentials with a wildcard origin")


def apply_cors(app: FastAPI, policy: CorsPolicy) -> None:
    """Install Starlette's ``CORSMiddleware`` configured from *policy*.

    Args:
        app: The application to install onto.
        policy: The CORS policy.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(policy.allow_origins),
        allow_credentials=policy.allow_credentials,
        allow_methods=list(policy.allow_methods),
        allow_headers=list(policy.allow_headers),
        expose_headers=list(policy.expose_headers),
        max_age=policy.max_age,
    )
