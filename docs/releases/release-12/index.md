# Release 12 — Dependency updates in the release cut

|  |  |
| -- | -- |
| **Status** | in progress |
| **Start Date** | 2026-11-21 |

The release cut absorbs the open Dependabot updates: the runbook gains the step,
and the update that opened after Release 11 is taken on the release branch
([E29](../../specs/epics/E29-release-12-dependency-updates/index.md)). Patch
releases of the packages whose requirements changed carry the floors. The
release also takes the database application foundations
([E32](../../specs/epics/E32-database-app-foundations/index.md)): a PostgreSQL
schema per test, an Alembic `env.py` helper, and typed settings.

[Back to releases](../index.md) ·
[Release runbook](../../runbooks/releasing-packages.md)

## Entry criteria

- Release 11 is shipped.

## Scope

<!-- BEGIN derived scope -->

| Feature | Epic | State |
| -- | -- | -- |
| [F29.1 — Dependency updates](../../specs/epics/E29-release-12-dependency-updates/F29.1-dependency-updates.md) | E29 | Closed |
| [F30.1 — PostgreSQL engine and driver extras](../../specs/epics/E30-postgresql-support-in-rn-forge-sqlalchemy/F30.1-postgresql-engine-and-driver-extras.md) | E30 | Closed |
| [F31.1 — Version flag and install route](../../specs/epics/E31-tool-version-and-install-route/F31.1-version-flag-and-install-route.md) | E31 | Closed |
| [F32.1 — A PostgreSQL schema per test](../../specs/epics/E32-database-app-foundations/F32.1-postgres-test-schema.md) | E32 | Closed |
| [F32.2 — Alembic `env.py` helper and migrations into a schema](../../specs/epics/E32-database-app-foundations/F32.2-alembic-env-helper.md) | E32 | Closed |
| [F32.3 — Typed settings from environment variables](../../specs/epics/E32-database-app-foundations/F32.3-typed-env-settings.md) | E32 | Closed |

<!-- END derived scope -->

## Decisions

- [ADR-0018](../../adr/ADR-0018.md): typed settings wrap `pydantic-settings`
  behind the `rn-forge-commons[settings]` extra.

## Breaking changes

None.

## Progress

F29.1 is closed: the updates of Dependabot pull request #42 are on the release
branch, with patch versions for the seven packages they touch. F31.1 is closed:
`CliApp` answers `--version`, and the tool install route is documented. F30.1 is
closed: `rn-forge-sqlalchemy` 0.2.5 has `create_postgres_engine` and the
`postgres` and `sqlite` driver extras. E32 joined the scope on 2026-11-22 and is
closed: `rn-forge-sqlalchemy` 0.2.5 also gains `search_path`, the
`postgres_schema` test plugin, `run_env` and `run_migrations(schema=...)`, and
`rn-forge-commons` 0.10.2 gains typed settings
([ADR-0018](../../adr/ADR-0018.md)). All scope is closed. The cut PR merges to
main, then a follow-up PR records the shipped evidence.

## Commits

Commits whose subject names a scope ID, newest first:

```bash
git log --format='%h %ad %s' --date=short -E --grep='[FS](29|30|31|32)\.'
```

```text
d0d451a2 2026-11-22 S32.2.2, F32.2, E32 close
93720fc9 2026-11-22 Briefs: S32.2.2
f80c0385 2026-11-22 S32.1.3, F32.1 close
c766528b 2026-11-22 S32.2.1
8c2f72ec 2026-11-22 Briefs: S32.2.1
dc47bb55 2026-11-22 Briefs: S32.1.3
5b520825 2026-11-22 S32.1.2
de2909e6 2026-11-22 S32.3.2, F32.3 close
4932e7b6 2026-11-22 Briefs: S32.1.2
7f521b46 2026-11-22 S32.1.1
b6023a9b 2026-11-22 E32 into Release 12; S32.3.1 close (ADR-0018); Briefs: S32.1.1, S32.3.2
9ac2e018 2026-11-21 S30.1.3, F30.1, E30 close
da23ca59 2026-11-21 S30.1.2
4a62dabb 2026-11-21 S30.1.1
b4f20b7f 2026-11-21 S31.1.1, F31.1, E31 close
6e6ca854 2026-11-21 S31.1.2
0689049e 2026-11-21 S29.1.2, F29.1, E29 close
9e5d0058 2026-11-21 Briefs: S30.1.2, S30.1.3
77a5b86d 2026-11-21 Briefs: S29.1.2, S30.1.1, S31.1.1, S31.1.2
```

## Exit criteria

- Every feature on this page's Scope is `Closed`.
- `task docs:generate` leaves the working tree unchanged.
- The main CI, including the Sonar gate, passes on the release's version bumps.
- Each patched package is tagged on the remote and installs from PyPI.
- No Dependabot pull request is open against `main`, or each open one is listed
  on this page as deferred with its reason.
