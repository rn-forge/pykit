"""JWT token-exchange views for rn-forge auth."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.commons.logging import AppLogger

from rn_forge.django.auth.drf.authentication import BaseLoginAPIView
from rn_forge.django.auth.jwt.mixins import JWTAuthenticationViewMixin
from rn_forge.django.auth.jwt.utils import JWTUtils
from rn_forge.django.auth.payload import LoginPayload
from rn_forge.django.drf import RequestUtils

__all__ = ["UserTokenView"]

_LOGGER = AppLogger.get_logger(__name__)


@_LOGGER.audit_class(include_inherited=True)
class UserTokenView[_UserT](JWTAuthenticationViewMixin[_UserT], BaseLoginAPIView):
    """Exchange a short-lived login token for the final JWT pair."""

    exchange_token_param = "exchange_token"

    def get_exchange_token(self, request: Request) -> str:
        """Return the incoming login-exchange token."""
        token = RequestUtils.get_string(request, self.exchange_token_param)
        if not token:
            raise ValidationError(
                {self.exchange_token_param: ["Missing exchange token"]}
            )
        return token

    def get_exchange_token_payload(self, request: Request) -> dict[str, object]:
        """Return the decoded login-exchange payload."""
        exchange_token = self.get_exchange_token(request)
        try:
            return dict(JWTUtils.validate_login_exchange_token(exchange_token))
        except ValueError as exc:
            raise ValidationError({self.exchange_token_param: [str(exc)]}) from exc

    def get_login_exchange_user(
        self,
        exchange_payload: Mapping[str, object],
    ) -> _UserT:
        """Resolve the target user from the exchange token payload."""
        from rest_framework_simplejwt.settings import api_settings

        simplejwt_settings = cast(Any, api_settings)
        user_id_claim = cast(str, simplejwt_settings.USER_ID_CLAIM)
        user_id_field = cast(str, simplejwt_settings.USER_ID_FIELD)
        user_id = exchange_payload.get(user_id_claim)
        if user_id in {None, ""}:
            raise ValidationError(
                {self.exchange_token_param: ["Missing user identity"]}
            )

        user_model = cast(type[Any], get_user_model())
        try:
            return cast(
                _UserT, user_model._default_manager.get(**{user_id_field: user_id})
            )
        except user_model.DoesNotExist:
            raise ValidationError(
                {self.exchange_token_param: ["Unknown user"]}
            ) from None

    def build_login_payload(self, request: Request) -> LoginPayload:
        """Build the final JWT payload from the exchange token."""
        exchange_payload = self.get_exchange_token_payload(request)
        user = self.get_login_exchange_user(exchange_payload)
        return LoginPayload(user=user)

    def complete_login(
        self,
        request: Request,
        login_payload: LoginPayload,
    ) -> Response:
        """Return the final JWT payload without creating a Django session."""
        del request
        return Response(
            self.build_login_response(login_payload),
            status=200,
        )
