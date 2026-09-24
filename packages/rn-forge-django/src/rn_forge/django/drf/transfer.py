"""Tabular export and import, and batch create and delete, for DRF viewsets.

Requires the ``transfer`` extra. Not re-exported by :mod:`rn_forge.django.drf`.
Register the viewset with :class:`~rn_forge.django.drf.routers.CustomMethodRouter`
so the actions are served as ``/orders:import`` and ``/orders:batchCreate``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, cast, override

import tablib
from django.db import transaction
from django.http import JsonResponse
from django.http.response import HttpResponseBase
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin
from rest_framework.parsers import MultiPartParser
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from rn_forge.commons.data.excel import write_xlsx
from rn_forge.django.drf._typing import action
from rn_forge.django.drf.views.mixins import AuditFieldsViewMixin
from rn_forge.django import settings as django_settings
from rn_forge.web import (
    PROBLEM_MEDIA_TYPE,
    TABULAR_FORMATS,
    ProblemResponse,
    RowError,
    TabularFormat,
    content_disposition,
    export_cap_problem,
    field_error,
    import_report_body,
    row_errors_problem,
)

__all__ = [
    "BatchCreateMixin",
    "BatchDeleteMixin",
    "ResourceExportMixin",
    "ResourceImportMixin",
]

_NON_FIELD_KEY = "non_field_errors"
_TEXT_FORMATS = frozenset({"csv", "tsv"})


class _PassthroughRenderer(BaseRenderer):
    """Lets DRF's content negotiation select a tabular format; the view builds the bytes."""

    render_style = "binary"

    @override
    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> bytes:
        if isinstance(data, bytes):
            return data
        # An error body raised while a tabular format was negotiated.
        renderer: Any = JSONRenderer()
        return renderer.render(data, accepted_media_type, renderer_context)


def _renderer_for(fmt: TabularFormat) -> type[BaseRenderer]:
    return type(
        f"{fmt.extension.title()}Renderer",
        (_PassthroughRenderer,),
        {
            "media_type": fmt.media_type,
            "format": fmt.extension,
            "charset": "utf-8" if fmt.extension in _TEXT_FORMATS else None,
        },
    )


def _problem_response(rendered: ProblemResponse) -> JsonResponse:
    """Return *rendered* as a plain response, which DRF sends without renderer negotiation."""
    response = JsonResponse(
        rendered.body, status=rendered.status, content_type=PROBLEM_MEDIA_TYPE
    )
    for name, value in rendered.headers.items():
        response[name] = value
    return response


def _tabular_response(
    dataset: tablib.Dataset,
    fmt: TabularFormat,
    filename: str,
    column_formats: Mapping[str, str] | None = None,
) -> Response:
    """Return *dataset* as a download; the passthrough renderer sends the bytes."""
    if fmt.extension == "xlsx":
        body = write_xlsx(dataset, column_formats)
    else:
        body = cast(str, cast(Any, dataset).export(fmt.tablib_name)).encode()
    return Response(
        body,
        headers={
            "Content-Disposition": content_disposition(f"{filename}.{fmt.extension}")
        },
    )


def _max_rows() -> int | None:
    # The facade is rebuilt on setting_changed, so it is read through the module.
    return django_settings.rn_forge_django_settings.drf.transfer.max_rows


def _too_many_rows(what: str, cap: int) -> ValidationError:
    return ValidationError(f"The {what} exceeds the limit of {cap} rows.")


