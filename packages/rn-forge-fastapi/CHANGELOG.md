# Changelog

Notable changes to `rn-forge-fastapi`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- Route factories in `rn_forge.fastapi.transfer` that match `rn-forge-django`'s transfer mixins:
  `import_router` (`POST :import`), `import_template_router` (`GET :importTemplate`),
  `batch_create_router` (`POST :batchCreate`) and `batch_delete_router` (`POST :batchDelete`).
  Each takes a dependency returning a store (`ImportStore`, `TemplateSource`, `BatchCreateStore`,
  `BatchDeleteStore`), `max_rows` and `dependencies=`. `tabular_export` applies the export cap
  inside an application's own list route. `RowsResult` gains `total`, `read_rows` takes
  `formats=` and raises `ValueError` with the shared unsupported and unreadable file details.
- JSON Merge Patch (RFC 7396) binding: `merge_patch_body()` checks the
  `application/merge-patch+json` media type (415 with `Accept-Patch`) and returns the raw body,
  `merge_into(model, current, body)` parses it, merges and validates against a pydantic model, and
  `merge_patch_openapi()` declares the request body. Declare `merge_patch_body()` before
  `require_if_match` and call `check_precondition` before `merge_into`. A `null` on a
  non-nullable field renders `This field may not be null.`

### Changed

- `read_rows` picks the format from the file extension, and uses the content type only when the
  file name has none, as `rn-forge-django` does. A `.pdf` sent as `text/csv` is now unsupported.

### Fixed

- `tabular_response` writes the CSV header row when there are no data rows.

## [0.1.0] - 2026-09-27

First release.
