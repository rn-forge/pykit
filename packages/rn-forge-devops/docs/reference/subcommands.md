# Subcommands

Run `rn-forge-devops` from inside a uv workspace. Its root is the nearest
directory at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`.

| Subcommand | Does |
| -- | -- |
| `requirements` | Checks every requirement from one workspace member on another, in dependencies, optional dependencies and dependency groups: it must not be a URL, must admit the member's current version, and must have a `<` or `<=` ceiling. Prints one line per problem to stderr and exits 1 if there are any. |
| `umbrella RELEASES_DIR BODY_FILE --site-url URL` | Reads `git ls-remote --tags --refs origin` output from stdin. When the newest `release-<n>` page whose status starts with `shipped` has no `release-<n>` tag, writes its `## Shipped` section and a link to the page under `URL` to `BODY_FILE`, and prints `tag=` and `title=` lines. Otherwise prints nothing. Exits 1 if `RELEASES_DIR` or `BODY_FILE` is outside the working directory. It does not need a workspace. |
