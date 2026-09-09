"""Tests for rn_forge.commons.secrets."""

from __future__ import annotations

import pytest

from rn_forge.commons.secrets import (
    AsyncSecretStore,
    EnvSecretStore,
    SecretNotFound,
    SecretStore,
)


class TestEnvSecretStore:
    def test_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_PASSWORD", "hunter2")
        store = EnvSecretStore()
        assert store.get_secret("db-password") == "hunter2"

    def test_miss_raises_with_key_in_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MISSING_SECRET", raising=False)
        store = EnvSecretStore()
        with pytest.raises(SecretNotFound, match="missing-secret"):
            store.get_secret("missing-secret")

    def test_empty_string_counts_as_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EMPTY_SECRET", "   ")
        store = EnvSecretStore()
        with pytest.raises(SecretNotFound):
            store.get_secret("empty-secret")

    def test_prefix_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYAPP_DB_PASSWORD", "hunter2")
        store = EnvSecretStore(prefix="myapp")
        assert store.get_secret("db-password") == "hunter2"

    def test_name_transformation_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # upper-case, '-' -> '_', prefix prepended with a trailing '_'
        monkeypatch.setenv("APP_SOME_KEY", "v")
        store = EnvSecretStore(prefix="app_")
        assert store.get_secret("some-key") == "v"

    def test_satisfies_secret_store_protocol(self) -> None:
        assert isinstance(EnvSecretStore(), SecretStore)

    def test_satisfies_async_secret_store_protocol_structurally(self) -> None:
        # runtime_checkable isinstance checks only method names, not
        # sync-vs-async signatures.
        assert isinstance(EnvSecretStore(), AsyncSecretStore)
