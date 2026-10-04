# Changelog

Notable changes to `rn-forge-web`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- JSON Merge Patch (RFC 7396), framework-neutral, in `rn_forge.web.merge_patch`:
  `MERGE_PATCH_MEDIA_TYPE`, `apply_merge_patch`, `merge_representation` and `require_patch_object`.
  A top-level `null` sets a field to `null`; below the top level `null` removes the member.
- `UNSUPPORTED_MEDIA_TYPE` and `NULL_FIELD_DETAIL` in `rn_forge.web.problem`.
- `UnsupportedMediaType` (415, with `Accept-Patch`) and `InvalidMergePatch` (422) in
  `rn_forge.web.exceptions`, both in `default_registry()`.
- The `patch` conformance area, with ten `patch.*` cases.

### Changed

- `EXPOSED_HEADERS` now ends with `Content-Disposition`, so a cross-origin browser
  client can read the file name of an export or an import template.

## [0.1.0] - 2026-09-27

First release.
