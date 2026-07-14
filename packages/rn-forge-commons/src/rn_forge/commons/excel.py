"""Excel utilities built on ``openpyxl``.

Provides:

- :class:`CellFormat` — dataclass capturing cell formatting attributes
  (font, fill, border, number format, alignment, protection).
- :class:`WorkbookTemplate` — config struct for sheet column layout and
  default formatting.
- :class:`ExcelUtils` — static helpers for creating, loading, and saving
  workbooks; applying row/column formats; managing named tables; and
  auto-adjusting column widths.
- :class:`ExcelAdapter` — adapters between workbook/file/bytes I/O and
  pandas DataFrame representations.

Requires ``openpyxl``. DataFrame adapter methods also require ``pandas``.
Install with ``pip install rn-forge-commons[excel]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
import pandas
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from rn_forge.commons.dataclasses import DataclassMixin
from rn_forge.commons.logging import AppLogger

__all__ = [
    "CellFormat",
    "ExcelAdapter",
    "ExcelUtils",
    "WorkbookTemplate",
]

_LOGGER = AppLogger.get_logger(__name__)


# ---------------------------------------------------------------------------
# CellFormat — cell formatting dataclass
# ---------------------------------------------------------------------------


@dataclass
class CellFormat(DataclassMixin):
    """Cell formatting attributes applied via :meth:`ExcelUtils.format_row`.

    All fields are optional; only non-``None`` values are applied to cells.
    """

    font: Font | None = None
    fill: PatternFill | None = None
    border: Border | None = None
    number_format: str | None = None
    alignment: Alignment | None = None
    protection: Protection | None = None


# ---------------------------------------------------------------------------
# WorkbookTemplate — sheet structure config
# ---------------------------------------------------------------------------


@dataclass
class WorkbookTemplate(DataclassMixin):
    """Configuration struct for a worksheet's column layout and default formats.

    Args:
        name: Sheet name.
        columns: Ordered list of column header strings.
        row_format: Default :class:`CellFormat` applied to every data row.
        column_formats: Per-column format overrides keyed by 1-based column index.
    """

    name: str
    columns: list[str]
    row_format: CellFormat | None = None
    column_formats: dict[int, CellFormat] = field(default_factory=dict[int, CellFormat])


# ---------------------------------------------------------------------------
# ExcelUtils — workbook helpers
# ---------------------------------------------------------------------------


class ExcelUtils:
    """Static helpers for Excel workbook operations via ``openpyxl``.

    Requires ``openpyxl`` — install with ``rn-forge-commons[excel]``.

    Typical workflow::

        wb = ExcelUtils.new_workbook()
        sheet = wb.active
        sheet.title = "Orders"
        sheet.append(["id", "total"])
        sheet.append([1001, 42.50])
        ExcelUtils.write_workbook(wb, "build/orders.xlsx")
    """

    # -- pre-built format constants ----------------------------------------

    FORMAT_CURRENCY: CellFormat = CellFormat(
        number_format='_([$$-en-US]* #,##0.00_);_([$$-en-US]* (#,##0.00);_([$$-en-US]* "-"??_);_(@_)'
    )
    FORMAT_DATE: CellFormat = CellFormat(number_format="mm/dd/yy;@")
    FORMAT_PERCENTAGE: CellFormat = CellFormat(number_format="0.00%")

    # -- workbook I/O ------------------------------------------------------

    @staticmethod
    def new_workbook(write_only: bool = False, iso_dates: bool = False) -> Workbook:
        """Create and return a new blank :class:`~openpyxl.workbook.Workbook`."""
        _LOGGER.debug(
            "ExcelUtils.new_workbook | write_only={} | iso_dates={}",
            write_only,
            iso_dates,
        )
        return openpyxl.Workbook(write_only=write_only, iso_dates=iso_dates)

    @staticmethod
    def load_workbook(
        source: str | Path | BytesIO,
        read_only: bool = False,
        keep_vba: bool = False,
        data_only: bool = False,
        keep_links: bool = True,
        rich_text: bool = False,
    ) -> Workbook:
        """Load an existing Excel file from a path or byte stream.

        Args:
            source: File path or :class:`~io.BytesIO` containing the workbook.
            read_only: Open in read-only mode (faster for large files).
            keep_vba: Preserve VBA macros.
            data_only: Return cell values instead of formulae.
            keep_links: Preserve external links.
            rich_text: Preserve rich-text cell content.
        """
        _LOGGER.debug(
            "ExcelUtils.load_workbook | source={} | read_only={} | keep_vba={} | data_only={} | keep_links={} | rich_text={}",
            source,
            read_only,
            keep_vba,
            data_only,
            keep_links,
            rich_text,
        )
        try:
            workbook = openpyxl.load_workbook(
                source,
                read_only=read_only,
                keep_vba=keep_vba,
                data_only=data_only,
                keep_links=keep_links,
                rich_text=rich_text,
            )
        except Exception:
            _LOGGER.exception("ExcelUtils.load_workbook failed | source={}", source)
            raise
        _LOGGER.verbose(
            "ExcelUtils.load_workbook complete | source={} | sheets={}",
            source,
            workbook.sheetnames,
        )
        return workbook

    @staticmethod
    def write_workbook(workbook: Workbook, path: str | Path) -> Path:
        """Save *workbook* to *path*, creating parent directories as needed.

        Returns the resolved :class:`~pathlib.Path` written.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _LOGGER.debug(
            "ExcelUtils.write_workbook | path={} | sheets={}",
            target,
            workbook.sheetnames,
        )
        try:
            workbook.save(target)
        except Exception:
            _LOGGER.exception("ExcelUtils.write_workbook failed | path={}", target)
            raise
        _LOGGER.verbose("ExcelUtils.write_workbook complete | path={}", target)
        return target

    @staticmethod
    def write_workbook_bytes(workbook: Workbook) -> BytesIO:
        """Serialise *workbook* to an in-memory :class:`~io.BytesIO` buffer."""
        target = BytesIO()
        _LOGGER.debug(
            "ExcelUtils.write_workbook_bytes | sheets={}",
            workbook.sheetnames,
        )
        try:
            workbook.save(target)
        except Exception:
            _LOGGER.exception("ExcelUtils.write_workbook_bytes failed")
            raise
        _LOGGER.trace(
            "ExcelUtils.write_workbook_bytes complete | bytes={}",
            target.tell(),
        )
        return target

    # -- formatting --------------------------------------------------------

    @staticmethod
    def format_row(
        row: tuple[Any, ...],
        row_format: CellFormat | None = None,
        column_formats: dict[int, CellFormat] | None = None,
    ) -> None:
        """Apply *row_format* and per-column *column_formats* to every cell in *row*.

        Args:
            row: Tuple of ``Cell`` objects as returned by iterating worksheet rows.
            row_format: Format applied to every cell in the row before column overrides.
            column_formats: Mapping of 1-based column index → :class:`CellFormat`.
                Applied after *row_format*, so column-specific values take precedence.
        """
        _column_formats = column_formats or {}
        _LOGGER.trace(
            "ExcelUtils.format_row | cells={} | row_format={} | column_formats={}",
            len(row),
            row_format is not None,
            sorted(_column_formats),
        )
        for cell in row:
            if row_format:
                for key, value in vars(row_format).items():
                    if value is not None:
                        setattr(cell, key, value)
            col_fmt = _column_formats.get(cell.column) if cell.column else None
            if col_fmt:
                for key, value in vars(col_fmt).items():
                    if value is not None:
                        setattr(cell, key, value)

    # -- table management --------------------------------------------------

    @staticmethod
    def add_table(
        sheet: Worksheet,
        table_name: str,
        cell_range: str,
        style: str,
        show_first_column: bool | None = None,
        show_last_column: bool | None = None,
        show_row_stripes: bool | None = None,
        show_column_stripes: bool | None = None,
    ) -> None:
        """Add a named table to *sheet*.

        Parameters
        ----------
        sheet:
            Target worksheet.
        table_name:
            Unique display name for the table (e.g. ``"SalesData"``).
        cell_range:
            Excel range reference (e.g. ``"A1:D20"``).
        style:
            Table style name (e.g. ``"TableStyleMedium9"``).
        show_first_column / show_last_column / show_row_stripes / show_column_stripes:
            Optional table style flags.
        """
        from openpyxl.worksheet.table import Table, TableStyleInfo

        _LOGGER.debug(
            "ExcelUtils.add_table | sheet={} | table_name={} | range={} | style={}",
            sheet.title,
            table_name,
            cell_range,
            style,
        )
        table = Table(displayName=table_name, ref=cell_range)
        table.tableStyleInfo = TableStyleInfo(
            name=style,
            showFirstColumn=show_first_column,
            showLastColumn=show_last_column,
            showRowStripes=show_row_stripes,
            showColumnStripes=show_column_stripes,
        )
        sheet.add_table(table)

    @staticmethod
    def resize_table(sheet: Worksheet, table_name: str) -> None:
        """Resize the named table to span all rows currently in *sheet*.

        Updates the table's ``ref`` to ``A1:<last-column><last-row>``.

        Raises:
            TypeError: If the last cell in the final row is a merged cell (no column letter).
        """
        from openpyxl.cell import Cell

        _LOGGER.debug(
            "ExcelUtils.resize_table | sheet={} | table_name={} | max_row={}",
            sheet.title,
            table_name,
            sheet.max_row,
        )
        last_row = sheet[sheet.max_row]
        last_cell = last_row[-1]
        if not isinstance(last_cell, Cell):
            _LOGGER.warning(
                "ExcelUtils.resize_table: merged cell prevents resize | sheet={} | table_name={} | row={}",
                sheet.title,
                table_name,
                sheet.max_row,
            )
            raise TypeError(
                f"resize_table: last cell in row {sheet.max_row} is a MergedCell "
                "and has no column letter — cannot determine table bounds"
            )
        sheet.tables[table_name].ref = f"A1:{last_cell.column_letter}{sheet.max_row}"
        _LOGGER.trace(
            "ExcelUtils.resize_table complete | table_name={} | ref={}",
            table_name,
            sheet.tables[table_name].ref,
        )

    # -- column utilities --------------------------------------------------

    @staticmethod
    def auto_adjust_column_width(sheet: Worksheet) -> None:
        """Set each column's width to fit the longest cell value in that column."""
        from openpyxl.cell import Cell

        _LOGGER.debug(
            "ExcelUtils.auto_adjust_column_width | sheet={} | columns={}",
            sheet.title,
            sheet.max_column,
        )
        for col_cells in sheet.columns:
            col_list = list(col_cells)
            max_length = 0
            for cell in col_list:
                if cell.value is None:
                    continue
                max_length = max(max_length, len(str(cell.value)))
            first = col_list[0]
            if not isinstance(first, Cell):
                continue
            sheet.column_dimensions[first.column_letter].width = max_length + 1
        _LOGGER.trace(
            "ExcelUtils.auto_adjust_column_width complete | sheet={}",
            sheet.title,
        )

    @staticmethod
    def column_letter(column_number: int) -> str:
        """Convert a 1-based column number to its Excel letter(s).

        Examples: ``1`` → ``"A"``, ``26`` → ``"Z"``, ``27`` → ``"AA"``.
        """
        from openpyxl.utils import get_column_letter

        return get_column_letter(column_number)


