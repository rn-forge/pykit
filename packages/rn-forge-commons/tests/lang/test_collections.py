"""Tests for rn_forge.commons.lang.collections."""

from __future__ import annotations

import pytest

from rn_forge.commons.lang.collections import DictUtils, ListUtils


# -- DictUtils.get ---------------------------------------------------------


class TestDictGet:
    def test_simple_key(self) -> None:
        assert DictUtils.get({"a": 1}, "a") == 1

    def test_nested_key(self) -> None:
        assert DictUtils.get({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key_returns_default(self) -> None:
        assert DictUtils.get({"a": 1}, "b") is None

    def test_custom_default(self) -> None:
        assert DictUtils.get({"a": 1}, "b", default=42) == 42

    def test_empty_dict(self) -> None:
        assert DictUtils.get({}, "a") is None

    def test_empty_key_path(self) -> None:
        assert DictUtils.get({"a": 1}, "") is None

    def test_list_index(self) -> None:
        data = {"a": [10, 20, 30]}
        assert DictUtils.get(data, "a.1") == 20

    def test_list_index_out_of_bounds(self) -> None:
        assert DictUtils.get({"a": [1]}, "a.5") is None

    def test_list_non_numeric_index(self) -> None:
        assert DictUtils.get({"a": [1]}, "a.x") is None

    def test_nested_through_list(self) -> None:
        data = {"a": [{"b": "found"}]}
        assert DictUtils.get(data, "a.0.b") == "found"

    def test_escaped_dot(self) -> None:
        data = {"a.b": 1}
        assert DictUtils.get(data, r"a\.b") == 1

    def test_none_intermediate(self) -> None:
        assert DictUtils.get({"a": None}, "a.b") is None

    def test_non_dict_non_list_intermediate(self) -> None:
        assert DictUtils.get({"a": 42}, "a.b") is None


# -- DictUtils.set ---------------------------------------------------------


class TestDictSet:
    def test_simple_set(self) -> None:
        d = {}
        DictUtils.set(d, "a", 1)
        assert d == {"a": 1}

    def test_nested_set_creates_intermediates(self) -> None:
        d = {}
        DictUtils.set(d, "a.b.c", 3)
        assert d == {"a": {"b": {"c": 3}}}

    def test_set_into_existing(self) -> None:
        d = {"a": {"b": 1}}
        DictUtils.set(d, "a.c", 2)
        assert d == {"a": {"b": 1, "c": 2}}

    def test_overwrite_existing(self) -> None:
        d = {"a": {"b": 1}}
        DictUtils.set(d, "a.b", 99)
        assert d == {"a": {"b": 99}}

    def test_set_into_list(self) -> None:
        d = {"a": [10, 20, 30]}
        DictUtils.set(d, "a.1", 99)
        assert d["a"] == [10, 99, 30]

    def test_list_non_numeric_raises(self) -> None:
        d = {"a": [1, 2]}
        with pytest.raises(KeyError, match="Non-numeric"):
            DictUtils.set(d, "a.x", 5)

    def test_list_index_out_of_bounds_raises(self) -> None:
        d = {"a": [1]}
        with pytest.raises(IndexError, match="out of bounds"):
            DictUtils.set(d, "a.5", 99)

    def test_empty_key_path_noop(self) -> None:
        d = {"a": 1}
        DictUtils.set(d, "", 2)
        assert d == {"a": 1}

    def test_escaped_dot(self) -> None:
        d = {}
        DictUtils.set(d, r"a\.b", 1)
        assert d == {"a.b": 1}

    def test_non_container_intermediate_raises(self) -> None:
        d = {"a": 1}
        with pytest.raises(TypeError, match="holds non-container type"):
            DictUtils.set(d, "a.b", 2)

    def test_list_entry_non_container_tail_raises(self) -> None:
        d = {"a": [42]}
        with pytest.raises(TypeError, match="resolved to non-container type"):
            DictUtils.set(d, "a.0.b", 99)

    def test_list_intermediate_non_numeric_raises(self) -> None:
        d = {"a": [{"b": 1}]}
        with pytest.raises(KeyError, match="Non-numeric"):
            DictUtils.set(d, "a.x.b", 2)

    def test_list_intermediate_index_out_of_bounds_raises(self) -> None:
        d = {"a": [{"b": 1}]}
        with pytest.raises(IndexError, match="out of bounds"):
            DictUtils.set(d, "a.5.b", 2)

    def test_list_intermediate_non_container_raises(self) -> None:
        d = {"a": [42]}
        with pytest.raises(TypeError, match="resolved to non-container type"):
            DictUtils.set(d, "a.0.b.c", 2)


# -- DictUtils.merge -------------------------------------------------------


class TestDictMerge:
    def test_no_overrides_returns_target(self) -> None:
        target = {"a": 1}
        assert (
            DictUtils.merge(target) is target
        )  # NOSONAR: deliberately asserting identity, not equality

    def test_simple_merge(self) -> None:
        target = {"a": 1}
        result = DictUtils.merge(target, {"b": 2})
        assert result == {"a": 1, "b": 2}
        assert result is target

    def test_deep_merge(self) -> None:
        target = {"a": {"x": 1, "y": 2}}
        DictUtils.merge(target, {"a": {"y": 99, "z": 3}})
        assert target == {"a": {"x": 1, "y": 99, "z": 3}}

    def test_override_replaces_non_dict(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, {"a": "replaced"})
        assert target["a"] == "replaced"

    def test_multiple_overrides(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, {"b": 2}, {"c": 3})
        assert target == {"a": 1, "b": 2, "c": 3}

    def test_empty_override_is_noop(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, {})
        assert target == {"a": 1}

    def test_none_override_skipped(self) -> None:
        target = {"a": 1}
        DictUtils.merge(target, None)
        assert target == {"a": 1}

    def test_deep_copy_prevents_shared_refs(self) -> None:
        inner = {"x": 1}
        override = {"a": inner}
        target = {}
        DictUtils.merge(target, override)
        inner["x"] = 999
        assert target["a"]["x"] == 1


# -- DictUtils.merge_layers -------------------------------------------------


class TestDictMergeLayers:
    def test_deep_merge_list_strategies_and_provenance(self) -> None:
        result = DictUtils.merge_layers(
            (
                "defaults",
                {"nested": {"one": 1, "two": 2}, "replace": [1], "append": [1]},
            ),
            ("global", {"nested": {"two": 20}, "replace": [2], "append": [2]}),
            ("local", {"nested": {"three": 3}}),
            append_paths={"append"},
        )
        assert result.config == {
            "nested": {"one": 1, "two": 20, "three": 3},
            "replace": [2],
            "append": [1, 2],
        }
        assert result.provenance["nested.one"] == "defaults"
        assert result.provenance["nested.two"] == "global"
        assert result.provenance["nested.three"] == "local"

    def test_precedence_across_three_unnamed_layers(self) -> None:
        result = DictUtils.merge_layers({"a": 1}, {"a": 2}, {"a": 3})
        assert result.config == {"a": 3}
        assert result.provenance["a"] == "local"

    def test_unnamed_layers_get_conventional_names(self) -> None:
        result = DictUtils.merge_layers(
            {"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}, {"e": 5}
        )
        assert result.provenance == {
            "a": "defaults",
            "b": "global",
            "c": "local",
            "d": "overrides",
            "e": "layer-5",
        }

    def test_provenance_for_key_overridden_twice_reports_last_layer(self) -> None:
        result = DictUtils.merge_layers(
            ("l1", {"a": 1}), ("l2", {"a": 2}), ("l3", {"a": 3})
        )
        assert result.provenance["a"] == "l3"

    def test_append_path_concatenates_normal_list_replaces(self) -> None:
        result = DictUtils.merge_layers(
            ("l1", {"append_me": [1], "replace_me": [1]}),
            ("l2", {"append_me": [2], "replace_me": [2]}),
            append_paths={"append_me"},
        )
        assert result.config["append_me"] == [1, 2]
        assert result.config["replace_me"] == [2]

    def test_subtree_introduced_wholesale_gets_provenance_on_every_leaf(self) -> None:
        result = DictUtils.merge_layers(
            ("l1", {}), ("l2", {"new": {"x": 1, "y": {"z": 2}}})
        )
        assert result.provenance["new.x"] == "l2"
        assert result.provenance["new.y.z"] == "l2"
        assert result.provenance["new.y"] == "l2"

    def test_escaped_append_paths_distinguish_literal_dots_from_nested_keys(
        self,
    ) -> None:
        result = DictUtils.merge_layers(
            {"a.b": [1], "a": {"b": [3], "c.d": [5]}},
            {"a.b": [2], "a": {"b": [4], "c.d": [6]}},
            append_paths={r"a\.b", r"a.c\.d"},
        )
        assert result.config == {"a.b": [1, 2], "a": {"b": [4], "c.d": [5, 6]}}
        assert result.provenance == {
            r"a\.b": "global",
            "a": "global",
            "a.b": "global",
            r"a.c\.d": "global",
        }
        for path in result.provenance:
            assert DictUtils.get(result.config, path) is not None

    @pytest.mark.parametrize("replacement", [2, [2], None])
    def test_replacing_subtree_removes_only_its_descendant_provenance(
        self, replacement
    ) -> None:
        result = DictUtils.merge_layers(
            {"a": {"b": {"c": 1}}, "a.b": 3, "ab": {"c": 4}},
            {"a": replacement},
        )
        assert result.config == {"a": replacement, "a.b": 3, "ab": {"c": 4}}
        assert result.provenance == {
            "a": "global",
            r"a\.b": "defaults",
            "ab": "defaults",
            "ab.c": "defaults",
        }

    def test_deep_copy_isolation(self) -> None:
        inner = {"x": 1}
        result = DictUtils.merge_layers(("l1", {"a": inner}))
        inner["x"] = 999
        assert result.config["a"]["x"] == 1

    def test_layer_names_argument(self) -> None:
        result = DictUtils.merge_layers(
            {"a": 1}, {"a": 2}, layer_names=["base", "user"]
        )
        assert result.provenance["a"] == "user"

    def test_explicit_name_tuple_overrides_layer_names(self) -> None:
        result = DictUtils.merge_layers(
            {"a": 1}, ("explicit", {"a": 2}), layer_names=["base", "user"]
        )
        assert result.provenance["a"] == "explicit"

    def test_merge_existing_tests_still_pass_unchanged(self) -> None:
        # DictUtils.merge itself is untouched by merge_layers.
        target = {"a": {"x": 1}, "b": 2}
        assert DictUtils.merge(target, {"a": {"y": 3}, "b": 99}) is target
        assert target == {"a": {"x": 1, "y": 3}, "b": 99}


# -- DictUtils.flatten -------------------------------------------------------


class TestDictFlatten:
    def test_flattens_nested_mapping(self) -> None:
        assert DictUtils.flatten({"a": {"b": 1, "c": 2}, "d": 3}) == {
            "a.b": 1,
            "a.c": 2,
            "d": 3,
        }

    def test_flat_mapping_unchanged(self) -> None:
        assert DictUtils.flatten({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_deeply_nested(self) -> None:
        assert DictUtils.flatten({"a": {"b": {"c": 1}}}) == {"a.b.c": 1}

    def test_is_inverse_of_get_dotted_path(self) -> None:
        nested = {"a": {"b": {"c": 42}}}
        flat = DictUtils.flatten(nested)
        for key, value in flat.items():
            assert DictUtils.get(nested, key) == value

    def test_key_with_literal_dot_is_escaped(self) -> None:
        flat = DictUtils.flatten({"a.b": {"c": 1}})
        assert flat == {"a\\.b.c": 1}


# -- DictUtils.compare -----------------------------------------------------


class TestDictCompare:
    def test_equal_dicts(self) -> None:
        assert DictUtils.compare({"a": 1}, {"a": 1}) == {}

    def test_only_in_a(self) -> None:
        result = DictUtils.compare({"a": 1, "b": 2}, {"a": 1})
        assert result == {"only_in_a": {"b": 2}}

    def test_only_in_b(self) -> None:
        result = DictUtils.compare({"a": 1}, {"a": 1, "c": 3})
        assert result == {"only_in_b": {"c": 3}}

    def test_conflict(self) -> None:
        result = DictUtils.compare({"a": 1}, {"a": 2})
        assert result == {"conflicts": {"a": [1, 2]}}

    def test_nested_conflict(self) -> None:
        result = DictUtils.compare(
            {"a": {"x": 1}},
            {"a": {"x": 2}},
        )
        assert result == {"conflicts": {"a": {"conflicts": {"x": [1, 2]}}}}

    def test_both_empty(self) -> None:
        assert DictUtils.compare({}, {}) == {}

    def test_one_empty(self) -> None:
        assert DictUtils.compare({}, {"a": 1}) == {"only_in_b": {"a": 1}}
        assert DictUtils.compare({"a": 1}, {}) == {"only_in_a": {"a": 1}}


# -- ListUtils -------------------------------------------------------------


class TestListUtils:
    def test_get_default_index(self) -> None:
        assert ListUtils.get(["a", "b"]) == "a"

    def test_get_custom_index(self) -> None:
        assert ListUtils.get(["a", "b"], 1) == "b"

    def test_get_out_of_bounds_returns_default(self) -> None:
        assert ListUtils.get(["a"], 3, default="missing") == "missing"

    def test_get_empty_returns_default(self) -> None:
        assert ListUtils.get([], default="missing") == "missing"

    def test_sort_mutates_and_returns_list(self) -> None:
        items = [{"name": "b"}, {"name": "a"}]
        result = ListUtils.sort(items, key=lambda item: item["name"])
        assert result is items
        assert items == [{"name": "a"}, {"name": "b"}]

    def test_filter_with_value(self) -> None:
        assert ListUtils.filter(["a", "b", "a"], "a") == ["a", "a"]

    def test_filter_with_predicate(self) -> None:
        assert ListUtils.filter([1, 2, 3, 4], lambda item: item % 2 == 0) == [2, 4]

    def test_group_by(self) -> None:
        items = [
            {"type": "b", "value": 2},
            {"type": "a", "value": 1},
            {"type": "b", "value": 3},
        ]
        result = ListUtils.group_by(
            items,
            key_fn=lambda item: item["type"],
            value_fn=lambda item: item["value"],
        )
        assert result == {"a": [1], "b": [2, 3]}

    def test_group_by_does_not_mutate_input(self) -> None:
        items = [{"type": "b"}, {"type": "a"}]
        ListUtils.group_by(items, key_fn=lambda item: item["type"])
        assert items == [{"type": "b"}, {"type": "a"}]

    def test_group_by_with_group_fn(self) -> None:
        items = [{"type": "a", "value": 1}, {"type": "a", "value": 2}]
        result = ListUtils.group_by(
            items,
            key_fn=lambda item: item["type"],
            value_fn=lambda item: item["value"],
            group_fn=sum,
        )
        assert result == {"a": 3}

    def test_group_by_empty_returns_empty_dict(self) -> None:
        assert ListUtils.group_by([], key_fn=str) == {}


# -- DictUtils typed reads -------------------------------------------------


class TestDictTypedReads:
    DOC = {
        "repository": {"name": "kiln", "private": True, "tags": ["a", 1, "b"]},
        "docs": "mkdocs",
        "tasks": {"build": {"cmds": "echo hi"}, "a.b": {"cmds": None}},
        "items": [{"name": "first"}],
    }

    def test_get_mapping(self) -> None:
        assert DictUtils.get_mapping(self.DOC, "repository")["name"] == "kiln"

    def test_get_mapping_through_list_index(self) -> None:
        assert DictUtils.get_mapping(self.DOC, "items.0") == {"name": "first"}

    def test_get_mapping_stringifies_keys(self) -> None:
        assert DictUtils.get_mapping({"m": {1: "x"}}, "m") == {"1": "x"}

    def test_get_mapping_returns_a_copy(self) -> None:
        DictUtils.get_mapping(self.DOC, "repository")["name"] = "changed"
        assert self.DOC["repository"]["name"] == "kiln"

    @pytest.mark.parametrize("path", ["docs", "missing", "repository.tags", ""])
    def test_get_mapping_wrong_shape_is_empty(self, path: str) -> None:
        assert DictUtils.get_mapping(self.DOC, path) == {}

    def test_get_list(self) -> None:
        assert DictUtils.get_list(self.DOC, "repository.tags") == ["a", 1, "b"]

    def test_get_list_scalar_is_one_element(self) -> None:
        assert DictUtils.get_list(self.DOC, "tasks.build.cmds") == ["echo hi"]

    def test_get_list_mapping_is_one_element(self) -> None:
        assert DictUtils.get_list(self.DOC, "items.0") == [{"name": "first"}]

    def test_get_list_none_is_empty(self) -> None:
        assert DictUtils.get_list(self.DOC, r"tasks.a\.b.cmds") == []

    def test_get_list_missing_is_empty(self) -> None:
        assert DictUtils.get_list(self.DOC, "nope.nope") == []

    def test_get_strings_drops_non_strings(self) -> None:
        assert DictUtils.get_strings(self.DOC, "repository.tags") == ["a", "b"]

    def test_get_strings_scalar(self) -> None:
        assert DictUtils.get_strings(self.DOC, "docs") == ["mkdocs"]

    def test_get_strings_missing(self) -> None:
        assert DictUtils.get_strings(self.DOC, "missing") == []

    def test_get_str(self) -> None:
        assert DictUtils.get_str(self.DOC, "repository.name") == "kiln"

    def test_get_str_wrong_shape_is_default(self) -> None:
        assert DictUtils.get_str(self.DOC, "repository.private") == ""
        assert DictUtils.get_str(self.DOC, "missing", default="x") == "x"

    def test_get_bool(self) -> None:
        assert DictUtils.get_bool(self.DOC, "repository.private") is True

    def test_get_bool_does_not_coerce(self) -> None:
        assert DictUtils.get_bool({"a": 1, "b": "true"}, "a") is False
        assert DictUtils.get_bool({"a": 1, "b": "true"}, "b", default=True) is True
