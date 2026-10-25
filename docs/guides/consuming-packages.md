# Consuming packages

This guide shows how an application depends on pykit packages by version range.
Every package's wheel and sdist are attached to its GitHub Release, and pykit
publishes a [PEP 503](https://peps.python.org/pep-0503/) simple index of those
files at `https://rn-forge.github.io/pykit/simple/` after each release.

## Declare the index

Add the index to the consumer's `pyproject.toml` once, then require packages by
name and range:

```toml
[project]
dependencies = ["rn-forge-commons>=0.7.0,<0.8"]

[[tool.uv.index]]
name = "rn-forge"
url = "https://rn-forge.github.io/pykit/simple/"
```

Before 1.0 the ceiling is the next minor version, because a minor release may
break. From 1.0 it is the next major.

## Use uv

uv's default `first-index` strategy searches a declared index before PyPI and
stops at the first index that has the name. An `rn-forge-*` name therefore
resolves from pykit's index, and a package of that name on PyPI is never
considered.

## The pip caveat

pip's `--extra-index-url` merges indexes and takes the highest version from any
of them. Someone who publishes an `rn-forge-*` name on PyPI with a higher
version would win. Use uv, or install by direct URL.

## Pin one exact version

Require `==0.7.0` instead of a range:

```toml
dependencies = ["rn-forge-commons==0.7.0"]
```

## Fall back to a direct URL

Without the index, pin a tag by git direct URL with its subdirectory:

```toml
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.7.0#subdirectory=packages/rn-forge-commons",
]
```

The [release pages](../releases/index.md) record which tags exist.
