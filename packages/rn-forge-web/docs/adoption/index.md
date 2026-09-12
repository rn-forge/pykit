# Adoption

This is the **consumer context pack**: what an application's specification is
written against, so that two applications built on this kit do not each
re-derive correlation IDs, error bodies, cursors and idempotency semantics in
their own dialect.

| Page | What it is for | Status |
| --- | --- | --- |
| [API conventions](api-conventions.md) | The wire contract every application must follow identically. Written so it can be pasted into a specification as a normative section. | **Normative** |
| [Model conventions](model-conventions.md) | The persistence vocabulary each ORM's base class conforms to without sharing code. Ships no code. | **Normative** for the ORM packages, advisory for applications |
| [Wiring into Django](wiring-django.md) | The full adapter layer for a Django/DRF application. | Guide |
| [Wiring into FastAPI](wiring-fastapi.md) | The full adapter layer for a FastAPI application. | Guide |
| [Checklist](checklist.md) | A per-application review checklist, so divergence is caught in review rather than at integration. | Guide |
| [Worked examples](examples/README.md) | Three applications serving the same ten endpoints — bare ASGI, Django/DRF and FastAPI. Copy one. | Guide |

## The test the two wiring guides are

If either wiring guide runs past about a page, the package boundary is wrong
and this design should be revisited — the whole argument for a separate
`rn-forge-web` is that each framework needs only a thin adapter over it. The
guides are kept short on purpose, and their length is a signal, not a
formatting preference.

## What is deliberately not here

Nothing in this pack names a specific application or assumes its domain. If a
sentence only makes sense for one application, it belongs in that
application's repository.

## Exit criterion

Someone writing an application specification can produce the API-behaviour
section of that spec from [api-conventions.md](api-conventions.md) alone,
without reading this package's source or its plan.
