# Subcommands

Run `rn-forge-devops` from inside a uv workspace. Its root is the nearest
directory at or above the current one whose `pyproject.toml` declares
`[tool.uv.workspace]`.

| Subcommand | Does |
| -- | -- |
| `requirements` | Checks every requirement from one workspace member on another, in dependencies, optional dependencies and dependency groups: it must not be a URL, must admit the member's current version, and must have a `<` or `<=` ceiling. Prints one line per problem to stderr and exits 1 if there are any. |
| `umbrella RELEASES_DIR BODY_FILE --site-url URL` | Reads `git ls-remote --tags --refs origin` output from stdin. When the newest `release-<n>` page whose status starts with `shipped` has no `release-<n>` tag, writes its `## Shipped` section and a link to the page under `URL` to `BODY_FILE`, and prints `tag=` and `title=` lines. Otherwise prints nothing. Exits 1 if `RELEASES_DIR` or `BODY_FILE` is outside the working directory. It does not need a workspace. |

## Requirements contract

Exit codes for `requirements`:

| Code | Meaning |
| -- | -- |
| 0 | No problems. |
| 1 | At least one incompatible requirement: a URL, a range excluding the member's version, or no `<`/`<=` ceiling. One stderr line per problem. |
| 2 | Invalid input; nothing was judged. Prints a diagnostic to stderr without a traceback. |

Invalid input means a malformed requirement string, a member manifest missing
`[project]` or `name`, an unparsable `[project].version`, a workspace table
without `members`, or no workspace found. Manifest diagnostics use
`<manifest path>: <reason>` and include the malformed requirement text.

Checked forms:

- `dependencies`, every `optional-dependencies` list, and string items in
  `[dependency-groups]`.
- Canonicalized names: `Rn_Forge.Cli` matches `rn-forge-cli`.
- Extras and ranges, such as `a[x]>=1,<2`.
- Direct URLs or paths on members, such as `a @ https://x/a.whl`, reported as
  URL problems.
- Marked requirements, checked as if unmarked.
- Only `<` or `<=` counts as a ceiling; `~=` and `==` report no ceiling.

Outside the contract and silently skipped:

- Requirements on non-members, including excluded members.
- `include-group` entries in dependency groups.
- Member globs matching no manifest.
- Version checks for members without `version`; the ceiling check still runs.
- Self-references.
