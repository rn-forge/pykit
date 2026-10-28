# E21 — Publish to PyPI

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-10-26 |

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

| Feature | Scope | State |
| -- | -- | -- |
| [F21.1 — PyPI as the index](F21.1-pypi-decision.md) | The decision, with ADR-0004 revised; the PyPI organization and GitHub environments set up by the owner. | Closed |
| [F21.2 — Package metadata for PyPI](F21.2-package-metadata.md) | The MIT licence, classifiers and a patch release of every package, so each one passes `twine check --strict`. | Closed |
| [F21.3 — Publish from the release job](F21.3-publish-from-release.md) | `main.yml` uploads each package to PyPI via OIDC, with a TestPyPI dry run; per-package GitHub releases take their changelog section as notes and are never "Latest"; an umbrella `release-<n>` release per shipped release page; external install checked from PyPI. | Active |
| [F21.4 — Consumers install from PyPI](F21.4-consumer-docs.md) | The README, consuming guide, per-package install guides and release runbook describe PyPI with no index declaration. | Closed |
| [F21.5 — Retire the self-hosted index](F21.5-retire-index.md) | `rn-forge-devops index`, its adapter, the `package-index` action and `simple/` on Pages are removed. | New |

## Context

**What changes between pykit's packages.** Very little, because E19 already made
every internal requirement a range (`rn-forge-commons>=0.7.0,<0.8`).

- **Unchanged:**
    - the requirement lines;
    - `[tool.uv.sources] … = { workspace = true }` for local development;
    - the floor/ceiling and bump rules;
    - the `internal-ranges` check;
    - dependency-ordered release.
- **What changes is where a range resolves outside the repo:** pypi.org instead
  of `rn-forge.github.io/pykit/simple/`. A built wheel's metadata is
  identical.
- **A PyPI version is immutable.** It cannot be deleted and re-uploaded, only
  yanked. A rerun skips a version PyPI already has, and a bad release is fixed
  by the next patch.
- **Partial runs stay safe.** Upload happens in dependency order, so a dependent
  is never uploaded before the floor it names.
- **The dependency-confusion caveat disappears.** pykit owns the names on PyPI,
  so `first-index` and the pip warning are no longer needed.

**What changes for consumers.** A consumer stops declaring
`[[tool.uv.index]] name = "rn-forge"` and just requires
`rn-forge-commons>=0.7.0,<0.8`. Its `uv.lock` changes each `rn-forge-*` source
to pypi.org on the next `uv lock`. Direct git-URL pins keep working, since tags
are still created. The self-hosted index stays up until F21.5, so a lock that
still names it keeps resolving in the meantime.

**Ordering with the kiln cutover.**

- F21.3 is built in `main.yml` now, in Release 7.
- [F16.3](../E16-kiln-adoption/F16.3-cutover.md) deletes `main.yml`, so it
  requires the kiln version it pins to render the same release behaviour. The
  umbrella release is a reusable workflow that pykit owns, which the cutover
  declares as a `[[ci.jobs]]` entry, so that part survives unchanged.
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
