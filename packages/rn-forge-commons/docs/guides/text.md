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
