"""Tests for rn_forge.fastapi.merge_patch."""

import json

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from rn_forge.fastapi import (
    merge_into,
    merge_patch_body,
    merge_patch_openapi,
    register_problem_handlers,
    require_if_match,
)
from rn_forge.web import (
    MERGE_PATCH_MEDIA_TYPE,
    NULL_FIELD_DETAIL,
    PROBLEM_MEDIA_TYPE,
    EntityVersionETagCodec,
    check_precondition,
)

pytestmark = pytest.mark.unit


def j(value: object) -> bytes:
    return json.dumps(value).encode()


MERGE = {"Content-Type": MERGE_PATCH_MEDIA_TYPE}


class Doc(BaseModel):
    name: str
    note: str | None = None
    display_name: str = Field(default="", alias="displayName")
    tags: list[str] = []
    settings: dict[str, str] = {}


def initial() -> dict[str, object]:
    return {
        "name": "widget",
        "note": "fragile",
        "displayName": "W",
        "tags": ["a", "b"],
        "settings": {"color": "red", "size": "L"},
    }


def build_app() -> FastAPI:
    app = FastAPI()
    register_problem_handlers(app)
    state = {"doc": initial(), "version": 1}
    codec = EntityVersionETagCodec()

    @app.patch(
        "/docs/1",
        openapi_extra=merge_patch_openapi(),
    )
    async def patch_doc(
        body: bytes = Depends(merge_patch_body()),
        if_match: str = Depends(require_if_match(codec=codec)),
    ):
        check_precondition(if_match, current_version=state["version"], codec=codec)
        merged = merge_into(Doc, state["doc"], body)
        state["doc"] = merged.model_dump(by_alias=True)
        state["version"] += 1
        return state["doc"]

    @app.patch("/free/1")
    async def patch_free(body: bytes = Depends(merge_patch_body())):
        return merge_into(Doc, state["doc"], body).model_dump(by_alias=True)

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_app())


def problem(response, status):
    assert_that(response.status_code).is_equal_to(status)
    assert_that(response.headers["content-type"]).is_equal_to(PROBLEM_MEDIA_TYPE)
    return response.json()


class TestMergePatchBody:
    def test_returns_the_patch_object(self, client):
        response = client.patch("/free/1", json={"name": "gadget"}, headers=MERGE)
        assert_that(response.status_code).is_equal_to(200)
        assert_that(response.json()["name"]).is_equal_to("gadget")

    def test_ignores_media_type_parameters_and_case(self, client):
        response = client.patch(
            "/free/1",
            content=b'{"name": "gadget"}',
            headers={"Content-Type": "Application/Merge-Patch+JSON; charset=utf-8"},
        )
        assert_that(response.status_code).is_equal_to(200)

    @pytest.mark.parametrize("content_type", ["application/json", None])
    def test_other_media_type_is_415_with_accept_patch(self, client, content_type):
        headers = {"Content-Type": content_type} if content_type else {}
        response = client.patch("/free/1", content=b'{"name": "x"}', headers=headers)
        body = problem(response, 415)
        assert_that(body["title"]).is_equal_to("Unsupported Media Type")
        assert_that(response.headers["Accept-Patch"]).is_equal_to(
            MERGE_PATCH_MEDIA_TYPE
        )

    def test_returns_the_raw_body_unparsed(self):
        app = FastAPI()

        @app.patch("/raw")
        async def raw(body: bytes = Depends(merge_patch_body())):
            return {"length": len(body)}

        response = TestClient(app).patch("/raw", content=b"{not json", headers=MERGE)
        assert_that(response.json()).is_equal_to({"length": 9})


@pytest.mark.parametrize("content", [b'["name"]', b'"x"', b"null", b"{not json"])
def test_merge_into_rejects_a_non_object_body(client, content):
    body = problem(client.patch("/free/1", content=content, headers=MERGE), 422)
    assert_that(body["detail"]).is_equal_to("A merge patch must be a JSON object.")
    assert_that(body).does_not_contain_key("errors")


