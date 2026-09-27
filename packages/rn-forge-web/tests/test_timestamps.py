"""Timestamps serialise as RFC 3339 UTC with a ``Z`` suffix (AIP-142)."""

from datetime import UTC, datetime

import pytest

from rn_forge.web.models import WireModel

pytestmark = pytest.mark.unit


class _Stamped(WireModel):
    create_time: datetime


def test_wire_model_renders_utc_with_z():
    body = _Stamped(create_time=datetime(2026, 9, 23, 14, 5, tzinfo=UTC)).model_dump(
        mode="json"
    )
    assert body == {"createTime": "2026-09-23T14:05:00Z"}
