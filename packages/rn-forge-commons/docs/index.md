# rn-forge-commons

`rn-forge-commons` is the shared utility layer for the `rn-forge-*` Python packages.

It provides:

- structured logging and audit helpers
- nested collection, JSON, and YAML utilities
- config loading with interpolation and inheritance
- dataclass serialization helpers
- subprocess and task-pool abstractions
- managed blocks, structured findings, and testing helpers
- optional pandas and Excel adapters

The developer-tooling surface — console, Typer wiring, local state, templates and installer
mechanics — lives in `rn-forge-tooling`, which depends on this package.

Use the guides for common workflows and the API reference for module details.
