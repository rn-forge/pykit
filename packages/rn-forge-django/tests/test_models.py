"""Tests for rn_forge.django.models."""

from __future__ import annotations

from datetime import date, timedelta
from operator import attrgetter

import pytest
from django.core.exceptions import ValidationError
from django.db import connection, models

from rn_forge.django.models import (
    BaseModel,
    DateRangeModel,
    FixtureModelMixin,
    ModelLookupCache,
    NaturalKeyLookupManager,
)
from rn_forge.django.models import Status


# ---------------------------------------------------------------------------
# Concrete models used throughout the tests
# ---------------------------------------------------------------------------


class Widget(BaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)

    objects = NaturalKeyLookupManager()

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"

    @classmethod
    def natural_keys(cls) -> list[str]:
        return ["code"]


class Campaign(DateRangeModel):
    title = models.CharField(max_length=200)

    class Meta(DateRangeModel.Meta):
        app_label = "rn_forge_django"

    @classmethod
    def natural_keys(cls) -> list[str]:
        return ["title"]


class StrictWidget(BaseModel):
    validate_on_save = True

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)

    objects = NaturalKeyLookupManager()

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django"

    @classmethod
    def natural_keys(cls) -> list[str]:
        return ["code"]


def _create_tables() -> None:
    """Create in-memory tables for our test models."""
    with connection.schema_editor() as editor:
        try:
            editor.create_model(Widget)
        except Exception:
            pass
        try:
            editor.create_model(Campaign)
        except Exception:
            pass
        try:
            editor.create_model(StrictWidget)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# FixtureModelMixin
# ---------------------------------------------------------------------------


class TestFixtureModelMixin:
    def test_natural_keys_raises_not_implemented_on_base(self) -> None:
        class Bare(FixtureModelMixin):
            pass

        with pytest.raises(NotImplementedError):
            Bare.natural_keys()

    def test_concrete_subclass_can_provide_natural_keys(self) -> None:
        class Concrete(FixtureModelMixin):
            @classmethod
            def natural_keys(cls) -> list[str]:
                return ["sku"]

        assert Concrete.natural_keys() == ["sku"]


TestFixtureModelMixin = pytest.mark.unit(TestFixtureModelMixin)


# ---------------------------------------------------------------------------
# DateRangeModel.is_date_range_active (no DB needed)
# ---------------------------------------------------------------------------


