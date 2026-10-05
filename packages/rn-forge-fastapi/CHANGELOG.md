# Changelog

Notable changes to `rn-forge-fastapi`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

## [0.2.0] - 2026-10-05

### Added

- Soft delete in AIP-164's shape: `soft_delete_router` (`DELETE {collection}/{id}` answering `200`
  with the resource, and `POST {collection}/{id}:undelete`), the `SoftDeleteStore` protocol and
  `SoftDeleteState`, and `show_deleted_param()`, all exported from `rn_forge.fastapi`.
- `read_mask_param(model)` and `masked(page, mask)` for the `readMask` query parameter.
  `batch_get_router` takes a new `read_mask` parameter (default `True`) and applies the mask.
- `batch_get_router` (`GET :batchGet`) and `batch_update_router` (`POST :batchUpdate`, one JSON
  Merge Patch and optional `ifMatch` per item) in `rn_forge.fastapi.transfer`, with the
  `BatchGetStore`, `BatchUpdateStore` and `Current` protocols. `batch_update_router` takes
  `require_if_match` and `codec`.
- Route factories in `rn_forge.fastapi.transfer` that match `rn-forge-django`'s transfer mixins:
  `import_router` (`POST :import`), `import_template_router` (`GET :importTemplate`),
  `batch_create_router` (`POST :batchCreate`) and `batch_delete_router` (`POST :batchDelete`).
  Each takes a dependency returning a store (`ImportStore`, `TemplateSource`, `BatchCreateStore`,
  `BatchDeleteStore`), `max_rows` and `dependencies=`. `tabular_export` applies the export cap
  inside an application's own list route. `RowsResult` gains `total`, `read_rows` takes
  `formats=` and raises `ValueError` with the shared unsupported and unreadable file details.
  A store raises `RowsInvalid` (422) or `ItemsDenied` (403) from `rn-forge-web` for a failure only it can
  find. The factories answer the shared 422s: a missing file, a missing or empty list, and a row cap.
  The transfer guide shows a complete resource over `rn-forge-sqlalchemy`'s `upsert` and `keyset`.
- JSON Merge Patch (RFC 7396) binding: `merge_patch_body()` checks the
  `application/merge-patch+json` media type (415 with `Accept-Patch`) and returns the raw body,
  `merge_into(model, current, body)` parses it, merges and validates against a pydantic model, and
  `merge_patch_openapi()` declares the request body. Declare `merge_patch_body()` before
  `require_if_match` and call `check_precondition` before `merge_into`. A `null` on a
  non-nullable field renders `This field may not be null.`

### Changed

- **Breaking:** `order_by_param` describes `orderBy` as a comma-separated list of fields and names the sortable fields. It described one field. It returns every term, as `parse_order_by` in `rn-forge-web` now accepts several and rejects a repeated field with 400.
- `read_rows` picks the format from the file extension, and uses the content type only when the
  file name has none, as `rn-forge-django` does. A `.pdf` sent as `text/csv` is now unsupported.

### Fixed

- `tabular_response` writes the CSV header row when there are no data rows.

## [0.1.0] - 2026-09-27

First release.
