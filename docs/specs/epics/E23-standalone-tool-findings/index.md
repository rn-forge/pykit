# E23 — What kiln's standalone install found

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-11-17 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F23.1 — Help text reads as written, and a command starts quietly](F23.1-help-text.md) | Active | release-9 | 2 New · 1 Closed |
| [F23.2 — A Python tool installs from a branch, a tag or a commit](F23.2-install-from-a-ref.md) | Active | release-9 | 3 New |

<!-- END derived features -->

kiln is the first real tool built on `rn-forge-cli` and `rn-forge-tooling`. This
epic fixes what kiln found on 2026-11-14 when it ran as a standalone tool: help
text that differs from what its docstrings say, a logger notice on every
command, and a lifecycle that can install only from a GitHub release, into a
directory that holds no runnable command. kiln's side is kiln
[F7.7](https://github.com/rn-forge/kiln/blob/feature/v1/docs/specs/epics/E7-pykit-release-pin-flip/F7.7-kiln-installs-as-a-tool.md),
which waits on both features through its upstream pins.
