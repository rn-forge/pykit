# Changelog

Notable changes to `rn-forge-fastapi`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- JSON Merge Patch (RFC 7396) binding: `merge_patch_body()` checks the
  `application/merge-patch+json` media type (415 with `Accept-Patch`) and returns the raw body,
  `merge_into(model, current, body)` parses it, merges and validates against a pydantic model, and
  `merge_patch_openapi()` declares the request body. Declare `merge_patch_body()` before
  `require_if_match` and call `check_precondition` before `merge_into`. A `null` on a
  non-nullable field renders `This field may not be null.`

## [0.1.0] - 2026-09-27

First release.
