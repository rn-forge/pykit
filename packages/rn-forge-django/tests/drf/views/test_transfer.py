from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

django = pytest.importorskip("django")
rest_framework = pytest.importorskip("rest_framework")

from django.http import HttpResponse  # noqa: E402
from rest_framework.exceptions import ValidationError  # noqa: E402
from rest_framework.request import Request  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from rn_forge.django.drf._typing import SerializerData  # noqa: E402
from rn_forge.django.drf.views.transfer import (  # noqa: E402
    ExportViewMixin,
    ImportDataset,
    ImportResult,
    UpsertImportViewMixin,
)
from rn_forge.django.drf.views.renderers import (  # noqa: E402
    CsvExportRenderer,
    ExcelExportRenderer,
    ExportDataset,
    ExportRenderer,
    JsonExportRenderer,
    TransferColumn,
)

pytestmark = pytest.mark.unit


class _Serializer:
    def __init__(self, data: object) -> None:
        self.data = data


class _XlsxRenderer(ExcelExportRenderer):
    def format_row(
        self,
        worksheet: object,
        row_index: int,
        row: dict[str, object],
        dataset: ExportDataset,
    ) -> None:
        del worksheet, dataset
        row["Row Number"] = row_index


class _QuerySet:
    model = type(
        "_Model",
        (),
        {"_meta": type("_Meta", (), {"model_name": "widget"})()},
    )

    def count(self) -> int:
        return 2


class _ExportView(ExportViewMixin):
    export_max_rows = 10
    transfer_renderers = {
        "csv": CsvExportRenderer,
        "xlsx": _XlsxRenderer,
        "json": JsonExportRenderer,
    }

    def get_serializer(self, *args: object, **kwargs: object) -> _Serializer:
        assert kwargs == {"many": True}
        return _Serializer(
            [
                {"id": 1, "name": "Alpha", "nested": {"code": "A"}},
                {"id": 2, "name": "Beta", "nested": {"code": "B"}},
            ]
        )

    def get_queryset(self) -> object:
        return _QuerySet()

    def filter_queryset(self, queryset: object) -> object:
        return queryset

    def get_export_columns(
        self,
        request: Request,
        export_format: str,
    ) -> list[TransferColumn]:
        assert export_format in {"csv", "xlsx"}
        return [
            TransferColumn(header="ID", source="id"),
            TransferColumn(header="Name", source="name"),
            TransferColumn(header="Code", source="nested.code"),
        ]


class _ImportView(UpsertImportViewMixin):
    transfer_columns = TransferColumn.from_mapping(
        {
            "Name": "name",
            "Code": "code",
        }
    )

    def get_import_format(self, request: Request) -> str:
        return "xlsx"

    def get_import_source(self, request: Request, import_format: str) -> object:
        del import_format
        return {"file": "demo"}

    def get_import_payload(
        self,
        request: Request,
        source: object,
        import_format: str,
        parser: object,
        columns: object,
    ) -> Sequence[Mapping[str, object]]:
        del parser, columns
        return [{"source": source, "format": import_format}]

    def _build_import_dataset(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
        columns: object,
    ) -> ImportDataset:
        del columns
        return ImportDataset(
            row_count=len(payload),
            create_instances=[],
            update_instances=[],
            errors=[],
        )

    def validate_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> None:
        del request, dataset, import_format

    def save_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> ImportResult:
        del request, import_format
        return ImportResult(
            created=1,
            updated=0,
            errors=[{"message": str(dataset.row_count)}],
        )


class _MappedImportView(UpsertImportViewMixin):
    import_columns = [
        TransferColumn("Name", "name"),
        TransferColumn("Role", "role", resolver=lambda value: str(value).upper()),
        TransferColumn("Ignored", "ignored", required=False, read_only=True),
    ]

    def get_import_format(self, request: Request) -> str:
        return "xlsx"

    def get_import_source(self, request: Request, import_format: str) -> object:
        del import_format
        return [{"Name": "Alice", "Role": "admin", "Ignored": "skip"}]

    def get_import_payload(
        self,
        request: Request,
        source: object,
        import_format: str,
        parser: object,
        columns: object,
    ) -> Sequence[Mapping[str, object]]:
        del request, import_format, parser, columns
        return [{"Name": "Alice", "Role": "admin", "Ignored": "skip"}]

    def get_import_defaults(
        self,
        request: Request,
        import_format: str,
    ) -> dict[str, object]:
        del request, import_format
        return {"status": "A"}

    def prepare_import_row(
        self,
        request: Request,
        row: SerializerData,
        import_format: str,
    ) -> SerializerData:
        del request, import_format
        row["name"] = str(row["name"]).title()
        return row

    def get_import_lookup_fields(self) -> tuple[str, ...]:
        return ("name",)

    def get_import_update_fields(self) -> tuple[str, ...]:
        return ("role",)

    def _build_import_dataset(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
        columns: Sequence[TransferColumn],
    ) -> ImportDataset:
        mapped_rows, errors = self.build_import_mapped_rows(
            request,
            payload,
            import_format,
            columns,
        )
        return ImportDataset(
            row_count=len(mapped_rows),
            create_instances=[],
            update_instances=[],
            errors=errors,
        )

    def validate_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> None:
        del request, dataset, import_format

    def save_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> ImportResult:
        del request, import_format
        return ImportResult(
            created=0,
            updated=0,
            errors=[{"message": str(dataset.row_count)}],
        )


