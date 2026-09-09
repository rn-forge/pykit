"""Tests for rn_forge.commons.plugins."""

from __future__ import annotations

import rn_forge.commons.plugins as plugins_module
from rn_forge.commons.plugins import EntryPointLoader, PluginError


class Base:
    pass


class GoodPluginClass(Base):
    pass


good_plugin_instance = GoodPluginClass()


def broken_plugin_factory() -> Base:
    raise RuntimeError("boom")


class WrongTypePlugin:
    pass


class _FakeEntryPoint:
    def __init__(self, name: str, target: object) -> None:
        self.name = name
        self.value = f"fake:{name}"
        self._target = target

    def load(self) -> object:
        return self._target


class TestEntryPointLoader:
    def test_loads_class_by_instantiating(self, monkeypatch):
        monkeypatch.setattr(
            plugins_module,
            "entry_points",
            lambda group: [_FakeEntryPoint("good", GoodPluginClass)],
        )
        loader = EntryPointLoader("test.plugins", expected_type=Base)
        plugins, errors = loader.load()
        assert len(plugins) == 1
        assert isinstance(plugins[0], GoodPluginClass)
        assert errors == []

    def test_loads_already_constructed_instance(self, monkeypatch):
        monkeypatch.setattr(
            plugins_module,
            "entry_points",
            lambda group: [_FakeEntryPoint("good", good_plugin_instance)],
        )
        loader = EntryPointLoader("test.plugins", expected_type=Base)
        plugins, errors = loader.load()
        assert plugins == [good_plugin_instance]
        assert errors == []

    def test_broken_plugin_isolated_as_error(self, monkeypatch):
        monkeypatch.setattr(
            plugins_module,
            "entry_points",
            lambda group: [
                _FakeEntryPoint("broken", broken_plugin_factory),
                _FakeEntryPoint("good", GoodPluginClass),
            ],
        )
        loader = EntryPointLoader("test.plugins", expected_type=Base)
        plugins, errors = loader.load()
        assert len(plugins) == 1
        assert isinstance(plugins[0], GoodPluginClass)
        assert len(errors) == 1
        assert errors[0].entry_point == "broken"
        assert "RuntimeError" in errors[0].reason

    def test_wrong_type_recorded_as_error(self, monkeypatch):
        monkeypatch.setattr(
            plugins_module,
            "entry_points",
            lambda group: [_FakeEntryPoint("wrong", WrongTypePlugin)],
        )
        loader = EntryPointLoader("test.plugins", expected_type=Base)
        plugins, errors = loader.load()
        assert plugins == []
        assert len(errors) == 1

    def test_sorted_by_name(self, monkeypatch):
        monkeypatch.setattr(
            plugins_module,
            "entry_points",
            lambda group: [
                _FakeEntryPoint("zebra", GoodPluginClass),
                _FakeEntryPoint("alpha", GoodPluginClass),
            ],
        )
        loader = EntryPointLoader("test.plugins", expected_type=Base)
        loader.load()
        # Cache holds insertion order, which must be sorted by entry-point name.
        # We can't directly inspect names post-instantiation, so verify via a
        # loader that records names through a wrapping factory.
        seen: list[str] = []

        class Recording(Base):
            def __init__(self, name: str) -> None:
                seen.append(name)

        monkeypatch.setattr(
            plugins_module,
            "entry_points",
            lambda group: [
                _FakeEntryPoint("zebra", lambda: Recording("zebra")),
                _FakeEntryPoint("alpha", lambda: Recording("alpha")),
            ],
        )
        loader2 = EntryPointLoader("test.plugins", expected_type=Base)
        loader2.load()
        assert seen == ["alpha", "zebra"]

    def test_caches_until_refresh(self, monkeypatch):
        calls = {"n": 0}

        def fake_entry_points(group):
            calls["n"] += 1
            return [_FakeEntryPoint("good", GoodPluginClass)]

        monkeypatch.setattr(plugins_module, "entry_points", fake_entry_points)
        loader = EntryPointLoader("test.plugins", expected_type=Base)
        loader.load()
        loader.load()
        assert calls["n"] == 1
        loader.load(refresh=True)
        assert calls["n"] == 2

    def test_plugin_error_is_dataclass_mixin(self):
        err = PluginError(entry_point="x", reason="y")
        assert err.as_dict() == {"entry_point": "x", "reason": "y"}
