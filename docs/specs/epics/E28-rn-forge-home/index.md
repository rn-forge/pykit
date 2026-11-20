# E28 — The rn-forge home

|  |  |
| -- | -- |
| **State** | Active |
| **Start Date** | 2026-11-20 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F28.1 — The home contract, `env.sh` and zsh completions](F28.1-home-contract-and-completions.md) | Active | release-11 | 2 New · 1 Closed |

<!-- END derived features -->

`$RNF_HOME` becomes a written contract that every rn-forge installer, Python or
shell, implements ([ADR-0017](../../../adr/ADR-0017.md)). The home owns a
sourced `env.sh` that puts its commands on `PATH` and its completions on
`fpath`. A Python tool's install links a zsh completion script, so a tool
installed without macsetup completes on `<TAB>` after a single `source` line.
The shell side is shkit's (its `install.sh` writes `env.sh`) and macsetup's (its
profile sources it). Those are planned in their own repositories.
