# Tool lifecycle

`rn_forge.tooling.install` gives an installable tool its `install`, `upgrade`,
`uninstall`, `cleanup`, `status` and `doctor` verbs. The tool describes itself
with a `ToolProduct`; this package owns every algorithm around that
description.

## The layout under `$RNF_HOME`

```text
$RNF_HOME/                      default ~/.rn-forge
  bin/golden-tool -> ../golden-tool/current/bin/golden-tool
  golden-tool/
    versions/1.0.0/             one directory per installed version
    current -> versions/1.0.0   swapped atomically
    state.json                  installed version and state schema
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
| --- | --- | --- |
| `release_source` | `GitHubReleases(repo)` | publish somewhere else, or verify a checksum asset |
| `state_schema_version` | `1` | have `doctor` report an install recorded under an older schema |
| `artifacts()` | nothing | put links on `PATH` |
| `checks()` | none | add product rows to `doctor` |
| `build(release_root, version_dir)` | copy the tree | build an environment in place |
| `migrate(frm, to)` | nothing | move state between versions |

Return an `info` finding from a passing check rather than nothing, so `doctor`
shows that the check ran.

## What `install` guarantees

`install` runs in the same shape as `generation.apply`:

1. fetch into scratch space and verify the checksum, if the source publishes one;
2. set aside an existing directory for the same version, then build the new one;
3. put the links in place, backing up any link already there;
4. migrate from the active version, then write `state.json`;
5. swap `current` **last**.

If any step raises, the steps already taken are undone in reverse, and the
previous version is active again. An `Exception` is re-raised as an
`AppException`. An interruption (`KeyboardInterrupt`) is re-raised as-is,
after the rollback.

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
| --- | --- | --- |
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
| --- | --- |
| `product` | import path of the `ToolProduct` |
| `verbs` | any of `install`, `upgrade`, `uninstall`, `cleanup`, `status`, `doctor` |
| `namespace` | optional sub-command group the verbs are mounted under |

Without `namespace`, `build_tool_app` mounts the verbs at the root:
`golden-tool doctor`, not `golden-tool lifecycle doctor`. With `namespace =
"self"`, they mount as a group instead: `golden-tool self doctor`, the same
shape as `uv self update` or `rustup self update`.

Whether a verb collides with a `[[cli.commands]]` name depends on the
namespace: without one, the verbs and the commands share the root, so a verb
may not repeat a command's name. With a namespace, only the namespace itself
occupies the root — a command may share a verb's name (e.g. a root `doctor`
next to `self doctor`), but not the namespace's own name. Either way, an
unknown verb, a blank or whitespace-containing namespace, or an unimportable
product raises before the application is built.

`build_tool_app` builds the application from `[cli]` with `CliSurface.load` and
`CliApp.from_surface`, then adds the verbs with `CliApp.add_typer`. A repository
that declares `[lifecycle]` depends on `rn-forge-tooling`; one that only needs
`[cli]` uses `CliApp.from_config` and does not.
