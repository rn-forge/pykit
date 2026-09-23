# Adoption

This is the **consumer context pack**: what an application's specification is
written against, so that two applications built on this kit do not each
re-derive trace propagation, error bodies, cursors and idempotency semantics in
their own dialect.

| Page | What it is for | Status |
| --- | --- | --- |
| [API conventions](api-conventions.md) | The wire contract every application must follow identically. Written so it can be pasted into a specification as a normative section. | **Normative** |
| [Model conventions](model-conventions.md) | The persistence vocabulary each ORM's base class conforms to without sharing code. Ships no code. | **Normative** for the ORM packages, advisory for applications |
| [Wiring into Django](wiring-django.md) | The full adapter layer for a Django/DRF application. | Guide |
| [Wiring into FastAPI](wiring-fastapi.md) | The full adapter layer for a FastAPI application. | Guide |
| [Checklist](checklist.md) | A per-application review checklist, so divergence is caught in review rather than at integration. | Guide |
| [Worked examples](examples/README.md) | Three applications serving the same ten endpoints — bare ASGI, Django/DRF and FastAPI. Copy one. | Guide |

## What is deliberately not here

Nothing in this pack names a specific application or assumes its domain. If a
sentence only makes sense for one application, it belongs in that
application's repository.

[API conventions](api-conventions.md) is enough on its own to write the
API-behaviour section of an application's specification.
