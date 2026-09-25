# E11 — Framework codegen

This epic tracks deferred Django and FastAPI generator work. Kiln owns the generator integration trigger.

**Status:** deferred

**Readiness:** not ready

**Readiness basis:** Concrete templates, feature scope and executable acceptance have not been elaborated. Entry criteria do not authorize implementation.

**Owner:** kiln integration with pykit framework package owners.

**Entry criteria:** Kiln's generator work starts and has a concrete framework template to generate.

[Back to the work index](../../index.md)

The Django and FastAPI packages have optional `codegen` import fences. The generator implementations do not exist. They will register only through the development extra and remain outside each runtime package's imports.

**Source:** `docs/plans/README.md`, “Waiting on kiln”; kiln D2/D37. The [workspace architecture](../../../architecture/workspace.md) describes the existing fences. No release assignment is implied.
