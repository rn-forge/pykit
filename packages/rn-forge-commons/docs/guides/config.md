# Config

`Config` loads one file or a directory of JSON or YAML files, deep-merges them,
and optionally resolves references.

Example YAML:

```yaml
service:
  host: localhost
  port: 8080

service_url: "https://${service.host}:${service.port}"

profiles:
  base:
    debug: true
    timeout: 30

production:
  __extends__: "@{profiles.base}"
  debug: false
```

Usage:

```python
from rn_forge.commons import Config

cfg = Config("config")
url = cfg.get("service_url")
production = cfg.get("production")
```

Reference forms:

- `${path}` scalar interpolation
- `@{path}` dict splice
- `#{path}` list splice
- `__extends__` dict inheritance

## Validating a document against a schema

`Config` merges and resolves; it does not say whether the result is well-formed.
When a hand-authored document has a fixed shape — a tool's `config.toml`, a
manifest — validate it with a `StrictModel` from the `pydantic` extra:

```python
import tomllib

from rn_forge.commons.lang.models import StrictModel


class Repository(StrictModel):
    name: str
    archetype: str = "python-tool"


class ProjectConfig(StrictModel):
    schema_version: int
    repository: Repository


with open("config.toml", "rb") as handle:
    config = ProjectConfig.parse(tomllib.load(handle), source="config.toml")
```

A `StrictModel` is strict (a string is never coerced to an integer), frozen, and
rejects any key it does not declare. A failure raises `ModelValidationError`, an
`AppException` whose message lists every failing key by dotted path — a missing
key, a wrong type and a misspelled key are reported together, not one per run.
`errors` holds the same failures as `FieldError` records. `parse_model` gives
the same reporting for a `BaseModel` that does not subclass `StrictModel`.

Choose it over `DataclassMixin.from_dict` when the author of the document needs
every mistake at once, or when the schema needs pydantic's validators. The extra
is opt-in, and `rn_forge.commons` never imports it, so a program that does not
use it pays nothing at import time.

## Settings

`EnvSettings` loads typed, frozen settings from prefixed environment variables.
It needs the `settings` extra (`pip install rn-forge-commons[settings]`).

```python
from decimal import Decimal
from pathlib import Path

from pydantic_settings import SettingsConfigDict
from rn_forge.commons.lang.settings import EnvSettings


class AppSettings(EnvSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    name: str = "app"
    data_dir: Path = Path("data")
    enabled: bool = False
    workers: int = 1
    cap: Decimal = Decimal("1.00")


settings = AppSettings.load()
```

`load()` reads `os.environ`. `load({...})` reads the mapping you pass instead
and never touches `os.environ`, which is what a test wants:

```python
def test_workers() -> None:
    settings = AppSettings.load({"APP_WORKERS": "4", "app_enabled": "yes"})
    assert settings.workers == 4
    assert settings.enabled is True
```

Variable names are matched without regard to case. Every invalid or missing
variable is reported in one `SettingsError`, named by its environment variable:

```python
AppSettings.load({"APP_WORKERS": "x", "APP_ENABLED": "maybe"})
# SettingsError: Invalid settings: APP_ENABLED: Value error, ...; APP_WORKERS: Input should be a valid integer, ...
```

`SettingsError.variables` holds the sorted names
(`("APP_ENABLED", "APP_WORKERS")`).

A `bool` field takes the tokens `AppUtils.parse_bool` takes, case-insensitively:
`true`, `yes`, `y`, `on`, `1`, `enabled` and `false`, `no`, `n`, `off`, `0`,
`disabled`, `none`. Any other string is an error.

No `.env` file or secrets directory is read unless a subclass sets `env_file` or
`secrets_dir` in its `model_config`.
