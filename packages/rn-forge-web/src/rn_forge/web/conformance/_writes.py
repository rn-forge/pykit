"""HTTP conformance cases for writes behavior."""

from __future__ import annotations

from typing import Final

from rn_forge.web.conformance._shared import _JSON, _PROBLEM, _problem_body
from rn_forge.web.conformance.types import ConformanceCase, RequestSpec
from rn_forge.web.merge_patch import MERGE_PATCH_MEDIA_TYPE
from rn_forge.web.problem import (
    BAD_REQUEST,
    CONFLICT,
    NOT_FOUND,
    NULL_FIELD_DETAIL,
    PRECONDITION_FAILED,
    PRECONDITION_REQUIRED,
    UNSUPPORTED_MEDIA_TYPE,
    VALIDATION_ERROR,
)

__all__ = ["WRITE_CASES"]

_MERGE: Final = {"Content-Type": MERGE_PATCH_MEDIA_TYPE}

_DOCUMENT_PATH: Final = "/conformance/documents/1"

_ITEM_PATH: Final = "/conformance/items/1"

_ITEM_ETAG: Final = 'W/"1:7"'

_CHARGES_PATH: Final = "/conformance/charges"

_FIRST_CALL_ID: Final = "idempotency.first-call-executes"


def _document(**changes: object) -> dict[str, object]:
    """The fixture document, as `GET /conformance/documents/1` serves it fresh."""
    return {
        "id": "1",
        "name": "widget",
        "note": "fragile",
        "tags": ["a", "b"],
        "settings": {"color": "red", "size": "L"},
        **changes,
    }


_NOTES_PATH: Final = "/conformance/notes"

_NOTE_1: Final = "/conformance/notes/1"

_NOTE_2: Final = "/conformance/notes/2"

_NOTE_3: Final = "/conformance/notes/3"


def _note(id: str, text: str, delete_time: str | None = None) -> dict[str, object]:
    return {"id": id, "text": text, "deleteTime": delete_time}


