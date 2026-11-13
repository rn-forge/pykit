# E12 — HTTP contract extensions

|  |  |
| -- | -- |
| **State** | Closed |
| **Start Date** | 2026-10-04 |
| **Closed Date** | 2026-10-04 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F12.1 — `:batchGet` and `:batchUpdate`](F12.1-batch-get-update.md) | Closed | release-3 | 5 Closed |
| [F12.2 — Soft delete](F12.2-soft-delete.md) | Closed | release-3 | 7 Closed |
| [F12.3 — Multi-column sorting](F12.3-multi-column-sorting.md) | Closed | release-3 | 6 Closed |
| [F12.9 — `readMask` partial responses](F12.9-read-mask.md) | Closed | release-3 | 5 Closed |
| [F12.12 — Django `RequestUtils` name collision](F12.12-requestutils-name-collision.md) | Closed | release-3 | 1 Closed |
| [F12.14 — JSON Merge Patch](F12.14-merge-patch.md) | Closed | release-3 | 6 Closed |
| [F12.15 — FastAPI resource operations](F12.15-fastapi-resource-operations.md) | Closed | release-3 | 5 Closed |
| [F12.16 — Expose `Content-Disposition` to browsers](F12.16-expose-content-disposition.md) | Closed | release-3 | 1 Closed |

<!-- END derived features -->

Wire features that the
[API conventions](../../../rn-forge-web/guides/api-conventions.md) describe but
no package implements, or only one stack does.
[E2](../E2-http-contract/index.md) delivered the contract; this epic extends it.
A feature whose trigger has fired has its own feature file with stories and
acceptance before any code; the rest are tagged `deferred` until their trigger
occurs.

[Back to the work index](../../index.md)

F12.4 and F12.11 were retired on 2026-09-29; tenancy and Django OIDC settings
are now covered by [E13's design](../E13-auth/design.md). F12.5, F12.6, F12.7,
F12.8, F12.10 and F12.13 were retired the same day, parked in the
[ideas list](../../ideas/index.md) because they are not HTTP contract work.
