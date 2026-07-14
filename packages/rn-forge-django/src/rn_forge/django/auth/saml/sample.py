"""Sample SAML JWT login view for consuming apps."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from django.contrib.auth import get_user_model, models
from rest_framework.request import Request
from rn_forge.commons.logging import AppLogger

from rn_forge.django.auth.saml.views import SAMLLoginAPIView

__all__ = [
    "SampleSAMLLoginAPIView",
    "SampleSAMLJWTLoginAPIView",
]

_LOGGER = AppLogger.get_logger(__name__)


@_LOGGER.audit_class(include_inherited=True)
class SampleSAMLLoginAPIView(SAMLLoginAPIView[models.AbstractUser]):
    """Example app-owned SAML login view that mints rn-forge JWT tokens."""

    auto_create_user = True
    saml_attribute_email = "email"
    saml_attribute_username = "username"
    saml_attribute_first_name = "first_name"
    saml_attribute_last_name = "last_name"

    def build_saml_request_data(self, request: Request) -> Mapping[str, object]:
        """Return the SAML callback request payload for the provider."""
        del request
        return {
            "https": "on",
        }

    def get_saml_user_lookup(
        self,
        request: Request,
        auth: Any,
    ) -> dict[str, str]:
        """Extract the local user lookup from the processed SAML assertion."""
        del request
        attributes = auth.get_attributes()
        email = self._get_saml_attribute(attributes, self.saml_attribute_email)
        username = self._get_saml_attribute(attributes, self.saml_attribute_username)
        if email:
            return {"email": email}
        if username:
            return {"username": username}
        raise ValueError("SAML assertion did not contain an email or username")

    def get_user(self, user_lookup: dict[str, str]) -> models.AbstractUser:
        """Resolve the local user for the SAML assertion."""
        user_model = cast(type[models.AbstractUser], get_user_model())
        return cast(models.AbstractUser, user_model.objects.get(**user_lookup))

    def create_user_for_login(
        self,
        request: Request,
        user_lookup: dict[str, str],
    ) -> models.AbstractUser:
        """Provision a local user when the SAML identity is new."""
        del request
        user_model = cast(type[models.AbstractUser], get_user_model())
        create_user = getattr(user_model.objects, "create_user", None)
        user_kwargs: dict[str, Any] = {
            **user_lookup,
            "first_name": "",
            "last_name": "",
        }
        if callable(create_user):
            return cast(models.AbstractUser, create_user(**user_kwargs))
        return cast(models.AbstractUser, user_model.objects.create(**user_kwargs))

    @staticmethod
    def _get_saml_attribute(
        attributes: Mapping[str, object],
        key: str,
    ) -> str | None:
        value = cast(Any, attributes.get(key))
        if isinstance(value, list) and value:
            return str(cast(Any, value[0]))
        if isinstance(value, str):
            return value
        if value is None:
            return None
        return str(cast(Any, value))


SampleSAMLJWTLoginAPIView = SampleSAMLLoginAPIView
