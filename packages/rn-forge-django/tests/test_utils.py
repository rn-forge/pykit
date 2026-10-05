"""Tests for rn_forge.django.utils."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.test import override_settings

from rn_forge.django.models import BaseModel, ModelUtils, NaturalKeyLookupManager
from rn_forge.django.utils import require_environment, require_settings


# ---------------------------------------------------------------------------
# Concrete model for ModelUtils tests
# ---------------------------------------------------------------------------


class Article(BaseModel):
    title = models.CharField(max_length=200)
    body = models.TextField(default="")

    objects = NaturalKeyLookupManager()

    class Meta:
        app_label = "rn_forge_django"

    @classmethod
    def natural_keys(cls) -> list[str]:
        return ["title"]


@pytest.fixture(scope="module", autouse=True)
def _django_tables(create_tables):  # noqa: PT004
    create_tables(Article)


# ---------------------------------------------------------------------------
# ModelUtils.as_json_value
# ---------------------------------------------------------------------------


class TestAsJsonValue:
    def test_str_passthrough(self) -> None:
        assert ModelUtils.as_json_value("hello") == "hello"

    def test_int_passthrough(self) -> None:
        assert ModelUtils.as_json_value(42) == 42

    def test_float_passthrough(self) -> None:
        assert ModelUtils.as_json_value(3.14) == 3.14

    def test_bool_passthrough(self) -> None:
        assert ModelUtils.as_json_value(True) is True

    def test_none_passthrough(self) -> None:
        assert ModelUtils.as_json_value(None) is None

    def test_date_to_isoformat(self) -> None:
        d = date(2024, 6, 15)
        assert ModelUtils.as_json_value(d) == "2024-06-15"

    def test_datetime_to_isoformat(self) -> None:
        dt = datetime(2024, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        assert ModelUtils.as_json_value(dt) == "2024-06-15T12:30:00+00:00"

    def test_time_to_isoformat(self) -> None:
        t = time(9, 45, 30)
        assert ModelUtils.as_json_value(t) == "09:45:30"

    def test_unknown_type_falls_back_to_str(self) -> None:
        class Obj:
            def __str__(self) -> str:
                return "custom"

        assert ModelUtils.as_json_value(Obj()) == "custom"

    def test_list_falls_back_to_str(self) -> None:
        result = ModelUtils.as_json_value([1, 2, 3])
        assert result == "[1, 2, 3]"


TestAsJsonValue = pytest.mark.unit(TestAsJsonValue)


# ---------------------------------------------------------------------------
# ModelUtils.as_dict
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.django_db
class TestAsDict:
    def _article(self, title: str) -> Article:
        return Article.objects.create(
            title=title,
            body="Some text",
            created_by="tester",
            updated_by="tester",
        )

    def test_returns_dict(self) -> None:
        a = self._article("Intro to Django")
        result = ModelUtils.as_dict(a)
        assert isinstance(result, dict)

    def test_contains_all_concrete_fields(self) -> None:
        a = self._article("Field Coverage")
        result = ModelUtils.as_dict(a)
        field_names = {f.name for f in a._meta.concrete_fields}
        assert set(result.keys()) == field_names

    def test_string_field_value(self) -> None:
        a = self._article("String Field")
        result = ModelUtils.as_dict(a)
        assert result["title"] == "String Field"

    def test_datetime_field_is_isoformat_string(self) -> None:
        a = self._article("Datetime Field")
        result = ModelUtils.as_dict(a)
        # create_time is a DateTimeField; as_dict should return ISO string
        assert isinstance(result["create_time"], str)

    def test_seen_set_prevents_mutation_of_caller_set(self) -> None:
        # Calling without _seen should work cleanly
        a = self._article("Seen Set")
        result1 = ModelUtils.as_dict(a)
        result2 = ModelUtils.as_dict(a)
        assert result1 == result2

    def test_fresh_seen_set_per_call(self) -> None:
        a = self._article("Fresh Seen")
        # Two separate calls must both succeed (no leftover _seen state)
        r1 = ModelUtils.as_dict(a)
        r2 = ModelUtils.as_dict(a)
        assert r1["id"] == r2["id"]


# ---------------------------------------------------------------------------
# ModelUtils.to_json
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.django_db
class TestToJson:
    def _article(self, title: str) -> Article:
        return Article.objects.create(
            title=title,
            body="body",
            created_by="u",
            updated_by="u",
        )

    def test_returns_valid_json_string(self) -> None:
        a = self._article("JSON Output")
        raw = ModelUtils.to_json(a)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_json_contains_title(self) -> None:
        a = self._article("Title In JSON")
        parsed = json.loads(ModelUtils.to_json(a))
        assert parsed["title"] == "Title In JSON"

    def test_compact_by_default(self) -> None:
        a = self._article("Compact JSON")
        raw = ModelUtils.to_json(a)
        # No leading whitespace / newlines in compact output
        assert "\n" not in raw

    def test_indent_produces_pretty_output(self) -> None:
        a = self._article("Pretty JSON")
        raw = ModelUtils.to_json(a, indent=2)
        assert "\n" in raw
        parsed = json.loads(raw)
        assert parsed["title"] == "Pretty JSON"

    def test_round_trip_preserves_all_fields(self) -> None:
        a = self._article("Round Trip")
        d = ModelUtils.as_dict(a)
        parsed = json.loads(ModelUtils.to_json(a))
        assert set(parsed.keys()) == set(d.keys())


@pytest.mark.unit
class TestRequireSettings:
    def test_passes_when_every_setting_is_present(self) -> None:
        with override_settings(RNF_ONE="a", RNF_TWO="b"):
            require_settings("RNF_ONE", "RNF_TWO")

    def test_names_every_missing_or_blank_setting_at_once(self) -> None:
        with override_settings(RNF_BLANK="  "):
            with pytest.raises(ImproperlyConfigured) as caught:
                require_settings("RNF_BLANK", "RNF_ABSENT", "DATABASES")
        message = str(caught.value)
        assert "RNF_ABSENT" in message
        assert "RNF_BLANK" in message
        assert "DATABASES" not in message


@pytest.mark.unit
class TestRequireEnvironment:
    def test_returns_the_values(self, monkeypatch) -> None:
        monkeypatch.setenv("RNF_DB_URL", "sqlite://")
        assert require_environment("RNF_DB_URL") == {"RNF_DB_URL": "sqlite://"}

    def test_names_every_missing_variable_as_improperly_configured(
        self, monkeypatch
    ) -> None:
        monkeypatch.delenv("RNF_MISSING_A", raising=False)
        monkeypatch.setenv("RNF_MISSING_B", "")
        with pytest.raises(ImproperlyConfigured) as caught:
            require_environment("RNF_MISSING_A", "RNF_MISSING_B")
        assert "RNF_MISSING_A" in str(caught.value)
        assert "RNF_MISSING_B" in str(caught.value)
