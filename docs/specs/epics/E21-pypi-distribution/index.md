# E21 — Publish to PyPI

|  |  |
| -- | -- |
| **State** | Closed |
| **Start Date** | 2026-10-26 |
| **Closed Date** | 2026-11-14 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F21.1 — PyPI as the index](F21.1-pypi-decision.md) | Closed | release-7 | 2 Closed |
| [F21.2 — Package metadata for PyPI](F21.2-package-metadata.md) | Closed | release-7 | 1 Closed |
| [F21.3 — Publish from the release job](F21.3-publish-from-release.md) | Closed | release-7 | 5 Closed |
| [F21.4 — Consumers install from PyPI](F21.4-consumer-docs.md) | Closed | release-7 | 1 Closed |
| [F21.5 — Retire the self-hosted index](F21.5-retire-index.md) | Closed | release-8 | 1 Closed |

<!-- END derived features -->

pykit serves its packages from its own PEP 503 index at
`https://rn-forge.github.io/pykit/simple/`, built from the files attached to
each package's GitHub Release ([ADR-0004](../../../adr/ADR-0004.md)). As a
result, every consumer has to declare that index, pip users are exposed to a
same-named package on PyPI, and the Releases page doubles as file hosting: nine
releases per run, a "Latest" label on whichever package was tagged last, and
generated notes that compare against another package's tag. Neither kiln nor any
other library that depends on pykit can be published to PyPI itself, because
PyPI rejects a direct-URL requirement.

This epic publishes every `rn-forge-*` package to PyPI with trusted publishing.
PyPI becomes the index, the GitHub Releases page goes back to being a
human-readable record with one "Latest" release per shipped release page, and
the self-hosted index retires once consumers have moved.

[Back to the work index](../../index.md)

## Context

**What changes between pykit's packages.** Very little, because E19 already made
every internal requirement a range. A range now resolves from pypi.org instead
of the self-hosted index, a PyPI version is immutable (a bad release is fixed by
the next patch), and pykit owns its names on PyPI, so the dependency-confusion
caveat disappears. The rules are in [ADR-0004](../../../adr/ADR-0004.md).

**What changes for consumers.** A consumer stops declaring the pykit index and
requires a package by name and range; the
[consuming guide](../../../guides/consuming-packages.md) has the usage. Owner
decision, 2026-11-03: F21.5 is scheduled in Release 8 and lands before the kiln
cutover, since no consumer lock names the index.

**Ordering with the kiln cutover.**

- F21.3 was built in `main.yml`, in Release 7.
- [F16.3](../E16-kiln-adoption/F16.3-cutover.md) deletes `main.yml`, so it
  requires the kiln version it pins to render the same release behaviour. The
  umbrella release is a reusable workflow that pykit owns, which the cutover
  declares as a `[[ci.jobs]]` entry, so that part survives unchanged.
- [F21.5](F21.5-retire-index.md) lands before the cutover, so the cutover has no
  index to carry and declares no `[ci.hooks] docs` anchor.
- PyPI's trusted publishers name the workflow file, so the cutover also adds a
  publisher for `ci.yml`.

**Owner decisions, 2026-10-26:**

- the licence is MIT;
- every package takes a patch release so its first PyPI upload carries complete
  metadata, and earlier versions are not backfilled;
- publishing is built in `main.yml` now, and kiln matches it at the cutover;
- the "Latest" release is `release-<n>`, taken from the release pages.

## Considered and rejected

- **Keep the self-hosted index and fix only the Releases page**
  (`--latest=false`, changelog notes). That fixes how the page looks, but
  keeps the index declaration for every consumer, the pip caveat, and the
  block on publishing kiln to PyPI.
- **GitHub Packages.** It has no Python registry.
- **A hosted private index** (CodeArtifact, Artifact Registry, Gemfury). The
  repository is public, so it adds an account and consumer credentials for no
  benefit.
- **Waiting for the cutover and building publishing in kiln only.** It avoids
  building the release change twice, but makes PyPI wait on kiln's schedule.
- **Backfilling the current tags to PyPI.** Those builds have no licence
  metadata, and PyPI keeps a version's metadata forever.
- **A dated umbrella release on every run, or none at all.** Dated tags do not
  match the release pages. With no umbrella, nothing on the Releases page is
  marked "Latest".
