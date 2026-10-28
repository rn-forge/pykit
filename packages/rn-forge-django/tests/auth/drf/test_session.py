from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from django.test import override_settings

pytest.importorskip("rest_framework")

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.sessions.backends.cache import SessionStore  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from rn_forge.auth import (  # noqa: E402
    InMemoryReplayStore,
    Principal,
    SessionInfo,
)
from rn_forge.django.auth.authorization import (  # noqa: E402
    DjangoAuthorizationContextProvider,
)
from rn_forge.django.auth.drf import (  # noqa: E402
    PermissionKeyPermission,
    PrincipalBearerAuthentication,
    PrincipalSessionAuthentication,
)
from rn_forge.django.auth.sessions import Sessions  # noqa: E402
from rn_forge.web import AuthenticationFailed  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

User = get_user_model()
CONTEXTS = DjangoAuthorizationContextProvider()
SESSIONS = Sessions(
    contexts=CONTEXTS,
    replay=InMemoryReplayStore(),
    idle_timeout=timedelta(minutes=30),
    absolute_timeout=timedelta(hours=1),
)


class _Tokens:
    def authenticate(self, *, credentials):
        if credentials.token == "good":
            return Principal(subject="s1", issuer="iss")
        raise AuthenticationFailed("bad")


class _Accounts:
    def lookup(self, issuer, subject):
        return str(User.objects.get(username="ada").pk)


class _Bearer(PrincipalBearerAuthentication):
    authenticator = _Tokens()
    accounts = _Accounts()
    contexts = CONTEXTS


class _Session(PrincipalSessionAuthentication):
    sessions = SESSIONS


class _View(APIView):
    authentication_classes = [_Bearer, _Session]
    permission_classes = [PermissionKeyPermission]

    def get(self, request):
        return Response(
            {"mechanism": request.user.mechanism, "roles": sorted(request.user.roles)}
        )


def _signed_in_get(user, **headers):
    request = APIRequestFactory().get("/", headers=headers)
    request.session = SessionStore()
    now = datetime.now(UTC)
    SESSIONS.start(
        request,
        SessionInfo(
            account_id=str(user.pk),
            session_version=0,
            provider="p",
            issuer="iss",
            external_subject="s1",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
    )
    return _View.as_view()(request)


def test_session_yields_a_session_principal() -> None:
    user = User.objects.create_user("ada", is_staff=True)
    response = _signed_in_get(user)
    assert response.status_code == 200
    assert response.data == {"mechanism": "session", "roles": ["staff"]}


def test_authorization_header_is_decided_by_the_bearer_path_alone() -> None:
    user = User.objects.create_user("ada")
    assert (
        _signed_in_get(user, Authorization="Bearer good").data["mechanism"] == "bearer"
    )
    assert _signed_in_get(user, Authorization="Bearer forged").status_code == 401
    assert _signed_in_get(user, Authorization="Basic abc").status_code == 401


def test_revoked_session_version_is_unauthenticated() -> None:
    user = User.objects.create_user("ada")
    request = APIRequestFactory().get("/")
    request.session = SessionStore()
    now = datetime.now(UTC)
    SESSIONS.start(
        request,
        SessionInfo(
            account_id=str(user.pk),
            session_version=7,
            provider="p",
            issuer="iss",
            external_subject="s1",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
    )
    assert _View.as_view()(request).status_code == 401


def _unauthenticated(*classes):
    class View(_View):
        authentication_classes = list(classes)

    request = APIRequestFactory().get("/")
    request.session = SessionStore()
    with override_settings(
        REST_FRAMEWORK={
            "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler"
        }
    ):
        response = View.as_view()(request)
    return response


@pytest.mark.parametrize("classes", [[_Session], [_Session, _Bearer]])
def test_session_first_is_401_without_a_challenge(classes) -> None:
    response = _unauthenticated(*classes)
    assert response.status_code == 401
    assert not response.has_header("WWW-Authenticate")


def test_bearer_first_keeps_the_bearer_challenge() -> None:
    response = _unauthenticated(_Bearer, _Session)
    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Bearer")


TOKEN = "a" * 32


class _Writable(APIView):
    authentication_classes = [_Session]
    permission_classes: list = []

    def post(self, request):
        return Response({"mechanism": request.user.mechanism})


def _signed_in_post(user, *, token: str | None, **headers):
    from rn_forge.django.auth import CSRF_SETTINGS

    request = APIRequestFactory(enforce_csrf_checks=True).post(
        "/", headers={**({"X-XSRF-TOKEN": token} if token else {}), **headers}
    )
    request.COOKIES["XSRF-TOKEN"] = TOKEN
    request.session = SessionStore()
    now = datetime.now(UTC)
    SESSIONS.start(
        request,
        SessionInfo(
            account_id=str(user.pk),
            session_version=0,
            provider="p",
            issuer="iss",
            external_subject="s1",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
    )
    with override_settings(
        **CSRF_SETTINGS,
        REST_FRAMEWORK={
            "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler"
        },
        RN_FORGE_DJANGO={"AUTH": {"PROBLEM_TYPE_BASE": "https://errors.example/"}},
    ):
        response = _Writable.as_view()(request)
    return response


def test_an_unsafe_session_request_without_the_token_is_csrf_failed() -> None:
    user = User.objects.create_user("ada")

    response = _signed_in_post(user, token=None)

    assert response.status_code == 403
    assert json.loads(response.content)["type"] == "https://errors.example/csrf-failed"


def test_an_unsafe_session_request_with_the_token_succeeds() -> None:
    user = User.objects.create_user("ada")

    response = _signed_in_post(user, token=TOKEN)

    assert response.status_code == 200
    assert response.data == {"mechanism": "session"}


def test_cross_site_fetch_metadata_is_csrf_failed_even_with_the_token() -> None:
    user = User.objects.create_user("ada")

    response = _signed_in_post(user, token=TOKEN, **{"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403
    assert json.loads(response.content)["type"] == "https://errors.example/csrf-failed"
