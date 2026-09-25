# E5 — Tool lifecycle

This epic records the implemented tool lifecycle surface. Users follow `rn-forge-tooling` guides for the current `[lifecycle]` contract.

**Status:** done

**Owner:** pykit.

**Implemented:** `757908e`, `1a8241b` (historical commits; no new tag implied).

[Back to the work index](../../index.md)

| Legacy feature | Result |
| --- | --- |
| Commons Part F | Installer mechanics and lifecycle verbs implemented. |
| Lifecycle retirement | `rn-forge-tooling` owns `LifecycleSurface` and `build_tool_app`; `rn-forge-cli` owns the generic `[cli]` declaration. |
| Namespace proposal | Its namespace behavior survives under tooling-owned `[lifecycle]`. |

[ADR-0005](../../../adr/ADR-0005.md) states the ownership choice. Kiln's lifecycle golden repo remains [E12](../E12-kiln-acceptance/index.md). The [ledger](../../../plans/context.md) preserves old section IDs.

## Considered and rejected

The standalone CLI lifecycle-namespace plan was superseded. The old `[cli.lifecycle]` location is not a current contract; no compatibility re-export keeps it alive.
