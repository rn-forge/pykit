# E12 — HTTP contract extensions

| | |
| --- | --- |
| **State** | New |

Wire features that the [API conventions](../../../rn-forge-web/guides/api-conventions.md) describe but no package implements, or only one stack does. [E2](../E2-http-contract/index.md) delivered the contract; this epic extends it. A feature whose trigger has fired has its own feature file with stories and acceptance before any code; the rest are tagged `deferred` until their trigger occurs.

[Back to the work index](../../index.md)

| Feature | Scope | Trigger | Tags | State |
| --- | --- | --- | --- | --- |
| F12.1 | `:batchGet` and `:batchUpdate` handlers; the spelling is already documented | A consumer needs the handlers. | deferred | New |
| F12.2 | Soft delete in AIP-164's shape: `deleteTime`, `:undelete`, `showDeleted`. Conflicts with the status-based soft delete in the [model-vocabulary](../../ideas.md#model-vocabulary) idea; whichever is taken up first settles the other. | A consumer needs soft delete on the wire. | deferred | New |
| F12.3 | Multi-column sorting, with composite keysets and NULL ordering | The owner starts the ideation. | deferred | New |
| F12.9 | AIP-157 `readMask` partial responses | Payload size makes partial responses necessary. | deferred | New |
| [F12.12 — Django `RequestUtils` name collision](F12.12-requestutils-name-collision.md) | Remove `rn_forge.django.utils.RequestUtils` (its `debug_request` moves to `rn_forge.django.views`) and the DRF module's compatibility aliases, so one `RequestUtils` remains | Fired 2026-09-29: F12.14 is a breaking change to `rn-forge-django`, and the owner approved carrying this one with it. | — | New |
| [F12.14 — JSON Merge Patch](F12.14-merge-patch.md) | JSON Merge Patch (RFC 7396): the merge in `rn-forge-web`, the media type and its conformance cases, and the Django and FastAPI bindings | Fired 2026-09-28: a browser client's resource screen sends `application/merge-patch+json`. | — | New |
| [F12.15 — FastAPI resource operations](F12.15-fastapi-resource-operations.md) | FastAPI route factories for `:import`, `:importTemplate`, `:batchCreate`, `:batchDelete` and capped export, over application stores; the shared transfer details moved into `rn-forge-web` | Fired 2026-09-28: a browser client's resource screen needs a FastAPI backend serving every row of the resource standards. | — | New |
| [F12.16 — Expose `Content-Disposition` to browsers](F12.16-expose-content-disposition.md) | `Content-Disposition` in `EXPOSED_HEADERS`, so a cross-origin browser can read export file names | Fired 2026-09-28: a cross-origin browser client could not read an export's file name. | — | New |

F12.4 and F12.11 were retired on 2026-09-29, now [E13's open questions](../E13-auth/F13.1-auth-design.md#open-questions) on tenancy and Django OIDC settings. F12.5, F12.6, F12.7, F12.8, F12.10 and F12.13 were retired the same day, parked in the [ideas list](../../ideas.md) because they are not HTTP contract work.