class ExcelAdapter:
    """Adapters between workbook primitives and pandas DataFrames.

    Use this layer when the calling code wants ``pandas`` for transformation
    but ``openpyxl`` for workbook-level formatting or templating.

    Example::

        data = ExcelAdapter.read_dataframe("orders.xlsx")
        workbook = ExcelAdapter.from_dataframe(data)
        ExcelUtils.write_workbook(workbook, "build/orders-copy.xlsx")
    """

    @staticmethod
    def read_dataframe(path: str | Path) -> dict[str, "pandas.DataFrame"]:
        """Read a workbook file into a sheet-name keyed DataFrame mapping."""
        _LOGGER.debug("ExcelAdapter.read_dataframe | path={}", path)
        try:
            workbook: dict[str, pandas.DataFrame] = pandas.read_excel(  # pyright: ignore[reportUnknownMemberType]  # pandas-stubs gap
                path, sheet_name=None
            )
        except Exception:
            _LOGGER.exception("ExcelAdapter.read_dataframe failed | path={}", path)
            raise
        _LOGGER.verbose(
            "ExcelAdapter.read_dataframe complete | path={} | sheets={}",
            path,
            list(workbook),
        )
        return workbook

    @staticmethod
    def load_dataframe(source: BytesIO) -> dict[str, "pandas.DataFrame"]:
        """Load an in-memory workbook into a sheet-name keyed DataFrame mapping."""
        _LOGGER.debug("ExcelAdapter.load_dataframe")
        try:
            workbook: dict[str, pandas.DataFrame] = pandas.read_excel(  # pyright: ignore[reportUnknownMemberType]  # pandas-stubs gap
                source, sheet_name=None
            )
        except Exception:
            _LOGGER.exception("ExcelAdapter.load_dataframe failed")
            raise
        _LOGGER.verbose(
            "ExcelAdapter.load_dataframe complete | sheets={}",
            list(workbook),
        )
        return workbook

    @staticmethod
    def from_dataframe(
        data: "pandas.DataFrame | dict[str, pandas.DataFrame]",
    ) -> Workbook:
        """Convert DataFrame data to an in-memory workbook."""
        buf = BytesIO()
        sheets = data if isinstance(data, dict) else {"Sheet1": data}
        _LOGGER.debug(
            "ExcelAdapter.from_dataframe | sheets={}",
            list(sheets),
        )
        try:
            with pandas.ExcelWriter(buf, engine="openpyxl") as writer:  # pyright: ignore[reportUnknownVariableType]  # pandas-stubs gap
                for sheet_name, frame in sheets.items():
                    _LOGGER.trace(
                        "ExcelAdapter.from_dataframe sheet | name={} | rows={} | columns={}",
                        sheet_name,
                        len(frame.index),
                        list(frame.columns),
                    )
                    frame.to_excel(writer, sheet_name=sheet_name, index=False)  # pyright: ignore[reportUnknownMemberType]  # pandas-stubs gap
        except Exception:
            _LOGGER.exception(
                "ExcelAdapter.from_dataframe failed | sheets={}",
                list(sheets),
            )
            raise
        buf.seek(0)
        workbook = ExcelUtils.load_workbook(buf)
        _LOGGER.verbose(
            "ExcelAdapter.from_dataframe complete | sheets={}",
            workbook.sheetnames,
        )
        return workbook

    @staticmethod
    def read_workbook(path: str | Path) -> Workbook:
        """Read a workbook from a filesystem path."""
        return ExcelUtils.load_workbook(path)

    @staticmethod
    def load_workbook(source: BytesIO) -> Workbook:
        """Load a workbook from an in-memory byte buffer."""
        return ExcelUtils.load_workbook(source)

    @staticmethod
    def write_workbook(workbook: Workbook, path: str | Path) -> Path:
        """Write a workbook to disk."""
        return ExcelUtils.write_workbook(workbook, path)

    @staticmethod
    def workbook_to_bytes(workbook: Workbook) -> BytesIO:
        """Serialise a workbook to an in-memory byte buffer."""
        return ExcelUtils.write_workbook_bytes(workbook)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
