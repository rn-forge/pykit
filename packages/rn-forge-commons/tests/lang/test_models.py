import subprocess
import sys

import pytest
from pydantic import BaseModel

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.models import (
    FieldError,
    ModelValidationError,
    StrictModel,
    parse_model,
)


class Repository(StrictModel):
    name: str
    archetype: str = "python-tool"
    packages: list[str] = []


class ProjectConfig(StrictModel):
    schema_version: int
    repository: Repository


def _paths(error: ModelValidationError) -> dict[str, str]:
    return {e.path: e.kind for e in error.errors}


def test_a_valid_document_parses():
    config = ProjectConfig.parse(
        {"schema_version": 1, "repository": {"name": "x", "packages": ["a"]}}
    )
    assert config.repository.name == "x"
    assert config.repository.archetype == "python-tool"
    assert config.repository.packages == ["a"]


def test_every_failure_is_reported_by_dotted_path():
    with pytest.raises(ModelValidationError) as caught:
        ProjectConfig.parse(
            {
                "schema_version": "1",
                "repository": {"archtype": "lib", "packages": ["a", 2]},
            }
        )
    assert _paths(caught.value) == {
        "schema_version": "int_type",
        "repository.name": "missing",
        "repository.archtype": "extra_forbidden",
        "repository.packages.1": "string_type",
    }


def test_the_message_names_the_source_and_each_path():
    with pytest.raises(ModelValidationError) as caught:
        ProjectConfig.parse({"repository": {"name": "x"}}, source="config.toml")
    message = caught.value.message
    assert message.startswith("config.toml: 1 invalid key(s)")
    assert "schema_version: Field required" in message
    assert caught.value.error_data["paths"] == ["schema_version"]


def test_the_error_is_an_app_exception():
    with pytest.raises(AppException):
        ProjectConfig.parse({})


def test_a_message_with_braces_is_not_formatted_twice():
    with pytest.raises(ModelValidationError) as caught:
        ProjectConfig.parse({"schema_version": 1, "repository": {"{name}": 1}})
    assert "repository.{name}" in caught.value.message


def test_strict_models_are_frozen():
    config = ProjectConfig.parse({"schema_version": 1, "repository": {"name": "x"}})
    with pytest.raises(Exception):
        config.schema_version = 2  # type: ignore[misc]


def test_parse_model_accepts_any_base_model():
    class Loose(BaseModel):
        port: int

    assert parse_model(Loose, {"port": "80"}).port == 80
    with pytest.raises(ModelValidationError) as caught:
        parse_model(Loose, {})
    assert caught.value.errors == (FieldError("port", "Field required", "missing"),)


def test_a_root_level_failure_has_an_empty_path():
    error = FieldError("", "Input should be a valid dictionary", "model_type")
    assert str(error) == "<root>: Input should be a valid dictionary"


def test_importing_commons_does_not_load_pydantic():
    code = "import sys, rn_forge.commons; print('pydantic' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"
