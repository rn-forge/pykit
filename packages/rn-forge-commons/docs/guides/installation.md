# Installation

Base package:

```bash
uv add "rn-forge-commons>=0.8,<0.9"
```

All optional integrations:

```bash
uv add "rn-forge-commons[all]>=0.8,<0.9"
```

Targeted extras:

- `json` for JSON-formatted log output (`python-json-logger`)
- `markdown` for Markdown structure (`rn_forge.commons.text.markdown`)
- `otel` for OpenTelemetry log correlation
- `pydantic` for strict configuration models (`rn_forge.commons.lang.models`)
- `templates` for the Jinja template engine (`rn_forge.commons.text.templates`)
- `testing` for `assertpy` test helpers

Docs commands:

```bash
uv run --directory packages/rn-forge-commons --group docs mkdocs serve
uv run --directory packages/rn-forge-commons --group docs mkdocs build
```
