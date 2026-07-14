"""Reusable renderer contracts for DRF transfer views."""

from __future__ import annotations

import csv
import io
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from openpyxl.styles import Font
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from rn_forge.commons.excel import CellFormat, ExcelAdapter, ExcelUtils

__all__ = [
    "CsvExportRenderer",
    "ExcelExportRenderer",
    "ExportDataset",
    "ExportRenderer",
    "JsonExportRenderer",
    "TransferColumn",
]


# ---------------------------------------------------------------------------
# Export Dataset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransferColumn:
    """Ordered transfer column definition shared by import and export flows."""

    header: str
    source: str
    required: bool = True
    read_only: bool = False
    write_only: bool = False
    help_text: str | None = None
    resolver: Callable[[object], object] | None = None
    excel_format: object | None = None
    width: int | None = None
    number_format: str | None = None

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, str]) -> tuple["TransferColumn", ...]:
        """Build simple columns from ``{header: source}`` mappings."""
        return tuple(
            cls(header=header, source=source) for header, source in mapping.items()
        )


@dataclass(frozen=True)
class ExportDataset:
    """Normalized tabular dataset consumed by format-specific renderers."""

    columns: Sequence[TransferColumn]
    rows: list[dict[str, object]]


# ---------------------------------------------------------------------------
# Renderer Contracts
# ---------------------------------------------------------------------------


class ExportRenderer(ABC):
    """Abstract file renderer for normalized export datasets."""

    content_type: str
    file_extension: str

    @abstractmethod
    def render_bytes(self, dataset: ExportDataset) -> bytes:
        """Render *dataset* to a downloadable byte payload."""


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


class CsvExportRenderer(ExportRenderer):
    """Render tabular export rows as a CSV file."""

    content_type = "text/csv"
    file_extension = "csv"

    def render_bytes(self, dataset: ExportDataset) -> bytes:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(column.header for column in dataset.columns)
        for row in dataset.rows:
            writer.writerow(
                "" if value is None else value
                for value in (row.get(column.header) for column in dataset.columns)
            )
        return output.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


class JsonExportRenderer(ExportRenderer):
    """Render tabular export rows as a JSON file."""

    content_type = "application/json"
    file_extension = "json"

    def render_bytes(self, dataset: ExportDataset) -> bytes:
        return json.dumps(dataset.rows, default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------


class ExcelExportRenderer(ExportRenderer):
    """Render tabular export datasets to an ``.xlsx`` workbook."""

    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    file_extension = "xlsx"
    worksheet_title = "Export"

    def render_bytes(self, dataset: ExportDataset) -> bytes:
        workbook = ExcelUtils.new_workbook()
        worksheet = workbook.active
        if worksheet is None:
            worksheet = workbook.create_sheet(self.worksheet_title)
        worksheet.title = self.worksheet_title
        self.render_header(worksheet, dataset)
        self.render_rows(worksheet, dataset)
        self.finalize_workbook(workbook, worksheet, dataset)
        return ExcelAdapter.workbook_to_bytes(workbook).getvalue()

    def render_header(self, worksheet: Worksheet, dataset: ExportDataset) -> None:
        """Write the header row for *dataset*."""
        worksheet.append([column.header for column in dataset.columns])
        self.format_header_row(worksheet, dataset)

    def render_rows(self, worksheet: Worksheet, dataset: ExportDataset) -> None:
        """Write all data rows for *dataset*."""
        column_formats = {
            index: cast(CellFormat, column.excel_format)
            for index, column in enumerate(dataset.columns, start=1)
            if column.excel_format is not None
        }
        column_formats.update(
            {
                index: CellFormat(number_format=column.number_format)
                for index, column in enumerate(dataset.columns, start=1)
                if column.number_format is not None and column.excel_format is None
            }
        )
        for row_index, row in enumerate(dataset.rows, start=2):
            values = [row.get(column.header) for column in dataset.columns]
            worksheet.append(values)
            ExcelUtils.format_row(worksheet[row_index], column_formats=column_formats)
            self.format_data_row(worksheet, row_index, row, dataset)

    def format_header_row(
        self,
        worksheet: Worksheet,
        dataset: ExportDataset,
    ) -> None:
        """Hook for subclasses to apply header-level formatting."""
        del dataset
        worksheet.freeze_panes = "A2"
        for cell in worksheet[1]:
            cell.font = Font(bold=True)

    def format_data_row(
        self,
        worksheet: Worksheet,
        row_index: int,
        row: dict[str, object],
        dataset: ExportDataset,
    ) -> None:
        """Hook for subclasses to apply row-level formatting."""
        del worksheet, row_index, row, dataset

    def format_row(
        self,
        worksheet: Worksheet,
        row_index: int,
        row: dict[str, object],
        dataset: ExportDataset,
    ) -> None:
        """Backward-compatible row formatting hook."""
        self.format_data_row(worksheet, row_index, row, dataset)

    def finalize_workbook(
        self,
        workbook: Workbook,
        worksheet: Worksheet,
        dataset: ExportDataset,
    ) -> None:
        """Apply final workbook-level adjustments after all rows are written."""
        del workbook
        if dataset.rows:
            last_column = ExcelUtils.column_letter(len(dataset.columns))
            ExcelUtils.add_table(
                worksheet,
                "ExportTable",
                f"A1:{last_column}{len(dataset.rows) + 1}",
                "TableStyleMedium2",
                show_row_stripes=True,
            )
        ExcelUtils.auto_adjust_column_width(worksheet)
        for index, column in enumerate(dataset.columns, start=1):
            if column.width is not None:
                letter = ExcelUtils.column_letter(index)
                worksheet.column_dimensions[letter].width = column.width