class TestMergeInto:
    def test_merges_nested_objects_and_replaces_arrays(self):
        merged = merge_into(
            Doc, initial(), j({"settings": {"color": "blue"}, "tags": ["c"]})
        )
        assert_that(merged.settings).is_equal_to({"color": "blue", "size": "L"})
        assert_that(merged.tags).is_equal_to(["c"])
        assert_that(merged.note).is_equal_to("fragile")

    def test_null_inside_a_json_value_removes_the_member(self):
        merged = merge_into(Doc, initial(), j({"settings": {"size": None}}))
        assert_that(merged.settings).is_equal_to({"color": "red"})

    def test_null_sets_a_nullable_field_to_none(self):
        assert_that(merge_into(Doc, initial(), j({"note": None})).note).is_none()

    def test_reads_attributes_and_writes_by_alias(self):
        class Row:
            name = "widget"
            note = None
            display_name = "W"
            tags: list[str] = []
            settings: dict[str, str] = {}

        class Loose(Doc):
            model_config = {"from_attributes": True, "populate_by_name": True}

        merged = merge_into(Loose, Row(), j({"displayName": "Z"}))
        assert_that(merged.display_name).is_equal_to("Z")

    def test_unknown_members_are_ignored(self):
        merged = merge_into(Doc, initial(), j({"id": "99", "name": "gadget"}))
        assert_that(merged.name).is_equal_to("gadget")

    def test_invalid_document_raises_request_validation_error_with_body_loc(self):
        from fastapi.exceptions import RequestValidationError

        with pytest.raises(RequestValidationError) as caught:
            merge_into(Doc, initial(), j({"tags": "x"}))
        assert_that(caught.value.errors()[0]["loc"]).is_equal_to(("body", "tags"))

    def test_route_renders_pointers(self, client):
        body = problem(
            client.patch(
                "/free/1", json={"settings": {"color": 1}, "tags": "x"}, headers=MERGE
            ),
            422,
        )
        assert_that(body["detail"]).is_equal_to("Validation Error")
        pointers = {error["pointer"] for error in body["errors"]}
        assert_that(pointers).is_equal_to({"/settings/color", "/tags"})

    def test_null_on_a_non_nullable_field_is_422(self, client):
        body = problem(client.patch("/free/1", json={"name": None}, headers=MERGE), 422)
        assert_that(body["errors"]).is_equal_to(
            [{"pointer": "/name", "detail": NULL_FIELD_DETAIL}]
        )


class TestMergePatchOpenapi:
    def test_declares_only_the_merge_patch_media_type(self, client):
        spec = client.app.openapi()
        content = spec["paths"]["/docs/1"]["patch"]["requestBody"]["content"]
        assert_that(content).is_equal_to(
            {MERGE_PATCH_MEDIA_TYPE: {"schema": {"type": "object"}}}
        )


class TestOrdering:
    def patch(self, client, content=b'{"name": "x"}', **headers):
        return client.patch("/docs/1", content=content, headers=headers)

    def test_media_type_beats_a_missing_if_match(self, client):
        problem(self.patch(client, **{"Content-Type": "application/json"}), 415)

    def test_media_type_beats_a_stale_if_match(self, client):
        response = self.patch(
            client, **{"Content-Type": "application/json", "If-Match": 'W/"1:9"'}
        )
        problem(response, 415)

    def test_missing_if_match_is_428_beating_a_non_object_body(self, client):
        problem(self.patch(client, b'["x"]', **MERGE), 428)

    def test_malformed_if_match_is_400_beating_a_non_object_body(self, client):
        problem(self.patch(client, b'["x"]', **MERGE, **{"If-Match": "bogus"}), 400)

    def test_stale_if_match_is_412_even_with_a_non_object_body(self, client):
        response = self.patch(client, b'["x"]', **MERGE, **{"If-Match": 'W/"1:9"'})
        assert_that(problem(response, 412)["detail"]).is_equal_to(
            "Precondition failed: expected version 1, got 9"
        )

    def test_matching_if_match_with_a_non_object_body_is_422(self, client):
        response = self.patch(client, b'["x"]', **MERGE, **{"If-Match": 'W/"1:1"'})
        problem(response, 422)

    def test_matching_if_match_applies_the_patch(self, client):
        response = self.patch(client, **MERGE, **{"If-Match": 'W/"1:1"'})
        assert_that(response.status_code).is_equal_to(200)
        assert_that(response.json()["name"]).is_equal_to("x")
