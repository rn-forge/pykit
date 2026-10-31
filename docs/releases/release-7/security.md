# Release 7 — security evidence

The result of each [ADR-0015](../../adr/ADR-0015.md) control for this release.
Passing the baseline is not a claim that the release is secure. The rows record
the [publish run](https://github.com/rn-forge/pykit/actions/runs/41151600463) on
`a038a0d`.

[Back to the release](index.md)

| Control | Effect | Result | Evidence |
| -- | -- | -- | -- |
| Dependency audit | Fails on a known vulnerability | Passed on `a038a0d`. | [`dependency-audit` job](https://github.com/rn-forge/pykit/actions/runs/41151600463/job/124389148999) |
| Licence inventory | Fails on GPL, AGPL, SSPL or an unknown licence | Passed on `a038a0d`. | [`licenses` job](https://github.com/rn-forge/pykit/actions/runs/41151600463/job/124389148959) |
| Source scan | Fails | Passed on `a038a0d`: ruff with the `S` rules ran in every package's `verify` job. | [`verify (rn-forge-commons)` job](https://github.com/rn-forge/pykit/actions/runs/41151600463/job/124389260495) and the other nine `verify` jobs of [the run](https://github.com/rn-forge/pykit/actions/runs/41151600463) |
| Secret scan | Fails | Passed on `a038a0d`. | [`secret-scan` job](https://github.com/rn-forge/pykit/actions/runs/41151600463/job/124389148937) |
| Push protection | Blocks the push; not in CI | Enabled. | `gh api repos/rn-forge/pykit --jq .security_and_analysis` returns `secret_scanning_push_protection` `enabled` on 2026-10-30 |
| SBOM | Reports; the release fails if it cannot be generated | Generated for all ten packages and attached to each GitHub release as `<name>-<version>.cdx.json`. | [`release` job](https://github.com/rn-forge/pykit/actions/runs/41151600463/job/124390093505) |
| Attestation | The release fails if it cannot be produced | GitHub build provenance and PyPI PEP 740 attestations are both proven. `gh attestation verify -R rn-forge/pykit` on the `rn-forge-commons` 0.8.1 wheel exits 0. PyPI's integrity API returns provenance (HTTP 200) for all ten wheels; for `rn-forge-commons` 0.8.1 it is a version 1 bundle with publisher kind GitHub, repository `rn-forge/pykit`, workflow `main.yml` and environment `pypi`. `rn-forge-commons` 0.8.0, published without attestations, returns 404. | [`release` job](https://github.com/rn-forge/pykit/actions/runs/41151600463/job/124390093505), and `https://pypi.org/integrity/<name>/<version>/<wheel>/provenance` |
| `SECURITY.md` | Reports | Present at the repository root. | [`SECURITY.md`](https://github.com/rn-forge/pykit/blob/main/SECURITY.md) |
| Scorecard | Reports; no threshold | Score 7.2 on `a038a0d` (Scorecard v5.6.0). | [Scorecard run](https://github.com/rn-forge/pykit/actions/runs/41151600436) |
