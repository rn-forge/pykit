# Changelog

Notable changes to `rn-forge-web`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- Shared transfer rules in `rn_forge.web.transfer`: `ImportCounts`, `parse_flag`,
  `row_cap_problem`, `NON_EMPTY_LIST_DETAIL`, `unsupported_file_detail` and
  `unreadable_file_detail`.
- `RowsInvalid` (422) and `ItemsDenied` (403) in `rn_forge.web.exceptions`, both in
  `default_registry()`.
- JSON Merge Patch (RFC 7396), framework-neutral, in `rn_forge.web.merge_patch`:
  `MERGE_PATCH_MEDIA_TYPE`, `apply_merge_patch`, `merge_representation` and `require_patch_object`.
  A top-level `null` sets a field to `null`; below the top level `null` removes the member.
- `UNSUPPORTED_MEDIA_TYPE` and `NULL_FIELD_DETAIL` in `rn_forge.web.problem`.
- `UnsupportedMediaType` (415, with `Accept-Patch`) and `InvalidMergePatch` (422) in
  `rn_forge.web.exceptions`, both in `default_registry()`.
- The `patch` conformance area, with ten `patch.*` cases.
- Eight `transfer.*` conformance cases: `import-without-a-file-is-422`, `import-over-the-cap-is-422`,
  `import-template-is-the-import-columns`, `import-template-prefill-adds-the-rows`,
  `batch-create-with-an-empty-list-is-422`, `batch-create-over-the-cap-is-422`,
  `batch-create-denied-item-is-403-pointer` and `denied-batch-create-persists-nothing`.
- A reference page for `rn_forge.web.transfer`.

### Changed

- **Breaking:** `orderBy` takes a comma-separated list of terms, and `null` sorts last in both directions.
  - `parse_order_by` accepts many terms and rejects a repeated field with `orderBy names '{field}' more than once`. It rejected a second term.
  - `Cursor(sort_key: str, ...)` is now `Cursor(sort_keys: tuple[SortValue, ...], ...)`, and `encode_cursor(sort_key, ...)` is now `encode_cursor(sort_keys, ...)`. `SortValue` (`str | int | float | bool | None`) is exported.
  - The token's JSON is `{"k": [<values>], "id": ..., "o": ...}`. Tokens issued before the change are rejected with 400.
  - `check_cursor_order` also rejects a token whose value count does not match the terms, with `Malformed page token`.
  - New conformance cases: `pagination.order-by-several-fields-sorts-by-each-in-turn`, `nulls-sort-last-ascending`, `nulls-sort-last-descending`, `first-page-carries-a-composite-token`, `composite-token-resumes-within-a-tie`, `composite-token-resumes-after-a-null`, `repeated-order-by-field-is-400` and `token-with-the-wrong-number-of-values-is-400`. The case that asserted the one-field rule is removed.
- `EXPOSED_HEADERS` now ends with `Content-Disposition`, so a cross-origin browser
  client can read the file name of an export or an import template.

## [0.1.0] - 2026-09-27

First release.
