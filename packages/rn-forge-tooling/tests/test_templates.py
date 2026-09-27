"""Tests for rn_forge.tooling.templates."""

from __future__ import annotations

import pytest

pytest.importorskip("jinja2")

from rn_forge.tooling.templates import RenderError, TemplateEngine  # noqa: E402


class TestConstruction:
    def test_neither_directory_nor_package_raises(self):
        with pytest.raises(ValueError, match="Exactly one"):
            TemplateEngine()

    def test_both_directory_and_package_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Exactly one"):
            TemplateEngine(directory=str(tmp_path), package="rn_forge.commons")


class TestRenderString:
    def test_renders_with_context(self, tmp_path):
        engine = TemplateEngine(directory=str(tmp_path))
        assert (
            engine.render_string("Hello {{ name }}", {"name": "world"}) == "Hello world"
        )

    def test_strict_undefined_raises(self, tmp_path):
        engine = TemplateEngine(directory=str(tmp_path))
        with pytest.raises(RenderError):
            engine.render_string("Hello {{ missing }}", {})

    def test_non_strict_renders_empty(self, tmp_path):
        engine = TemplateEngine(directory=str(tmp_path), strict=False)
        assert engine.render_string("Hello {{ missing }}", {}) == "Hello "


class TestRenderNamed:
    def test_filesystem_loader(self, tmp_path):
        (tmp_path / "greeting.txt.j2").write_text("Hi {{ name }}!")
        engine = TemplateEngine(directory=str(tmp_path))
        assert engine.render("greeting.txt.j2", {"name": "there"}) == "Hi there!"

    def test_missing_named_template_raises(self, tmp_path):
        engine = TemplateEngine(directory=str(tmp_path))
        with pytest.raises(RenderError):
            engine.render("missing.j2", {})


class TestValidate:
    def test_validate_reports_broken_template_by_name(self, tmp_path):
        (tmp_path / "good.j2").write_text("{{ x }}")
        (tmp_path / "bad.j2").write_text("{% if %}")
        engine = TemplateEngine(directory=str(tmp_path))
        errors = engine.validate()
        assert len(errors) == 1
        assert "bad.j2" in errors[0]

    def test_validate_returns_empty_for_no_errors(self, tmp_path):
        (tmp_path / "good.j2").write_text("{{ x }}")
        engine = TemplateEngine(directory=str(tmp_path))
        assert engine.validate() == []


class TestKeepTrailingNewline:
    def test_trailing_newline_kept_by_default(self, tmp_path):
        engine = TemplateEngine(directory=str(tmp_path))
        assert engine.render_string("line\n", {}) == "line\n"

    def test_environment_kwargs_forwarded(self, tmp_path):
        engine = TemplateEngine(directory=str(tmp_path), trim_blocks=True)
        assert engine.environment.trim_blocks is True


class TestDocumentFilters:
    def test_to_toml_filter_round_trips(self, tmp_path):
        pytest.importorskip("tomlkit")
        from rn_forge.commons.fs.documents import ConfigFormat, DocumentUtils

        engine = TemplateEngine(directory=str(tmp_path))
        rendered = engine.render_string("{{ data | to_toml }}", {"data": {"a": 1}})
        assert DocumentUtils.loads(rendered, ConfigFormat.TOML) == {"a": 1}

    def test_to_yaml_filter_round_trips(self, tmp_path):
        pytest.importorskip("ruamel.yaml")
        from rn_forge.commons.fs.documents import ConfigFormat, DocumentUtils

        engine = TemplateEngine(directory=str(tmp_path))
        rendered = engine.render_string("{{ data | to_yaml }}", {"data": {"a": 1}})
        assert DocumentUtils.loads(rendered, ConfigFormat.YAML) == {"a": 1}


class TestEscapeHatch:
    def test_environment_property_is_jinja_environment(self, tmp_path):
        import jinja2

        engine = TemplateEngine(directory=str(tmp_path))
        assert isinstance(engine.environment, jinja2.Environment)


class TestPackageLoader:
    def test_package_loader_style_supported(self, tmp_path):
        # "." resolves to the package's own directory, which always exists —
        # this exercises PackageLoader construction and rendering without
        # requiring a dedicated packaged templates/ resource dir.
        engine = TemplateEngine(package="rn_forge.commons", package_path=".")
        assert engine.render_string("{{ x }}", {"x": 1}) == "1"
