# API Reference

The API reference is generated from source docstrings with `mkdocstrings`.

The modules are listed in the order an application wires them: `problem` first,
because every other adapter raises an exception it renders; `schemas` and
`openapi` for what a generated client sees; then the request dependencies, the
health router and the auth binding.
