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

The verbs are declared, not written. Add a `[cli.lifecycle]` table beside the
repository's `[cli]` table:

```toml
[cli.lifecycle]
product = "golden_tool.product:PRODUCT"
target = "rn_forge.tooling.cli.lifecycle:lifecycle_commands"
verbs = ["status", "doctor"]    # optional; default: all six
```

`CliApp.from_config` mounts the verbs at the root, which gives
`golden-tool doctor` and `golden-tool status --json`. `rn-forge-cli` is not
allowed to import this package, so `target` names the factory by string.
The table itself is documented with the rest of the declared surface in
`rn-forge-cli`.
