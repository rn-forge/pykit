# Installation

## Install from PyPI

Require the package by version range:

```toml
[project]
dependencies = ["rn-forge-web>=0.3,<0.4"]
```

Its dependencies are `rn-forge-commons[pydantic]` and `opentelemetry-api`. The
`security` extra adds `secure`, for `rn_forge.web.security`; the `testing` extra
adds `assertpy` and `pytest`.

## Inside this workspace

The workspace resolves this package to the local checkout, for development only;
see the
[workspace boundaries](https://rn-forge.github.io/pykit/architecture/workspace/)
page. The package imports no web framework, `rn_forge.cli` or
`rn_forge.tooling`; `task lint` proves it.
