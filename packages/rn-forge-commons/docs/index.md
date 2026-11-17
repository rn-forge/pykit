# rn-forge-commons

`rn-forge-commons` is the shared utility layer for the `rn-forge-*` Python
packages.

It provides:

- structured logging and audit helpers
- nested collection, JSON, and YAML utilities
- config loading with interpolation and inheritance
- dataclass serialization helpers
- subprocess and task-pool abstractions
- managed blocks, structured findings, and testing helpers
- a locked JSON state store and a generation engine (plan, diff, atomic apply)

The developer-tooling surface — console, Typer wiring, local state and installer
mechanics — lives in `rn-forge-tooling`, which depends on this package.

## Install

```toml
dependencies = ["rn-forge-commons>=0.9,<0.10"]
```

Extras: `json`, `structlog`, `resilience`, `otel`, `pydantic`, `markdown`,
`templates`, `testing` and `all`; see [Installation](guides/installation.md).
Minimum example: [Quickstart](guides/quickstart.md). Failures a caller handles
are `AppException`s carrying a message, an integer `error_code` and
`error_data`.

Use the guides for common workflows and the API reference for module details.
