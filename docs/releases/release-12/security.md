# Release 12 — security evidence

The result of each [ADR-0015](../../adr/ADR-0015.md) control for this release.
Passing the baseline is not a claim that the release is secure. The rows record
[run 45407929434](https://github.com/rn-forge/pykit/actions/runs/45407929434)
(attempt 3) on `9e15ed95`.

[Back to the release](index.md)

| Control | Effect | Result | Evidence |
| -- | -- | -- | -- |
| Dependency audit | Fails on a known vulnerability | Passed on `9e15ed95`: `python:lint:audit` reports no known vulnerabilities. | [`validate` job](https://github.com/rn-forge/pykit/actions/runs/45407929434/job/138518930329), step 8 of `task lint` |
| Licence inventory | Fails on GPL, AGPL, SSPL or an unknown licence | Passed on `9e15ed95`. | [`validate` job](https://github.com/rn-forge/pykit/actions/runs/45407929434/job/138518930329), step 9 of `task lint` (`python:lint:licenses`) |
| Source scan | Fails | Passed on `9e15ed95`: ruff with the `S` rules ran over all ten packages. | [`validate` job](https://github.com/rn-forge/pykit/actions/runs/45407929434/job/138518930329), step 1 of `task lint` (`python:lint`) |
| Secret scan | Fails | Passed on `9e15ed95`. | [`secret-scan` job](https://github.com/rn-forge/pykit/actions/runs/45407929434/job/138518999443) |
| Push protection | Blocks the push; not in CI | Enabled. | `gh api repos/rn-forge/pykit --jq .security_and_analysis` returns `secret_scanning_push_protection` `enabled` on 2026-11-24 |
| SBOM | Reports; the release fails if it cannot be generated | Generated for all eight released packages and attached to each GitHub release as `<name>.cdx.json`. | [`release` job](https://github.com/rn-forge/pykit/actions/runs/45407929434/job/138518949597) |
| Attestation | The release fails if it cannot be produced | GitHub build provenance and PyPI PEP 740 attestations are both present. `gh attestation verify -R rn-forge/pykit` on the `rn-forge-commons` 0.10.2 wheel exits 0. PyPI's integrity API returns provenance (HTTP 200) for all eight wheels. | [`release` job](https://github.com/rn-forge/pykit/actions/runs/45407929434/job/138518949597), and `https://pypi.org/integrity/<name>/<version>/<wheel>/provenance` |
| `SECURITY.md` | Reports | Present at the repository root. | [`SECURITY.md`](https://github.com/rn-forge/pykit/blob/main/SECURITY.md) |
| Scorecard | Reports; no threshold | Score 7.2 (Scorecard v5.6.0) on `3173142e`, the weekly run of 2026-11-23. Scorecard runs on a schedule, so no run is at `9e15ed95`. | [Scorecard run](https://github.com/rn-forge/pykit/actions/runs/45196817777) |
