# E27 — Key-path artifacts

|  |  |
| -- | -- |
| **State** | Closed |
| **Start Date** | 2026-11-20 |
| **Closed Date** | 2026-11-20 |

<!-- BEGIN derived features -->

| Feature | State | Iteration | Stories |
| -- | -- | -- | -- |
| [F27.1 — A `keys` artifact kind](F27.1-keys-artifact-kind.md) | Closed | release-11 | 2 Closed |

<!-- END derived features -->

The `rn-forge-commons` generation engine owns whole files and fenced blocks.
This epic adds a third kind of ownership: named key paths inside a JSON or TOML
document that another program also writes. A generator can then keep a few
settings right in an application's own config file, leaving every other key
alone. The epic ships `rn-forge-commons` 0.10.1 with that kind
([F27.1](F27.1-keys-artifact-kind.md)).
