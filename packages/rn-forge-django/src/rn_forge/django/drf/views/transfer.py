"""Format-agnostic import and export mixins for DRF model views."""

from __future__ import annotations

from abc import ABC
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast

from django.http import HttpResponse
from django.http.response import HttpResponseBase
from django.db import connection, transaction
from django.db.models import Q
from rn_forge.commons.lang.collections import DictUtils
from rn_forge.commons.logging import AppLogger
from rn_forge.commons.lang.utils import AppUtils
from rest_framework import status
from rn_forge.django.drf._typing import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rn_forge.django.models import get_model_meta
from rn_forge.django.drf._typing import (
    GenericAPIViewProtocol,
    QuerySetProtocol,
    RequestProtocol,
    SerializerData,
)
from rn_forge.django.drf.utils import RequestUtils
from rn_forge.django.settings import rn_forge_django_settings
from rn_forge.django.drf.views.mixins import AuditFieldsViewMixin
from rn_forge.django.drf.views.parsers import (
    CsvImportParser,
    ExcelImportParser,
    ImportParser,
    JsonImportParser,
)
from rn_forge.django.drf.views.renderers import (
    CsvExportRenderer,
    ExcelExportRenderer,
    ExportDataset,
    ExportRenderer,
    JsonExportRenderer,
    TransferColumn,
)

__all__ = [
    "ExportDataset",
    "ExportRenderer",
    "ExportViewMixin",
    "BaseImportViewMixin",
    "BulkLoadImportViewMixin",
    "ImportDataset",
    "ImportParser",
    "ImportResult",
    "SnapshotImportViewMixin",
    "TransferColumn",
    "TransferViewMixin",
    "UpsertImportViewMixin",
    "ViewResponse",
]

type ViewResponse = HttpResponseBase | Response
view_action = cast(Any, action)
_LOGGER = AppLogger.get_logger(__name__)


@dataclass(frozen=True)
class ImportDataset:
    """Serializer-ready rows and model instances produced from import input."""

    row_count: int
    create_instances: list[object]
    update_instances: list[object]
    errors: list[dict[str, str]]
    lookup_keys: tuple[tuple[object, ...], ...] = ()
    delete_instances: list[object] | None = None
    update_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportResult:
    """Summary returned after import validation and persistence."""

    created: int
    updated: int
    errors: list[dict[str, str]]
    deleted: int = 0
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------


