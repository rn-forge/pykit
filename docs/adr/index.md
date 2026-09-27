# Architecture decisions

Each record states one choice that constrains future work across pykit packages, why it was made, and what it costs. Package guides describe the current APIs; the [spec board](../specs/index.md) tracks work.

| Decision | Scope | Status |
| --- | --- | --- |
| [ADR-0001: Standards and proven libraries come first; pykit wraps, never reimplements](ADR-0001.md) | Design principles | accepted |
| [ADR-0002: Code is placed by what its API contains, and boundaries are one-way](ADR-0002.md) | Package placement and imports | accepted |
| [ADR-0003: Optional integrations stay behind explicit extras and outside the facade](ADR-0003.md) | Optional dependencies | accepted |
| [ADR-0004: Packages release independently through pinned git tags](ADR-0004.md) | Package distribution | accepted |
| [ADR-0005: One framework-neutral HTTP contract, adapted natively by each framework](ADR-0005.md) | HTTP contract | accepted |
| [ADR-0006: pykit verifies tokens but does not issue them](ADR-0006.md) | Authentication scope | accepted |
| [ADR-0007: pykit's docs follow the shared rn-forge docs standard](ADR-0007.md) | Documentation structure | accepted |
| [ADR-0008: pykit is accepted by its own specs and tests](ADR-0008.md) | Specs, acceptance and releases | accepted |
| [ADR-0009: Each package publishes its own versioned docs; the root site browses them all](ADR-0009.md) | Package documentation | accepted |
