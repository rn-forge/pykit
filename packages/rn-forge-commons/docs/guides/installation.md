# Installation

Base package:

```bash
uv add rn-forge-commons
```

All optional integrations:

```bash
uv add "rn-forge-commons[all]"
```

Targeted extras:

- `auth` for JWT/JWKS token verification and OIDC discovery (`pyjwt[crypto]`)
- `json` for JSON-formatted log output (`python-json-logger`)
- `excel` for `openpyxl` and `pandas`
- `otel` for OpenTelemetry log correlation
- `pandas` for dataframe helpers
- `pydantic` for strict configuration models (`rn_forge.commons.lang.models`)
- `testing` for `assertpy` test helpers

Docs commands:

```bash
uv run --directory packages/rn-forge-commons --group docs mkdocs serve
uv run --directory packages/rn-forge-commons --group docs mkdocs build
```
