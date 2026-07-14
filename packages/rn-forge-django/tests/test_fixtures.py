from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

pd = pytest.importorskip("pandas")

from rn_forge.django.fixtures import (  # noqa: E402
    ColumnType,
    FixtureColumn,
    FixtureDefinition,
    FixtureManager,
    FixtureManagerConfig,
)

pytestmark = pytest.mark.unit


def _fixture_config(root_path: Path) -> FixtureManagerConfig:
    return FixtureManagerConfig(
        root_path=root_path,
        fixtures=[
            FixtureDefinition(
                app_label="inventory",
                model="Widget",
                input_file="widgets.xlsx",
                output_file="widgets.json",
                columns=[
                    FixtureColumn("code"),
                    FixtureColumn("enabled", ColumnType.BOOLEAN),
                    FixtureColumn("released_on", ColumnType.DATE, required=False),
                    FixtureColumn("category", ColumnType.FOREIGN_KEY),
                    FixtureColumn("tags", ColumnType.MANY_TO_MANY, required=False),
                ],
                key_columns=["code"],
                common_fields={"status": "A", "created_by": "tester"},
            )
        ],
    )


class TestFixtureManager:
    def test_prepare_fixtures_writes_expected_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        manager = FixtureManager(_fixture_config(tmp_path))
        fixture = manager.config.fixtures[0]

        workbook = {
            "Widget": pd.DataFrame(
                [
                    {
                        "code": "W1",
                        "enabled": "true",
                        "released_on": pd.Timestamp("2024-06-01"),
                        "category": "hardware",
                    }
                ]
            ),
            "tags": pd.DataFrame(
                [
                    {"code": "W1", "tags": "featured"},
                    {"code": "W1", "tags": "sale"},
                ]
            ),
        }

        monkeypatch.setattr(
            "rn_forge.commons.excel.ExcelAdapter.read_dataframe",
            lambda path: workbook,
        )

        manager.prepare_fixtures()

        output = fixture.output_file
        written = manager.config.get_output_file(fixture)
        assert written.name == output
        assert written.exists()
        assert json.loads(written.read_text()) == [
            {
                "model": "inventory.Widget",
                "pk": 1,
                "fields": {
                    "code": "W1",
                    "enabled": True,
                    "released_on": "2024-06-01",
                    "category": ["hardware"],
                    "tags": [["featured"], ["sale"]],
                    "status": "A",
                    "created_by": "tester",
                },
            }
        ]

    def test_prepare_fixtures_validates_missing_sheet(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        manager = FixtureManager(_fixture_config(tmp_path))
        monkeypatch.setattr(
            "rn_forge.commons.excel.ExcelAdapter.read_dataframe",
            lambda path: {"Other": pd.DataFrame()},
        )

        with pytest.raises(Exception, match="Worksheet not found"):
            manager.prepare_fixtures()

    def test_load_data_filters_requested_models(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        calls: list[tuple[str, str]] = []
        django_module = ModuleType("django")
        django_module.setup = lambda: None  # type: ignore[attr-defined]
        management_module = ModuleType("django.core.management")

        def fake_call_command(command: str, target: str) -> None:
            calls.append((command, target))

        management_module.call_command = fake_call_command  # type: ignore[attr-defined]

        monkeypatch.setattr(
            "rn_forge.django.fixtures._has_settings_module",
            lambda: False,
        )
        import django.core as _django_core

        monkeypatch.setitem(os.environ, "DJANGO_SETTINGS_MODULE", "")
        monkeypatch.setitem(sys.modules, "django", django_module)
        monkeypatch.setitem(sys.modules, "django.core.management", management_module)
        monkeypatch.setattr(_django_core, "management", management_module)

        manager = FixtureManager(
            FixtureManagerConfig(
                root_path=tmp_path,
                settings_module="tests.settings",
                fixtures=[
                    FixtureDefinition(
                        app_label="inventory",
                        model="Widget",
                        input_file="widgets.xlsx",
                        output_file="widgets.json",
                        columns=[FixtureColumn("code")],
                    ),
                    FixtureDefinition(
                        app_label="inventory",
                        model="Category",
                        input_file="categories.xlsx",
                        output_file="categories.json",
                        columns=[FixtureColumn("name")],
                    ),
                ],
            )
        )

        manager.load_data(["inventory.Category"])

        assert calls == [
            (
                "loaddata",
                str(tmp_path / "output" / "inventory" / "categories.json"),
            )
        ]
