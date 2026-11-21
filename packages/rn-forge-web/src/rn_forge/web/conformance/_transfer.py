"""HTTP conformance cases for transfer behavior."""

from __future__ import annotations

from typing import Final

from rn_forge.web.conformance._shared import (
    _BOOKS_GET,
    _CSV_TYPE,
    _CSV_TYPE_PATTERN,
    _JSON,
    _ORDERS_CSV,
    _PROBLEM,
    _problem_body,
)
from rn_forge.web.conformance.types import REDACTED, ConformanceCase, RequestSpec
from rn_forge.web.problem import (
    BAD_REQUEST,
    BLANK_TYPE,
    FORBIDDEN,
    NOT_FOUND,
    NULL_FIELD_DETAIL,
    PRECONDITION_FAILED,
    VALIDATION_ERROR,
)

__all__ = ["TRANSFER_CASES"]

_BOOKS_UPDATE: Final = "/conformance/books:batchUpdate"
_ORDERS_IMPORT: Final = "/conformance/orders:import"
_MULTIPART: Final = "multipart/form-data"
_ROWS_INVALID: Final = "One or more rows are invalid."
_ORDERS_BATCH_CREATE: Final = "/conformance/orders:batchCreate"
_VALIDATION_ERROR: Final = "Validation Error"

_STALE_BOOK: Final = "Precondition failed: expected version 1, got 9"

