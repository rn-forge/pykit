# Release 7 — security evidence

The result of each [ADR-0015](../../adr/ADR-0015.md) control for this release.
Passing the baseline is not a claim that the release is secure. The rows record
the run on `ed566a0`; the publish run at the cut refreshes them.

[Back to the release](index.md)

| Control | Effect | Result | Evidence |
| -- | -- | -- | -- |
| Dependency audit | Fails on a known vulnerability | Passed on `ed566a0`. | [`dependency-audit` job](https://github.com/rn-forge/pykit/actions/runs/41066847153/job/124100374520) |
| Licence inventory | Fails on GPL, AGPL, SSPL or an unknown licence | Passed on `ed566a0`. | [`licenses` job](https://github.com/rn-forge/pykit/actions/runs/41066847153/job/124100374396) |
| Source scan | Fails | Passed on `ed566a0`: ruff with the `S` rules ran in every package's `verify` job. | [`verify (rn-forge-commons)` job](https://github.com/rn-forge/pykit/actions/runs/41066847153/job/124100532361) and the other nine `verify` jobs of [the run](https://github.com/rn-forge/pykit/actions/runs/41066847153) |
| Secret scan | Fails | Passed on `ed566a0`. | [`secret-scan` job](https://github.com/rn-forge/pykit/actions/runs/41066847153/job/124100374741) |
| Push protection | Blocks the push; not in CI | Enabled. | `gh api repos/rn-forge/pykit --jq .security_and_analysis` returns `secret_scanning_push_protection` `enabled` on 2026-10-30 |
| SBOM | Reports; the release fails if it cannot be generated | Generated for `rn-forge-commons` 0.8.0 and attached to its GitHub release. | [`release` job](https://github.com/rn-forge/pykit/actions/runs/41066847153/job/124101905983) and the `rn-forge-commons-v0.8.0` release asset `rn-forge-commons-0.8.0.cdx.json` |
| Attestation | The release fails if it cannot be produced | GitHub build provenance for `rn-forge-commons` 0.8.0 verifies with `gh attestation verify`. PyPI attestations are not yet proven. | [`release` job](https://github.com/rn-forge/pykit/actions/runs/41066847153/job/124101905983), step `Attest build provenance` |
| `SECURITY.md` | Reports | Present at the repository root. | [`SECURITY.md`](https://github.com/rn-forge/pykit/blob/main/SECURITY.md) |
| Scorecard | Reports; no threshold | Score 7.2 on `ed566a0` (Scorecard v5.6.0). | [Scorecard run](https://github.com/rn-forge/pykit/actions/runs/41066847242) |
