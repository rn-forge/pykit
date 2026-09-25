# Architecture decisions

These records explain the choices that govern work across pykit packages. Package guides describe the current APIs; the [spec board](../specs/index.md) tracks work and release questions.

**Status:** done

**Owner:** pykit.

| Decision | Scope | Status |
| --- | --- | --- |
| [ADR-0001: Libraries follow explicit runtime and tooling boundaries](ADR-0001.md) | Package graph and imports | accepted |
| [ADR-0002: Packages release independently through pinned git tags](ADR-0002.md) | Package distribution | accepted |
| [ADR-0003: Standards and adopted frameworks precede pykit wrappers](ADR-0003.md) | Cross-stack design | accepted |
| [ADR-0004: Frameworks share HTTP contracts without sharing an ORM abstraction](ADR-0004.md) | HTTP and persistence | accepted |
| [ADR-0005: Tooling owns lifecycle composition; cli stays generic](ADR-0005.md) | Command-line lifecycle | accepted |
| [ADR-0006: Optional integrations stay behind explicit extras and import boundaries](ADR-0006.md) | Optional dependencies | accepted |
| [ADR-0007: Package usage docs and monorepo governance have separate homes](ADR-0007.md) | Documentation ownership | accepted |
