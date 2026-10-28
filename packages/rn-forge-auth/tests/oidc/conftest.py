"""Fixtures for the OIDC tests.

``idp`` is the in-process fake provider from :mod:`rn_forge.auth.testing`, with
a bearer-token helper the profile tests use. Nothing leaves the machine.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from rn_forge.auth.oidc import OidcProvider  # noqa: E402
from rn_forge.auth.testing import FakeOidcProvider  # noqa: E402

AUDIENCE = "api://orders"


class FakeIdP(FakeOidcProvider):
    """The fake provider with a one-call signed token."""

    def sign(self, claims: Any, *, typ: str | None = "JWT", **kwargs: Any) -> str:
        return super().sign(claims, typ=typ, **kwargs)

    def token(self, *, kid: str | None = None, key: Any = None, **claims: Any) -> str:
        """A signed token; a claim set to ``None`` is omitted."""
        payload: dict[str, Any] = {
            "sub": "u1",
            "iss": self.issuer,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 300,
            **claims,
        }
        return self.sign(payload, kid=kid, key=key)


@pytest.fixture
def idp() -> Iterator[FakeIdP]:
    with FakeIdP() as fake:
        yield fake


@dataclass(frozen=True)
class CallbackRequest:
    """The native request a test binding hands the adapter."""

    query: Mapping[str, str] = field(default_factory=dict[str, str])
    form: Mapping[str, str] = field(default_factory=dict[str, str])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


@pytest.fixture
def request_of() -> type[CallbackRequest]:
    return CallbackRequest


@pytest.fixture
def browser() -> Callable[[str], CallbackRequest]:
    """Follow the authorization redirect, stopping at the callback.

    Returns the callback request the browser would send.
    """
    opener = urllib.request.build_opener(_NoRedirect)

    def visit(url: str) -> CallbackRequest:
        try:
            opener.open(url, timeout=5)
        except urllib.error.HTTPError as redirect:
            location = redirect.headers["Location"]
            return CallbackRequest(dict(parse_qsl(urlsplit(location).query)))
        raise AssertionError("the authorization endpoint did not redirect")

    return visit


@pytest.fixture
def make_provider(idp: FakeIdP) -> Callable[..., OidcProvider]:
    def make(**overrides: Any) -> OidcProvider:
        options: dict[str, Any] = {
            "id": "acme",
            "issuer": idp.issuer,
            "client_id": idp.client_id,
            "client_secret": idp.client_secret,
            "redirect_uri": idp.redirect_uris[0],
            **overrides,
        }
        return OidcProvider(**options)

    return make
