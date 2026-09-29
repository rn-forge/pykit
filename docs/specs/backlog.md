# Backlog

Ideas that are not yet agreed as pykit work. An entry has no ID and no status, and it does not authorize starting work. When the owner takes one up, it becomes an `elaborating` epic or feature, its section moves into that file, and the entry is deleted. A dropped idea is deleted too.

[Back to the work index](index.md)

| Idea | Summary | Source |
| --- | --- | --- |
| [django-optional-areas](#django-optional-areas) | Decide whether Celery, fixtures and messaging stay in `rn-forge-django`. | Former E8, retired 2026-09-28 |

## django-optional-areas

`rn-forge-django` carries Celery, fixtures and messaging behind their own extras. For release-1 the owner kept all of them, and SAML, in the package (2026-09-26). SAML's placement is now part of [E13's design](epics/E13-auth/design.md#package-placement). The question left is whether the other three stay. A move after release-1 is a breaking version of `rn-forge-django`, because [ADR-0002](../adr/ADR-0002.md) forbids aliases.
