"""Pandas utilities for DataFrame and Series manipulation.

Provides:

- :class:`PandasUtils` — static helpers for extracting typed field values
  from ``pandas.Series`` rows (with NaN handling and required-field
  validation).

Requires ``pandas``.
Install with ``pip install rn-forge-commons[pandas]``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas
from rn_forge.commons.lang.types import series_columns, series_value
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.logging import AppLogger

__all__ = ["PandasUtils"]

_LOGGER = AppLogger.get_logger(__name__)


class PandasUtils:
    """Static helpers for pandas DataFrame and Series operations.

    Requires ``pandas`` — install with ``rn-forge-commons[pandas]``.

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
            _LOGGER.exception(
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
            _LOGGER.warning(
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
            _LOGGER.exception(
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