class _TemplateView(UpsertImportViewMixin):
    transfer_renderers = {
        "xlsx": _XlsxRenderer,
        "json": JsonExportRenderer,
    }
    transfer_columns = TransferColumn.from_mapping(
        {
            "Name": "name",
            "Value": "value",
        }
    )

    def get_queryset(self) -> object:
        return _QuerySet()


class _TemplateExportOnlyView(ExportViewMixin):
    def get_queryset(self) -> object:
        return _QuerySet()


class _LargeExportView(_ExportView):
    export_max_rows = 1


class TestExportViewMixin:
    def test_export_orchestrates_hooks(self) -> None:
        request = Request(APIRequestFactory().get("/export/?format=xlsx"))
        response = _ExportView().export(request)

        assert isinstance(response, HttpResponse)
        assert (
            response["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert response["Content-Disposition"] == 'attachment; filename="widget.xlsx"'
        assert response.content

    def test_export_rejects_queryset_over_row_limit(self) -> None:
        request = Request(APIRequestFactory().get("/export/?format=xlsx"))
        view = _LargeExportView()

        with pytest.raises(ValidationError):
            view.export(request)

    def test_export_allows_request_row_limit_override(self) -> None:
        request = Request(
            APIRequestFactory().get("/export/?format=xlsx&export-max-rows=2")
        )
        response = _LargeExportView().export(request)

        assert isinstance(response, HttpResponse)

    def test_export_returns_csv_response(self) -> None:
        request = Request(APIRequestFactory().get("/export/?format=csv"))
        response = _ExportView().export(request)

        assert isinstance(response, HttpResponse)
        assert response["Content-Type"] == "text/csv"
        assert response["Content-Disposition"] == 'attachment; filename="widget.csv"'
        assert response.content == (b"ID,Name,Code\r\n1,Alpha,A\r\n2,Beta,B\r\n")


class TestJsonExportRenderer:
    def test_render_bytes_returns_projected_rows(self) -> None:
        renderer = JsonExportRenderer()
        dataset = ExportDataset(
            columns=[TransferColumn(header="ID", source="id")],
            rows=[{"ID": 1}, {"ID": 2}],
        )

        assert renderer.render_bytes(dataset) == b'[{"ID": 1}, {"ID": 2}]'


class TestCsvExportRenderer:
    def test_render_bytes_returns_csv_rows(self) -> None:
        renderer = CsvExportRenderer()
        dataset = ExportDataset(
            columns=[
                TransferColumn(header="ID", source="id"),
                TransferColumn(header="Name", source="name"),
            ],
            rows=[{"ID": 1, "Name": "Alpha, Inc."}],
        )

        assert renderer.render_bytes(dataset) == b'ID,Name\r\n1,"Alpha, Inc."\r\n'


class TestUpsertImportViewMixin:
    def test_upload_orchestrates_hooks(self) -> None:
        request = Request(APIRequestFactory().post("/import/", {"format": "xlsx"}))
        response = _ImportView().import_items(request)

        assert response.data == {
            "created": 1,
            "updated": 0,
            "errors": [
                {
                    "message": "1",
                }
            ],
        }

    def test_import_maps_columns_defaults_and_prepares_rows(self) -> None:
        request = Request(APIRequestFactory().post("/import/", {"format": "xlsx"}))
        response = _MappedImportView().import_items(request)

        assert response.data == {
            "created": 0,
            "updated": 0,
            "errors": [
                {
                    "message": "1",
                }
            ],
        }


class TestImportTemplate:
    def test_import_template_orchestrates_hooks(self) -> None:
        request = Request(APIRequestFactory().get("/import-template/"))
        response = _TemplateView().import_template(request)

        assert isinstance(response, HttpResponse)
        assert (
            response["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert (
            response["Content-Disposition"]
            == 'attachment; filename="template_widget.xlsx"'
        )
        assert response.content

    def test_export_only_view_does_not_include_import_template(self) -> None:
        assert not hasattr(_TemplateExportOnlyView(), "import_template")