WRITE_CASES: Final[tuple[ConformanceCase, ...]] = (
    ConformanceCase(
        id="concurrency.absent-if-match-on-required-route-is-428",
        area="concurrency",
        description="RFC 6585 §3: the route demands a precondition and none was sent.",
        request=RequestSpec("PATCH", _ITEM_PATH, headers=_JSON, body={}),
        expect_status=428,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            PRECONDITION_REQUIRED, "This endpoint requires an If-Match precondition"
        ),
    ),
    ConformanceCase(
        id="concurrency.stale-if-match-is-412-not-409",
        area="concurrency",
        description=(
            "RFC 9110 §15.5.13: the precondition evaluated to false. 412, not 409."
        ),
        request=RequestSpec(
            "PATCH",
            _ITEM_PATH,
            headers={**_JSON, "If-Match": 'W/"1:6"'},
            body={},
        ),
        expect_status=412,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            PRECONDITION_FAILED, "Precondition failed: expected version 7, got 6"
        ),
    ),
    ConformanceCase(
        id="concurrency.star-if-match-passes",
        area="concurrency",
        description="RFC 9110 §13.1.1: `*` matches any current representation.",
        request=RequestSpec(
            "PATCH",
            _ITEM_PATH,
            headers={**_JSON, "If-Match": "*"},
            body={},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"id": "1", "version": 7},
    ),
    ConformanceCase(
        id="concurrency.malformed-if-match-is-400",
        area="concurrency",
        description="An unparseable validator is a 400, never a crash and never a 412.",
        request=RequestSpec(
            "PATCH",
            _ITEM_PATH,
            headers={**_JSON, "If-Match": "not-an-etag"},
            body={},
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            BAD_REQUEST, "Malformed If-Match validator: not-an-etag"
        ),
    ),
    ConformanceCase(
        id="concurrency.if-none-match-matches-is-304",
        area="concurrency",
        description=(
            "RFC 9110 §13.1.2, §15.4.5: a GET whose If-None-Match weakly matches "
            "the current ETag gets 304, no body, ETag repeated."
        ),
        request=RequestSpec("GET", _ITEM_PATH, headers={"If-None-Match": _ITEM_ETAG}),
        expect_status=304,
        expect_headers={"ETag": _ITEM_ETAG},
        expect_body={},
    ),
    ConformanceCase(
        id="concurrency.if-none-match-mismatch-is-200",
        area="concurrency",
        description="A stale If-None-Match is an ordinary 200 with the current ETag.",
        request=RequestSpec("GET", _ITEM_PATH, headers={"If-None-Match": 'W/"1:1"'}),
        expect_status=200,
        expect_headers={**_JSON, "ETag": _ITEM_ETAG},
        expect_body={"id": "1", "version": 7},
    ),
    ConformanceCase(
        id=_FIRST_CALL_ID,
        area="idempotency",
        description="First sight of a key: the handler runs and its response is stored.",
        request=RequestSpec(
            "POST",
            _CHARGES_PATH,
            headers={**_JSON, "Idempotency-Key": "k-1"},
            body={"amount": 100},
        ),
        expect_status=201,
        expect_headers=_JSON,
        expect_body={"charged": 100, "replayed": False},
    ),
    ConformanceCase(
        id="idempotency.replay-returns-the-stored-response",
        area="idempotency",
        description=(
            "The same key and the same body replays the stored response, "
            "including its original status."
        ),
        depends_on=(_FIRST_CALL_ID,),
        request=RequestSpec(
            "POST",
            _CHARGES_PATH,
            headers={**_JSON, "Idempotency-Key": "k-1"},
            body={"amount": 100},
        ),
        expect_status=201,
        expect_headers=_JSON,
        expect_body={"charged": 100, "replayed": True},
    ),
    ConformanceCase(
        id="idempotency.same-key-different-body-is-422",
        area="idempotency",
        description=(
            "Body hashing is the whole point of the module: a replayed key with a "
            "different body is a detectable client bug, not a silently-wrong replay. "
            "422 per draft-ietf-httpapi-idempotency-key-header §2.7."
        ),
        depends_on=(_FIRST_CALL_ID,),
        request=RequestSpec(
            "POST",
            _CHARGES_PATH,
            headers={**_JSON, "Idempotency-Key": "k-1"},
            body={"amount": 999},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "Idempotency key k-1 was replayed with a different request body",
        ),
    ),
    ConformanceCase(
        id="timestamps.rfc-3339-utc-with-z",
        area="timestamps",
        description=(
            "AIP-142: an instant is an RFC 3339 string in UTC with a Z suffix, "
            "not an offset and not a zone name."
        ),
        request=RequestSpec("GET", "/conformance/stamped"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"id": "1", "createTime": "2026-09-23T14:05:00Z"},
    ),
    ConformanceCase(
        id="patch.nested-merge-keeps-absent-members",
        area="patch",
        description=(
            "RFC 7396 §2: objects merge recursively, so a member the patch does "
            "not name keeps its value."
        ),
        request=RequestSpec(
            "PATCH",
            _DOCUMENT_PATH,
            headers=_MERGE,
            body={"settings": {"color": "blue"}},
        ),
        expect_status=200,
        expect_headers={**_JSON, "ETag": 'W/"1:2"'},
        expect_body=_document(settings={"color": "blue", "size": "L"}),
    ),
    ConformanceCase(
        id="patch.null-inside-a-json-value-removes-the-member",
        area="patch",
        description=("RFC 7396 §2: below the top level, null removes the member."),
        request=RequestSpec(
            "PATCH", _DOCUMENT_PATH, headers=_MERGE, body={"settings": {"size": None}}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_document(settings={"color": "red"}),
    ),
    ConformanceCase(
        id="patch.null-sets-a-nullable-field-to-null",
        area="patch",
        description=("At the top level a null names a field and stores null in it."),
        request=RequestSpec(
            "PATCH", _DOCUMENT_PATH, headers=_MERGE, body={"note": None}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_document(note=None),
    ),
    ConformanceCase(
        id="patch.array-is-replaced-whole",
        area="patch",
        description=("RFC 7396 §2: an array is a value, so it replaces the target's."),
        request=RequestSpec(
            "PATCH", _DOCUMENT_PATH, headers=_MERGE, body={"tags": ["c"]}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_document(tags=["c"]),
    ),
    ConformanceCase(
        id="patch.read-only-members-are-ignored",
        area="patch",
        description=(
            "A server-owned member in the patch changes nothing; the rest applies."
        ),
        request=RequestSpec(
            "PATCH", _DOCUMENT_PATH, headers=_MERGE, body={"id": "99", "name": "gadget"}
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_document(name="gadget"),
    ),
    ConformanceCase(
        id="patch.null-on-a-non-nullable-field-is-422",
        area="patch",
        description="A null on a required field fails validation, naming the field.",
        request=RequestSpec(
            "PATCH", _DOCUMENT_PATH, headers=_MERGE, body={"name": None}
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "Validation Error",
            errors=[{"pointer": "/name", "detail": NULL_FIELD_DETAIL}],
        ),
    ),
    ConformanceCase(
        id="patch.non-object-body-is-422",
        area="patch",
        description="RFC 7396 lets a non-object replace the target; pykit refuses it.",
        request=RequestSpec("PATCH", _DOCUMENT_PATH, headers=_MERGE, body=["name"]),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR, "A merge patch must be a JSON object."
        ),
    ),
    ConformanceCase(
        id="patch.json-content-type-is-415",
        area="patch",
        description=(
            "RFC 5789 §2.2: a patch format the server does not support is 415, "
            "and Accept-Patch names the one it does."
        ),
        request=RequestSpec(
            "PATCH", _DOCUMENT_PATH, headers=_JSON, body={"name": "gadget"}
        ),
        expect_status=415,
        expect_headers={**_PROBLEM, "Accept-Patch": MERGE_PATCH_MEDIA_TYPE},
        expect_body=_problem_body(
            UNSUPPORTED_MEDIA_TYPE,
            "Use Content-Type: application/merge-patch+json for PATCH",
        ),
    ),
    ConformanceCase(
        id="patch.stale-if-match-is-412",
        area="patch",
        description="The precondition is checked before the patch is applied.",
        request=RequestSpec(
            "PATCH",
            _DOCUMENT_PATH,
            headers={**_MERGE, "If-Match": 'W/"1:9"'},
            body={"name": "gadget"},
        ),
        expect_status=412,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            PRECONDITION_FAILED, "Precondition failed: expected version 1, got 9"
        ),
    ),
    ConformanceCase(
        id="patch.failed-precondition-changes-nothing",
        area="patch",
        description="After the 412, the document is still the original.",
        request=RequestSpec("GET", _DOCUMENT_PATH),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_document(),
        depends_on=("patch.stale-if-match-is-412",),
    ),
    ConformanceCase(
        id="soft-delete.delete-returns-the-resource-with-its-delete-time",
        area="soft-delete",
        description="AIP-164: DELETE soft-deletes and answers 200 with the resource, its deleteTime and the new ETag.",
        request=RequestSpec("DELETE", _NOTE_1),
        expect_status=200,
        expect_headers={**_JSON, "ETag": 'W/"1:2"'},
        expect_body=_note("1", "first", "2026-01-02T00:00:00Z"),
    ),
    ConformanceCase(
        id="soft-delete.list-omits-deleted-resources",
        area="soft-delete",
        description="A list leaves out soft-deleted resources.",
        request=RequestSpec("GET", _NOTES_PATH),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [_note("1", "first"), _note("3", "third")],
            "nextPageToken": None,
        },
    ),
    ConformanceCase(
        id="soft-delete.show-deleted-lists-them",
        area="soft-delete",
        description="showDeleted=true brings soft-deleted resources back into a list.",
        request=RequestSpec("GET", _NOTES_PATH, query={"showDeleted": "true"}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [
                _note("1", "first"),
                _note("2", "second", "2026-01-01T00:00:00Z"),
                _note("3", "third"),
            ],
            "nextPageToken": None,
        },
    ),
    ConformanceCase(
        id="soft-delete.get-returns-a-deleted-resource",
        area="soft-delete",
        description="AIP-164: a get returns the soft-deleted resource, with its deleteTime.",
        request=RequestSpec("GET", _NOTE_2),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_note("2", "second", "2026-01-01T00:00:00Z"),
    ),
    ConformanceCase(
        id="soft-delete.delete-of-a-deleted-resource-is-404",
        area="soft-delete",
        description="A DELETE on an already soft-deleted resource is not found.",
        request=RequestSpec("DELETE", _NOTE_2),
        expect_status=404,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(NOT_FOUND, "Note 2 not found"),
    ),
    ConformanceCase(
        id="soft-delete.undelete-restores-the-resource",
        area="soft-delete",
        description="AIP-164: :undelete answers 200 with the live resource and the new ETag.",
        request=RequestSpec("POST", "/conformance/notes/2:undelete"),
        expect_status=200,
        expect_headers={**_JSON, "ETag": 'W/"2:3"'},
        expect_body=_note("2", "second"),
    ),
    ConformanceCase(
        id="soft-delete.undeleted-resource-is-listed-again",
        area="soft-delete",
        description="An undeleted resource is back in the default list.",
        request=RequestSpec("GET", _NOTES_PATH),
        depends_on=("soft-delete.undelete-restores-the-resource",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "items": [
                _note("1", "first"),
                _note("2", "second"),
                _note("3", "third"),
            ],
            "nextPageToken": None,
        },
    ),
    ConformanceCase(
        id="soft-delete.undelete-of-a-live-resource-is-409",
        area="soft-delete",
        description="Undeleting a resource that is not deleted conflicts.",
        request=RequestSpec("POST", "/conformance/notes/1:undelete"),
        expect_status=409,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(CONFLICT, "Note 1 is not deleted"),
    ),
    ConformanceCase(
        id="soft-delete.write-to-a-deleted-resource-is-409",
        area="soft-delete",
        description="A PATCH on a soft-deleted resource conflicts.",
        request=RequestSpec("PATCH", _NOTE_2, headers=_MERGE, body={"text": "x"}),
        expect_status=409,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(CONFLICT, "Note 2 is deleted"),
    ),
    ConformanceCase(
        id="soft-delete.stale-if-match-is-412",
        area="soft-delete",
        description="DELETE honours If-Match; a stale validator is a 412.",
        request=RequestSpec("DELETE", _NOTE_1, headers={"If-Match": 'W/"1:9"'}),
        expect_status=412,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            PRECONDITION_FAILED, "Precondition failed: expected version 1, got 9"
        ),
    ),
    ConformanceCase(
        id="soft-delete.failed-precondition-deletes-nothing",
        area="soft-delete",
        description="A failed precondition leaves the resource live.",
        request=RequestSpec("GET", _NOTE_1),
        depends_on=("soft-delete.stale-if-match-is-412",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_note("1", "first"),
    ),
    ConformanceCase(
        id="soft-delete.batch-delete-soft-deletes",
        area="soft-delete",
        description="AIP-235 over AIP-164: a batch delete soft-deletes and answers 204.",
        request=RequestSpec(
            "POST", "/conformance/notes:batchDelete", headers=_JSON, body={"ids": ["3"]}
        ),
        expect_status=204,
        expect_body={},
    ),
    ConformanceCase(
        id="soft-delete.batch-deleted-resource-is-still-readable",
        area="soft-delete",
        description="A resource soft-deleted in a batch is still returned by a get.",
        request=RequestSpec("GET", _NOTE_3),
        depends_on=("soft-delete.batch-delete-soft-deletes",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body=_note("3", "third", "2026-01-02T00:00:00Z"),
    ),
)
