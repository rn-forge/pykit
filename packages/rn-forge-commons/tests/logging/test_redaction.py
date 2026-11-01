"""Tests for rn_forge.commons.logging.redaction and RedactFilter."""

from __future__ import annotations

import copy
import io
import json
import logging
import re
from typing import Any

import pytest
from rn_forge.commons.logging import (
    REDACTED,
    AppLogger,
    LoggingConfig,
    RedactFilter,
    RedactionPolicy,
    redact,
)


@pytest.fixture(autouse=True)
def reset_logger_state():
    AppLogger._configured = False
    yield
    AppLogger._configured = False
    logging.getLogger().handlers.clear()


def _record(msg: str, args: Any = (), **extra: Any) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
    for name, value in extra.items():
        setattr(record, name, value)
    return record


class TestKeyMatching:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "Authorization",
            "access_token",
            "accessToken",
            "client_secret",
            "set-cookie",
            "x-csrf-token",
            "TOKEN",
            "tokens",
        ],
    )
    def test_secret_keys_are_redacted(self, key: str) -> None:
        assert redact({key: "v"}) == {key: REDACTED}

    @pytest.mark.parametrize(
        "key",
        ["token_count", "tokenCount", "password_hint", "secret_santa", "cookie_jar"],
    )
    def test_other_keys_are_kept(self, key: str) -> None:
        assert redact({key: "v"}) == {key: "v"}

    def test_matched_value_of_any_type_is_replaced(self) -> None:
        data = {"token": {"a": 1}, "password": [1, 2], "secret": 42}
        assert redact(data) == dict.fromkeys(data, REDACTED)

    def test_none_and_empty_string_are_preserved(self) -> None:
        assert redact({"token": None, "password": ""}) == {
            "token": None,
            "password": "",
        }

    def test_key_argument_applies_to_a_bare_value(self) -> None:
        assert redact("x", key="api_token") == REDACTED


class TestStructure:
    def test_nested_mixes_are_redacted_at_depth(self) -> None:
        data = {
            "a": [{"password": "p"}, ("keep", {"token": "t"})],
            "b": ({"secret": "s"},),
        }
        assert redact(data) == {
            "a": [{"password": REDACTED}, ("keep", {"token": REDACTED})],
            "b": ({"secret": REDACTED},),
        }

    def test_input_is_not_mutated(self) -> None:
        data = {"a": [{"password": "p", "u": "http://x:y@h"}], "t": ("Bearer abc123",)}
        before = copy.deepcopy(data)
        redact(data)
        assert data == before

    def test_unmatched_fields_and_other_types_untouched(self) -> None:
        obj = object()
        assert redact({"n": 1, "o": obj, "f": 1.5}) == {"n": 1, "o": obj, "f": 1.5}


class TestValueScrubbing:
    def test_bearer_credential_keeps_scheme(self) -> None:
        assert (
            redact("Authorization: Bearer abc.d3f")
            == f"Authorization: Bearer {REDACTED}"
        )

    def test_basic_credential_keeps_scheme(self) -> None:
        assert redact("Basic dXNlcjpwYXNz") == f"Basic {REDACTED}"

    @pytest.mark.parametrize(
        "prose",
        [
            "bearer token expired",
            "basic authentication failed",
            "Basic configuration loaded",
            "Bearer token.",
        ],
    )
    def test_prose_after_a_scheme_word_is_kept(self, prose: str) -> None:
        assert redact(prose) == prose

    def test_url_password_only(self) -> None:
        assert (
            redact("postgres://ann:hunter2@db:5432/x")
            == f"postgres://ann:{REDACTED}@db:5432/x"
        )

    def test_url_password_without_a_user(self) -> None:
        assert redact("redis://:s3cret@host:6379/0") == (
            f"redis://:{REDACTED}@host:6379/0"
        )

    def test_url_without_password_is_kept(self) -> None:
        assert redact("https://ann@host/p") == "https://ann@host/p"

    def test_scrubs_under_unmatched_key_and_in_containers(self) -> None:
        assert redact({"note": ["Bearer z3z"]}) == {"note": [f"Bearer {REDACTED}"]}

    def test_idempotent(self) -> None:
        once = redact({"password": "p", "u": "s://a:b@h", "h": "Bearer t0k"})
        assert redact(once) == once


class TestPolicy:
    def test_custom_pattern(self) -> None:
        policy = RedactionPolicy(re.compile("^ssn$"), False, False)
        data = {"ssn": "1", "password": "p", "h": "Bearer t0k", "u": "s://a:b@h"}
        assert redact(data, policy=policy) == {
            "ssn": REDACTED,
            "password": "p",
            "h": "Bearer t0k",
            "u": "s://a:b@h",
        }

    def test_scrub_flags_are_independent(self) -> None:
        policy = RedactionPolicy(re.compile("^$"), True, False)
        assert (
            redact("Bearer t0k s://a:b@h", policy=policy)
            == f"Bearer {REDACTED} s://a:b@h"
        )


