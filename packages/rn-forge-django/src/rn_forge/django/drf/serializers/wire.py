"""DRF serializer mirrors of the shared web error and health shapes."""

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
