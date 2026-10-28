# Consuming packages

This guide shows how an application depends on pykit packages by version range.
Every package is published to [PyPI](https://pypi.org/), so a consumer requires
one by name like any other dependency:

```toml
[project]
dependencies = ["rn-forge-commons>=0.7,<0.8"]
```

Before 1.0 the ceiling is the next minor version, because a minor release may
break. From 1.0 it is the next major.

## Moving off the pykit index

Earlier releases were served from a package index at
`https://rn-forge.github.io/pykit/simple/`. A consumer that declared it deletes
the table from `pyproject.toml`, then runs `uv lock`:

```toml
[[tool.uv.index]]
name = "rn-forge"
url = "https://rn-forge.github.io/pykit/simple/"
```

## Pin one exact version

Require `==0.7.1` instead of a range:

```toml
dependencies = ["rn-forge-commons==0.7.1"]
```

## Fall back to a direct URL

To install a tag straight from the repository, pin it by git direct URL with its
subdirectory:

```toml
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.7.1#subdirectory=packages/rn-forge-commons",
]
```

A tag exists once its release is cut. The [release pages](../releases/index.md)
record which tags exist.
