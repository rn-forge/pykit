from __future__ import annotations

import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from rn_forge.auth.oidc import JwtVerifier
from rn_forge.auth.testing import FakeOidcProvider

Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


def test_key_refresh(
    measure: Measure,
) -> None:
    verifications = 100
    with (
        FakeOidcProvider() as idp,
        measure(
            "auth_key_refresh",
            {"verifications": verifications, "rotations": 1},
            "io",
        ) as counts,
    ):
        verifier = JwtVerifier.from_jwks_url(
            idp.jwks_url,
            issuer=idp.issuer,
            audience=idp.client_id,
            cooldown_duration=0.0,
        )
        verifier.verify(
            idp.sign(
                {
                    "sub": "u1",
                    "iss": idp.issuer,
                    "aud": idp.client_id,
                    "exp": int(time.time()) + 300,
                }
            )
        )
        idp.rotate_key()
        token = idp.sign(
            {
                "sub": "u1",
                "iss": idp.issuer,
                "aud": idp.client_id,
                "exp": int(time.time()) + 300,
            }
        )
        verifier.verify(token)
        for _ in range(verifications - 2):
            verifier.verify(token)
        counts["verifications"] = verifications
        counts["requests"] = idp.fetches("/keys")
