"""Optional SAML login views for rn-forge auth."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote, urldefrag
from typing import Any

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rn_forge.commons.logging import AppLogger
from rn_forge.django.auth.drf.authentication import BaseLoginAPIView
from rn_forge.django.auth.jwt.mixins import LoginExchangeViewMixin
from rn_forge.django.auth.payload import LoginPayload
from rn_forge.django.drf import RequestUtils
from rn_forge.django.settings import rn_forge_django_settings

from django.contrib.auth import get_user_model
from django.http import HttpResponseBase, HttpResponseRedirect

__all__ = [
    "SAMLLoginAPIView",
    "SAMLLoginViewMixin",
]

_LOGGER = AppLogger.get_logger(__name__)


class SAMLLoginViewMixin[_UserT](LoginExchangeViewMixin[_UserT]):
    """Hook-driven SAML login flow for consuming apps."""

    # -----------------------------------------------------------------------
    # Shared settings
    # -----------------------------------------------------------------------

    def get_saml_settings(self) -> Mapping[str, Any]:
        """Return the SAML provider settings for this view."""
        return rn_forge_django_settings.auth.saml.settings

    def get_saml_return_to(self, request: Request) -> str | None:
        """Return the SAML post-login target URL for the init-login flow."""
        return (
            RequestUtils.get_string(request, "return_to")
            or rn_forge_django_settings.auth.saml.return_to
        )

    # -----------------------------------------------------------------------
    # GET / login-init flow
    # -----------------------------------------------------------------------

    def build_saml_login_response(
        self,
        request: Request,
        auth: Any,
    ) -> HttpResponseBase:
        """Return a redirect to the SAML provider for login initiation."""
        return_to = self.get_saml_return_to(request)
        return HttpResponseRedirect(str(auth.login(return_to=return_to)))

    def build_saml_login_request_data(
        self,
        request: Request,
    ) -> Mapping[str, object]:
        """Hook for child classes to build the login-init SAML request data."""
        return {}

    def get_saml_login_auth(self, request: Request) -> Any:
        """Build the SAML client used for the login-init redirect flow."""
        return OneLogin_Saml2_Auth(
            self.build_saml_login_request_data(request),
            self.get_saml_settings(),
        )

    def get(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponseBase:
        """Dispatch ``GET`` requests to the SAML login initiation flow."""
        del args, kwargs
        auth = self.get_saml_login_auth(request)
        return self.build_saml_login_response(request, auth)

    # -----------------------------------------------------------------------
    # POST / ACS callback flow
    # -----------------------------------------------------------------------

    def build_saml_request_data(self, request: Request) -> Mapping[str, object]:
        """Hook for child classes to build the ACS/callback SAML request data."""
        raise NotImplementedError

    def get_saml_auth(self, request: Request) -> Any:
        """Build the SAML client used for the ACS/callback flow."""
        return OneLogin_Saml2_Auth(
            self.build_saml_request_data(request),
            self.get_saml_settings(),
        )

    def process_saml_auth(self, request: Request, auth: Any) -> None:
        """Process the provider response and reject invalid SAML state."""
        del request
        auth.process_response()
        errors = auth.get_errors()
        if errors:
            raise ValidationError({"saml": list(errors)})
        if not auth.is_authenticated():
            raise ValidationError({"saml": ["SAML user not authenticated"]})

    def get_saml_user_lookup(
        self,
        request: Request,
        auth: Any,
    ) -> dict[str, str]:
        """Return the local user lookup extracted from processed SAML data."""
        raise NotImplementedError

    def get_user(self, user_lookup: dict[str, str]) -> _UserT:
        """Resolve and return the target user for login."""
        raise NotImplementedError

    def create_user_for_login(
        self,
        request: Request,
        user_lookup: dict[str, str],
    ) -> _UserT:
        """Provision and return a user when auto-create is enabled."""
        raise NotImplementedError

    def build_saml_exchange_return_url(
        self,
        request: Request,
        exchange_token: str,
    ) -> str:
        """Return the browser redirect URL that carries the exchange token."""
        return_to = self.get_saml_return_to(request)
        if not return_to:
            raise ValidationError({"return_to": ["Missing SAML return target"]})
        base_return_to, _fragment = urldefrag(return_to)
        return f"{base_return_to}#exchange_token={quote(exchange_token, safe='')}"

    def complete_login(
        self,
        request: Request,
        login_payload: LoginPayload,
    ) -> HttpResponseBase:
        """Redirect the browser back with a short-lived exchange token."""
        exchange_token = self.build_login_exchange_token(login_payload)
        _LOGGER.success(
            "SAML login completed: user={}",
            getattr(login_payload.user, "email", login_payload.user),
        )
        return HttpResponseRedirect(
            self.build_saml_exchange_return_url(request, exchange_token),
        )

    def build_login_payload(self, request: Request) -> LoginPayload:
        """Return the normalized login payload for this SAML login request."""
        auth = self.get_saml_auth(request)
        self.process_saml_auth(request, auth)
        user_lookup = self.get_saml_user_lookup(request, auth)
        try:
            user = self.get_user(user_lookup)
        except get_user_model().DoesNotExist:
            if not getattr(self, "auto_create_user", False):
                raise
            user = self.create_user_for_login(request, user_lookup)
        return LoginPayload(user=user)


class SAMLLoginAPIView[_UserT](
    SAMLLoginViewMixin[_UserT],
    BaseLoginAPIView,
):
    """Common SAML login API view that returns an exchange token."""


SAMLJWTLoginAPIView = SAMLLoginAPIView
