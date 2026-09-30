# E11 — Framework codegen

| | |
| --- | --- |
| **State** | New |
| **Tags** | deferred |
| **Entry criteria** | the owner schedules it with a concrete framework template to generate |

Code generators for Django and FastAPI applications, shipped as each framework package's `codegen` extra and run by a scaffolding tool through an entry point.

[Back to the work index](../../index.md)

Both framework packages have a `codegen` import fence in `.importlinter`, and nothing behind it. A generator will live in `rn_forge.django.codegen` or `rn_forge.fastapi.codegen`, register under the `rn_forge.kiln.generators` entry-point group, install only with the `codegen` extra, and stay outside the runtime package's imports ([ADR-0003](../../../adr/ADR-0003.md)). The [workspace architecture](../../../architecture/workspace.md) describes the fences.
