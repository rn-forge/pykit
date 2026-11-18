from __future__ import annotations

import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from statistics import median

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
        first_token = idp.sign(
            {
                "sub": "u1",
                "iss": idp.issuer,
                "aud": idp.client_id,
                "exp": int(time.time()) + 300,
            }
        )
        started = time.perf_counter()
        verifier.verify(first_token)
        counts["first_verify_s"] = time.perf_counter() - started
        idp.rotate_key()
        token = idp.sign(
            {
                "sub": "u1",
                "iss": idp.issuer,
                "aud": idp.client_id,
                "exp": int(time.time()) + 300,
            }
        )
        started = time.perf_counter()
        verifier.verify(token)
        counts["refresh_verify_s"] = time.perf_counter() - started
        cached = []
        for _ in range(verifications - 2):
            started = time.perf_counter()
            verifier.verify(token)
            cached.append(time.perf_counter() - started)
        counts["cached_verify_median_s"] = median(cached)
        counts["verifications"] = verifications
        counts["requests"] = idp.fetches("/keys")
