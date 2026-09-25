# E1 — Foundation and boundaries

This epic records the implemented foundation across `rn-forge-commons`, `rn-forge-cli` and `rn-forge-tooling`. Maintainers use it for implementation evidence; package guides define current use.

**Status:** done

**Owner:** pykit.

**Implemented:** `28bef7f`, `4624bfe`, `f59c40f`, `757908e`, `37fa7fc`, `231a68e` (historical commits; no new tag implied).

[Back to the work index](../../index.md)

| Legacy feature | Result |
| --- | --- |
| Commons Parts A–C | Language, filesystem, runtime and integration mechanisms. |
| Part D | Three package layers, import boundaries and pinned git dependency declarations. |
| Part E and E.1a | `CliApp`, commons console, strict dataclass default and explicit lenient opt-out. |
| Part F | Installer mechanics; current lifecycle composition is recorded in [E5](../E5-tool-lifecycle/index.md). |
| Part G | Optional pydantic `StrictModel`; kiln adoption is tracked in [E12](../E12-kiln-acceptance/index.md). |

Current package boundaries are in [workspace architecture](../../../architecture/workspace.md). [ADR-0001](../../../adr/ADR-0001.md), [ADR-0002](../../../adr/ADR-0002.md) and [ADR-0006](../../../adr/ADR-0006.md) constrain future changes. The [ledger](../../../plans/context.md) maps each original phase.

## Considered and rejected

Commons Phase 6 rejected an OmegaConf resolver. Phase 5.1 did not add `mergedeep`; Phase 11.4 removed the earlier YAML extra design. `Environment.rnf_home()` was withdrawn. The old strict opt-in class was replaced by strict `DataclassMixin`. These are historical choices, not open tasks.
