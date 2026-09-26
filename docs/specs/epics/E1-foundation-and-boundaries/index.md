# E1 — Foundation and boundaries

**Status:** done · **Implemented:** 2026-09-09 to 2026-09-16 · **Owner:** pykit

The runtime foundation in `rn-forge-commons` and the split of the developer layer into `rn-forge-cli` and `rn-forge-tooling`. The package guides describe current use; [workspace architecture](../../../architecture/workspace.md) describes the boundaries.

[Back to the work index](../../index.md)

| ID | Delivered | Implemented |
| --- | --- | --- |
| F1.1 | Commons runtime foundation: reflection, logging and console, dataclasses, environment guards, resilience, messaging, secret and object-store protocols, structured logging, atomic writes, documents, hashing, paths, merge and entry-point discovery | `28bef7f` |
| F1.2 | First tooling extraction: local state, the Jinja template engine and installer mechanics. F1.3 corrected its boundary. | `4624bfe` |
| F1.3 | Three-layer split and re-layout: defect fixes, the `rn-forge-cli`/`rn-forge-tooling` split, the injected docs policy, grouped modules with unchanged public names, CI for both packages and the pinned-URL contract | `f59c40f` |
| F1.4 | CLI reshape: `CliApp`, the console moved to commons, declaration helpers removed | `f59c40f` |
| F1.5 | Strict dataclasses: `DataclassMixin` strict by default with a `LenientDataclassMixin` opt-out; `StrictDataclassMixin` then reintroduced to reject unknown keys | `37fa7fc`, `231a68e` |
| F1.6 | Optional pydantic `StrictModel` behind the `pydantic` extra. | `231a68e` |

The installer lifecycle built on F1.2 is [E5](../E5-tool-lifecycle/index.md). [ADR-0002](../../../adr/ADR-0002.md), [ADR-0004](../../../adr/ADR-0004.md) and [ADR-0003](../../../adr/ADR-0003.md) constrain future changes.

## Considered and rejected

- An OmegaConf resolver, rejected at its gate.
- `mergedeep`; layered merge with provenance replaced it.
- A separate YAML `documents` extra; one ruamel backend became a base dependency.
- `Environment.rnf_home()`; the workstation home convention stays out of commons.
- The first, opt-in `StrictDataclassMixin`, which made strictness optional; strictness became the default instead. The name returned in F1.5 with a different meaning.
