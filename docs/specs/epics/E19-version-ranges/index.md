# E19 — Version ranges between packages

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-10-25 |

Each `rn-forge-*` package pins every other one it needs by one git tag URL
([ADR-0004](../../../adr/ADR-0004.md)). A URL admits exactly one version, and uv
refuses two URLs for one distribution. As a result:

- every additive commons release forces a patch release of each package that
  depends on commons, only to move a pin
  (E18's commons 0.7.0 alone would re-tag seven packages for that reason, which
  is why [F18.5](../E18-kiln-extraction/F18.5-coherent-pins.md) folded into
  F19.3);
- a consumer that takes two packages at different times cannot install them
  together until both are re-tagged on the same commons.

This epic lets packages depend on each other by version range. pykit publishes
a standard package index of its existing release files, and each internal
requirement becomes a range that admits every compatible release. The
coordinated release that switches every package to ranges is the last one that
has to re-tag dependents for a pin.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| -- | -- | -- |
| [F19.1 — How packages find each other by version](F19.1-distribution-decision.md) | The decision: a static PEP 503 index on GitHub Pages of the wheels already on GitHub Releases, ranges between packages, and the compatibility rule; ADR-0004 revised. | Closed |
| [F19.2 — The package index](F19.2-package-index.md) | `rn-forge-devops index` writes the index from GitHub Releases; the docs job publishes it at `/pykit/simple/`; a consumer guide. | New |
| [F19.3 — Internal requirements become ranges](F19.3-internal-ranges.md) | Every internal requirement becomes `name>=floor,<next-breaking`; `rn-forge-devops requirements` checks them in CI; the runbook's re-pin step goes away. | New |

## Context

**What ranges fix, and what they don't.** With ranges, an additive release
(a patch before 1.0, a minor after) needs no release of its dependents. A
consumer simply locks the newest version every range admits. A breaking
release still needs each dependent to widen its upper bound, after checking
that it works on the new version. That is real work and should stay a release.

**What survives the kiln cutover.** The range check and the index publish
live in files pykit owns: a reusable workflow, a composite action, and two
`rn-forge-devops` modules apart from the planner. `main.yml` references them
today. After the cutover, kiln's generated CI references the same files through
`[[ci.jobs]]` and a `[ci.hooks] docs` anchor (kiln F4.11's extension by
reference). Only the `docs` anchor is new kiln work, and it gates the cutover
(F16.3), not this epic.

**What a consumer changes.** A consumer that keeps declaring direct URLs keeps
working: uv lets a root URL requirement satisfy a transitive requirement by
name. A consumer that wants ranges adds one `[[tool.uv.index]]` entry.

## Considered and rejected

- **Exact pins, re-tagging every dependent on each release.** That is today's
  rule. It costs six releases for one additive commons change, and still
  breaks a consumer that takes packages at different times.
- **One version for the whole workspace.** ADR-0004 already rejected it: it
  couples packages whose dependencies and release needs differ.
- **Loosening only the git pins** (a branch instead of a tag). A branch moves
  under a consumer's feet, which is why ADR-0004 ended the `feature/upgrade`
  interim.
