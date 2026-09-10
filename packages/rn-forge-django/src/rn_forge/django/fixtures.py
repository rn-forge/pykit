"""Prepare Django JSON fixtures from Excel workbooks.

Provides a focused port of the useful part of the earlier accelerate-django
fixture workflow:

- read one workbook per fixture definition
- validate required sheets and columns
- convert rows into Django ``loaddata`` JSON payloads
- optionally load the generated JSON fixtures into a configured Django app

This module intentionally does *not* include project-level database reset or
global Django bootstrap wrappers; those were too coupled to application
runtime and introduced side effects that do not belong in a reusable library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, cast

import pandas
from rn_forge.commons.fs.documents import JsonUtils
from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.data.excel import ExcelAdapter
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.data.pandas import PandasUtils
from rn_forge.commons.lang.utils import AppUtils

__all__ = [
    "ColumnType",
    "FixtureColumn",
    "FixtureDefinition",
    "FixtureManager",
    "FixtureManagerConfig",
]


class ColumnType(Enum):
    """Supported source-column conversions for fixture generation."""

    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    FOREIGN_KEY = "foreign_key"
    MANY_TO_MANY = "many_to_many"


@dataclass
class FixtureColumn(DataclassMixin):
    """Describe how a single workbook column should be mapped."""

    name: str
    type: ColumnType = ColumnType.STRING
    required: bool = True


@dataclass
class FixtureDefinition(DataclassMixin):
    """Describe one generated Django fixture."""

    app_label: str
    model: str
    input_file: str
    output_file: str
    columns: list[FixtureColumn]
    key_columns: list[str] = field(default_factory=list[str])
    common_fields: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class FixtureManagerConfig(DataclassMixin):
    """Top-level configuration for fixture generation and loading."""

    root_path: Path
    fixtures: list[FixtureDefinition]
    settings_module: str | None = None

    def get_input_file(self, fixture: FixtureDefinition) -> Path:
        """Return the workbook path for *fixture*."""
        return self.root_path.joinpath("input", fixture.app_label, fixture.input_file)

    def get_output_file(self, fixture: FixtureDefinition) -> Path:
        """Return the generated JSON output path for *fixture*."""
        return self.root_path.joinpath("output", fixture.app_label, fixture.output_file)


class FixtureManager:
    """Generate Django JSON fixtures from configured Excel workbooks."""

    __slots__ = ("config",)

    def __init__(self, config: FixtureManagerConfig) -> None:
        self.config = config

    def prepare_fixtures(self) -> "FixtureManager":
        """Read all configured workbooks and write JSON fixture files."""
        for fixture in self.config.fixtures:
            workbook = ExcelAdapter.read_dataframe(self.config.get_input_file(fixture))
            self._validate_fixture_data(fixture, workbook)
            output = [
                {
                    "model": f"{fixture.app_label}.{fixture.model}",
                    "pk": index,
                    "fields": self._build_fields(fixture, workbook, row),
                }
                for index, (_, row) in enumerate(
                    workbook[fixture.model].iterrows(), start=1
                )
            ]
            JsonUtils.write_file(output, self.config.get_output_file(fixture))

        return self

    def load_data(self, fixture_models: list[str] | None = None) -> None:
        """Load generated fixture JSON files with Django's ``loaddata`` command."""
        fixture_filter = set(fixture_models or [])
        load_all = not fixture_filter or fixture_filter == {"ALL"}

        settings_module = self.config.settings_module
        AppException.check(
            settings_module,
            "FixtureManagerConfig.settings_module is required to load fixtures",
        )
        configured_settings_module = cast(str, settings_module)

        import os

        import django
        from django.core import management

        if not _has_settings_module():
            os.environ["DJANGO_SETTINGS_MODULE"] = configured_settings_module
        django.setup()

        for fixture in self.config.fixtures:
            model_label = f"{fixture.app_label}.{fixture.model}"
            if not load_all and model_label not in fixture_filter:
                continue
            call_command = cast(Any, management).call_command
            call_command("loaddata", str(self.config.get_output_file(fixture)))

    def _validate_fixture_data(
        self,
        fixture: FixtureDefinition,
        workbook: dict[str, pandas.DataFrame],
    ) -> None:
        AppException.check(
            fixture.model in workbook,
            "Worksheet not found for fixture model: {}",
            fixture.model,
        )

        input_frame = workbook[fixture.model]
        configured_columns = {column.name: column.type for column in fixture.columns}

        for column in fixture.columns:
            if column.type is not ColumnType.MANY_TO_MANY:
                AppException.check(
                    column.name in input_frame.columns,
                    "Column '{}' not present in worksheet '{}'",
                    column.name,
                    fixture.model,
                )
                continue

            AppException.check(
                column.name in workbook,
                "Worksheet missing for many-to-many column: {}",
                column.name,
            )
            AppException.check(
                fixture.key_columns,
                "key_columns is required for many-to-many column: {}",
                column.name,
            )

            m2m_frame = workbook[column.name]
            for key_column in fixture.key_columns:
                AppException.check(
                    key_column in configured_columns,
                    "key_columns contains unknown column: {}",
                    key_column,
                )
                AppException.check(
                    key_column in m2m_frame.columns,
                    "Worksheet '{}' is missing key column '{}'",
                    column.name,
                    key_column,
                )
            AppException.check(
                column.name in m2m_frame.columns,
                "Worksheet '{}' is missing relation column '{}'",
                column.name,
                column.name,
            )

    def _build_fields(
        self,
        fixture: FixtureDefinition,
        workbook: dict[str, pandas.DataFrame],
        row: pandas.Series,
    ) -> dict[str, Any]:
        fields = {
            column.name: self._get_field_value(fixture, workbook, column, row)
            for column in fixture.columns
        }
        fields.update(fixture.common_fields)
        return fields

    def _get_field_value(
        self,
        fixture: FixtureDefinition,
        workbook: dict[str, pandas.DataFrame],
        column: FixtureColumn,
        row: pandas.Series,
    ) -> Any:
        if column.type is ColumnType.MANY_TO_MANY:
            return self._get_many_to_many_values(
                fixture,
                workbook[column.name],
                column,
                row,
            )

        raw_value = PandasUtils.get_field(row, column.name, required=column.required)

        if raw_value is None:
            return None if column.type is not ColumnType.STRING else ""
        if column.type is ColumnType.BOOLEAN:
            return AppUtils.parse_bool(raw_value)
        if column.type is ColumnType.INTEGER:
            return int(raw_value)
        if column.type is ColumnType.DECIMAL:
            return str(raw_value)
        if column.type is ColumnType.DATE:
            return (
                raw_value.strftime("%Y-%m-%d")
                if hasattr(raw_value, "strftime")
                else str(raw_value)
            )
        if column.type is ColumnType.FOREIGN_KEY:
            return [str(raw_value)]
        return str(raw_value).strip()

    def _get_many_to_many_values(
        self,
        fixture: FixtureDefinition,
        relation_frame: pandas.DataFrame,
        column: FixtureColumn,
        row: pandas.Series,
    ) -> list[list[str]]:
        filtered: pandas.DataFrame = relation_frame
        for key_column in fixture.key_columns:
            row_value = cast(object, cast(Any, row).get(key_column))
            filtered = cast(
                pandas.DataFrame,
                filtered[cast(object, filtered[key_column] == row_value)],
            )

        values: list[list[str]] = []
        raw_values = cast(
            list[object],
            cast(Any, filtered[column.name]).tolist(),
        )
        for value in raw_values:
            if PandasUtils.is_na(value):
                continue
            values.append([str(value)])
        return values


def _has_settings_module() -> bool:
    import os

    return bool(os.environ.get("DJANGO_SETTINGS_MODULE"))
