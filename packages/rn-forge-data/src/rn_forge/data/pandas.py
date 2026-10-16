"""The pandas adapter: row field extraction and Excel DataFrame conversion.

Requires the ``pandas`` extra.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas
from openpyxl.workbook.workbook import Workbook
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger
from rn_forge.data.excel import ExcelUtils

__all__ = [
    "ExcelAdapter",
    "PandasUtils",
    "SeriesRow",
    "series_columns",
    "series_value",
]

_LOGGER = AppLogger.get_logger(__name__)

type SeriesRow = pandas.Series


def series_value(row: SeriesRow, field_name: str) -> Any:
    """Return ``row[field_name]``, normalized to ``Any``.

    ``Series.__getitem__`` has a wide overload set; pinning the result to
    ``Any`` here keeps the variation out of every call site.
    """
    return row[field_name]


def series_columns(row: SeriesRow) -> list[Any]:
    """Return the index labels of *row* as a plain list."""
    return row.index.tolist()


class PandasUtils:
    """Field extraction from pandas DataFrame and Series rows.

    Requires ``pandas`` — install with ``rn-forge-data[pandas]``.

    Example::

        row = df.iloc[0]
        customer_id = PandasUtils.get_string_field(row, "customer_id")
        total = PandasUtils.get_decimal_field(row, "total", precision=2)
    """

    # -- row field extraction ----------------------------------------------

    @staticmethod
    def get_field(
        row: pandas.Series,
        field_name: str,
        required: bool = True,
    ) -> Any:
        """Return the value of *field_name* from *row*, or ``None`` if NaN.

        Args:
            row: A ``pandas.Series`` (e.g. from ``df.itertuples()`` or
                ``df.iterrows()``).
            field_name: Column name to extract.
            required: When ``True`` (default), raise
                :exc:`~rn_forge.commons.AppException` if the field is NaN / missing.
        """
        try:
            field_value: Any = series_value(row, field_name)
        except Exception:
            columns = series_columns(row) if hasattr(row, "index") else "<unavailable>"
            _LOGGER.exception(  # noqa: PLE1205  # brace-style log format
                "PandasUtils.get_field failed | field={} | required={} | columns={}",
                field_name,
                required,
                columns,
            )
            raise
        is_valid = not PandasUtils.is_na(field_value)
        _LOGGER.trace(
            "PandasUtils.get_field | field={} | required={} | is_valid={} | value={}",
            field_name,
            required,
            is_valid,
            field_value,
        )

        if required and not is_valid:
            _LOGGER.warning(  # noqa: PLE1205  # brace-style log format
                "PandasUtils.get_field missing required value | field={} | columns={}",
                field_name,
                series_columns(row),
            )
        AppException.check(
            not required or is_valid,
            "Field is required: {}",
            field_name,
        )

        return field_value if is_valid else None

    @staticmethod
    def get_string_field(
        row: pandas.Series,
        field_name: str,
        required: bool = True,
    ) -> str:
        """Return *field_name* from *row* as a string.

        NaN values are returned as an empty string ``""``.
        """
        field_value = PandasUtils.get_field(row, field_name, required)
        result = str(field_value or "").strip()
        _LOGGER.trace(
            "PandasUtils.get_string_field | field={} | required={} | result={}",
            field_name,
            required,
            result,
        )
        return result

    @staticmethod
    def get_decimal_field(
        row: pandas.Series,
        field_name: str,
        precision: int = 2,
        required: bool = True,
    ) -> Decimal:
        """Return *field_name* from *row* as a :class:`~decimal.Decimal`.

        Args:
            row: A ``pandas.Series`` row.
            field_name: Column name to extract.
            precision: Number of decimal places to round to (default ``2``).
            required: When ``True`` (default), raise
                :exc:`~rn_forge.commons.AppException` if the field is NaN / missing.
        """
        field_value = PandasUtils.get_string_field(row, field_name, required)
        try:
            result = round(Decimal(str(field_value or 0)), precision)
        except Exception:
            _LOGGER.exception(  # noqa: PLE1205  # brace-style log format
                "PandasUtils.get_decimal_field failed | field={} | precision={} | value={}",
                field_name,
                precision,
                field_value,
            )
            raise
        _LOGGER.trace(
            "PandasUtils.get_decimal_field | field={} | precision={} | result={}",
            field_name,
            precision,
            result,
        )
        return result

    @staticmethod
    def is_na(value: Any) -> bool:
        """Return whether *value* is considered missing by pandas.

        Mirrors :func:`pandas.isna` but always returns a plain ``bool``.
        """
        # pandas-stubs gap: the ``isna`` overload set leaks Unknown type vars.
        result = bool(pandas.isna(value))  # pyright: ignore[reportUnknownArgumentType]
        _LOGGER.trace("PandasUtils.is_na | result={}", result)
        return result


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
    def read_dataframe(path: str | Path) -> dict[str, pandas.DataFrame]:
        """Read a workbook file into a sheet-name keyed DataFrame mapping."""
        _LOGGER.debug("ExcelAdapter.read_dataframe | path={}", path)  # noqa: PLE1205  # brace-style log format
        try:
            workbook: dict[str, pandas.DataFrame] = pandas.read_excel(  # pyright: ignore[reportUnknownMemberType]  # pandas-stubs gap
                path, sheet_name=None
            )
        except Exception:
            _LOGGER.exception("ExcelAdapter.read_dataframe failed | path={}", path)  # noqa: PLE1205  # brace-style log format
            raise
        _LOGGER.verbose(
            "ExcelAdapter.read_dataframe complete | path={} | sheets={}",
            path,
            list(workbook),
        )
        return workbook

    @staticmethod
    def load_dataframe(source: BytesIO) -> dict[str, pandas.DataFrame]:
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
        data: pandas.DataFrame | dict[str, pandas.DataFrame],
    ) -> Workbook:
        """Convert DataFrame data to an in-memory workbook."""
        buf = BytesIO()
        sheets = data if isinstance(data, dict) else {"Sheet1": data}
        _LOGGER.debug(  # noqa: PLE1205  # brace-style log format
            "ExcelAdapter.from_dataframe | sheets={}",
            list(sheets),
        )
        try:
            with pandas.ExcelWriter(
                buf, engine="openpyxl"
            ) as writer:  # pandas-stubs gap
                for sheet_name, frame in sheets.items():
                    _LOGGER.trace(
                        "ExcelAdapter.from_dataframe sheet | name={} | rows={} | columns={}",
                        sheet_name,
                        len(frame.index),
                        list(frame.columns),
                    )
                    frame.to_excel(writer, sheet_name=sheet_name, index=False)  # pyright: ignore[reportUnknownMemberType]  # pandas-stubs gap
        except Exception:
            _LOGGER.exception(  # noqa: PLE1205  # brace-style log format
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
