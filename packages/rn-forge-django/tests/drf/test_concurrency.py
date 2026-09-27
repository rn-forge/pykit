from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

rest_framework = pytest.importorskip("rest_framework")

from rest_framework.parsers import JSONParser  # noqa: E402
from rest_framework.request import Request  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.drf.concurrency import enforce_version, etag_for  # noqa: E402
from rn_forge.django.drf.exceptions import problem_details_exception_handler  # noqa: E402
from rn_forge.web import (  # noqa: E402
    EntityVersionETagCodec,
    MalformedPrecondition,
    PreconditionRequired,
    VersionConflict,
    check_precondition,
)

pytestmark = pytest.mark.unit

ROW = SimpleNamespace(pk=17, version=3)


def _request(body=None, **headers: str) -> Request:
    raw = APIRequestFactory().patch(
        "/orders/17", body or {}, format="json", headers=headers
    )
    return Request(raw, parsers=[JSONParser()])


def _status(exc: Exception, request: Request) -> int:
    return problem_details_exception_handler(
        exc, {"request": request, "view": None}
    ).status_code


class TestEnforceVersion:
    def test_matching_header_passes(self) -> None:
        enforce_version(_request(**{"If-Match": 'W/"3"'}), ROW)

    def test_star_passes(self) -> None:
        enforce_version(_request(**{"If-Match": "*"}), ROW)

    def test_stale_header_is_version_conflict_and_412(self) -> None:
        request = _request(**{"If-Match": 'W/"2"'})
        with pytest.raises(VersionConflict) as caught:
            enforce_version(request, ROW)
        assert _status(caught.value, request) == 412

    def test_malformed_header_raises(self) -> None:
        with pytest.raises(MalformedPrecondition):
            enforce_version(_request(**{"If-Match": "3"}), ROW)

    def test_body_version_fallback(self) -> None:
        enforce_version(_request({"version": 3}), ROW)
        with pytest.raises(VersionConflict):
            enforce_version(_request({"version": 2}), ROW)

    @pytest.mark.parametrize("value", ["three", True, -1, 2.5])
    def test_malformed_body_version_raises(self, value) -> None:
        with pytest.raises(MalformedPrecondition):
            enforce_version(_request({"version": value}), ROW)

    def test_header_takes_precedence_over_body(self) -> None:
        enforce_version(_request({"version": 1}, **{"If-Match": 'W/"3"'}), ROW)

    def test_absent_and_required_is_428(self) -> None:
        request = _request()
        with pytest.raises(PreconditionRequired) as caught:
            enforce_version(request, ROW, required=True)
        assert _status(caught.value, request) == 428

    def test_absent_and_not_required_passes(self) -> None:
        enforce_version(_request(), ROW)

    def test_entity_codec_binds_the_id(self) -> None:
        codec = EntityVersionETagCodec()
        enforce_version(_request(**{"If-Match": 'W/"17:3"'}), ROW, codec=codec)
        with pytest.raises(VersionConflict):
            enforce_version(_request(**{"If-Match": 'W/"18:3"'}), ROW, codec=codec)


class TestEtagFor:
    def test_default_form(self) -> None:
        assert etag_for(ROW) == 'W/"3"'

    def test_round_trips_through_check_precondition(self) -> None:
        codec = EntityVersionETagCodec()
        check_precondition(
            etag_for(ROW, codec=codec),
            current_version=ROW.version,
            entity_id=ROW.pk,
            codec=codec,
            required=True,
        )
