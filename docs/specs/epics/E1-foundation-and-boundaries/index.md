# E1 — Foundation and boundaries

**Status:** done · **Implemented:** 2026-09-09 to 2026-09-16 · **Owner:** pykit

The runtime foundation in `rn-forge-commons` and the split of the developer layer into `rn-forge-cli` and `rn-forge-tooling`. The package guides describe current use; [workspace architecture](../../../architecture/workspace.md) describes the boundaries.

[Back to the work index](../../index.md)

| ID | Delivered | Source | Implemented |
| --- | --- | --- | --- |
| F1.1 | Commons runtime foundation: reflection, logging and console, dataclasses, environment guards, resilience, messaging, secret and object-store protocols, structured logging, atomic writes, documents, hashing, paths, merge and entry-point discovery | Commons plan Parts A–C, Phases 0–15 and 17 | `28bef7f` |
| F1.2 | First tooling extraction: local state, the Jinja template engine and installer mechanics. F1.3 corrected its boundary. | Commons plan Phases 12, 16 and 18 | `4624bfe` |
| F1.3 | Three-layer split and re-layout: defect fixes F1–F6, the `rn-forge-cli`/`rn-forge-tooling` split, the injected docs policy, grouped modules with unchanged public names, CI for both packages and the pinned-URL contract | Commons plan Part D (kiln D52, D55, A2) | `f59c40f` |
| F1.4 | CLI reshape: `CliApp`, the console moved to commons, declaration helpers removed | Commons plan Part E | `f59c40f` |
| F1.5 | Strict dataclasses: `DataclassMixin` strict by default with a `LenientDataclassMixin` opt-out; `StrictDataclassMixin` then reintroduced to reject unknown keys | Commons plan E.1a | `37fa7fc`, `231a68e` |
| F1.6 | Optional pydantic `StrictModel` behind the `pydantic` extra. | Commons plan Part G (kiln F4.2) | `231a68e` |

The installer lifecycle built on F1.2 is [E5](../E5-tool-lifecycle/index.md). [ADR-0002](../../../adr/ADR-0002.md), [ADR-0004](../../../adr/ADR-0004.md) and [ADR-0003](../../../adr/ADR-0003.md) constrain future changes. The [ledger](../../../plans/context.md) maps each original phase.

## Considered and rejected

- An OmegaConf resolver (commons Phase 6, rejected at its gate).
- `mergedeep` (Phase 5.1); layered merge with provenance (Phase 14) replaced it.
- A separate YAML `documents` extra (Phase 11.4); one ruamel backend became a base dependency.
- `Environment.rnf_home()` (Phase 18.3); the workstation home convention stays out of commons.
- The E.1 opt-in `StrictDataclassMixin` that made strictness optional; E.1a made strictness the default. The name returned in F1.5 with a different meaning.
