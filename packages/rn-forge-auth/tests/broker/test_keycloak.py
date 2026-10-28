"""The broker profile against a real Keycloak (compose.yml in this directory).

Skipped unless RN_FORGE_AUTH_KEYCLOAK_URL names the server, such as
http://127.0.0.1:8080. The realms are imported from ``realms/``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit

import pytest

BASE_URL = os.environ.get("RN_FORGE_AUTH_KEYCLOAK_URL", "").rstrip("/")

pytestmark = [
    pytest.mark.broker,
    pytest.mark.skipif(not BASE_URL, reason="RN_FORGE_AUTH_KEYCLOAK_URL is not set"),
]

requests = pytest.importorskip("requests")
pytest.importorskip("authlib")
pytest.importorskip("jwt")

from assertpy import assert_that  # noqa: E402
from rn_forge.auth import InMemoryTransactionStore, LoginFlow  # noqa: E402
from rn_forge.auth.oidc import OidcAuthenticator, OidcProvider  # noqa: E402
from rn_forge.web import AuthenticationFailed, Credentials  # noqa: E402

ISSUER = f"{BASE_URL}/realms/broker"
REDIRECT_URI = "http://127.0.0.1:8099/auth/callback/keycloak"
AUDIENCE = "api://orders"
TIMEOUT = 10


@dataclass(frozen=True)
class CallbackRequest:
    query: Mapping[str, str] = field(default_factory=dict[str, str])
    form: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass
class Form:
    action: str
    method: str
    fields: dict[str, str] = field(default_factory=dict[str, str])


class FormParser(HTMLParser):
    """Collects every form and its named inputs."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[Form] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "form":
            self.forms.append(
                Form(values.get("action", ""), values.get("method", "get").lower())
            )
        elif tag == "input" and self.forms and "name" in values:
            self.forms[-1].fields[values["name"]] = values.get("value", "")


class HttpSession(requests.Session):
    """A session that sends Keycloak's Secure cookies over plain HTTP."""

    def request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        for cookie in self.cookies:
            cookie.secure = False
        return super().request(*args, **kwargs)


def _follow_to_callback(
    session: HttpSession, url: str, username: str, password: str
) -> CallbackRequest:
    """Drive the browser from *url* to the application's callback URL.

    Follows redirects by hand, fills the login form it meets, and submits the
    auto-post forms (the SAML request and response) unchanged.
    """
    response = session.get(url, allow_redirects=False, timeout=TIMEOUT)
    for _ in range(20):
        if response.is_redirect:
            target = urljoin(response.url, response.headers["Location"])
            if target.startswith(REDIRECT_URI):
                return CallbackRequest(query=dict(parse_qsl(urlsplit(target).query)))
            response = session.get(target, allow_redirects=False, timeout=TIMEOUT)
            continue
        assert response.status_code == 200, response.text[:500]
        parser = FormParser()
        parser.feed(response.text)
        assert parser.forms, f"no form at {response.url}: {response.text[:500]}"
        form = parser.forms[0]
        fields = dict(form.fields)
        if "password" in fields:
            fields.update(username=username, password=password)
        action = urljoin(response.url, form.action)
        response = session.post(
            action, data=fields, allow_redirects=False, timeout=TIMEOUT
        )
    raise AssertionError("too many redirects")


@pytest.fixture
def flow() -> LoginFlow[CallbackRequest]:
    provider = OidcProvider(
        id="keycloak",
        issuer=ISSUER,
        client_id="rn-forge-app",
        client_secret="app-secret",
        redirect_uri=REDIRECT_URI,
    )
    return LoginFlow(
        {"keycloak": provider},
        InMemoryTransactionStore(),
        return_to_prefixes=["/app"],
    )


def _login(
    flow: LoginFlow[CallbackRequest], *, hint: str = "", username: str, password: str
):
    start = flow.begin("keycloak", CallbackRequest(), return_to="/app/orders")
    assert start.redirect_url is not None
    url = start.redirect_url + (f"&kc_idp_hint={hint}" if hint else "")
    callback = _follow_to_callback(HttpSession(), url, username, password)
    return flow.complete("keycloak", callback, transaction_id=start.transaction.id)


def test_oidc_login(flow: LoginFlow[CallbackRequest]) -> None:
    identity = _login(flow, username="alice", password="alice-pw")

    assert_that(identity.provider).is_equal_to("keycloak")
    assert_that(identity.issuer).is_equal_to(ISSUER)
    assert_that(identity.subject).is_not_empty()
    assert_that(identity.email).is_equal_to("alice@example.com")
    assert_that(identity.email_verified).is_true()


def test_login_federated_from_a_saml_idp(flow: LoginFlow[CallbackRequest]) -> None:
    identity = _login(flow, hint="saml-idp", username="bob", password="bob-pw")

    assert_that(identity.issuer).is_equal_to(ISSUER)
    assert_that(identity.subject).is_not_empty()
    assert_that(identity.email).is_equal_to("bob@example.com")


def test_client_credentials_token_authenticates_a_bearer_call() -> None:
    response = requests.post(
        f"{ISSUER}/protocol/openid-connect/token",
        data={"grant_type": "client_credentials"},
        auth=("orders-m2m", "m2m-secret"),
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    credentials = Credentials("Bearer", response.json()["access_token"])

    principal = OidcAuthenticator.from_issuer(ISSUER, audience=AUDIENCE).authenticate(
        credentials=credentials
    )

    assert_that(principal.issuer).is_equal_to(ISSUER)
    assert_that(principal.subject).is_not_empty()
    assert_that(principal.mechanism).is_equal_to("bearer")

    wrong_audience = OidcAuthenticator.from_issuer(ISSUER, audience="api://other")
    with pytest.raises(AuthenticationFailed):
        wrong_audience.authenticate(credentials=credentials)
