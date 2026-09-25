# Adoption

This is the **consumer context pack**: what an application's specification is
written against, so that two applications built on this kit do not each
re-derive trace propagation, error bodies, cursors and idempotency semantics in
their own dialect.

| Page | What it is for | Status |
| --- | --- | --- |
| [API conventions](api-conventions.md) | The wire contract every application must follow identically. Written so it can be pasted into a specification as a normative section. | **Normative** |
| [Model conventions](model-conventions.md) | Implemented Django and SQLAlchemy building blocks, with application design advice called out separately. | Guide |
| [Wiring into Django](wiring-django.md) | A plain Django/DRF composition recipe. The `rn-forge-django` quickstart is the package adapter guide. | Guide |
| [Wiring into FastAPI](wiring-fastapi.md) | A pointer to the `rn-forge-fastapi` wiring guide. | Pointer |
| [Checklist](checklist.md) | A per-application review checklist, so divergence is caught in review rather than at integration. | Guide |
| [Worked examples](examples/index.md) | Three applications serving the same ten endpoints — bare ASGI, Django/DRF and FastAPI. Copy one. | Guide |

## What is deliberately not here

Nothing in this pack names a specific application or assumes its domain. If a
sentence only makes sense for one application, it belongs in that
application's repository.

[API conventions](api-conventions.md) is enough on its own to write the
API-behaviour section of an application's specification.
