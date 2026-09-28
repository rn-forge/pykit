# E14 — Workspace CI

**Status:** in progress

A CI pipeline that finds the workspace's packages from the uv manifests instead of naming them, so the same workflow runs any uv monorepo of separately released packages. pykit is the reference; kiln's golden templates adopt it from here.

[Back to the work index](../../index.md)

| Feature | Status | Scope |
| --- | --- | --- |
| [F14.1 — Discovered pipeline](F14.1-discovered-pipeline.md) | in progress | Plan every job from the manifests; keep per-package release gating. |

**Source:** owner request, 2026-09-28.