class ResourceExportMixin(ListModelMixin, GenericAPIView):
    """Answer ``list`` as CSV or XLSX when the client asks for it.

    ``Accept: text/csv``, or ``?format=csv``, runs
    ``filter_queryset()`` then ``export_resource_class().export()``. The result
    is not paginated. More rows than ``transfer.max_rows`` is a 422 problem
    naming the cap. Without a tabular ``Accept`` the JSON list is unchanged.

    Attributes:
        export_resource_class: An ``import_export.resources.Resource`` subclass.
        export_formats: Extensions offered; keys of
            :data:`rn_forge.web.TABULAR_FORMATS`.
        export_filename: The download name without extension; the router
            basename when unset.
        export_column_formats: Excel number format per header, for XLSX.
    """

    export_resource_class: ClassVar[type[Any] | None] = None
    export_formats: ClassVar[tuple[str, ...]] = ("csv", "xlsx")
    export_filename: ClassVar[str | None] = None
    export_column_formats: ClassVar[Mapping[str, str]] = {}

    @override
    def get_renderers(self) -> list[Any]:
        renderers = cast("list[Any]", super().get_renderers())
        return [
            *renderers,
            *(_renderer_for(TABULAR_FORMATS[ext])() for ext in self.export_formats),
        ]

    @override
    def list(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponseBase:
        format_name = cast(
            str | None, getattr(request.accepted_renderer, "format", None)
        )
        if format_name not in self.export_formats:
            return cast(Response, cast(Any, super()).list(request, *args, **kwargs))
        fmt = TABULAR_FORMATS[format_name]
        queryset: Any = cast(Any, self).filter_queryset(cast(Any, self).get_queryset())
        cap = _max_rows()
        if cap is not None and queryset.count() > cap:
            return _problem_response(export_cap_problem(cap, instance=request.path))
        resource = self.get_export_resource()
        dataset = cast(
            tablib.Dataset, resource.export(queryset, user=cast(Any, request).user)
        )
        return _tabular_response(
            dataset, fmt, self._filename(), self.export_column_formats
        )

    def get_export_resource(self) -> Any:
        """Return the resource instance that builds the export."""
        assert self.export_resource_class is not None
        return self.export_resource_class()

    def _filename(self) -> str:
        if self.export_filename:
            return self.export_filename
        basename = cast(str | None, getattr(self, "basename", None))
        model: Any = cast(Any, self).get_queryset().model
        return basename or str(model._meta.verbose_name_plural)


class ResourceImportMixin(GenericAPIView):
    """Add ``POST :import`` and ``GET :importTemplate``.

    ``:import`` takes a ``multipart/form-data`` ``file`` part (CSV, TSV, XLSX or
    ODS, by extension) and upserts through ``import_resource_class``. The
    request user is passed to the resource as the ``user`` keyword, so
    ``before_import_row`` can set audit fields and authorize each row. The
    response is ``200`` with ``{created, updated, skipped, validateOnly}``;
    with ``?validateOnly=true`` nothing is persisted. Any row error is a 422
    problem with ``errors[].pointer = "/rows/<row>/<column>"`` and nothing
    persisted.

    ``:importTemplate`` returns the import columns as an empty file,
    negotiated like an export; ``?prefill=true`` adds the current filtered rows.

    Attributes:
        import_resource_class: An ``import_export.resources.Resource`` subclass.
        import_formats: Extensions accepted for upload and offered for the template.
        import_rollback_on_validation_errors: ``False`` commits the valid rows
            and answers ``200`` with the failures listed under ``errors``.
    """

    import_resource_class: ClassVar[type[Any] | None] = None
    import_formats: ClassVar[tuple[str, ...]] = ("csv", "xlsx")
    import_rollback_on_validation_errors: ClassVar[bool] = True

    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        url_name="import",
        parser_classes=[MultiPartParser],
    )
    def import_items(self, request: Request) -> HttpResponseBase:
        upload: Any = cast(Any, request).FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "No file was submitted."})
        fmt = self._upload_format(str(upload.name))
        dataset = self._load(fmt, upload.read())
        cap = _max_rows()
        if cap is not None and len(dataset) > cap:
            raise _too_many_rows("import", cap)

        validate_only = request.query_params.get("validateOnly", "").lower() in (
            "true",
            "1",
        )
        resource = self.get_import_resource()
        result: Any = resource.import_data(
            dataset,
            dry_run=validate_only,
            use_transactions=True,
            rollback_on_validation_errors=self.import_rollback_on_validation_errors,
            user=cast(Any, request).user,
        )
        for base in cast("list[Any]", result.base_errors):
            raise ValidationError({"file": str(base.error)})
        errors = self._row_errors(resource, result)
        report = import_report_body(
            created=result.totals["new"],
            updated=result.totals["update"],
            skipped=result.totals["skip"],
            validate_only=validate_only,
        )
        if not errors:
            return Response(report)
        if self.import_rollback_on_validation_errors or result.has_errors():
            return _problem_response(row_errors_problem(errors, instance=request.path))
        report["errors"] = [
            field_error(("rows", e.row, *([e.field] if e.field else [])), e.message)
            for e in errors
        ]
        return Response(report)

    @action(
        detail=False,
        methods=["get"],
        url_path="importTemplate",
        url_name="import-template",
    )
    def import_template(self, request: Request) -> HttpResponseBase:
        fmt = self._template_format(request)
        queryset: Any = cast(Any, self).filter_queryset(cast(Any, self).get_queryset())
        if request.query_params.get("prefill", "").lower() not in ("true", "1"):
            queryset = queryset.none()
        elif (cap := _max_rows()) is not None and queryset.count() > cap:
            return _problem_response(export_cap_problem(cap, instance=request.path))
        dataset = cast(
            tablib.Dataset,
            self.get_import_resource().export(queryset, user=cast(Any, request).user),
        )
        return _tabular_response(dataset, fmt, "import-template")

    def get_import_resource(self) -> Any:
        """Return the resource instance that performs the import."""
        assert self.import_resource_class is not None
        return self.import_resource_class()

    @override
    def get_renderers(self) -> list[Any]:
        renderers = cast("list[Any]", super().get_renderers())
        if getattr(self, "action", None) != "import_template":
            return renderers
        return [
            *renderers,
            *(_renderer_for(TABULAR_FORMATS[e])() for e in self.import_formats),
        ]

    def _template_format(self, request: Request) -> TabularFormat:
        name = cast(str | None, getattr(request.accepted_renderer, "format", None))
        return TABULAR_FORMATS[
            name if name in self.import_formats else self.import_formats[0]
        ]

    def _upload_format(self, filename: str) -> TabularFormat:
        extension = filename.rsplit(".", 1)[-1].lower()
        if extension not in self.import_formats:
            raise ValidationError(
                {
                    "file": f"Unsupported file type; use one of: {', '.join(self.import_formats)}."
                }
            )
        return TABULAR_FORMATS[extension]

    @staticmethod
    def _load(fmt: TabularFormat, raw: bytes) -> tablib.Dataset:
        content: str | bytes = (
            raw.decode("utf-8-sig") if fmt.extension in _TEXT_FORMATS else raw
        )
        try:
            return cast(Any, tablib.Dataset()).load(content, format=fmt.tablib_name)
        except Exception as exc:  # noqa: BLE001  # tablib and openpyxl raise unrelated types for a corrupt file
            raise ValidationError(
                {"file": f"The file could not be read as {fmt.extension}."}
            ) from exc

    @staticmethod
    def _row_errors(resource: Any, result: Any) -> list[RowError]:
        """Map an import ``Result`` to rows numbered from 0 and columns named as in the file."""
        columns: Mapping[str, Any] = resource.fields
        errors: list[RowError] = []
        for invalid in cast("list[Any]", result.invalid_rows):
            for name, messages in cast(
                "dict[str, list[str]]", invalid.field_specific_errors
            ).items():
                column = str(columns[name].column_name) if name in columns else name
                errors.extend(RowError(invalid.number - 1, column, m) for m in messages)
            errors.extend(
                RowError(invalid.number - 1, "", m)
                for m in invalid.non_field_specific_errors
            )
        for number, row_errors in cast(
            "list[tuple[int, list[Any]]]", result.row_errors()
        ):
            errors.extend(RowError(number - 1, "", str(e.error)) for e in row_errors)
        return errors