class TransferViewMixin(ABC):
    """Shared column configuration for import and export transfer flows."""

    transfer_columns: ClassVar[Sequence[TransferColumn]] = ()
    transfer_format_param = "format"
    default_transfer_format: str | None = None
    transfer_renderers: ClassVar[Mapping[str, type[ExportRenderer]]] = {
        "csv": CsvExportRenderer,
        "json": JsonExportRenderer,
        "xlsx": ExcelExportRenderer,
    }
    transfer_parsers: ClassVar[Mapping[str, type[ImportParser]]] = {
        "csv": CsvImportParser,
        "json": JsonImportParser,
        "xlsx": ExcelImportParser,
    }
    transfer_filename_prefix = ""
    transfer_filename_suffix = ""

    def get_transfer_format(
        self,
        request: Request,
        default_format: str | None = None,
    ) -> str:
        """Return the requested transfer format."""
        value = RequestUtils.get_value(request, self.transfer_format_param)
        if value is None:
            value = RequestUtils.get_param(request, self.transfer_format_param)
        configured_default = rn_forge_django_settings.drf.views.default_transfer_format
        return str(
            value
            or default_format
            or self.default_transfer_format
            or configured_default
        ).lower()

    def get_transfer_renderer(
        self,
        request: Request,
        transfer_format: str,
    ) -> ExportRenderer:
        """Return the configured renderer for *transfer_format*."""
        del request
        renderer_class = self.transfer_renderers.get(transfer_format)
        if renderer_class is None:
            raise ValidationError(f"Unsupported transfer format: {transfer_format}")
        _LOGGER.verbose(
            "Selected transfer renderer: format={} renderer={}",
            transfer_format,
            renderer_class.__name__,
        )
        return renderer_class()

    def get_transfer_parser(
        self,
        request: Request,
        transfer_format: str,
    ) -> ImportParser:
        """Return the configured parser for *transfer_format*."""
        del request
        parser_class = self.transfer_parsers.get(transfer_format)
        if parser_class is None:
            raise ValidationError(f"Unsupported import format: {transfer_format}")
        _LOGGER.verbose(
            "Selected import parser: format={} parser={}",
            transfer_format,
            parser_class.__name__,
        )
        return parser_class()

    def get_transfer_filename_stem(self, request: Request) -> str:
        """Return the base filename stem for transfer responses."""
        del request
        view = cast(GenericAPIViewProtocol, self)
        model_name = get_model_meta(view.get_queryset().model).model_name
        return f"{self.transfer_filename_prefix}{model_name}{self.transfer_filename_suffix}"

    def get_transfer_columns(
        self,
        request: Request,
        transfer_format: str,
    ) -> Sequence[TransferColumn]:
        """Return the common transfer columns for *transfer_format*."""
        del request, transfer_format
        return self.transfer_columns

    def build_transfer_response(
        self,
        payload: bytes,
        filename: str,
        renderer: ExportRenderer,
    ) -> HttpResponse:
        """Return a downloadable file response for rendered transfer bytes."""
        response = HttpResponse(payload, content_type=renderer.content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _build_transfer_dataset(
        self,
        payload: Sequence[Mapping[str, object]],
        columns: Sequence[TransferColumn],
    ) -> ExportDataset:
        """Project mapping payload into an ordered tabular transfer dataset."""
        rows: list[dict[str, object]] = []
        for source_row in payload:
            projected_row = {
                column.header: self.resolve_transfer_value(source_row, column.source)
                for column in columns
            }
            rows.append(projected_row)
        return ExportDataset(columns=list(columns), rows=rows)

    def resolve_transfer_value(
        self,
        row: Mapping[str, object],
        source: str,
    ) -> object:
        """Resolve a dotted source path from a transfer row."""
        return DictUtils.get(row, source)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class ExportViewMixin(TransferViewMixin, ABC):
    """Format-agnostic contract for export/download actions.

    The library owns queryset orchestration, serializer execution, renderer
    dispatch, and file-response construction. App views only provide the
    filtered queryset, filename stem, requested format, and renderer.
    """

    export_columns: ClassVar[Sequence[TransferColumn] | None] = None
    export_max_rows: int | None = None
    export_max_rows_param = "export-max-rows"

    def get_export_format(self, request: Request) -> str:
        """Return the requested export format for *request*."""
        return self.get_transfer_format(request)

    def get_export_queryset(self, request: Request) -> QuerySetProtocol:
        """Return the filtered queryset to export."""
        view = cast(GenericAPIViewProtocol, self)
        return view.filter_queryset(view.get_queryset())

    def get_export_filename_stem(self, request: Request) -> str:
        """Return the filename stem for the generated export file."""
        return self.get_transfer_filename_stem(request)

    def get_export_renderer(
        self,
        request: Request,
        export_format: str,
    ) -> ExportRenderer:
        """Return the renderer used for the requested export format."""
        return self.get_transfer_renderer(request, export_format)

    def get_export_columns(
        self,
        request: Request,
        export_format: str,
    ) -> Sequence[TransferColumn]:
        """Return ordered export columns for the requested format."""
        columns = (
            self.export_columns
            if self.export_columns is not None
            else self.get_transfer_columns(request, export_format)
        )
        return tuple(column for column in columns if not column.write_only)

    def get_export_max_rows(self, request: Request) -> int | None:
        """Return the effective export row limit for *request*."""
        value = RequestUtils.get_value(request, self.export_max_rows_param)
        if value is None:
            value = RequestUtils.get_param(request, self.export_max_rows_param)
        if value in {None, ""}:
            return (
                self.export_max_rows
                if self.export_max_rows is not None
                else rn_forge_django_settings.drf.views.export_max_rows
            )
        limit = int(cast(str | int, value))
        return None if limit < 1 else limit

    def validate_export_queryset(
        self,
        request: Request,
        queryset: QuerySetProtocol,
    ) -> None:
        """Reject exports that exceed the configured row limit."""
        max_rows = self.get_export_max_rows(request)
        if max_rows is None:
            return
        row_count = queryset.count()
        if row_count > max_rows:
            _LOGGER.warning(
                "Export row limit exceeded: rows={} max_rows={}",
                row_count,
                max_rows,
            )
            raise ValidationError(
                f"Export supports up to {max_rows} rows; filtered queryset has {row_count} rows"
            )

    def get_export_payload(
        self,
        request: Request,
        queryset: QuerySetProtocol,
        export_format: str,
    ) -> Sequence[Mapping[str, object]]:
        """Return the serialized export payload for *queryset*.

        By default this uses the view's configured serializer with
        ``many=True`` and returns ``serializer.data``.
        """
        del request, export_format
        serializer = cast(GenericAPIViewProtocol, self).get_serializer(
            queryset,
            many=True,
        )
        return cast(Sequence[Mapping[str, object]], serializer.data)

    def resolve_export_value(
        self,
        row: Mapping[str, object],
        source: str,
    ) -> object:
        """Resolve a dotted source path from a serialized export row."""
        return self.resolve_transfer_value(row, source)

    def _build_export_dataset(
        self,
        payload: Sequence[Mapping[str, object]],
        columns: Sequence[TransferColumn],
    ) -> ExportDataset:
        """Project serializer output into an ordered tabular export dataset."""
        return self._build_transfer_dataset(payload, columns)

    def get_export_filename(
        self,
        request: Request,
        renderer: ExportRenderer,
        export_format: str,
    ) -> str:
        """Return the final output filename for the export response."""
        del export_format
        return f"{self.get_export_filename_stem(request)}.{renderer.file_extension}"

    def build_export_response(
        self,
        dataset: ExportDataset,
        filename: str,
        renderer: ExportRenderer,
    ) -> HttpResponseBase:
        """Return a downloadable response for rendered export data."""
        return self.build_transfer_response(
            renderer.render_bytes(dataset),
            filename,
            renderer,
        )

    @view_action(methods=["post"], detail=False, url_path="export")
    def export(
        self,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> ViewResponse:
        """Build and return a format-specific export response."""
        del args, kwargs
        export_format = self.get_export_format(request)
        _LOGGER.notice("Export started: path={} format={}", request.path, export_format)
        renderer = self.get_export_renderer(request, export_format)
        columns = self.get_export_columns(request, export_format)
        queryset = self.get_export_queryset(request)
        self.validate_export_queryset(request, queryset)
        export_payload = self.get_export_payload(request, queryset, export_format)
        dataset = self._build_export_dataset(export_payload, columns)
        filename = self.get_export_filename(request, renderer, export_format)
        response = self.build_export_response(dataset, filename, renderer)
        _LOGGER.success(
            "Export completed: rows={} format={} filename={}",
            len(dataset.rows),
            export_format,
            filename,
        )
        return response


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class BaseImportViewMixin(TransferViewMixin, ABC):
    """Shared transport contract for all import modes."""

    import_columns: ClassVar[Sequence[TransferColumn] | None] = None
    import_source_key = "file"
    import_max_rows: int | None = None
    import_max_rows_param = "import-max-rows"
    import_dry_run_param = "dry-run"
    import_template_prefill_param = "prefill"

    # ---------------------------------------------------------------------
    # Action
    # ---------------------------------------------------------------------

    @view_action(methods=["post"], detail=False, url_path="import")
    def import_items(
        self,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> ViewResponse:
        """Parse, validate, and persist an imported payload."""
        del args, kwargs
        import_format = self.get_import_format(request)
        dry_run = self.get_import_dry_run(request)
        _LOGGER.notice(
            "Import started: path={} mode={} format={} dry_run={}",
            request.path,
            type(self).__name__,
            import_format,
            dry_run,
        )
        parser = self.get_import_parser(request, import_format)
        columns = self.get_import_columns(request, import_format)
        source = self.get_import_source(request, import_format)
        self.validate_import_source(request, source, import_format)
        payload = self.get_import_payload(
            request,
            source,
            import_format,
            parser,
            columns,
        )
        self.validate_import_payload(request, payload, import_format)
        dataset = self._build_import_dataset(request, payload, import_format, columns)
        self.validate_import_dataset(request, dataset, import_format)
        result = self.save_import_dataset(request, dataset, import_format)
        _LOGGER.success(
            "Import completed: created={} updated={} deleted={} errors={} dry_run={}",
            result.created,
            result.updated,
            result.deleted,
            len(result.errors),
            result.dry_run,
        )
        return self.build_import_response(request, result, import_format)

    # ---------------------------------------------------------------------
    # Source
    # ---------------------------------------------------------------------

    def get_import_format(self, request: Request) -> str:
        """Return the requested import format for *request*."""
        return self.get_transfer_format(request)

    def get_import_columns(
        self,
        request: Request,
        import_format: str,
    ) -> Sequence[TransferColumn]:
        """Return ordered import columns for the requested format."""
        columns = (
            self.import_columns
            if self.import_columns is not None
            else self.get_transfer_columns(request, import_format)
        )
        return tuple(column for column in columns if not column.read_only)

    def get_import_parser(
        self,
        request: Request,
        import_format: str,
    ) -> ImportParser:
        """Return the parser used for the requested import format."""
        return self.get_transfer_parser(request, import_format)

    def get_import_source(self, request: Request, import_format: str) -> object:
        """Return the raw import source object from *request*."""
        try:
            return RequestUtils.get_uploaded_file(request, self.import_source_key)
        except ValidationError:
            pass
        if import_format == "json":
            return cast(RequestProtocol, request).data
        raise ValidationError(
            f"{import_format} import requires uploaded file field: {self.import_source_key}"
        )

    def validate_import_source(
        self,
        request: Request,
        source: object,
        import_format: str,
    ) -> None:
        """Validate the raw import source before parsing."""
        del request, source, import_format

    def get_import_payload(
        self,
        request: Request,
        source: object,
        import_format: str,
        parser: ImportParser,
        columns: Sequence[TransferColumn],
    ) -> Sequence[Mapping[str, object]]:
        """Parse *source* into the raw import payload."""
        del request, import_format
        payload = parser.parse(source, columns)
        _LOGGER.verbose("Parsed import payload: rows={}", len(payload))
        return payload

    # ---------------------------------------------------------------------
    # Template
    # ---------------------------------------------------------------------

    def get_import_template_format(self, request: Request) -> str:
        """Return the requested import-template format for *request*."""
        return self.get_import_format(request)

    def get_import_template_filename(
        self,
        request: Request,
        template_format: str,
    ) -> str:
        """Return the filename for the generated import template."""
        return f"template_{self.get_transfer_filename_stem(request)}.{template_format}"

    def get_import_template_renderer(
        self,
        request: Request,
        template_format: str,
    ) -> ExportRenderer:
        """Return the renderer used for the requested import-template format."""
        return self.get_transfer_renderer(request, template_format)

    def build_import_template_payload(
        self,
        request: Request,
        template_format: str,
    ) -> ExportDataset:
        """Return the dataset used to generate the import template."""
        columns = tuple(
            column
            for column in self.get_import_columns(request, template_format)
            if not column.read_only
        )
        if not self.get_import_template_prefill(request):
            return ExportDataset(columns=columns, rows=[])

        queryset = self.get_import_template_queryset(request, template_format)
        self.validate_import_template_queryset(request, queryset, template_format)
        payload = self.get_import_template_payload(request, queryset, template_format)
        return self._build_transfer_dataset(payload, columns)

    def get_import_template_prefill(self, request: Request) -> bool:
        """Return whether import-template generation should include current rows."""
        value = RequestUtils.get_param(request, self.import_template_prefill_param)
        return AppUtils.parse_bool(value, strict=False) is True

    def get_import_template_queryset(
        self,
        request: Request,
        template_format: str,
    ) -> QuerySetProtocol:
        """Return queryset used for a prefilled import template."""
        del template_format
        view = cast(GenericAPIViewProtocol, self)
        return view.filter_queryset(view.get_queryset())

    def validate_import_template_queryset(
        self,
        request: Request,
        queryset: QuerySetProtocol,
        template_format: str,
    ) -> None:
        """Reject prefilled templates that exceed the export row limit."""
        del template_format
        if isinstance(self, ExportViewMixin):
            self.validate_export_queryset(request, queryset)
            return
        max_rows = rn_forge_django_settings.drf.views.export_max_rows
        if max_rows is not None and queryset.count() > max_rows:
            raise ValidationError(
                f"Import template supports up to {max_rows} prefilled rows"
            )

    def get_import_template_payload(
        self,
        request: Request,
        queryset: QuerySetProtocol,
        template_format: str,
    ) -> Sequence[Mapping[str, object]]:
        """Return serializer payload used for a prefilled import template."""
        del request, template_format
        serializer = cast(GenericAPIViewProtocol, self).get_serializer(
            queryset,
            many=True,
        )
        return cast(Sequence[Mapping[str, object]], serializer.data)

    def build_import_template_response(
        self,
        request: Request,
        payload: ExportDataset,
        template_format: str,
        filename: str,
    ) -> HttpResponse:
        """Return the HTTP response for the generated import template."""
        renderer = self.get_import_template_renderer(request, template_format)
        response_bytes = renderer.render_bytes(payload)
        return self.build_transfer_response(response_bytes, filename, renderer)

    @view_action(methods=["get"], detail=False, url_path="import-template")
    def import_template(
        self,
        request: Request,
        *args: Any,
        **kwargs: Any,
    ) -> ViewResponse:
        """Build and return an import-template response."""
        del args, kwargs
        template_format = self.get_import_template_format(request)
        _LOGGER.notice(
            "Import template started: path={} format={}", request.path, template_format
        )
        filename = self.get_import_template_filename(request, template_format)
        payload = self.build_import_template_payload(request, template_format)
        response = self.build_import_template_response(
            request,
            payload,
            template_format,
            filename,
        )
        _LOGGER.success(
            "Import template completed: rows={} format={} filename={}",
            len(payload.rows),
            template_format,
            filename,
        )
        return response

    # ---------------------------------------------------------------------
    # Payload Validation
    # ---------------------------------------------------------------------

    def get_import_max_rows(self, request: Request) -> int | None:
        """Return the effective import row limit for *request*."""
        value = RequestUtils.get_param(request, self.import_max_rows_param)
        if value in {None, ""}:
            return (
                self.import_max_rows
                if self.import_max_rows is not None
                else rn_forge_django_settings.drf.views.import_max_rows
            )
        limit = int(cast(str | int, value))
        return None if limit < 1 else limit

    def validate_import_payload(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
    ) -> None:
        """Reject imports that exceed the configured row limit."""
        del import_format
        max_rows = self.get_import_max_rows(request)
        if max_rows is None:
            return
        row_count = len(payload)
        if row_count > max_rows:
            _LOGGER.warning(
                "Import row limit exceeded: rows={} max_rows={}",
                row_count,
                max_rows,
            )
            raise ValidationError(
                f"Import supports up to {max_rows} rows; parsed payload has {row_count} rows"
            )

    def get_import_dry_run(self, request: Request) -> bool:
        """Return whether import should validate and plan without persistence."""
        value = RequestUtils.get_param(request, self.import_dry_run_param)
        dry_run = AppUtils.parse_bool(value, strict=False) is True
        if dry_run:
            _LOGGER.warning("Import dry-run enabled: path={}", request.path)
        return dry_run

    # ---------------------------------------------------------------------
    # Dataset/Persistence Boundary
    # ---------------------------------------------------------------------

    def _build_import_dataset(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
        columns: Sequence[TransferColumn],
    ) -> ImportDataset:
        """Build a mode-specific import dataset from parsed rows."""
        raise NotImplementedError

    def validate_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> None:
        """Validate the fully built import dataset before persistence."""
        del request, dataset, import_format

    def save_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> ImportResult:
        """Persist a mode-specific import dataset."""
        raise NotImplementedError

    def build_import_response(
        self,
        request: Request,
        result: ImportResult,
        import_format: str,
    ) -> Response:
        """Return the HTTP response for an import result."""
        del request, import_format
        body: dict[str, object] = {
            "created": result.created,
            "updated": result.updated,
            "errors": result.errors,
        }
        if result.deleted:
            body["deleted"] = result.deleted
        if result.dry_run:
            body["dry_run"] = True
        return Response(body, status=400 if result.errors else status.HTTP_201_CREATED)


class UpsertImportViewMixin(BaseImportViewMixin, ABC):
    """Natural-key upsert import mode for incremental entity loads."""

    import_lookup_batch_size = 1000

    # ---------------------------------------------------------------------
    # Dataset
    # ---------------------------------------------------------------------

    def get_import_defaults(
        self,
        request: Request,
        import_format: str,
    ) -> Mapping[str, object]:
        """Return default serializer values merged into every imported row."""
        del request, import_format
        return {}

    def prepare_import_row(
        self,
        request: Request,
        row: SerializerData,
        import_format: str,
    ) -> SerializerData:
        """Hook for per-row derivation before serializer validation."""
        del request, import_format
        return row

    def prepare_import_data(
        self,
        request: Request,
        data: SerializerData,
        import_format: str,
    ) -> SerializerData:
        """Hook for derived serializer values before validation."""
        del request, import_format
        return data

    def map_import_row(
        self,
        row: Mapping[str, object],
        columns: Sequence[TransferColumn],
    ) -> SerializerData:
        """Map one parsed source row to serializer field names."""
        mapped: SerializerData = {}
        for column in columns:
            value = row.get(column.header)
            if value is None and column.required:
                raise ValueError(f"Missing required import column: {column.header}")
            if column.resolver is not None and value is not None:
                value = column.resolver(value)
            mapped[column.source] = value
        return mapped

    def build_import_mapped_rows(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
        columns: Sequence[TransferColumn],
    ) -> tuple[list[tuple[int, SerializerData]], list[dict[str, str]]]:
        """Map parsed rows to serializer data and collect row mapping errors."""
        defaults = dict(self.get_import_defaults(request, import_format))
        errors: list[dict[str, str]] = []
        mapped_rows: list[tuple[int, SerializerData]] = []

        for row_number, source_row in enumerate(payload, start=1):
            try:
                row = self.map_import_row(source_row, columns)
                row.update(defaults)
                row = self.prepare_import_row(request, row, import_format)
                row = self.prepare_import_data(request, row, import_format)
                mapped_rows.append((row_number, row))
            except Exception as error:  # noqa: BLE001 - row errors are reported together
                errors.append({"row": str(row_number), "message": str(error)})

        return mapped_rows, errors

    def _build_import_dataset(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
        columns: Sequence[TransferColumn],
    ) -> ImportDataset:
        """Build serializer rows and model instances from the parsed payload."""
        mapped_rows, errors = self.build_import_mapped_rows(
            request,
            payload,
            import_format,
            columns,
        )
        serializer_rows = [row for _, row in mapped_rows]
        lookup_cache = self.build_import_lookup_cache(
            request,
            serializer_rows,
        )
        update_fields = tuple(self.get_import_update_fields())
        create_instances: list[object] = []
        update_instances: list[object] = []
        lookup_keys: list[tuple[object, ...]] = []

        for row_number, row in mapped_rows:
            try:
                if self.get_import_lookup_fields():
                    lookup_keys.append(self.get_import_lookup_key(row))
                instance = self.get_import_instance(row, lookup_cache)
                validated_data = self.validate_import_row(request, row, instance)
                if instance is None:
                    if isinstance(self, AuditFieldsViewMixin):
                        self.prepare_create_data(validated_data)
                    create_instances.append(
                        self.build_import_create_instance(request, validated_data)
                    )
                    continue

                if isinstance(self, AuditFieldsViewMixin):
                    self.prepare_update_data(validated_data)
                if self.apply_import_update(instance, validated_data, update_fields):
                    update_instances.append(instance)
            except Exception as error:  # noqa: BLE001 - row errors are reported together
                errors.append({"row": str(row_number), "message": str(error)})

        if errors:
            _LOGGER.warning("Import row validation errors: count={}", len(errors))
        return ImportDataset(
            row_count=len(payload),
            create_instances=create_instances,
            update_instances=update_instances,
            errors=errors,
            lookup_keys=tuple(lookup_keys),
            update_fields=update_fields,
        )

    # ---------------------------------------------------------------------
    # Upsert Planning
    # ---------------------------------------------------------------------

    def get_import_lookup_fields(self) -> Sequence[str]:
        """Return serializer field names that identify existing records."""
        raise NotImplementedError("Upsert imports require natural-key lookup fields")

    def get_import_update_fields(self) -> Sequence[str]:
        """Return model field names that may be updated during import upserts."""
        raise NotImplementedError("Upsert imports require update fields")

    def get_import_lookup_batch_size(self) -> int:
        """Return lookup batch size capped by the active database parameter limit."""
        configured = max(1, self.import_lookup_batch_size)
        db_limit = connection.features.max_query_params
        if db_limit is None:
            return configured
        return max(1, min(configured, db_limit))

    def get_import_queryset(self, request: Request) -> QuerySetProtocol:
        """Return the base queryset used for import lookups."""
        del request
        view = cast(GenericAPIViewProtocol, self)
        return view.get_queryset()

    def get_import_model(self, request: Request) -> type[Any]:
        """Return the model class used for bulk create/update operations."""
        queryset = self.get_import_queryset(request)
        return queryset.model

    def filter_import_queryset_by_lookup_values(
        self,
        queryset: QuerySetProtocol,
        field: str,
        values: Iterable[object],
    ) -> QuerySetProtocol:
        """Filter *queryset* by lookup values using DB-safe batches."""
        value_list = list(values)
        batch_size = self.get_import_lookup_batch_size()
        if len(value_list) <= batch_size:
            return queryset.filter(**{f"{field}__in": value_list})

        query: Any = Q()
        for index in range(0, len(value_list), batch_size):
            query |= Q(
                **{f"{field}__in": cast(Any, value_list[index : index + batch_size])}
            )
        return queryset.filter(query)

    def build_import_lookup_cache(
        self,
        request: Request,
        payload: Sequence[SerializerData],
    ) -> dict[tuple[object, ...], object]:
        """Build an existing-record cache keyed by one or more natural-key fields."""
        lookup_fields = tuple(self.get_import_lookup_fields())
        if not lookup_fields:
            return {}

        queryset = self.get_import_queryset(request)
        for field in lookup_fields:
            values = {
                row[field] for row in payload if field in row and row[field] is not None
            }
            if not values:
                return {}
            queryset = self.filter_import_queryset_by_lookup_values(
                queryset,
                field,
                values,
            )

        return {
            tuple(getattr(instance, field) for field in lookup_fields): instance
            for instance in cast(Iterable[object], queryset)
        }

    def get_import_lookup_key(self, data: Mapping[str, object]) -> tuple[object, ...]:
        """Return the lookup key for one validated import row."""
        return tuple(data[field] for field in self.get_import_lookup_fields())

    def get_import_instance(
        self,
        data: Mapping[str, object],
        lookup_cache: Mapping[tuple[object, ...], object],
    ) -> object | None:
        """Return an existing instance for *data*, if upsert lookup fields match."""
        if not self.get_import_lookup_fields():
            return None
        return lookup_cache.get(self.get_import_lookup_key(data))

    def validate_import_row(
        self,
        request: Request,
        data: SerializerData,
        instance: object | None,
    ) -> SerializerData:
        """Validate one import row through the configured DRF serializer."""
        del request
        serializer = cast(GenericAPIViewProtocol, self).get_serializer(
            instance,
            data=data,
            partial=instance is not None,
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def build_import_create_instance(
        self,
        request: Request,
        data: SerializerData,
    ) -> object:
        """Build an unsaved model instance for one validated create row."""
        model = self.get_import_model(request)
        return model(**data)

    def apply_import_update(
        self,
        instance: object,
        data: SerializerData,
        update_fields: Sequence[str],
    ) -> bool:
        """Apply changed import values to *instance* and return whether it changed."""
        changed = False
        for field in update_fields:
            if field not in data:
                continue
            new_value = data[field]
            if getattr(instance, field) != new_value:
                setattr(instance, field, new_value)
                changed = True
        return changed

    # ---------------------------------------------------------------------
    # Persistence
    # ---------------------------------------------------------------------

    def save_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> ImportResult:
        """Persist a validated import dataset atomically."""
        del import_format
        if dataset.errors:
            return ImportResult(created=0, updated=0, errors=dataset.errors)

        model = self.get_import_model(request)
        update_fields = dataset.update_fields or tuple(self.get_import_update_fields())
        if self.get_import_dry_run(request):
            return ImportResult(
                created=len(dataset.create_instances),
                updated=len(dataset.update_instances),
                errors=[],
                dry_run=True,
            )
        with cast(Any, transaction).atomic():
            if dataset.create_instances:
                model.objects.bulk_create(dataset.create_instances)
            if dataset.update_instances and update_fields:
                model.objects.bulk_update(
                    dataset.update_instances,
                    fields=update_fields,
                )

        return ImportResult(
            created=len(dataset.create_instances),
            updated=len(dataset.update_instances),
            errors=[],
        )


class SnapshotImportViewMixin(UpsertImportViewMixin, ABC):
    """Authoritative full-snapshot import mode with optional delete-missing."""

    delete_missing_param = "delete-missing"

    def get_delete_missing(self, request: Request) -> bool:
        """Return whether missing existing rows should be deleted."""
        value = RequestUtils.get_param(request, self.delete_missing_param)
        return AppUtils.parse_bool(value, strict=False) is True

    def build_import_lookup_cache(
        self,
        request: Request,
        payload: Sequence[SerializerData],
    ) -> dict[tuple[object, ...], object]:
        """Build a full in-memory cache of the target queryset."""
        del payload
        lookup_fields = tuple(self.get_import_lookup_fields())
        if not lookup_fields:
            return {}

        return {
            tuple(getattr(instance, field) for field in lookup_fields): instance
            for instance in self.get_import_queryset(request)
        }

    def _build_import_dataset(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
        columns: Sequence[TransferColumn],
    ) -> ImportDataset:
        """Build a full snapshot import dataset and optional delete plan."""
        dataset = super()._build_import_dataset(
            request,
            payload,
            import_format,
            columns,
        )
        if not self.get_delete_missing(request):
            return dataset

        existing_cache = self.build_import_lookup_cache(request, [])
        imported_keys = set(dataset.lookup_keys)
        delete_instances = [
            instance
            for key, instance in existing_cache.items()
            if key not in imported_keys
        ]
        return ImportDataset(
            row_count=dataset.row_count,
            create_instances=dataset.create_instances,
            update_instances=dataset.update_instances,
            errors=dataset.errors,
            lookup_keys=dataset.lookup_keys,
            delete_instances=delete_instances,
            update_fields=dataset.update_fields,
        )

    def delete_missing_import_instances(
        self,
        request: Request,
        instances: Sequence[object],
    ) -> int:
        """Delete missing instances from a snapshot import."""
        del request
        deleted = 0
        for instance in instances:
            delete = getattr(instance, "delete")
            delete()
            deleted += 1
        return deleted

    def save_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> ImportResult:
        """Persist snapshot creates/updates and optional deletes atomically."""
        del import_format
        if dataset.errors:
            return ImportResult(created=0, updated=0, errors=dataset.errors)

        model = self.get_import_model(request)
        update_fields = dataset.update_fields or tuple(self.get_import_update_fields())
        if self.get_import_dry_run(request):
            return ImportResult(
                created=len(dataset.create_instances),
                updated=len(dataset.update_instances),
                deleted=len(dataset.delete_instances or ()),
                errors=[],
                dry_run=True,
            )
        deleted = 0
        with cast(Any, transaction).atomic():
            if dataset.create_instances:
                model.objects.bulk_create(dataset.create_instances)
            if dataset.update_instances and update_fields:
                model.objects.bulk_update(
                    dataset.update_instances,
                    fields=update_fields,
                )
            if dataset.delete_instances:
                deleted = self.delete_missing_import_instances(
                    request,
                    dataset.delete_instances,
                )

        return ImportResult(
            created=len(dataset.create_instances),
            updated=len(dataset.update_instances),
            deleted=deleted,
            errors=[],
        )


class BulkLoadImportViewMixin(BaseImportViewMixin, ABC):
    """DB-shaped bulk load import mode for PK/FK-ready rows."""

    validate_bulk_load_rows = False

    def get_import_queryset(self, request: Request) -> QuerySetProtocol:
        """Return the queryset used to determine the bulk-load model."""
        del request
        view = cast(GenericAPIViewProtocol, self)
        return view.get_queryset()

    def get_import_model(self, request: Request) -> type[Any]:
        """Return the model class used for bulk-load operations."""
        return self.get_import_queryset(request).model

    def get_bulk_load_update_fields(
        self,
        request: Request,
        rows: Sequence[SerializerData],
    ) -> tuple[str, ...]:
        """Return fields used by bulk update for DB-shaped load rows."""
        model = self.get_import_model(request)
        pk_fields = {
            field.attname
            for field in get_model_meta(model).concrete_fields
            if field.primary_key
        }
        return tuple(
            sorted({field for row in rows for field in row if field not in pk_fields})
        )

    def prepare_bulk_load_row(
        self,
        request: Request,
        row: SerializerData,
        import_format: str,
    ) -> SerializerData:
        """Hook to adjust one DB-shaped bulk-load row."""
        del request, import_format
        return row

    def validate_bulk_load_row(
        self,
        request: Request,
        data: SerializerData,
        instance: object | None,
    ) -> SerializerData:
        """Optionally validate one bulk-load row through the configured serializer."""
        if not self.validate_bulk_load_rows:
            return data
        serializer = cast(GenericAPIViewProtocol, self).get_serializer(
            instance,
            data=data,
            partial=instance is not None,
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _build_import_dataset(
        self,
        request: Request,
        payload: Sequence[Mapping[str, object]],
        import_format: str,
        columns: Sequence[TransferColumn],
    ) -> ImportDataset:
        """Build create/update instances from DB-shaped import rows."""
        del columns
        model = self.get_import_model(request)
        pk_field = next(
            field.attname
            for field in get_model_meta(model).concrete_fields
            if field.primary_key
        )
        create_instances: list[object] = []
        update_instances: list[object] = []
        errors: list[dict[str, str]] = []
        rows: list[SerializerData] = []

        for row_number, source_row in enumerate(payload, start=1):
            try:
                data = self.prepare_bulk_load_row(
                    request,
                    dict(source_row),
                    import_format,
                )
                instance = model(**self.validate_bulk_load_row(request, data, None))
                rows.append(data)
                if data.get(pk_field) in {None, ""}:
                    create_instances.append(instance)
                else:
                    update_instances.append(instance)
            except Exception as error:  # noqa: BLE001 - row errors are reported together
                errors.append({"row": str(row_number), "message": str(error)})

        return ImportDataset(
            row_count=len(payload),
            create_instances=create_instances,
            update_instances=update_instances,
            errors=errors,
            update_fields=self.get_bulk_load_update_fields(request, rows),
        )

    def save_import_dataset(
        self,
        request: Request,
        dataset: ImportDataset,
        import_format: str,
    ) -> ImportResult:
        """Persist DB-shaped bulk-load instances atomically."""
        del import_format
        if dataset.errors:
            return ImportResult(created=0, updated=0, errors=dataset.errors)

        model = self.get_import_model(request)
        if self.get_import_dry_run(request):
            return ImportResult(
                created=len(dataset.create_instances),
                updated=len(dataset.update_instances),
                errors=[],
                dry_run=True,
            )
        with cast(Any, transaction).atomic():
            if dataset.create_instances:
                model.objects.bulk_create(dataset.create_instances)
            if dataset.update_instances and dataset.update_fields:
                model.objects.bulk_update(
                    dataset.update_instances,
                    fields=dataset.update_fields,
                )

        return ImportResult(
            created=len(dataset.create_instances),
            updated=len(dataset.update_instances),
            errors=[],
        )
