"""Fixtures for the rn-forge-auth test suite.

``idp`` is an in-process fake identity provider on a loopback port: it serves
discovery and a key set, signs tokens, and counts requests. Nothing leaves the
machine.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

AUDIENCE = "api://orders"


class FakeIdP:
    """Serves ``/.well-known/openid-configuration`` and ``/keys`` for one issuer."""

    def __init__(self) -> None:
        self.keys: dict[str, Any] = {}
        self.requests: list[str] = []
        self.private_keys: dict[str, Any] = {}
        self.forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        idp = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802  # http.server hook name
                idp.requests.append(self.path)
                if self.path.endswith("/.well-known/openid-configuration"):
                    body: dict[str, Any] = {
                        "issuer": idp.issuer,
                        "jwks_uri": idp.jwks_url,
                    }
                elif self.path.endswith("/keys"):
                    body = {"keys": list(idp.keys.values())}
                else:
                    self.send_error(404)
                    return
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.issuer = f"http://127.0.0.1:{self._server.server_port}/tenant"
        self.jwks_url = f"{self.issuer}/keys"
        self.publish("k1")

    def publish(self, kid: str) -> Any:
        """Generate a key, serve its public half under *kid*, return the private key."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_keys[kid] = private_key
        self.keys[kid] = {
            **RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True),
            "kid": kid,
            "alg": "RS256",
            "use": "sig",
        }
        return private_key

    def fetches(self, suffix: str) -> int:
        """How many requests ended with *suffix*."""
        return sum(path.endswith(suffix) for path in self.requests)

    def token(self, *, kid: str = "k1", key: Any = None, **claims: Any) -> str:
        """A signed token; a claim set to ``None`` is omitted."""
        payload: dict[str, Any] = {
            "sub": "u1",
            "iss": self.issuer,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 300,
            **claims,
        }
        payload = {name: value for name, value in payload.items() if value is not None}
        signing_key = key if key is not None else self.private_keys[kid]
        return jwt.encode(payload, signing_key, algorithm="RS256", headers={"kid": kid})

    def sign(
        self,
        claims: dict[str, Any],
        *,
        typ: str | None = "JWT",
        kid: str = "k1",
        key: Any = None,
    ) -> str:
        """A token with exactly *claims* (``None`` values omitted) and header *typ*."""
        payload = {name: value for name, value in claims.items() if value is not None}
        headers: dict[str, Any] = {"kid": kid, "typ": typ}
        signing_key = key if key is not None else self.private_keys[kid]
        return jwt.encode(payload, signing_key, algorithm="RS256", headers=headers)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


@pytest.fixture
def idp() -> Iterator[FakeIdP]:
    fake = FakeIdP()
    yield fake
    fake.close()
