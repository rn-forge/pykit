# Release 7 — security evidence

The result of each [ADR-0015](../../adr/ADR-0015.md) control for this release.
Passing the baseline is not a claim that the release is secure.

[Back to the release](index.md)

| Control | Effect | Result | Evidence |
| -- | -- | -- | -- |
| Dependency audit | Fails on a known vulnerability | Filled at the cut. |  |
| Licence inventory | Fails on GPL, AGPL, SSPL or an unknown licence | Filled at the cut. |  |
| Source scan | Fails | Filled at the cut. |  |
| Secret scan | Fails | Filled at the cut. |  |
| Push protection | Blocks the push; not in CI | Filled at the cut. |  |
| SBOM | Reports; the release fails if it cannot be generated | Filled at the cut. |  |
| Attestation | The release fails if it cannot be produced | Filled at the cut. |  |
| `SECURITY.md` | Reports | Filled at the cut. |  |
| Scorecard | Reports; no threshold | Filled at the cut. |  |
