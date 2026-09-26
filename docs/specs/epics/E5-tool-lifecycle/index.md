# E5 — Tool lifecycle

**Status:** done · **Implemented:** 2026-09-14 to 2026-09-22 · **Owner:** pykit

The install, upgrade and doctor lifecycle a developer tool gets from `rn-forge-tooling`. The tooling lifecycle guide describes the current `[lifecycle]` contract.

[Back to the work index](../../index.md)

| ID | Delivered | Source | Implemented |
| --- | --- | --- | --- |
| F5.1 | Installer mechanics and lifecycle verbs: `$RNF_HOME`, versioned installs, the `current` symlink, `ToolProduct`, and `install`, `upgrade`, `uninstall`, `cleanup`, `status` and `doctor` | Commons plan Part F (kiln Phase C.3) | `757908e` |
| F5.2 | Lifecycle composition moved to tooling: `LifecycleSurface`, `build_tool_app` and the sibling `[lifecycle]` table; `[cli]` stays generic | Lifecycle retirement plan | `1a8241b` |
| F5.3 | The optional lifecycle `namespace`, now under `[lifecycle]` | Lifecycle namespace plan | `1a8241b` |

Rule 3 of [ADR-0002](../../../adr/ADR-0002.md) states the ownership choice: `[cli]` stays generic and lifecycle policy belongs to tooling. A scaffolded tool exercises the lifecycle in [S9.8.2](../E9-release-readiness/F9.8-scaffolded-acceptance.md#s982-a-tool-with-a-lifecycle).

## Considered and rejected

- The CLI-owned `[cli.lifecycle]` table and its `target` field, retired by F5.2. No compatibility re-export keeps it alive.