class TestRedactFilter:
    def test_always_returns_true(self) -> None:
        assert RedactFilter().filter(_record("m")) is True

    def test_message_with_bearer_token(self) -> None:
        record = _record("sent Bearer abc123 to api")
        RedactFilter().filter(record)
        assert record.getMessage() == f"sent Bearer {REDACTED} to api"

    def test_tuple_args_keep_shape_and_non_string_types(self) -> None:
        record = _record("%d items for %s", (3, "Bearer abc123"))
        RedactFilter().filter(record)
        assert record.args == (3, f"Bearer {REDACTED}")
        assert record.getMessage() == f"3 items for Bearer {REDACTED}"

    def test_mapping_args_are_redacted(self) -> None:
        args = {"user": "ann", "password": "p"}
        record = _record("%(user)s %(password)s", (args,))
        RedactFilter().filter(record)
        assert record.args == {"user": "ann", "password": REDACTED}
        assert args == {"user": "ann", "password": "p"}

    def test_credential_formed_only_by_formatting(self) -> None:
        record = _record("Bearer %s", ("abc123",))
        RedactFilter().filter(record)
        assert record.getMessage() == f"Bearer {REDACTED}"

    def test_extra_fields_are_redacted_without_mutating_caller(self) -> None:
        payload = {"token": "t", "n": 1}
        record = _record("m", ctx=payload, api_key_secret="s")
        RedactFilter().filter(record)
        assert record.ctx == {"token": REDACTED, "n": 1}  # pyright: ignore[reportAttributeAccessIssue]
        assert record.api_key_secret == REDACTED  # pyright: ignore[reportAttributeAccessIssue]
        assert payload == {"token": "t", "n": 1}

    def test_idempotent(self) -> None:
        record = _record("Bearer %s", ("abc123",), ctx={"password": "p"})
        flt = RedactFilter()
        flt.filter(record)
        snapshot = (record.msg, record.args, record.ctx)  # pyright: ignore[reportAttributeAccessIssue]
        flt.filter(record)
        assert (record.msg, record.args, record.ctx) == snapshot  # pyright: ignore[reportAttributeAccessIssue]

    def test_non_string_message_is_left_alone(self) -> None:
        record = _record("x")
        record.msg = 42
        assert RedactFilter().filter(record) is True
        assert record.msg == 42

    def test_failure_fails_closed_without_raising(self) -> None:
        class Boom:
            def __str__(self) -> str:
                raise RuntimeError("boom")

        record = _record("%s", (Boom(),))
        assert RedactFilter().filter(record) is True
        assert record.msg == REDACTED


class TestIntegration:
    def test_json_output_is_redacted(self, capsys: pytest.CaptureFixture[str]) -> None:
        pytest.importorskip("pythonjsonlogger")
        AppLogger.initialize(
            root_logger_name="redact_json",
            level=logging.INFO,
            use_json=True,
            force_reconfigure=True,
        )
        AppLogger.get_logger("redact_json").info(
            "login Bearer abc123", extra={"password": "hunter2", "user": "ann"}
        )
        line = next(ln for ln in capsys.readouterr().err.splitlines() if "login" in ln)
        assert "hunter2" not in line
        assert "abc" not in line
        assert json.loads(line)["message"] == f"login Bearer {REDACTED}"

    def test_plain_output_is_redacted(self, capsys: pytest.CaptureFixture[str]) -> None:
        AppLogger.initialize(
            root_logger_name="redact_plain",
            level=logging.INFO,
            fmt="%(message)s %(password)s",
            enable_color=False,
            force_reconfigure=True,
        )
        AppLogger.get_logger("redact_plain").info(
            "url s://a:pw@h", extra={"password": "hunter2"}
        )
        err = capsys.readouterr().err
        assert f"url s://a:{REDACTED}@h {REDACTED}" in err
        assert "hunter2" not in err

    def test_redact_false_disables_the_filter(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        AppLogger.initialize(
            root_logger_name="redact_off",
            level=logging.INFO,
            fmt="%(message)s",
            enable_color=False,
            redact=False,
            force_reconfigure=True,
        )
        AppLogger.get_logger("redact_off").info("Bearer abc123")
        assert "Bearer abc123" in capsys.readouterr().err

    def test_config_flag(self) -> None:
        assert LoggingConfig.defaults()["redact"] is True
        assert LoggingConfig.build(root_logger_name="x").redact is True
        assert LoggingConfig.build(root_logger_name="x", redact=False).redact is False

    def test_filter_registered_only_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(logging.config, "dictConfig", captured.update)
        for flag in (True, False):
            AppLogger._configure_logging(
                LoggingConfig.build(root_logger_name="x", redact=flag), None
            )
            assert ("redact" in captured["filters"]) is flag
            assert ("redact" in captured["handlers"]["console"]["filters"]) is flag


class TestStructlogProcessor:
    def test_redacts_a_copy_of_the_event(self) -> None:
        pytest.importorskip("structlog")
        from rn_forge.commons.logging.structlog import redact_processor

        event = {"event": "Bearer abc123", "password": "p", "n": 1}
        out = redact_processor(None, "info", event)
        assert out == {"event": f"Bearer {REDACTED}", "password": REDACTED, "n": 1}
        assert event["password"] == "p"

    def test_structlogger_output_is_redacted(self) -> None:
        pytest.importorskip("structlog")
        from rn_forge.commons.logging.structlog import StructLogger

        stream = io.StringIO()
        AppLogger.initialize(
            root_logger_name="redact_struct",
            level=logging.INFO,
            force_reconfigure=True,
        )
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        StructLogger("redact_struct").info("hi", password="hunter2", user="ann")
        out = stream.getvalue()
        assert "hunter2" not in out
        assert "user='ann'" in out
