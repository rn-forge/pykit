# E20 — Security baseline

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-10-27 |

A green Sonar quality gate covers first-party static analysis, security
hotspots, coverage and duplication, and nothing else. It does not cover
vulnerable dependencies (Dependabot watches only `github-actions`, not
`uv.lock`), the integrity of the pinned tags consumers install (no SBOM, signing
or attestation, though Actions are already SHA-pinned), secrets in git history,
a licence inventory, or a disclosure process (there is no `SECURITY.md`). Agent-
written code passes style gates easily, so the baseline has to be explicit and
evidenced per release.

This epic defines that baseline and delivers its controls. The goal is that
pykit can state "meets the pykit security baseline" with per-release evidence,
not "certified safe". Auth-specific security tests (denied paths, privilege
boundaries, token expiry) and the auth threat model are out of scope: they stay
in [E13](../E13-auth/index.md), which owns them.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| -- | -- | -- |
| [F20.1 — Baseline decision](F20.1-baseline-decision.md) | The decision: which controls are required, which fail the build and which only report; recorded as an ADR. | Closed |
| [F20.2 — Dependency risk](F20.2-dependency-risk.md) | Vulnerability audit of `uv.lock` in CI, a `uv` Dependabot ecosystem, and a dependency licence inventory. | Closed |
| [F20.3 — Source and secret scanning](F20.3-source-and-secret-scanning.md) | A security linter with Django rules in CI, gitleaks over full history, and GitHub push protection. | Active |
| [F20.4 — Release provenance](F20.4-release-provenance.md) | A CycloneDX SBOM per package tag, and artifact attestations on release tags so a consumer can verify a tag's origin. | New |
| [F20.5 — Disclosure and posture](F20.5-disclosure-and-posture.md) | `SECURITY.md`, OpenSSF Scorecard, and a per-release evidence page. | Active |

[F20.1](F20.1-baseline-decision.md) comes first: every other feature depends on
the controls and thresholds it settles.

## Considered and rejected

- **Treat the Sonar gate as the baseline.** It already runs, but it covers
  first-party code only; the gaps above are outside what it analyses.
- **Claim a certification.** The aim is a stated, evidenced baseline per
  release; "certified safe" is not something these controls can support.
