"""Tests for rn_forge.commons.runtime.environment."""

from __future__ import annotations

import os

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.runtime.environment import Environment


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class TestEnvironment:
    def test_get_all_returns_dict(self):
        result = Environment.get_all()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_get_existing(self, monkeypatch):
        monkeypatch.setenv("_TEST_VAR", "hello")
        assert Environment.get("_TEST_VAR") == "hello"

    def test_get_missing_returns_none(self, monkeypatch):
        monkeypatch.delenv("_MISSING_VAR", raising=False)
        assert Environment.get("_MISSING_VAR") is None

    def test_get_missing_with_default(self, monkeypatch):
        monkeypatch.delenv("_MISSING_VAR", raising=False)
        assert Environment.get("_MISSING_VAR", "fallback") == "fallback"

    def test_set_returns_value(self, monkeypatch):
        monkeypatch.delenv("_SET_VAR", raising=False)
        result = Environment.set("_SET_VAR", "world")
        assert result == "world"
        assert os.environ["_SET_VAR"] == "world"

    def test_is_enabled_true_tokens(self, monkeypatch):
        for token in ("true", "True", "TRUE", "yes", "YES", "enabled", "ENABLED"):
            monkeypatch.setenv("_FLAG", token)
            assert Environment.is_enabled("_FLAG") is True, token

    def test_is_enabled_false_tokens(self, monkeypatch):
        for token in ("false", "False", "no", "NO", "disabled", "none", "None"):
            monkeypatch.setenv("_FLAG", token)
            assert Environment.is_enabled("_FLAG") is False, token

    def test_is_enabled_missing_returns_default(self, monkeypatch):
        monkeypatch.delenv("_FLAG", raising=False)
        assert Environment.is_enabled("_FLAG") is False
        assert Environment.is_enabled("_FLAG", default=True) is True

    def test_is_enabled_unrecognised_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("_FLAG", "maybe")
        assert Environment.is_enabled("_FLAG") is False
        assert Environment.is_enabled("_FLAG", default=True) is True


class TestEnvironmentRequire:
    def test_all_present_returns_mapping(self, monkeypatch):
        monkeypatch.setenv("_REQ_A", "1")
        monkeypatch.setenv("_REQ_B", "2")
        assert Environment.require("_REQ_A", "_REQ_B") == {"_REQ_A": "1", "_REQ_B": "2"}

    def test_one_missing_raises(self, monkeypatch):
        monkeypatch.setenv("_REQ_A", "1")
        monkeypatch.delenv("_REQ_MISSING", raising=False)
        with pytest.raises(AppException):
            Environment.require("_REQ_A", "_REQ_MISSING")

    def test_several_missing_all_appear_in_one_message(self, monkeypatch):
        monkeypatch.delenv("_REQ_M1", raising=False)
        monkeypatch.delenv("_REQ_M2", raising=False)
        with pytest.raises(AppException) as exc_info:
            Environment.require("_REQ_M1", "_REQ_M2")
        assert "_REQ_M1" in str(exc_info.value)
        assert "_REQ_M2" in str(exc_info.value)

    def test_empty_string_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("_REQ_EMPTY", "   ")
        with pytest.raises(AppException):
            Environment.require("_REQ_EMPTY")


class TestEnvironmentForbid:
    def test_matches_raises(self, monkeypatch):
        monkeypatch.setenv("_SECRET", "change-me")
        with pytest.raises(AppException):
            Environment.forbid("_SECRET", "change-me")

    def test_does_not_match_passes(self, monkeypatch):
        monkeypatch.setenv("_SECRET", "a-real-secret")
        Environment.forbid("_SECRET", "change-me")

    def test_custom_message_used(self, monkeypatch):
        monkeypatch.setenv("_SECRET", "change-me")
        with pytest.raises(AppException, match="custom message"):
            Environment.forbid("_SECRET", "change-me", message="custom message")
