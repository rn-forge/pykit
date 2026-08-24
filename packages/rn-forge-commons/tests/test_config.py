"""Tests for rn_forge.commons.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rn_forge.commons.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def yaml_file(tmp_path: Path) -> Path:
    p = tmp_path / "app.yaml"
    p.write_text(
        """\
database:
  host: localhost
  port: 5432
  name: mydb
app:
  name: test-app
  debug: true
  tags:
    - web
    - api
"""
    )
    return p


@pytest.fixture
def json_file(tmp_path: Path) -> Path:
    p = tmp_path / "app.json"
    p.write_text(
        json.dumps(
            {
                "database": {"host": "localhost", "port": 5432},
                "app": {"name": "json-app"},
            }
        )
    )
    return p


@pytest.fixture
def yaml_dir(tmp_path: Path) -> Path:
    """Directory with two YAML files that get merged."""
    (tmp_path / "01_base.yaml").write_text(
        """\
database:
  host: localhost
  port: 5432
app:
  name: base-app
"""
    )
    (tmp_path / "02_override.yaml").write_text(
        """\
database:
  port: 3306
  name: overridden
app:
  debug: true
"""
    )
    return tmp_path


@pytest.fixture
def refs_yaml(tmp_path: Path) -> Path:
    """YAML with various reference types."""
    p = tmp_path / "refs.yaml"
    p.write_text(
        """\
defaults:
  timeout: 30
  retries: 3
  hosts:
    - host-a
    - host-b

service_a:
  timeout: "${defaults.timeout}"
  name: service-a

service_b:
  url: "https://${defaults.hosts.0}:8080/${service_a.name}"
"""
    )
    return p


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------


class TestLoading:
    def test_load_yaml_file(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        assert cfg.get("database.host") == "localhost"
        assert cfg.get("database.port") == 5432
        assert cfg.get("app.name") == "test-app"

    def test_load_json_file(self, json_file: Path) -> None:
        cfg = Config(json_file, config_type="json")
        assert cfg.get("database.host") == "localhost"
        assert cfg.get("app.name") == "json-app"

    def test_load_directory_merges_sorted(self, yaml_dir: Path) -> None:
        cfg = Config(yaml_dir, resolve=False)
        # 02_override.yaml overrides port and adds name
        assert cfg.get("database.port") == 3306
        assert cfg.get("database.name") == "overridden"
        # base values preserved
        assert cfg.get("database.host") == "localhost"
        # merged from override
        assert cfg.get("app.debug") is True
        # base value preserved
        assert cfg.get("app.name") == "base-app"

    def test_path_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            Config(tmp_path / "nonexistent.yaml")

    def test_path_segments_joined(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "cfg.yaml"
        f.write_text("key: value\n")
        cfg = Config(tmp_path, "sub", "cfg.yaml")
        assert cfg.get("key") == "value"

    def test_load_without_resolve(self, refs_yaml: Path) -> None:
        cfg = Config(refs_yaml, resolve=False)
        # raw reference strings preserved
        assert cfg.get("service_a.timeout") == "${defaults.timeout}"

    def test_as_dict_returns_defensive_copy(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        data = cfg.as_dict()
        data["database"]["host"] = "changed"
        assert cfg.get("database.host") == "localhost"


# ---------------------------------------------------------------------------
# Reference resolution tests — ${} value interpolation
# ---------------------------------------------------------------------------


class TestValueReferences:
    def test_simple_value_ref(self, refs_yaml: Path) -> None:
        cfg = Config(refs_yaml)
        assert cfg.get("service_a.timeout") == 30

    def test_partial_string_interpolation(self, refs_yaml: Path) -> None:
        cfg = Config(refs_yaml)
        assert cfg.get("service_b.url") == "https://host-a:8080/service-a"

    def test_preserves_type_on_full_ref(self, tmp_path: Path) -> None:
        """A full ${} ref to a non-string preserves the original type."""
        (tmp_path / "t.yaml").write_text(
            "source:\n  count: 42\ntarget:\n  count: '${source.count}'\n"
        )
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("target.count") == 42
        assert isinstance(cfg.get("target.count"), int)

    def test_unresolvable_ref_left_as_is(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text("val: '${no.such.path}'\n")
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("val") == "${no.such.path}"

    def test_nested_value_refs(self, tmp_path: Path) -> None:
        """${} inside another ${} path — resolved iteratively."""
        (tmp_path / "t.yaml").write_text(
            """\
lookup:
  key: target
target:
  value: resolved
result: "${${lookup.key}.value}"
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("result") == "resolved"

    def test_ref_to_list_preserves_list(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            "source:\n  items:\n    - a\n    - b\ntarget: '${source.items}'\n"
        )
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("target") == ["a", "b"]


# ---------------------------------------------------------------------------
# Reference resolution tests — @{} dict refs
# ---------------------------------------------------------------------------


