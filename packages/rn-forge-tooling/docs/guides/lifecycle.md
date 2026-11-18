# Tool lifecycle

`rn_forge.tooling.install` gives an installable tool its `install`, `upgrade`,
`uninstall`, `cleanup`, `status` and `doctor` verbs. The tool describes itself
with a `ToolProduct`; this package owns every algorithm around that description.

## The layout under `$RNF_HOME`

```text
$RNF_HOME/                      default ~/.rn-forge
  bin/golden-tool -> ../golden-tool/current/bin/golden-tool
  golden-tool/
    versions/1.0.0/             one directory per installed version
    current -> versions/1.0.0   swapped atomically
    state.json                  version, ref, commit, schema_version
    .lock/                      held by every verb that writes
```

`ToolHome` holds these paths. Links point *through* `current`, so an upgrade
changes what they resolve to without touching them.

## Describing a product

Every member except the name and version has a default:

```python
from rn_forge.tooling.install import ToolProduct

PRODUCT = ToolProduct(name="golden-tool", version=__version__, repo="rn-forge/golden-tool")
```

Override only what the tool needs:

```python
from collections.abc import Sequence

from rn_forge.commons.findings import Finding, Severity
from rn_forge.tooling.install import Check, Link, ToolHome, ToolProduct


def config_readable(home: ToolHome) -> list[Finding]:
    return [Finding("golden.config", Severity.INFO, "config is readable")]


class GoldenTool(ToolProduct):
    def artifacts(self) -> Sequence[Link]:
        return (Link("bin/golden-tool", "bin/golden-tool"),)

    def checks(self) -> Sequence[Check]:
        return (config_readable,)


PRODUCT = GoldenTool(name="golden-tool", version=__version__, repo="rn-forge/golden-tool")
```

| Member | Default | Override to |
| -- | -- | -- |
| `release_source` | `GitHubReleases(repo)` | publish somewhere else, or verify a checksum asset |
| `state_schema_version` | `1` | have `doctor` report an install recorded under an older schema |
| `artifacts()` | nothing | put links on `PATH` |
| `checks()` | none | add product rows to `doctor` |
| `preflight()` | nothing | refuse an install before it writes anything |
| `build(release_root, version_dir)` | copy the tree | build an environment in place |
| `migrate(frm, to)` | nothing | move state between versions |

Return an `info` finding from a passing check rather than nothing, so `doctor`
shows that the check ran.

## Installing a branch, tag or commit

`install --ref <ref>` installs the commit a branch, tag or commit SHA of the
product's GitHub repository names, with no release needed. It is exclusive with
`--version` and `--archive`, and the product's source must be a
`GitHubReleases`. The version directory is named for the commit's first 12
characters.

`state.json` records what was asked for and what was installed:

| Key | Holds |
| -- | -- |
| `version` | the package version the build reports, from the built tree's `pyproject.toml`; the target when absent |
| `ref` | the ref as given, or the release tag for a release install |
| `commit` | the 40-character SHA for a ref install, `null` for a release install |
| `schema_version` | the product's state schema version |

A state recorded before `ref` existed reads as a release install whose `ref` is
the release tag.

- `upgrade` re-resolves a ref install's `ref`, and returns `already-current`
  when the commit has not moved. A release install moves to the newest
  release.
- `status` prints `installed: <version> (<ref> @ <commit 12>)` for a ref
  install; its `--json` carries `ref`, `commit` and `package_version`.
- `doctor`'s `install.version-mismatch` compares the running version with
  `state.json`'s `version`, not the directory name.

## Python tools

`PythonTool` is a `ToolProduct` for a tool released as a Python package:

```python
from rn_forge.tooling.install import PythonTool

PRODUCT = PythonTool(name="golden-tool", version=__version__, repo="rn-forge/golden-tool")
```

Its `build` runs `uv tool install` on the release tree with `UV_TOOL_DIR` and
`UV_TOOL_BIN_DIR` inside the version directory, so the console script lands in
`<version>/bin/<name>` and the default `artifacts()` link `bin/<name>` runs it
through `current`. The package must declare a console script named like the
product. `uv` must be on `PATH`; without it the install is refused before
anything is written. `uninstall` removes the uv environment with the version
directory.

