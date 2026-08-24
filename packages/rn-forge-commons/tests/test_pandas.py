"""Tests for rn_forge.commons.pandas."""

from __future__ import annotations

import decimal
from decimal import Decimal

import pytest

pd = pytest.importorskip("pandas")

import rn_forge.commons.pandas as pandas_module
from rn_forge.commons.pandas import PandasUtils
from rn_forge.commons.exceptions import AppException


def _row(**kwargs) -> pd.Series:
    """Helper: build a single-row Series from keyword arguments."""
    return pd.DataFrame([kwargs]).iloc[0]


# ---------------------------------------------------------------------------
# get_field
# ---------------------------------------------------------------------------


class TestGetField:
    def test_returns_value(self):
        row = _row(name="alice", age=30)
        assert PandasUtils.get_field(row, "name") == "alice"

    def test_returns_none_for_nan(self):
        row = _row(name=float("nan"))
        result = PandasUtils.get_field(row, "name", required=False)
        assert result is None

    def test_required_nan_raises(self):
        row = _row(name=float("nan"))
        with pytest.raises(AppException, match="name"):
            PandasUtils.get_field(row, "name", required=True)

    def test_required_false_nan_returns_none(self):
        row = _row(name=float("nan"))
        assert PandasUtils.get_field(row, "name", required=False) is None

    def test_required_true_valid_value_does_not_raise(self):
        row = _row(score=99)
        assert PandasUtils.get_field(row, "score") == 99

    def test_numeric_zero_is_valid(self):
        row = _row(count=0)
        assert PandasUtils.get_field(row, "count") == 0

    def test_none_cell_raises_when_required(self):
        row = _row(val=None)
        with pytest.raises(AppException, match="val"):
            PandasUtils.get_field(row, "val", required=True)

    def test_missing_column_raises_key_error(self):
        row = _row(name="alice")
        with pytest.raises(KeyError):
            PandasUtils.get_field(row, "missing")


# ---------------------------------------------------------------------------
# get_string_field
# ---------------------------------------------------------------------------


class TestGetStringField:
    def test_returns_string(self):
        row = _row(city="london")
        assert PandasUtils.get_string_field(row, "city") == "london"

    def test_numeric_coerced_to_string(self):
        row = _row(count=42)
        assert PandasUtils.get_string_field(row, "count") == "42"

    def test_nan_returns_empty_string(self):
        row = _row(name=float("nan"))
        assert PandasUtils.get_string_field(row, "name", required=False) == ""

    def test_required_nan_raises(self):
        row = _row(name=float("nan"))
        with pytest.raises(AppException):
            PandasUtils.get_string_field(row, "name", required=True)


# ---------------------------------------------------------------------------
# get_decimal_field
# ---------------------------------------------------------------------------


class TestGetDecimalField:
    def test_basic_conversion(self):
        row = _row(amount="12.50")
        result = PandasUtils.get_decimal_field(row, "amount")
        assert result == Decimal("12.50")

    def test_default_precision_is_two(self):
        row = _row(amount="12.5678")
        result = PandasUtils.get_decimal_field(row, "amount")
        assert result == Decimal("12.57")

    def test_custom_precision(self):
        row = _row(rate="0.123456")
        result = PandasUtils.get_decimal_field(row, "rate", precision=4)
        assert result == Decimal("0.1235")

    def test_zero_precision(self):
        row = _row(amount="12.9")
        result = PandasUtils.get_decimal_field(row, "amount", precision=0)
        assert result == Decimal("13")

    def test_float_value(self):
        row = _row(amount=1.5)
        result = PandasUtils.get_decimal_field(row, "amount")
        assert result == Decimal("1.50")

    def test_empty_string_returns_zero(self):
        row = _row(amount="")
        result = PandasUtils.get_decimal_field(row, "amount", required=False)
        assert result == Decimal("0.00")

    def test_nan_not_required_returns_zero(self):
        row = _row(amount=float("nan"))
        result = PandasUtils.get_decimal_field(row, "amount", required=False)
        assert result == Decimal("0.00")

    def test_nan_required_raises(self):
        row = _row(amount=float("nan"))
        with pytest.raises(AppException):
            PandasUtils.get_decimal_field(row, "amount", required=True)

    def test_returns_decimal_type(self):
        row = _row(amount="5.00")
        result = PandasUtils.get_decimal_field(row, "amount")
        assert isinstance(result, Decimal)

    def test_invalid_decimal_raises(self):
        row = _row(amount="not-a-number")
        with pytest.raises(decimal.InvalidOperation):
            PandasUtils.get_decimal_field(row, "amount")


class TestIsNa:
    def test_true_for_nan(self):
        assert PandasUtils.is_na(float("nan")) is True

    def test_false_for_regular_value(self):
        assert PandasUtils.is_na("value") is False


# Coverage ROI notes:
# - pandas missing-value semantics are delegated to pandas itself; tests cover
#   integration points and error propagation, not pandas internals.