class BatchCreateMixin(GenericAPIView):
    """Add ``POST :batchCreate``: ``{"requests": [...]}``, all or nothing.

    Each item goes through the view's serializer. The response is ``200`` with
    the created resources under the plural resource name. A validation failure
    is a 422 problem with ``errors[].pointer = "/requests/<i>/<field>"``; an
    error string from :meth:`validate_batch_create_item` is a 403 problem
    pointing at the item. Nothing is persisted on failure.

    Attributes:
        batch_resource_name: The response key; the model's plural verbose name
            in camelCase when unset.
    """

    batch_resource_name: ClassVar[str | None] = None

    def prepare_batch_create_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Return one request item before serializer validation."""
        return item

    def validate_batch_create_item(self, item: dict[str, Any]) -> str | None:
        """Return an error message for one validated item, or ``None`` when allowed."""
        del item
        return None

    @action(
        detail=False, methods=["post"], url_path="batchCreate", url_name="batch-create"
    )
    def batch_create(self, request: Request) -> HttpResponseBase:
        items = _list_member(request, "requests")
        cap = _max_rows()
        if cap is not None and len(items) > cap:
            raise _too_many_rows("batch", cap)
        prepared = [
            self.prepare_batch_create_item(cast("dict[str, Any]", i)) for i in items
        ]
        serializer: Any = cast(Any, self).get_serializer(data=prepared, many=True)
        if not serializer.is_valid():
            errors = [
                e
                for i, item_errors in enumerate(serializer.errors)
                for e in _flatten(i, item_errors)
            ]
            return _problem_response(
                row_errors_problem(errors, instance=request.path, root="requests")
            )

        denied: dict[str, list[str]] = {}
        for index, item in enumerate(
            cast("list[dict[str, Any]]", serializer.validated_data)
        ):
            if isinstance(self, AuditFieldsViewMixin):
                self.prepare_create_data(item)
            message = self.validate_batch_create_item(item)
            if message is not None:
                denied[str(index)] = [message]
        if denied:
            raise PermissionDenied({"requests": denied})

        with transaction.atomic():
            serializer.save()
        return Response({self._resource_name(): serializer.data})

    def _resource_name(self) -> str:
        if self.batch_resource_name:
            return self.batch_resource_name
        model: Any = cast(Any, self).get_queryset().model
        first, *rest = str(model._meta.verbose_name_plural).split()
        return first + "".join(word.title() for word in rest)


class BatchDeleteMixin(GenericAPIView):
    """Add ``POST :batchDelete``: ``{"ids": [...]}``, all or nothing, ``204``.

    Ids are matched within ``filter_queryset(get_queryset())``; an id outside it
    is a 404 problem naming the id. An error string from
    :meth:`validate_batch_delete_instance` is a 403 problem pointing at the id.
    """

    def validate_batch_delete_instance(self, instance: Any) -> str | None:
        """Return an error message for one delete target, or ``None`` when allowed."""
        del instance
        return None

    @action(
        detail=False, methods=["post"], url_path="batchDelete", url_name="batch-delete"
    )
    def batch_delete(self, request: Request) -> Response:
        ids = _list_member(request, "ids")
        cap = _max_rows()
        if cap is not None and len(ids) > cap:
            raise _too_many_rows("batch", cap)
        queryset: Any = cast(Any, self).filter_queryset(cast(Any, self).get_queryset())
        found = {str(obj.pk): obj for obj in queryset.filter(pk__in=ids)}
        for raw_id in ids:
            if str(raw_id) not in found:
                label = str(queryset.model._meta.verbose_name).capitalize()
                raise NotFound(f"{label} {raw_id} not found")

        denied: dict[str, list[str]] = {}
        for index, raw_id in enumerate(ids):
            message = self.validate_batch_delete_instance(found[str(raw_id)])
            if message is not None:
                denied[str(index)] = [message]
        if denied:
            raise PermissionDenied({"ids": denied})

        with transaction.atomic():
            for instance in list(found.values()):
                instance.delete()
        return Response(status=204)


def _list_member(request: Request, key: str) -> list[object]:
    """Return ``request.data[key]``, which must be a non-empty list."""
    data: object = cast(Any, request).data
    value = (
        cast("Mapping[str, object]", data).get(key)
        if isinstance(data, Mapping)
        else None
    )
    if not isinstance(value, list) or not value:
        raise ValidationError({key: "A non-empty list is required."})
    return cast("list[object]", value)


def _flatten(row: int, errors: object) -> list[RowError]:
    """Flatten one item's serializer errors to :class:`RowError` (nested keys joined by ``.``)."""
    found: list[RowError] = []

    def walk(node: object, path: tuple[str, ...]) -> None:
        if isinstance(node, Mapping):
            for key, value in cast("Mapping[str, object]", node).items():
                walk(value, path if key == _NON_FIELD_KEY else (*path, key))
        elif isinstance(node, list):
            for value in cast("list[object]", node):
                walk(value, path)
        else:
            found.append(RowError(row, ".".join(path), str(node)))

    walk(errors, ())
    return found