## What `install` guarantees

`install` runs in the same shape as `rn_forge.commons.generation.apply`:

1. fetch into scratch space and verify the checksum, if the source publishes
   one;
1. set aside an existing directory for the same version, then build the new one;
1. put the links in place, backing up any link already there;
1. migrate from the active version, then write `state.json`;
1. swap `current` **last**.

If any step raises, every undo step is attempted in reverse, even if an undo
step fails. An `Exception` is re-raised as an `AppException` with the initiating
failure as its cause. Its message says "rolled back" only when every undo step
succeeded; otherwise it says `recovery is incomplete` and names each failed step
and its error. An interruption such as `KeyboardInterrupt` is re-raised as-is
after recovery, with recovery failures logged at error level.

If restoring a displaced version fails, it survives in a unique transaction
directory under `$RNF_HOME/<product>/.work`, at the reported path. `cleanup`
keeps that directory and warns with its path; later installs leave it alone.
Recover the previous version by hand, then remove the retained directory.
`uninstall` still removes the whole product directory, including retained
versions. For interruptions, the retained path is logged at error level.

Other verbs:

- `uninstall` does not assume the install ever completed.
- `uninstall` removes a link only if it still points where the install put it.
- A regular file standing where a link should go aborts the install instead of
  being replaced.

## `doctor` in a development checkout

A product that is not installed is a **warning**, not an error. The same
`doctor` runs from a development checkout, where nothing is under `$RNF_HOME`
and nothing is wrong. The product's own checks run either way.

| Code | Severity | Meaning |
| -- | -- | -- |
| `install.not-installed` | warning | no `current` link |
| `install.ok` | info | the install checks found nothing |
| `install.current-broken` | error | `current` points at a missing version |
| `install.version-mismatch` | warning | the running code is not the installed version |
| `install.state-unreadable` | warning | `state.json` is missing or malformed |
| `install.state-schema` | error | state was recorded under another schema version |
| `install.link-missing` / `install.link-broken` | error | an artifact link is absent, foreign or dangling |

## Exposing the verbs on a command line

The verbs are declared, not written. Add a `[lifecycle]` table beside the
repository's `[cli]` table, and build the application with `build_tool_app`
instead of `rn-forge-cli`'s own `CliApp.from_config`:

```toml
[cli]
name = "golden-tool"

[lifecycle]
product = "golden_tool.product:PRODUCT"
verbs = ["status", "doctor"]    # optional; default: all six
namespace = "self"              # optional; default: mounted at the root
```

```python
from pathlib import Path

from rn_forge.tooling.cli.lifecycle import build_tool_app

app = build_tool_app(Path(__file__).parent / "cli.toml")
```

| Key | Meaning |
| -- | -- |
| `product` | import path of the `ToolProduct` |
| `verbs` | any of `install`, `upgrade`, `uninstall`, `cleanup`, `status`, `doctor` |
| `namespace` | optional sub-command group the verbs are mounted under |

Without `namespace`, `build_tool_app` mounts the verbs at the root:
`golden-tool doctor`, not `golden-tool lifecycle doctor`. With
`namespace = "self"`, they mount as a group instead: `golden-tool self doctor`,
the same shape as `uv self update` or `rustup self update`.

Whether a verb collides with a `[[cli.commands]]` name depends on the namespace:
without one, the verbs and the commands share the root, so a verb may not repeat
a command's name. With a namespace, only the namespace itself occupies the root
— a command may share a verb's name (e.g. a root `doctor` next to
`self doctor`), but not the namespace's own name. Either way, an unknown verb, a
blank or whitespace-containing namespace, or an unimportable product raises
before the application is built.

`build_tool_app` builds the application from `[cli]` with `CliSurface.load` and
`CliApp.from_surface`, then adds the verbs with `CliApp.add_typer`. A repository
that declares `[lifecycle]` depends on `rn-forge-tooling`; one that only needs
`[cli]` uses `CliApp.from_config` and does not.
