# Model conventions

This page compares the model vocabulary available in the Django and SQLAlchemy packages. Application teams can use the remaining proposals as design guidance, not as guarantees supplied by both packages.

## Implemented building blocks

| Concern | `rn-forge-django` | `rn-forge-sqlalchemy` |
| --- | --- | --- |
| Audit fields | `BaseModel` declares `created_by`, `create_time`, `updated_by`, and `update_time`. Django updates its timestamp fields on save. | `AuditMixin` declares the same four fields. It defaults timestamps to UTC; callers set actors, while `upsert` stamps them. |
| Optimistic concurrency | `VersionedModelMixin` starts `version` at 1. An existing model instance increments it on `save()` and raises `VersionConflict` for a stale version. | `VersionMixin` starts `version` at 1. `update_versioned` checks and increments it for that operation. |
| Natural keys | `FixtureModelMixin.natural_keys()` and `NaturalKeyLookupManager.get_by_natural_key()` support fixture lookup. | No shared natural-key mixin is supplied. An application declares its own key and constraint. |
| Soft delete | `SoftDeleteModelMixin` adds a nullable, indexed `delete_time`, `soft_delete(actor=...)`, `undelete(actor=...)` and a `.live()` / `.deleted()` queryset. | `SoftDeleteMixin` adds the same `delete_time`; `live()`, `soft_delete()` and `undelete()` act on it. |
| Record status | `BaseModel.status` uses Django's `Status` values: `Active`, `Inactive`, `Error`, `Deleted`, and `Expired`. | No status mixin or shared status enumeration is supplied. |

These pieces share field names where shown. They do not create a shared model base, repository protocol, or serializer. Django and SQLAlchemy retain their own persistence and transaction models.

## Application design guidance

An application may use a stable natural key for fixtures and cross-environment references. It may choose a status field. That choice requires application-specific query, update and authorization behavior, and the packages do not enforce a universal lifecycle.

Soft delete is a nullable `delete_time` column, never a status value, so that it can be served as AIP-164's `deleteTime` and survive later writes. Neither package filters deleted rows implicitly: a query asks for live rows with `.live()` on Django or `live()` on SQLAlchemy, and a read of one resource can still return a deleted row. Purging is the application's own authorized operation. The wire rules are §21 of the API conventions.

Keep persisted timestamps timezone-aware and use UTC in application code. `rn-forge-sqlalchemy.UTCDateTime` enforces UTC normalization for its mapped timestamps. Check the Django project's timezone settings when using `BaseModel`.

The `version` field is a useful concurrency convention. Use Django's `VersionedModelMixin.save()` or SQLAlchemy's `update_versioned()` where an endpoint promises conditional writes. Bulk writes and arbitrary SQL are outside those guarantees.

This page records implemented guarantees and optional advice. A stronger cross-package model requirement would need a separate feature decision; SQLAlchemy status and natural keys are not required here.
