import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from assertpy import assert_that
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.settings import EnvSettings, SettingsError
from rn_forge.commons.lang.utils import AppUtils


class _App(EnvSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    name: str = "app"
    data_dir: Path = Path("data")
    enabled: bool = False
    workers: int = 1
    cap: Decimal = Decimal("1.00")


def test_settings_defaults_with_empty_mapping() -> None:
    settings = _App.load({})

    assert_that(settings.name).is_equal_to("app")
    assert_that(settings.data_dir).is_equal_to(Path("data"))
    assert_that(settings.enabled).is_false()
    assert_that(settings.workers).is_equal_to(1)
    assert_that(settings.cap).is_equal_to(Decimal("1.00"))


def test_settings_prefix_maps_fields() -> None:
    settings = _App.load(
        {
            "APP_NAME": "svc",
            "APP_DATA_DIR": "/var/data",
            "APP_ENABLED": "true",
            "app_workers": "4",
            "APP_CAP": "2.50",
        }
    )

    assert_that(settings.name).is_equal_to("svc")
    assert_that(settings.data_dir).is_equal_to(Path("/var/data"))
    assert_that(settings.enabled).is_true()
    assert_that(settings.workers).is_equal_to(4)
    assert_that(settings.cap).is_equal_to(Decimal("2.50"))


@pytest.mark.parametrize("token", ["Enabled", "YES", "off", "none"])
def test_settings_bool_accepts_parse_bool_tokens(token: str) -> None:
    settings = _App.load({"APP_ENABLED": token})

    assert_that(settings.enabled).is_equal_to(AppUtils.parse_bool(token))


def test_settings_bool_rejects_unknown_token() -> None:
    with pytest.raises(SettingsError) as raised:
        _App.load({"APP_ENABLED": "maybe"})

    assert_that(raised.value.variables).is_equal_to(("APP_ENABLED",))
    assert_that(str(raised.value)).contains("APP_ENABLED")


def test_settings_decimal_kept_exact() -> None:
    settings = _App.load({"APP_CAP": "0.10"})

    assert_that(settings.cap).is_equal_to(Decimal("0.10"))
    assert_that(settings.cap.as_tuple().exponent).is_equal_to(-2)


def test_settings_reports_every_invalid_variable() -> None:
    with pytest.raises(SettingsError) as raised:
        _App.load({"APP_WORKERS": "x", "APP_ENABLED": "maybe"})

    assert_that(raised.value.variables).is_equal_to(("APP_ENABLED", "APP_WORKERS"))
    assert_that(str(raised.value)).contains("APP_ENABLED").contains("APP_WORKERS")


def test_settings_reports_missing_required_variable() -> None:
    class _Required(_App):
        database_url: str

    with pytest.raises(SettingsError) as raised:
        _Required.load({})

    assert_that(raised.value.variables).is_equal_to(("APP_DATABASE_URL",))
    assert_that(str(raised.value)).contains("APP_DATABASE_URL")


def test_settings_load_ignores_os_environ_when_mapping_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_NAME", "env")

    assert_that(_App.load({}).name).is_equal_to("app")
    assert_that(_App.load().name).is_equal_to("env")


def test_settings_ignores_dotenv_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("APP_NAME=dotenv\n")

    assert_that(_App.load({}).name).is_equal_to("app")


def test_settings_are_immutable() -> None:
    settings = _App.load({})

    with pytest.raises(ValidationError):
        settings.name = "x"


def test_settings_error_is_app_exception() -> None:
    assert_that(issubclass(SettingsError, AppException)).is_true()


def test_settings_not_imported_by_facade() -> None:
    script = (
        "import sys\n"
        "import rn_forge.commons\n"
        "print(sorted(n for n in sys.modules if n == 'pydantic_settings' "
        "or n.startswith('pydantic_settings.') "
        "or n == 'rn_forge.commons.lang.settings'))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )

    assert_that(result.stdout.strip()).is_equal_to("[]")
