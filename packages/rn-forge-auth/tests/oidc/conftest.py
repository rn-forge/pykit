"""Fixtures for the OIDC tests.

``idp`` is the in-process fake provider from :mod:`rn_forge.auth.testing`, with
a bearer-token helper the profile tests use. Nothing leaves the machine.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("jwt")
pytest.importorskip("cryptography")

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
