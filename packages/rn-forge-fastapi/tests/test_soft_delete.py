from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from assertpy import assert_that
from fastapi import Depends, Header
from fastapi.testclient import TestClient

from rn_forge.fastapi import (
    AppConfig,
    FastApiApp,
    SoftDeleteState,
    show_deleted_param,
    soft_delete_router,
)
from rn_forge.web import (
    EntityVersionETagCodec,
    PermissionDenied,
    WireModel,
)

pytestmark = pytest.mark.unit

DELETED_AT = datetime(2026, 1, 1, tzinfo=UTC)


class NoteRow(WireModel):
    id: str
    text: str
    delete_time: datetime | None = None


@dataclass
class Note:
    id: str
    text: str
    delete_time: datetime | None = None
    version: int | None = 1


class Store:
    """Records every write, so a test can say nothing was written."""

    def __init__(self, notes: list[Note]) -> None:
        self.rows = {n.id: n for n in notes}
        self.writes: list[str] = []

    async def find(self, id):
        note = self.rows.get(id)
        return (
            None
            if note is None
            else SoftDeleteState(note, note.version, note.delete_time)
        )

    async def soft_delete(self, id):
        self.writes.append(f"delete {id}")
        note = self.rows[id]
        note.delete_time = DELETED_AT
        if note.version is not None:
            note.version += 1
        return note

    async def undelete(self, id):
        self.writes.append(f"undelete {id}")
        note = self.rows[id]
        note.delete_time = None
        if note.version is not None:
            note.version += 1
        return note


def make(store: Store, **options) -> TestClient:
    app = FastApiApp(AppConfig(tracing=False))
    app.include_router(
        soft_delete_router(
            "/notes",
            response_model=NoteRow,
            resource_label="Note",
            store=lambda: store,
            **options,
        )
    )

    @app.get("/notes")
    async def list_notes(show_deleted: bool = Depends(show_deleted_param())):
        return [n.id for n in store.rows.values() if show_deleted or not n.delete_time]

    return TestClient(app, raise_server_exceptions=False)


def test_a_required_if_match_is_428_and_writes_nothing():
    store = Store([Note("1", "a")])

    response = make(store, require_if_match=True).delete("/notes/1")

    assert_that(response.status_code).is_equal_to(428)
    assert_that(store.writes).is_empty()


def test_a_required_if_match_guards_undelete_too():
    store = Store([Note("1", "a", DELETED_AT)])

    response = make(store, require_if_match=True).post("/notes/1:undelete")

    assert_that(response.status_code).is_equal_to(428)
    assert_that(store.writes).is_empty()


def test_a_stale_if_match_is_412_and_writes_nothing():
    store = Store([Note("1", "a")])

    response = make(store).delete("/notes/1", headers={"If-Match": 'W/"9"'})

    assert_that(response.status_code).is_equal_to(412)
    assert_that(store.writes).is_empty()


def test_a_malformed_if_match_is_400_and_writes_nothing():
    store = Store([Note("1", "a")])

    response = make(store).delete("/notes/1", headers={"If-Match": "nope"})

    assert_that(response.status_code).is_equal_to(400)
    assert_that(store.writes).is_empty()


def test_a_current_if_match_deletes_and_answers_with_the_new_etag():
    store = Store([Note("1", "a")])

    response = make(store).delete("/notes/1", headers={"If-Match": 'W/"1"'})

    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.headers["ETag"]).is_equal_to('W/"2"')
    assert_that(response.json()["deleteTime"]).is_equal_to("2026-01-01T00:00:00Z")


def test_the_codec_formats_the_etag():
    store = Store([Note("1", "a")])

    response = make(store, codec=EntityVersionETagCodec()).delete("/notes/1")

    assert_that(response.headers["ETag"]).is_equal_to('W/"1:2"')


def test_an_unversioned_resource_has_no_precondition_and_no_etag():
    store = Store([Note("1", "a", version=None)])

    response = make(store, require_if_match=True).delete("/notes/1")

    assert_that(response.status_code).is_equal_to(200)
    assert_that(response.headers).does_not_contain_key("etag")


def test_a_missing_resource_is_404_before_any_precondition():
    response = make(Store([]), require_if_match=True).delete("/notes/9")

    assert_that(response.status_code).is_equal_to(404)
    assert_that(response.json()["detail"]).is_equal_to("Note 9 not found")


def test_undelete_of_a_missing_resource_is_404():
    response = make(Store([])).post("/notes/9:undelete")

    assert_that(response.status_code).is_equal_to(404)


def test_a_dependencies_guard_runs_before_the_store():
    store = Store([Note("1", "a")])

    def deny(authorization: str | None = Header(default=None)) -> None:
        raise PermissionDenied("no")

    app = FastApiApp(AppConfig(tracing=False))
    app.include_router(
        soft_delete_router(
            "/notes",
            response_model=NoteRow,
            resource_label="Note",
            store=lambda: store,
            dependencies=[Depends(deny)],
        )
    )
    client = TestClient(app, raise_server_exceptions=False)

    assert_that(client.delete("/notes/1").status_code).is_equal_to(403)
    assert_that(client.post("/notes/1:undelete").status_code).is_equal_to(403)
    assert_that(store.writes).is_empty()


@pytest.mark.parametrize(
    ("value", "listed"),
    [("true", 2), ("1", 2), ("TRUE", 2), ("false", 1), ("0", 1), ("yes", 1), ("", 1)],
)
def test_show_deleted_includes_deleted_only_for_true_or_1(value, listed):
    store = Store([Note("1", "a"), Note("2", "b", DELETED_AT)])

    response = make(store).get("/notes", params={"showDeleted": value})

    assert_that(response.json()).is_length(listed)


def test_openapi_has_notes_undelete_and_a_200_delete_with_problem_responses():
    paths = make(Store([])).app.openapi()["paths"]

    delete = paths["/notes/{id}"]["delete"]
    undelete = paths["/notes/{id}:undelete"]["post"]

    assert_that(undelete["operationId"]).is_equal_to("notesUndelete")
    assert_that(delete["operationId"]).is_equal_to("notesDelete")
    for operation in (delete, undelete):
        assert_that(operation["responses"]).contains_key("200")
        assert_that(operation["responses"]).does_not_contain_key("204")
        problems = [
            code
            for code, body in operation["responses"].items()
            if "application/problem+json" in body.get("content", {})
        ]
        assert_that(problems).contains("404")
    assert_that(undelete["responses"]).contains_key("409")
    assert_that(delete["responses"]).contains_key("412")