class TestIsDateRangeActive:
    def _campaign(self, start: date, end: date | None) -> Campaign:
        c = Campaign.__new__(Campaign)
        c.start_date = start
        c.end_date = end
        return c

    def test_active_when_today_in_range(self) -> None:
        today = date.today()
        c = self._campaign(today - timedelta(days=1), today + timedelta(days=1))
        assert c.is_date_range_active is True

    def test_active_on_start_date(self) -> None:
        today = date.today()
        c = self._campaign(today, today + timedelta(days=5))
        assert c.is_date_range_active is True

    def test_active_on_end_date(self) -> None:
        today = date.today()
        c = self._campaign(today - timedelta(days=5), today)
        assert c.is_date_range_active is True

    def test_inactive_before_start(self) -> None:
        tomorrow = date.today() + timedelta(days=1)
        c = self._campaign(tomorrow, tomorrow + timedelta(days=5))
        assert c.is_date_range_active is False

    def test_inactive_after_end(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        c = self._campaign(yesterday - timedelta(days=5), yesterday)
        assert c.is_date_range_active is False

    def test_open_ended_range_is_active(self) -> None:
        past = date.today() - timedelta(days=10)
        c = self._campaign(past, None)
        assert c.is_date_range_active is True

    def test_open_ended_future_start_is_inactive(self) -> None:
        future = date.today() + timedelta(days=1)
        c = self._campaign(future, None)
        assert c.is_date_range_active is False


TestIsDateRangeActive = pytest.mark.unit(TestIsDateRangeActive)


# ---------------------------------------------------------------------------
# BaseModel.get_attrs (no DB needed)
# ---------------------------------------------------------------------------


class TestGetAttrs:
    def _widget(self, name: str, code: str) -> Widget:
        w = Widget.__new__(Widget)
        w.name = name
        w.code = code
        return w

    def test_single_attr_returns_tuple(self) -> None:
        w = self._widget("Sprocket", "SPR-1")
        result = w.get_attrs(attrgetter("name"))
        assert result == ("Sprocket",)

    def test_multiple_attrs_returns_tuple(self) -> None:
        w = self._widget("Sprocket", "SPR-1")
        result = w.get_attrs(attrgetter("name", "code"))
        assert result == ("Sprocket", "SPR-1")

    def test_natural_key_returns_instance_values(self) -> None:
        w = self._widget("Sprocket", "SPR-1")
        assert w.natural_key() == ("SPR-1",)


TestGetAttrs = pytest.mark.unit(TestGetAttrs)


# ---------------------------------------------------------------------------
# ModelLookupCache (no DB needed for get/set)
# ---------------------------------------------------------------------------


class _FakeModel:
    """Stand-in model for cache tests that don't need a real DB."""

    __name__ = "FakeModel"

    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class _FakeModelClass:
    __name__ = "FakeModel"


class TestModelLookupCacheWithoutDb:
    def _make_cache(self) -> ModelLookupCache:
        return ModelLookupCache()

    def test_get_returns_none_for_unknown_model(self) -> None:
        cache = self._make_cache()
        result = cache.get(_FakeModelClass, "x")  # type: ignore[arg-type]
        assert result is None

    def test_get_returns_none_for_missing_key(self) -> None:
        cache = self._make_cache()
        obj = _FakeModel("k", "v")
        cache.set(_FakeModelClass, obj, "key")  # type: ignore[arg-type]
        assert cache.get(_FakeModelClass, "missing") is None  # type: ignore[arg-type]

    def test_set_then_get_single_key(self) -> None:
        cache = self._make_cache()
        obj = _FakeModel("abc", "hello")
        cache.set(_FakeModelClass, obj, "key")  # type: ignore[arg-type]
        assert cache.get(_FakeModelClass, "abc") is obj  # type: ignore[arg-type]

    def test_set_then_get_composite_key(self) -> None:
        cache = self._make_cache()

        class TwoKey:
            __name__ = "TwoKey"

            def __init__(self, a: str, b: str) -> None:
                self.a = a
                self.b = b

        cls = TwoKey
        obj = cls("x", "y")
        cache.set(cls, obj, "a", "b")  # type: ignore[arg-type]
        assert cache.get(cls, "x", "y") is obj  # type: ignore[arg-type]

    def test_set_overwrites_existing_entry(self) -> None:
        cache = self._make_cache()
        obj1 = _FakeModel("k", "first")
        obj2 = _FakeModel("k", "second")
        cache.set(_FakeModelClass, obj1, "key")  # type: ignore[arg-type]
        cache.set(_FakeModelClass, obj2, "key")  # type: ignore[arg-type]
        assert cache.get(_FakeModelClass, "k") is obj2  # type: ignore[arg-type]

    def test_different_model_classes_are_isolated(self) -> None:
        cache = self._make_cache()

        class A:
            __name__ = "A"

            key = "same"

        class B:
            __name__ = "B"

            key = "same"

        obj_a = A()
        obj_b = B()
        cache.set(A, obj_a, "key")  # type: ignore[arg-type]
        cache.set(B, obj_b, "key")  # type: ignore[arg-type]
        assert cache.get(A, "same") is obj_a  # type: ignore[arg-type]
        assert cache.get(B, "same") is obj_b  # type: ignore[arg-type]

    def test_same_class_name_different_modules_are_isolated(self) -> None:
        cache = self._make_cache()

        SharedA = type("Shared", (), {"__module__": "pkg_a"})
        SharedB = type("Shared", (), {"__module__": "pkg_b"})

        obj_a = SharedA()
        obj_b = SharedB()
        obj_a.key = "same"
        obj_b.key = "same"

        cache.set(SharedA, obj_a, "key")  # type: ignore[arg-type]
        cache.set(SharedB, obj_b, "key")  # type: ignore[arg-type]

        assert cache.get(SharedA, "same") is obj_a  # type: ignore[arg-type]
        assert cache.get(SharedB, "same") is obj_b  # type: ignore[arg-type]


TestModelLookupCacheWithoutDb = pytest.mark.unit(TestModelLookupCacheWithoutDb)


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _django_tables(django_db_setup, django_db_blocker):  # noqa: PT004
    """Create Widget and Campaign tables for this module."""
    with django_db_blocker.unblock():
        _create_tables()


@pytest.mark.integration
@pytest.mark.django_db
class TestNaturalKeyLookupManager:
    def _make_widget(self, name: str, code: str) -> Widget:
        return Widget.objects.create(
            name=name,
            code=code,
            created_by="test",
            updated_by="test",
        )

    def test_get_by_natural_key_returns_correct_instance(self) -> None:
        w = self._make_widget("Bolt", "BOLT-1")
        found = Widget.objects.get_by_natural_key("BOLT-1")
        assert found.pk == w.pk

    def test_get_by_natural_key_wrong_count_raises_runtime_error(self) -> None:
        with pytest.raises(RuntimeError, match="Incorrect natural keys"):
            Widget.objects.get_by_natural_key("a", "b")  # expects 1, got 2

    def test_get_by_natural_key_missing_raises_does_not_exist(self) -> None:
        from django.core.exceptions import ObjectDoesNotExist

        with pytest.raises(ObjectDoesNotExist):
            Widget.objects.get_by_natural_key("NONEXISTENT")


@pytest.mark.django_db
class TestTruncateModelMixin:
    def test_truncate_clears_all_rows(self) -> None:
        Widget.objects.create(name="A", code="A1", created_by="t", updated_by="t")
        Widget.objects.create(name="B", code="B1", created_by="t", updated_by="t")
        assert Widget.objects.count() >= 2
        Widget.truncate()
        assert Widget.objects.count() == 0

    def test_truncate_uses_quoted_table_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def execute(self, sql: str) -> None:
                calls.append(sql)

        monkeypatch.setattr(connection.ops, "quote_name", lambda name: f'"{name}"')
        monkeypatch.setattr(connection, "cursor", lambda: FakeCursor())

        Widget.truncate()

        assert calls == ['DELETE FROM "rn_forge_django_widget"']


@pytest.mark.django_db
class TestBaseModelFields:
    def test_default_status_is_active(self) -> None:
        w = Widget.objects.create(name="X", code="X1", created_by="u", updated_by="u")
        assert w.status == Status.Active

    def test_created_at_auto_populated(self) -> None:
        w = Widget.objects.create(name="Y", code="Y1", created_by="u", updated_by="u")
        assert w.created_at is not None

    def test_updated_at_auto_populated(self) -> None:
        w = Widget.objects.create(name="Z", code="Z1", created_by="u", updated_by="u")
        assert w.updated_at is not None

    def test_status_can_be_set_to_inactive(self) -> None:
        w = Widget.objects.create(
            name="Q", code="Q1", created_by="u", updated_by="u", status=Status.Inactive
        )
        assert w.status == Status.Inactive

    def test_default_save_does_not_run_full_clean(self) -> None:
        widget = Widget(name="x" * 101, code="TOO-LONG", created_by="u", updated_by="u")
        widget.save()
        assert widget.pk is not None

    def test_opt_in_save_runs_full_clean(self) -> None:
        widget = StrictWidget(
            name="x" * 101, code="TOO-LONG", created_by="u", updated_by="u"
        )
        with pytest.raises(ValidationError):
            widget.save()

    def test_opt_in_save_respects_update_fields(self) -> None:
        widget = StrictWidget.objects.create(
            name="Valid",
            code="SW1",
            created_by="u",
            updated_by="u",
        )
        widget.name = "x" * 101
        widget.status = Status.Inactive
        widget.save(update_fields=["status"])

        refreshed = StrictWidget.objects.get(pk=widget.pk)
        assert refreshed.status == Status.Inactive


@pytest.mark.django_db
class TestModelLookupCacheWithDb:
    def test_load_and_get(self) -> None:
        Widget.objects.create(name="Gear", code="G1", created_by="u", updated_by="u")
        cache = ModelLookupCache()
        cache.load(Widget, "code")
        result = cache.get(Widget, "G1")
        assert result is not None
        assert result.code == "G1"

    def test_load_composite_key(self) -> None:
        Widget.objects.create(name="Spring", code="SP1", created_by="u", updated_by="u")
        cache = ModelLookupCache()
        cache.load(Widget, "name", "code")
        result = cache.get(Widget, "Spring", "SP1")
        assert result is not None
        assert result.name == "Spring"

    def test_get_returns_none_after_load_for_missing_key(self) -> None:
        cache = ModelLookupCache()
        cache.load(Widget, "code")
        assert cache.get(Widget, "DOES_NOT_EXIST") is None