class TestDictReferences:
    def test_at_ref_resolves_dict(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            """\
defaults:
  timeout: 30
  retries: 3
service: "@{defaults}"
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        svc = cfg.get("service")
        assert isinstance(svc, dict)
        assert svc["timeout"] == 30

    def test_unresolvable_at_ref(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text('val: "@{missing}"\n')
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("val") == "@{missing}"


# ---------------------------------------------------------------------------
# Reference resolution tests — #{} list refs
# ---------------------------------------------------------------------------


class TestListReferences:
    def test_hash_ref_flattens_into_list(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            """\
common_tags:
  - shared-a
  - shared-b
service:
  tags:
    - own-tag
    - "#{common_tags}"
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("service.tags") == ["own-tag", "shared-a", "shared-b"]

    def test_hash_ref_non_list_appended(self, tmp_path: Path) -> None:
        """#{} pointing to a non-list is appended, not flattened."""
        (tmp_path / "t.yaml").write_text("scalar: hello\nitems:\n  - '#{scalar}'\n")
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("items") == ["hello"]

    def test_unresolvable_hash_ref(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text("items:\n  - '#{missing}'\n")
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("items") == ["#{missing}"]


# ---------------------------------------------------------------------------
# __extends__ tests
# ---------------------------------------------------------------------------


class TestExtends:
    def test_extends_inherits_parent(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            """\
base:
  timeout: 30
  retries: 3
  name: base-service
derived:
  __extends__: "@{base}"
  name: derived-service
  extra: true
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        d = cfg.get("derived")
        assert d["timeout"] == 30  # inherited
        assert d["retries"] == 3  # inherited
        assert d["name"] == "derived-service"  # overridden
        assert d["extra"] is True  # new

    def test_extends_non_dict_raises(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            "scalar: hello\nderived:\n  __extends__: '${scalar}'\n  key: val\n"
        )
        with pytest.raises(TypeError, match="must resolve to a dict"):
            Config(tmp_path / "t.yaml")


# ---------------------------------------------------------------------------
# Depth / recursion tests
# ---------------------------------------------------------------------------


class TestDepthProtection:
    def test_circular_ref_raises(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text("a: '${b}'\nb: '${a}'\n")
        with pytest.raises(RecursionError, match="max depth"):
            Config(tmp_path / "t.yaml")


# ---------------------------------------------------------------------------
# Dunder protocol tests
# ---------------------------------------------------------------------------


class TestProtocols:
    def test_getitem(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        assert cfg["app"]["name"] == "test-app"

    def test_contains(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        assert "database" in cfg
        assert "nonexistent" not in cfg

    def test_iter(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        assert set(cfg) == {"database", "app"}

    def test_len(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        assert len(cfg) == 2

    def test_repr(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        r = repr(cfg)
        assert r.startswith("Config(")

    def test_as_dict(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        d = cfg.as_dict()
        assert isinstance(d, dict)
        assert d["database"]["host"] == "localhost"


# ---------------------------------------------------------------------------
# set / get tests
# ---------------------------------------------------------------------------


class TestGetSet:
    def test_get_default(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        assert cfg.get("no.such.key", default="fallback") == "fallback"

    def test_set_and_get(self, yaml_file: Path) -> None:
        cfg = Config(yaml_file)
        cfg.set("database.pool_size", 10)
        assert cfg.get("database.pool_size") == 10

    def test_re_resolve_after_mutation(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text("base:\n  x: 1\nref: '${base.x}'\n")
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("ref") == 1
        # mutate and re-resolve
        cfg.set("base.x", 99)
        cfg.set("ref", "${base.x}")
        cfg.resolve_references()
        assert cfg.get("ref") == 99


# ---------------------------------------------------------------------------
# Mixed / complex scenarios
# ---------------------------------------------------------------------------


class TestComplexScenarios:
    def test_list_of_dicts_with_refs(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            """\
defaults:
  port: 8080
services:
  - name: svc-a
    port: "${defaults.port}"
  - name: svc-b
    port: 9090
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        services = cfg.get("services")
        assert services[0]["port"] == 8080
        assert services[1]["port"] == 9090

    def test_nested_list_in_dict_ref(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            """\
shared:
  envs:
    - dev
    - staging
app:
  environments: "${shared.envs}"
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("app.environments") == ["dev", "staging"]

    def test_deeply_nested_extends(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            """\
level0:
  a: 1
  b: 2
level1:
  __extends__: "@{level0}"
  b: 20
  c: 30
level2:
  __extends__: "@{level1}"
  c: 300
  d: 400
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        d = cfg.get("level2")
        assert d == {"a": 1, "b": 20, "c": 300, "d": 400}

    def test_json_directory_loading(self, tmp_path: Path) -> None:
        (tmp_path / "01.json").write_text(json.dumps({"a": 1, "b": 2}))
        (tmp_path / "02.json").write_text(json.dumps({"b": 20, "c": 30}))
        cfg = Config(tmp_path, config_type="json", resolve=False)
        assert cfg.get("a") == 1
        assert cfg.get("b") == 20
        assert cfg.get("c") == 30

    def test_bool_and_null_values_untouched(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text("flag: true\nnothing: null\ncount: 0\n")
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("flag") is True
        assert cfg.get("nothing") is None
        assert cfg.get("count") == 0

    def test_nested_list_resolved(self, tmp_path: Path) -> None:
        (tmp_path / "t.yaml").write_text(
            """\
matrix:
  - - "${val}"
    - b
  - - c
    - d
val: resolved
"""
        )
        cfg = Config(tmp_path / "t.yaml")
        assert cfg.get("matrix") == [["resolved", "b"], ["c", "d"]]