TRANSFER_CASES: Final[tuple[ConformanceCase, ...]] = (
    ConformanceCase(
        id="transfer.export-is-negotiated-from-accept",
        area="transfer",
        description=(
            "RFC 9110 §12: a list asked for as text/csv is answered as CSV, "
            "as an attachment (RFC 6266)."
        ),
        request=RequestSpec(
            "GET", "/conformance/orders", headers={"Accept": _CSV_TYPE}
        ),
        expect_status=200,
        expect_header_patterns={"Content-Type": _CSV_TYPE_PATTERN},
        expect_headers={
            "Content-Disposition": (
                "attachment; filename=\"orders.csv\"; filename*=UTF-8''orders.csv"
            ),
        },
        expect_text=_ORDERS_CSV,
    ),
    ConformanceCase(
        id="transfer.export-format-param-is-the-fallback",
        area="transfer",
        description="?format=csv selects CSV for a plain link that cannot send Accept.",
        request=RequestSpec("GET", "/conformance/orders", query={"format": "csv"}),
        expect_status=200,
        expect_header_patterns={"Content-Type": _CSV_TYPE_PATTERN},
        expect_headers={
            "Content-Disposition": (
                "attachment; filename=\"orders.csv\"; filename*=UTF-8''orders.csv"
            ),
        },
        expect_text=_ORDERS_CSV,
    ),
    ConformanceCase(
        id="transfer.export-filename-carries-rfc8187-encoding",
        area="transfer",
        description=(
            "A non-ASCII filename gets an ASCII fallback in filename= and the "
            "percent-encoded UTF-8 in filename*= (RFC 8187)."
        ),
        request=RequestSpec(
            "GET", "/conformance/orders/named", headers={"Accept": _CSV_TYPE}
        ),
        expect_status=200,
        expect_header_patterns={"Content-Type": _CSV_TYPE_PATTERN},
        expect_headers={
            "Content-Disposition": (
                'attachment; filename="Ord_rs 2026.csv"; '
                "filename*=UTF-8''Ord%C3%A9rs%202026.csv"
            ),
        },
        expect_text=_ORDERS_CSV,
    ),
    ConformanceCase(
        id="transfer.export-over-the-cap-is-422",
        area="transfer",
        description="An export above the configured cap is a 422 problem naming the cap.",
        request=RequestSpec(
            "GET", "/conformance/orders/over-cap", headers={"Accept": _CSV_TYPE}
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            "The export exceeds the limit of 1 rows; narrow the filter.",
        ),
    ),
    ConformanceCase(
        id="transfer.import-report-counts-and-validate-only",
        area="transfer",
        description=(
            "AIP-136/AIP-163: a multipart upload with validateOnly=true is 200 "
            "with the counts it would produce."
        ),
        request=RequestSpec(
            "POST",
            _ORDERS_IMPORT,
            headers={"Content-Type": _MULTIPART},
            query={"validateOnly": "true"},
            body={"file": "id,name,Quantity\n2,gadget,3\n"},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"created": 1, "updated": 0, "skipped": 0, "validateOnly": True},
    ),
    ConformanceCase(
        id="transfer.import-row-errors-are-422-pointers",
        area="transfer",
        description=(
            "Any row error fails the whole import as a 422 whose errors[].pointer "
            "is /rows/<row>/<column>."
        ),
        request=RequestSpec(
            "POST",
            _ORDERS_IMPORT,
            headers={"Content-Type": _MULTIPART},
            body={"file": "id,name,Quantity\n2,gadget,three\n"},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            _ROWS_INVALID,
            errors=[{"pointer": "/rows/0/Quantity", "detail": "Enter a whole number."}],
        ),
    ),
    ConformanceCase(
        id="transfer.batch-create-item-failure-is-422-pointer",
        area="transfer",
        description=(
            "AIP-233: one invalid item fails the whole batch; the pointer names "
            "the item in the requests array."
        ),
        request=RequestSpec(
            "POST",
            _ORDERS_BATCH_CREATE,
            headers=_JSON,
            body={"requests": [{"name": "ok"}, {}]},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            _ROWS_INVALID,
            errors=[
                {"pointer": "/requests/1/name", "detail": "This field is required."}
            ],
        ),
    ),
    ConformanceCase(
        id="transfer.failed-batch-create-persists-nothing",
        area="transfer",
        description="All or nothing: after the failed batch, the collection still has one order.",
        request=RequestSpec("GET", "/conformance/orders/count"),
        depends_on=("transfer.batch-create-item-failure-is-422-pointer",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"count": 1},
    ),
    ConformanceCase(
        id="transfer.batch-create-returns-the-created-resources",
        area="transfer",
        description="AIP-233: a successful batch is 200 with the created resources under the plural name.",
        request=RequestSpec(
            "POST",
            _ORDERS_BATCH_CREATE,
            headers=_JSON,
            body={"requests": [{"name": "gadget"}]},
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"orders": [{"id": "2", "name": "gadget"}]},
    ),
    ConformanceCase(
        id="transfer.batch-delete-with-unknown-id-is-404",
        area="transfer",
        description="AIP-235: one id that does not exist fails the whole batch.",
        request=RequestSpec(
            "POST",
            "/conformance/orders:batchDelete",
            headers=_JSON,
            body={"ids": ["1", "missing"]},
        ),
        expect_status=404,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(NOT_FOUND, "Order missing not found"),
    ),
    ConformanceCase(
        id="transfer.failed-batch-delete-deletes-nothing",
        area="transfer",
        description="All or nothing: the order named alongside the unknown id is still there.",
        request=RequestSpec("GET", "/conformance/orders/1"),
        depends_on=("transfer.batch-delete-with-unknown-id-is-404",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"id": "1", "name": "widget"},
    ),
    ConformanceCase(
        id="transfer.batch-delete-is-204",
        area="transfer",
        description="AIP-235: a successful batch delete is 204 with no body.",
        request=RequestSpec(
            "POST",
            "/conformance/orders:batchDelete",
            headers=_JSON,
            body={"ids": ["1"]},
        ),
        expect_status=204,
        expect_body={},
    ),
    ConformanceCase(
        id="transfer.import-template-is-the-import-columns",
        area="transfer",
        description=(
            "AIP-136: the import template is a CSV attachment whose only row is "
            "the import model's column names."
        ),
        request=RequestSpec(
            "GET", "/conformance/orders:importTemplate", headers={"Accept": _CSV_TYPE}
        ),
        expect_status=200,
        expect_header_patterns={"Content-Type": _CSV_TYPE_PATTERN},
        expect_headers={
            "Content-Disposition": (
                'attachment; filename="import-template.csv"; '
                "filename*=UTF-8''import-template.csv"
            ),
        },
        expect_text="id,name,Quantity\r\n",
    ),
    ConformanceCase(
        id="transfer.import-template-prefill-adds-the-rows",
        area="transfer",
        description="?prefill=true adds the current rows under the header row.",
        request=RequestSpec(
            "GET",
            "/conformance/orders:importTemplate",
            headers={"Accept": _CSV_TYPE},
            query={"prefill": "true"},
        ),
        expect_status=200,
        expect_header_patterns={"Content-Type": _CSV_TYPE_PATTERN},
        expect_text="id,name,Quantity\r\n1,widget,0\r\n",
    ),
    ConformanceCase(
        id="transfer.import-without-a-file-is-422",
        area="transfer",
        description="A multipart import with no file part is a 422 naming /file.",
        request=RequestSpec(
            "POST",
            _ORDERS_IMPORT,
            headers={"Content-Type": _MULTIPART},
            body={},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            _VALIDATION_ERROR,
            errors=[{"pointer": "/file", "detail": "This field is required."}],
        ),
    ),
    ConformanceCase(
        id="transfer.import-over-the-cap-is-422",
        area="transfer",
        description="An import with more data rows than the cap is a 422 naming the cap.",
        request=RequestSpec(
            "POST",
            "/conformance/capped:import",
            headers={"Content-Type": _MULTIPART},
            body={"file": "id,name,Quantity\n2,a,3\n3,b,4\n"},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR, "The import exceeds the limit of 1 rows."
        ),
    ),
    ConformanceCase(
        id="transfer.batch-create-with-an-empty-list-is-422",
        area="transfer",
        description="AIP-233: an empty requests list is a 422 naming /requests.",
        request=RequestSpec(
            "POST",
            _ORDERS_BATCH_CREATE,
            headers=_JSON,
            body={"requests": []},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            _VALIDATION_ERROR,
            errors=[
                {"pointer": "/requests", "detail": "A non-empty list is required."}
            ],
        ),
    ),
    ConformanceCase(
        id="transfer.batch-create-over-the-cap-is-422",
        area="transfer",
        description="A batch with more items than the cap is a 422 naming the cap.",
        request=RequestSpec(
            "POST",
            "/conformance/capped:batchCreate",
            headers=_JSON,
            body={"requests": [{"name": "a"}, {"name": "b"}]},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR, "The batch exceeds the limit of 1 rows."
        ),
    ),
    ConformanceCase(
        id="transfer.batch-create-denied-item-is-403-pointer",
        area="transfer",
        description=(
            "One item the principal may not create fails the whole batch as a "
            "403 whose pointer names the item."
        ),
        request=RequestSpec(
            "POST",
            _ORDERS_BATCH_CREATE,
            headers=_JSON,
            body={"requests": [{"name": "ok"}, {"name": "forbidden"}]},
        ),
        expect_status=403,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            FORBIDDEN,
            "Forbidden",
            errors=[
                {"pointer": "/requests/1", "detail": "You may not create this order."}
            ],
        ),
    ),
    ConformanceCase(
        id="transfer.denied-batch-create-persists-nothing",
        area="transfer",
        description="All or nothing: after the denied batch, the collection still has one order.",
        request=RequestSpec("GET", "/conformance/orders/count"),
        depends_on=("transfer.batch-create-denied-item-is-403-pointer",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"count": 1},
    ),
    ConformanceCase(
        id="transfer.batch-get-returns-resources-in-request-order",
        area="transfer",
        description="AIP-231: :batchGet answers 200 with the resources under the plural name, in request order.",
        request=RequestSpec("GET", _BOOKS_GET, query={"ids": ("3", "1")}),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "books": [{"id": "3", "name": "gamma"}, {"id": "1", "name": "alpha"}]
        },
    ),
    ConformanceCase(
        id="transfer.batch-get-with-an-unknown-id-is-404",
        area="transfer",
        description="AIP-231: one id that does not exist fails the whole batch.",
        request=RequestSpec("GET", _BOOKS_GET, query={"ids": ("1", "999")}),
        expect_status=404,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(NOT_FOUND, "Book 999 not found"),
    ),
    ConformanceCase(
        id="transfer.batch-get-without-ids-is-400",
        area="transfer",
        description="A :batchGet with no ids parameter is a 400, as a query-parameter fault is.",
        request=RequestSpec("GET", _BOOKS_GET),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            BAD_REQUEST, "A non-empty ids parameter is required."
        ),
    ),
    ConformanceCase(
        id="transfer.batch-get-over-the-cap-is-400",
        area="transfer",
        description="A :batchGet naming more ids than the cap is a 400 naming the cap.",
        request=RequestSpec(
            "GET", "/conformance/capped-books:batchGet", query={"ids": ("1", "2")}
        ),
        expect_status=400,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            BAD_REQUEST, "The batch exceeds the limit of 1 rows."
        ),
    ),
    ConformanceCase(
        id="transfer.batch-update-applies-each-merge-patch",
        area="transfer",
        description="AIP-234 with RFC 7396 items: each patch is merged and the updated resources are returned in request order.",
        request=RequestSpec(
            "POST",
            _BOOKS_UPDATE,
            headers=_JSON,
            body={
                "requests": [
                    {"id": "2", "patch": {"name": "beta2"}, "ifMatch": 'W/"2:1"'}
                ]
            },
        ),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={"books": [{"id": "2", "name": "beta2"}]},
    ),
    ConformanceCase(
        id="transfer.batch-update-stale-if-match-is-412-pointer",
        area="transfer",
        description="An item whose ifMatch is stale fails the whole batch as a 412 whose pointer names the item.",
        request=RequestSpec(
            "POST",
            _BOOKS_UPDATE,
            headers=_JSON,
            body={
                "requests": [
                    {"id": "1", "patch": {"name": "x"}},
                    {"id": "3", "patch": {"name": "y"}, "ifMatch": 'W/"3:9"'},
                ]
            },
        ),
        expect_status=412,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            PRECONDITION_FAILED,
            _STALE_BOOK,
            errors=[{"pointer": "/requests/1/ifMatch", "detail": _STALE_BOOK}],
        ),
    ),
    ConformanceCase(
        id="transfer.failed-batch-update-changes-nothing",
        area="transfer",
        description="All or nothing: after the failed batch, the first item is still unchanged.",
        request=RequestSpec("GET", _BOOKS_GET, query={"ids": ("1", "3")}),
        depends_on=("transfer.batch-update-stale-if-match-is-412-pointer",),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "books": [{"id": "1", "name": "alpha"}, {"id": "3", "name": "gamma"}]
        },
    ),
    ConformanceCase(
        id="transfer.batch-update-item-validation-is-422-pointer",
        area="transfer",
        description="An item whose merged document is invalid fails the whole batch; the pointer names the member in the patch.",
        request=RequestSpec(
            "POST",
            _BOOKS_UPDATE,
            headers=_JSON,
            body={"requests": [{"id": "1", "patch": {"name": None}}]},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            _ROWS_INVALID,
            errors=[{"pointer": "/requests/0/patch/name", "detail": NULL_FIELD_DETAIL}],
        ),
    ),
    ConformanceCase(
        id="transfer.batch-update-with-an-unknown-id-is-404",
        area="transfer",
        description="One id that does not exist fails the whole batch.",
        request=RequestSpec(
            "POST",
            _BOOKS_UPDATE,
            headers=_JSON,
            body={"requests": [{"id": "999", "patch": {}}]},
        ),
        expect_status=404,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(NOT_FOUND, "Book 999 not found"),
    ),
    ConformanceCase(
        id="transfer.batch-update-with-a-duplicate-id-is-422",
        area="transfer",
        description="An id named twice is a 422 pointing at the later item.",
        request=RequestSpec(
            "POST",
            _BOOKS_UPDATE,
            headers=_JSON,
            body={"requests": [{"id": "1", "patch": {}}, {"id": "1", "patch": {}}]},
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            _ROWS_INVALID,
            errors=[{"pointer": "/requests/1/id", "detail": "Duplicate id in batch."}],
        ),
    ),
    ConformanceCase(
        id="transfer.batch-update-with-an-empty-list-is-422",
        area="transfer",
        description="An empty requests list is a 422 naming /requests.",
        request=RequestSpec(
            "POST", _BOOKS_UPDATE, headers=_JSON, body={"requests": []}
        ),
        expect_status=422,
        expect_headers=_PROBLEM,
        expect_body=_problem_body(
            VALIDATION_ERROR,
            _VALIDATION_ERROR,
            errors=[
                {"pointer": "/requests", "detail": "A non-empty list is required."}
            ],
        ),
    ),
    ConformanceCase(
        id="operations.start-is-202-with-location",
        area="operations",
        description=(
            "AIP-151: the call answers 202, names the operation in Location, and "
            "returns it unfinished."
        ),
        request=RequestSpec("POST", "/conformance/exports", headers=_JSON, body={}),
        expect_status=202,
        expect_headers={**_JSON, "Location": "/conformance/operations/1"},
        expect_body={"name": "operations/1", "done": False},
    ),
    ConformanceCase(
        id="operations.finished-carries-its-response",
        area="operations",
        description="A finished operation has done=true and a response, and no error.",
        request=RequestSpec("GET", "/conformance/operations/1"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "name": "operations/1",
            "done": True,
            "response": {"id": "1"},
        },
    ),
    ConformanceCase(
        id="operations.failed-carries-a-problem",
        area="operations",
        description=(
            "A failed operation has done=true and an RFC 9457 problem as its error, "
            "never google.rpc.Status."
        ),
        request=RequestSpec("GET", "/conformance/operations/2"),
        expect_status=200,
        expect_headers=_JSON,
        expect_body={
            "name": "operations/2",
            "done": True,
            "error": {
                "type": BLANK_TYPE,
                "title": "Conflict",
                "status": 409,
                "detail": "Order already dispatched",
                "instance": REDACTED,
            },
        },
    ),
)
