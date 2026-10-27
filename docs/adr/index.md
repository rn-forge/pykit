# Architecture decisions

Each record states one choice that constrains future work across pykit packages,
why it was made, and what it costs. Package guides describe the current APIs;
the [spec board](../specs/index.md) tracks work.

| Decision | Scope | Status |
| -- | -- | -- |
| [ADR-0001: Standards and proven libraries come first; pykit wraps, never reimplements](ADR-0001.md) | Design principles | accepted |
| [ADR-0002: Code is placed by what its API contains, and boundaries are one-way](ADR-0002.md) | Package placement and imports | accepted |
| [ADR-0003: Optional integrations stay behind explicit extras and outside the facade](ADR-0003.md) | Optional dependencies | accepted |
| [ADR-0004: Packages release independently under their own tags and version ranges](ADR-0004.md) | Package distribution | accepted |
| [ADR-0005: One framework-neutral HTTP contract, adapted natively by each framework](ADR-0005.md) | HTTP contract | accepted |
| [ADR-0006: pykit verifies tokens an authorization server issued and never issues its own; browsers hold a session, not a token](ADR-0006.md) | Authentication scope | accepted |
| [ADR-0007: pykit's docs follow the shared rn-forge docs standard](ADR-0007.md) | Documentation structure | accepted |
| [ADR-0008: pykit is accepted by its own specs and tests](ADR-0008.md) | Specs, acceptance and releases | accepted |
| [ADR-0009: Each package publishes its own versioned docs; the root site browses them all](ADR-0009.md) | Package documentation | accepted |
| [ADR-0010: Soft delete is a nullable `delete_time` column, in AIP-164's shape](ADR-0010.md) | Soft delete | accepted |
| [ADR-0011: A part of commons becomes its own package only when it passes three tests, and every package takes adapters the same way](ADR-0011.md) | Package boundaries | accepted |
| [ADR-0012: CI and release logic ships as the rn-forge-devops package, never as workflow logic or copied scripts](ADR-0012.md) | CI and release automation | accepted |
| [ADR-0013: Every caller resolves to an internal account, and authorization is computed on the server per request](ADR-0013.md) | Identity resolution and authorization | accepted |
| [ADR-0014: Django and FastAPI expose the same auth HTTP surface and security defaults, over whichever library fits each framework](ADR-0014.md) | Auth framework parity | accepted |
