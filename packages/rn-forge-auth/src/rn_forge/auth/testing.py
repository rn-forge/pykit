"""An in-process OpenID Connect provider for tests.

:class:`FakeOidcProvider` serves discovery, a key set with rotation, an
authorization endpoint, a token endpoint, UserInfo and back-channel logout
tokens on a loopback port. Nothing leaves the machine. Each field of
:class:`Faults` switches one failure on.

Requires the ``oidc`` extra. Not imported by :mod:`rn_forge.auth`; import this
module directly.

Example:
    >>> with FakeOidcProvider() as idp:
    ...     idp.issuer.startswith("http://127.0.0.1:")
    True
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Literal, NamedTuple, Self, cast
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

__all__ = ["FakeOidcProvider", "Faults", "RecordedRequest"]

_BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
_OTHER_ISSUER = "https://other-issuer.invalid"
_OTHER_CLIENT = "other-client"
_JSON = "application/json"


class RecordedRequest(NamedTuple):
    """One request the provider received."""

    method: str
    path: str
    """The URL path without the query string."""


@dataclass
class Faults:
    """Failure switches for :class:`FakeOidcProvider`. Each is off by default.

    Attributes:
        response_iss: The authorization response carries an ``iss`` parameter
            naming another issuer.
        response_iss_missing: The authorization response carries no ``iss``
            parameter, although discovery advertises it.
        discovery_issuer: The discovery document names another issuer.
        userinfo_sub_mismatch: UserInfo returns a ``sub`` that differs from the
            ID token's.
        wrong_nonce: The ID token carries a different ``nonce``.
        wrong_aud: The ID token's ``aud`` is another client.
        wrong_azp: The ID token's ``aud`` lists the client and another one, and
            ``azp`` names the other one.
        wrong_at_hash: The ID token's ``at_hash`` is not the access token's hash.
        expired: The ID token's ``exp`` is in the past.
        alg_none: The ID token is unsigned (``alg: none``).
        unknown_kid: The ID token is signed with a key the key set does not
            list, under a ``kid`` it does not list.
    """

    response_iss: bool = False
    response_iss_missing: bool = False
    discovery_issuer: bool = False
    userinfo_sub_mismatch: bool = False
    wrong_nonce: bool = False
    wrong_aud: bool = False
    wrong_azp: bool = False
    wrong_at_hash: bool = False
    expired: bool = False
    alg_none: bool = False
    unknown_kid: bool = False


@dataclass
class _Grant:
    client_id: str
    redirect_uri: str
    code_challenge: str
    nonce: str
    scope: str
    user: dict[str, Any]
    auth_time: int


@dataclass(frozen=True)
class _Reply:
    status: int
    body: bytes = b""
    headers: tuple[tuple[str, str], ...] = ()

    @classmethod
    def json(
        cls, status: int, body: Mapping[str, Any], *headers: tuple[str, str]
    ) -> _Reply:
        return cls(
            status,
            json.dumps(body).encode(),
            (("Content-Type", _JSON), ("Cache-Control", "no-store"), *headers),
        )

    @classmethod
    def redirect(cls, location: str) -> _Reply:
        return cls(302, headers=(("Location", location),))

    @classmethod
    def oauth_error(cls, status: int, error: str, description: str) -> _Reply:
        return cls.json(status, {"error": error, "error_description": description})


class _Server(ThreadingHTTPServer):
    provider: FakeOidcProvider


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # http.server hook name
        self._dispatch("GET")

    def do_POST(self) -> None:  # http.server hook name
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parts = urlsplit(self.path)
        form: dict[str, str] = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            form = dict(parse_qsl(self.rfile.read(length).decode(), True))
        provider = cast(_Server, self.server).provider
        reply = provider._handle(  # pyright: ignore[reportPrivateUsage]
            method,
            parts.path,
            dict(parse_qsl(parts.query, True)),
            form,
            self.headers.get("Authorization"),
        )
        self.send_response(reply.status)
        for name, value in reply.headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(reply.body)))
        self.end_headers()
        self.wfile.write(reply.body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _half_hash(value: str) -> str:
    """OIDC Core §3.1.3.6 ``at_hash`` for RS256: half of the SHA-256 digest."""
    return _b64(hashlib.sha256(value.encode("ascii")).digest()[:16])


def _pkce_challenge(verifier: str) -> str:
    return _b64(hashlib.sha256(verifier.encode("ascii")).digest())


class FakeOidcProvider:
    """An OpenID Connect provider on ``127.0.0.1`` and an ephemeral port.

    The issuer is ``http://127.0.0.1:<port>/<tenant>``. The authorization
    endpoint approves *user* without a login page and redirects back with a
    single-use code; the token endpoint exchanges it, checking PKCE and the
    client's credentials. Use it as a context manager, or call :meth:`start`
    and :meth:`close`.

    Args:
        client_id: The registered client.
        client_secret: The client's secret, accepted as ``client_secret_post``
            or HTTP Basic. ``None`` registers a public client.
        redirect_uris: The registered redirect URIs.
        user: The claims of the user the authorization endpoint approves; it
            must contain ``sub``.
        tenant: The issuer's path segment.
        id_token_ttl: Seconds an ID token or an access token stays valid.

    Attributes:
        faults: The failure switches; assign :class:`Faults` or set fields.
        deny_authorization: When true the authorization endpoint answers
            ``access_denied`` instead of approving.
        advertise_end_session: Whether discovery lists ``end_session_endpoint``.
        auth_age: Seconds before each authorization request that the approved
            user is recorded as having authenticated; it sets the ID token's
            ``auth_time``.
        requests: Every request received, in order.
        issuer: The issuer URL.
        jwks_url: Where the key set is served.
    """

    def __init__(
        self,
        *,
        client_id: str = "web-login",
        client_secret: str | None = "fake-secret",
        redirect_uris: Sequence[str] = ("http://127.0.0.1/callback",),
        user: Mapping[str, Any] | None = None,
        tenant: str = "tenant",
        id_token_ttl: float = 300.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uris = list(redirect_uris)
        self.user: dict[str, Any] = dict(
            user or {"sub": "u1", "email": "u1@example.com", "name": "User One"}
        )
        self.id_token_ttl = id_token_ttl
        self.faults = Faults()
        self.deny_authorization = False
        self.advertise_end_session = True
        self.auth_age = 0.0
        self.requests: list[RecordedRequest] = []
        self.private_keys: dict[str, rsa.RSAPrivateKey] = {}
        self.keys: dict[str, dict[str, Any]] = {}
        self.current_kid = ""
        self._lock = threading.Lock()
        self._grants: dict[str, _Grant] = {}
        self._access_tokens: dict[str, dict[str, Any]] = {}
        self._rotations = 0
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.provider = self
        self._thread: threading.Thread | None = None
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._path = f"/{tenant.strip('/')}"
        self.issuer = f"{self._base}{self._path}"
        self.jwks_url = f"{self.issuer}/keys"
        self.authorization_endpoint = f"{self.issuer}/authorize"
        self.token_endpoint = f"{self.issuer}/token"
        self.userinfo_endpoint = f"{self.issuer}/userinfo"
        self.end_session_endpoint = f"{self.issuer}/logout"
        self.publish(self._next_kid(), current=True)

    def start(self) -> Self:
        """Begin serving. Calling it again has no effect."""
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._thread.start()
        return self

    def close(self) -> None:
        """Stop serving and release the port."""
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join()
            self._thread = None
        self._server.server_close()

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @cached_property
    def forged_key(self) -> rsa.RSAPrivateKey:
        """A private key the key set never lists."""
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def _next_kid(self) -> str:
        self._rotations += 1
        return f"k{self._rotations}"

    def publish(self, kid: str, *, current: bool = False) -> rsa.RSAPrivateKey:
        """Generate a key, list its public half in the key set under *kid* and
        return the private key. With *current*, new tokens are signed with it."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self._lock:
            self.private_keys[kid] = private_key
            self.keys[kid] = {
                **RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True),
                "kid": kid,
                "alg": "RS256",
                "use": "sig",
            }
            if current:
                self.current_kid = kid
        return private_key

    def rotate_key(self, *, retire_old: bool = False) -> str:
        """Publish a new key, make it the signing key and return its ``kid``.

        The old key stays in the key set unless *retire_old* is true.
        """
        old = self.current_kid
        kid = self._next_kid()
        self.publish(kid, current=True)
        if retire_old:
            with self._lock:
                self.keys.pop(old, None)
        return kid

    def sign(
        self,
        claims: Mapping[str, Any],
        *,
        typ: str | None = None,
        kid: str | None = None,
        alg: str = "RS256",
        key: rsa.RSAPrivateKey | None = None,
    ) -> str:
        """A token with exactly *claims* (``None`` values omitted).

        Args:
            claims: The payload.
            typ: The ``typ`` header; ``None`` omits it.
            kid: The ``kid`` header; defaults to the current signing key's.
            alg: ``RS256``, ``RS384``, ``RS512`` or ``none``.
            key: The private key to sign with; defaults to the one published
                under *kid*.
        """
        payload = {name: value for name, value in claims.items() if value is not None}
        kid = kid or self.current_kid
        headers: dict[str, Any] = {"kid": kid, "typ": typ}
        if alg == "none":
            return jwt.encode(payload, "", algorithm="none", headers=headers)
        signing_key = key if key is not None else self.private_keys[kid]
        return jwt.encode(payload, signing_key, algorithm=alg, headers=headers)

    def access_token(
        self,
        *,
        profile: Literal["rfc9068", "rfc7519"] = "rfc9068",
        audience: str | Sequence[str] = "api://orders",
        subject: str | None = None,
        client_id: str | None = None,
        scope: str | None = None,
        ttl: float = 300.0,
        **claims: Any,
    ) -> str:
        """A signed JWT access token for bearer tests.

        ``rfc9068`` carries ``typ: at+jwt`` and ``iss``, ``exp``, ``aud``,
        ``sub``, ``client_id``, ``iat`` and ``jti``. ``rfc7519`` carries no
        ``typ`` and only ``iss``, ``exp``, ``aud``, ``sub`` and ``iat``. Extra
        *claims* override those; a claim set to ``None`` is omitted.
        """
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "sub": subject or self.user["sub"],
            "aud": audience if isinstance(audience, str) else list(audience),
            "iat": now,
            "exp": now + int(ttl),
            "scope": scope,
        }
        if profile == "rfc9068":
            payload["client_id"] = client_id or self.client_id
            payload["jti"] = secrets.token_hex(8)
        return self.sign(
            {**payload, **claims}, typ="at+jwt" if profile == "rfc9068" else None
        )

    def logout_token(
        self,
        *,
        sid: str | None = None,
        sub: str | None = None,
        audience: str | None = None,
        ttl: float = 120.0,
        **claims: Any,
    ) -> str:
        """A back-channel logout token (OIDC Back-Channel Logout 1.0 §2.4).

        Args:
            sid: The session ID to end.
            sub: The subject whose sessions end.
            audience: The ``aud``; defaults to the client.
            ttl: Seconds until ``exp``.
            **claims: Extra or overriding claims; ``None`` omits one.

        Raises:
            ValueError: Neither *sid* nor *sub* is given.
        """
        if sid is None and sub is None:
            raise ValueError("A logout token needs a sid or a sub")
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": audience or self.client_id,
            "iat": now,
            "exp": now + int(ttl),
            "jti": secrets.token_hex(8),
            "events": {_BACKCHANNEL_LOGOUT_EVENT: {}},
            "sid": sid,
            "sub": sub,
        }
        return self.sign({**payload, **claims}, typ="logout+jwt")

    def fetches(self, suffix: str) -> int:
        """How many requests had a path ending with *suffix*."""
        return sum(request.path.endswith(suffix) for request in self.requests)

    def _handle(
        self,
        method: str,
        path: str,
        query: Mapping[str, str],
        form: Mapping[str, str],
        authorization: str | None,
    ) -> _Reply:
        self.requests.append(RecordedRequest(method, path))
        route = path.removeprefix(self._path)
        if method == "GET" and route == "/.well-known/openid-configuration":
            return _Reply.json(200, self._discovery())
        if method == "GET" and route == "/keys":
            with self._lock:
                return _Reply.json(200, {"keys": list(self.keys.values())})
        if method == "GET" and route == "/authorize":
            return self._authorize(query)
        if method == "POST" and route == "/token":
            return self._token(form, authorization)
        if method in ("GET", "POST") and route == "/userinfo":
            return self._userinfo(authorization)
        if method == "GET" and route == "/logout":
            target = query.get("post_logout_redirect_uri")
            return _Reply.redirect(target) if target else _Reply(200)
        return _Reply(404)

    def _discovery(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "issuer": _OTHER_ISSUER if self.faults.discovery_issuer else self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "jwks_uri": self.jwks_url,
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
            ],
            "authorization_response_iss_parameter_supported": True,
            "backchannel_logout_supported": True,
            "backchannel_logout_session_supported": True,
        }
        if self.advertise_end_session:
            document["end_session_endpoint"] = self.end_session_endpoint
        return document

    def _authorize(self, query: Mapping[str, str]) -> _Reply:
        redirect_uri = query.get("redirect_uri", "")
        if query.get("client_id") != self.client_id:
            return _Reply.oauth_error(400, "invalid_request", "unknown client_id")
        if redirect_uri not in self.redirect_uris:
            return _Reply.oauth_error(400, "invalid_request", "unregistered redirect")
        state = query.get("state", "")

        def back(**params: str) -> _Reply:
            params = {**params, "state": state}
            if not self.faults.response_iss_missing:
                params["iss"] = (
                    _OTHER_ISSUER if self.faults.response_iss else self.issuer
                )
            separator = "&" if urlsplit(redirect_uri).query else "?"
            return _Reply.redirect(f"{redirect_uri}{separator}{urlencode(params)}")

        problem = self._request_problem(query)
        if problem:
            return back(error="invalid_request", error_description=problem)
        if self.deny_authorization:
            return back(error="access_denied")
        code = secrets.token_urlsafe(24)
        with self._lock:
            self._grants[code] = _Grant(
                client_id=self.client_id,
                redirect_uri=redirect_uri,
                code_challenge=query["code_challenge"],
                nonce=query["nonce"],
                scope=query.get("scope", "openid"),
                user=dict(self.user),
                auth_time=int(time.time() - self.auth_age),
            )
        return back(code=code)

    @staticmethod
    def _request_problem(query: Mapping[str, str]) -> str | None:
        if query.get("response_type") != "code":
            return "response_type must be code"
        if "openid" not in query.get("scope", "").split():
            return "scope must include openid"
        if not query.get("state"):
            return "state is required"
        if not query.get("nonce"):
            return "nonce is required"
        if not query.get("code_challenge"):
            return "code_challenge is required"
        if query.get("code_challenge_method") != "S256":
            return "code_challenge_method must be S256"
        return None

    def _client_credentials(
        self, form: Mapping[str, str], authorization: str | None
    ) -> tuple[str | None, str | None]:
        if authorization and authorization.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(authorization[6:]).decode()
            except ValueError:
                return None, None
            client_id, _, secret = decoded.partition(":")
            return unquote_plus(client_id), unquote_plus(secret)
        return form.get("client_id"), form.get("client_secret")

    def _token(self, form: Mapping[str, str], authorization: str | None) -> _Reply:
        client_id, secret = self._client_credentials(form, authorization)
        if client_id != self.client_id or (
            self.client_secret is not None
            and not secrets.compare_digest(
                (secret or "").encode(), self.client_secret.encode()
            )
        ):
            return _Reply.oauth_error(401, "invalid_client", "client authentication")
        if form.get("grant_type") != "authorization_code":
            return _Reply.oauth_error(
                400, "unsupported_grant_type", "authorization_code only"
            )
        with self._lock:
            grant = self._grants.pop(form.get("code", ""), None)
        if grant is None:
            return _Reply.oauth_error(400, "invalid_grant", "unknown or used code")
        if (
            grant.client_id != client_id
            or grant.redirect_uri != form.get("redirect_uri")
            or not secrets.compare_digest(
                _pkce_challenge(form.get("code_verifier", "")).encode(),
                grant.code_challenge.encode(),
            )
        ):
            return _Reply.oauth_error(400, "invalid_grant", "grant does not match")
        access_token = secrets.token_urlsafe(24)
        with self._lock:
            self._access_tokens[access_token] = dict(grant.user)
        return _Reply.json(
            200,
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": int(self.id_token_ttl),
                "scope": grant.scope,
                "id_token": self._id_token(grant, access_token),
            },
        )

    def _id_token(self, grant: _Grant, access_token: str) -> str:
        faults = self.faults
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "sub": grant.user["sub"],
            "aud": grant.client_id,
            "iat": now,
            "exp": now + int(self.id_token_ttl),
            "auth_time": grant.auth_time,
            "nonce": "wrong-nonce" if faults.wrong_nonce else grant.nonce,
            "at_hash": _half_hash(
                "not-the-access-token" if faults.wrong_at_hash else access_token
            ),
            "sid": f"sid-{grant.auth_time}",
        }
        if faults.wrong_aud:
            claims["aud"] = _OTHER_CLIENT
        if faults.wrong_azp:
            claims["aud"] = [grant.client_id, _OTHER_CLIENT]
            claims["azp"] = _OTHER_CLIENT
        if faults.expired:
            claims["iat"], claims["exp"] = now - 7200, now - 3600
        if faults.alg_none:
            return self.sign(claims, alg="none")
        if faults.unknown_kid:
            return self.sign(claims, kid="unknown-kid", key=self.forged_key)
        return self.sign(claims)

    def _userinfo(self, authorization: str | None) -> _Reply:
        scheme, _, token = (authorization or "").partition(" ")
        with self._lock:
            user = (
                self._access_tokens.get(token) if scheme.lower() == "bearer" else None
            )
        if user is None:
            return _Reply(
                401, headers=(("WWW-Authenticate", 'Bearer error="invalid_token"'),)
            )
        if self.faults.userinfo_sub_mismatch:
            user = {**user, "sub": f"not-{user['sub']}"}
        return _Reply.json(200, user)
