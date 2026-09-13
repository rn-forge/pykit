"""DRF serializer mirrors of the :mod:`rn_forge.web` wire shapes.

drf-spectacular builds ``components/schemas`` from serializers, so without
these the shared error and health types never reach a Django schema. They are
the counterparts of ``rn-forge-fastapi``'s pydantic mirrors, and each is named
so the component drf-spectacular derives (the class name less ``Serializer``)
is exactly the FastAPI side's: ``ProblemDetail``, ``Page``, ``CheckResult``,
``HealthReport``.

Field names are ``snake_case``; the camelCase renderer and the schema hook in
:mod:`rn_forge.django.drf.openapi` put them on the wire as camelCase. A
problem's extension members are flattened on the wire (RFC 9457 §3.2) and are
not modelled here.
"""

from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "CheckResultSerializer",
    "HealthReportSerializer",
    "PageSerializer",
    "ProblemDetailSerializer",
]

_CHECK_STATUSES = ["pass", "warn", "fail", "skipped"]


class ProblemDetailSerializer(serializers.Serializer):
    """Mirror of :class:`rn_forge.web.ProblemDetail`'s wire body."""

    type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.IntegerField()
    detail = serializers.CharField()
    instance = serializers.CharField()


class PageSerializer(serializers.Serializer):
    """Mirror of :class:`rn_forge.web.Page`: the AIP-158 envelope."""

    items = serializers.ListField(child=serializers.JSONField())
    next_page_token = serializers.CharField(allow_null=True)
    total_size = serializers.IntegerField(allow_null=True, required=False)


class CheckResultSerializer(serializers.Serializer):
    """Mirror of :class:`rn_forge.web.CheckResult`."""

    status = serializers.ChoiceField(choices=_CHECK_STATUSES)
    reason = serializers.CharField(allow_null=True, required=False)
    remediation = serializers.CharField(allow_null=True, required=False)
    details = serializers.DictField(required=False)


class HealthReportSerializer(serializers.Serializer):
    """Mirror of :meth:`rn_forge.web.HealthReport.as_body`; ``http_status`` stays off the wire."""

    status = serializers.ChoiceField(choices=_CHECK_STATUSES)
    checks = serializers.DictField(child=CheckResultSerializer())
