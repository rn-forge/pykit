# Text

## Templates

`rn_forge.commons.text.templates` renders Jinja templates. It needs the
`templates` extra and is imported directly, never through `rn_forge.commons`.

```bash
uv add "rn-forge-commons[templates]"
```

`TemplateEngine.cached` returns one shared engine per set of arguments, so each
template compiles once per process. Do not mutate its `environment`.

```python
from rn_forge.commons.text.templates import TemplateEngine

engine = TemplateEngine.cached(package="my_tool", package_path="templates")

engine.render("pyproject.toml.j2", {"name": "demo"})
engine.render_string("Hello {{ name }}", {"name": "world"})
```

Undefined variables raise `RenderError`. Pass `strict=False` to render them
empty.

For HTML output, pass `autoescape=True` so every rendered value is escaped:

```python
html = TemplateEngine.cached(package="my_tool", autoescape=True)
html.render_string("{{ v }}", {"v": "<b>"})  # "&lt;b&gt;"
```

The `to_toml` and `to_yaml` filters serialize a mapping:

```python
engine.render_string("{{ data | to_toml }}", {"data": {"a": 1}})
```

Other keyword arguments reach `jinja2.Environment`. To render YAML that uses
`{{ }}` itself, move the variable delimiters:

```python
engine = TemplateEngine.cached(
    directory="templates",
    variable_start_string="[[",
    variable_end_string="]]",
)
```

## Markdown

`rn_forge.commons.text.markdown` reads the structure of a Markdown document. It
needs the `markdown` extra and is imported directly, never through
`rn_forge.commons`.

```bash
uv add "rn-forge-commons[markdown]"
```

Anchors follow Python-Markdown's `toc` extension, which MkDocs uses. Links and
tables come from a CommonMark parser, so a link inside code is not a link.

```python
from rn_forge.commons.text.markdown import MarkdownUtils

page = """# Guide

See [setup](setup.md#install) and [the site](https://example.com).

| Name | Role |
| -- | -- |
| ann | dev |
"""

MarkdownUtils.anchors(page)  # {"guide"}
[link for link in MarkdownUtils.links(page) if not MarkdownUtils.is_external(link)]
# ["setup.md#install"]
MarkdownUtils.tables(page)[0].rows  # (("ann", "dev"),)
```
