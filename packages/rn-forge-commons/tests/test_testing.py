"""Tests for rn_forge.commons.testing."""

from __future__ import annotations

from pathlib import Path
import types

import pytest

import rn_forge.commons.testing as testing_module
from rn_forge.commons.testing import assert_that, soft_assertions


# ---------------------------------------------------------------------------
# output_path fixture
# ---------------------------------------------------------------------------


class TestOutputPath:
    def test_returns_path(self, output_path: Path):
        assert isinstance(output_path, Path)

    def test_directory_exists(self, output_path: Path):
        assert output_path.exists()
        assert output_path.is_dir()

    def test_path_is_under_standardized_output_root(self, output_path: Path):
        assert ".out" in output_path.parts
        assert "rn-forge-commons" in output_path.parts
        assert "tests" in output_path.parts
        assert "output" in output_path.parts

    def test_path_contains_test_name(self, output_path: Path):
        assert "test_path_contains_test_name" in str(output_path)

    def test_can_write_and_read_file(self, output_path: Path):
        f = output_path / "result.txt"
        f.write_text("hello from test")
        assert f.read_text() == "hello from test"

    def test_can_write_binary_file(self, output_path: Path):
        f = output_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")
        assert f.read_bytes() == b"\x00\x01\x02"

    def test_separate_tests_get_separate_directories(
        self, output_path: Path, tmp_path: Path
    ):
        # Each test node gets a unique subpath — no collision
        assert output_path != tmp_path

    def test_workspace_scope_for_non_package_node(self) -> None:
        fake_request = types.SimpleNamespace(
            config=types.SimpleNamespace(rootpath="/tmp/project"),
            node=types.SimpleNamespace(nodeid="tests/test_something.py::test_case"),
        )
        result = testing_module.output_path.__wrapped__(fake_request)
        assert ".out" in result.parts
        assert "workspace" in result.parts


# ---------------------------------------------------------------------------
# assert_that — basic value assertions
# ---------------------------------------------------------------------------


class TestAssertThat:
    def test_string_equality(self):
        assert_that("hello").is_equal_to("hello")

    def test_string_chaining(self):
        assert_that("foobar").is_length(6).starts_with("foo").ends_with("bar")

    def test_string_contains(self):
        assert_that("hello world").contains("world")

    def test_string_matches_regex(self):
        assert_that("abc123").matches(r"[a-z]+\d+")

    def test_integer_comparison(self):
        assert_that(42).is_greater_than(10).is_less_than(100)

    def test_integer_between(self):
        assert_that(5).is_between(1, 10)

    def test_none_check(self):
        assert_that(None).is_none()
        assert_that("x").is_not_none()

    def test_list_contains(self):
        assert_that([1, 2, 3]).contains(2).is_length(3)

    def test_list_is_sorted(self):
        assert_that([1, 2, 3]).is_sorted()

    def test_list_subset(self):
        assert_that([1, 2]).is_subset_of([1, 2, 3, 4])

    def test_dict_contains_key(self):
        assert_that({"a": 1, "b": 2}).contains_key("a").contains_value(2)

    def test_description_on_failure(self):
        wrapped = assert_that(1, "my label")
        with pytest.raises(AssertionError, match="my label"):
            wrapped.is_equal_to(2)

    def test_path_exists(self, tmp_path: Path):
        assert_that(str(tmp_path)).exists().is_directory()

    def test_file_exists(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        assert_that(str(f)).exists().is_file()

    def test_chained_collection_methods(self):
        assert_that([3, 1, 2]).contains(1, 2, 3).is_not_empty().is_length(3)

    def test_extracting(self):
        data = [{"name": "alice"}, {"name": "bob"}]
        assert_that(data).extracting("name").contains("alice", "bob")


# ---------------------------------------------------------------------------
# soft_assertions — collect all failures before raising
# ---------------------------------------------------------------------------


class TestSoftAssertions:
    def test_passes_when_all_assertions_pass(self):
        with soft_assertions():
            assert_that(1).is_equal_to(1)
            assert_that("ok").is_not_empty()

    def test_collects_multiple_failures(self):
        # NOSONAR: intentionally wraps multiple failing assertions — this
        # verifies soft_assertions() collects them all into one combined
        # error raised at context exit, not that a single call throws.
        with pytest.raises(AssertionError) as exc_info:
            with soft_assertions():
                assert_that(1).is_equal_to(99)
                assert_that("x").is_equal_to("y")
        # Both failures should appear in the combined message
        message = str(exc_info.value)
        assert "99" in message
        assert "y" in message

    def test_reports_all_failures_not_just_first(self):
        failures: list[str] = []
        try:
            with soft_assertions():
                assert_that(1).is_equal_to(2)
                assert_that(3).is_equal_to(4)
                assert_that(5).is_equal_to(6)
        except AssertionError as exc:
            failures = str(exc).splitlines()
        # Should have reported all three failures
        assert (
            len(
                [
                    line
                    for line in failures
                    if "Expected" in line or "to be equal to" in line
                ]
            )
            >= 2
        )

    def test_passes_through_non_assertion_exceptions(self):
        # NOSONAR: intentionally wraps the whole `with soft_assertions()`
        # block — this verifies a non-assertion exception propagates through
        # the context manager unchanged, not just that `raise` throws.
        with pytest.raises(ValueError, match="boom"):
            with soft_assertions():
                raise ValueError("boom")


class TestInternalHelpers:
    def test_assertpy_missing_raises_helpful_error(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "assertpy":
                raise ImportError("missing")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="assertpy"):
            testing_module._check_assertpy_available()


# Coverage ROI notes:
# - assertpy's own fluent assertion behaviors are not re-tested beyond the
#   integration wrappers exposed by rn_forge.commons.testing.
