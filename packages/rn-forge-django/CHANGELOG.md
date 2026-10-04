# Changelog

Notable changes to `rn-forge-django`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- `ReadMaskMixin` in `rn_forge.django.drf`: `retrieve`, `list` and `batch_get` accept `readMask` and
  answer `200` with only the named fields. `BaseModelViewSet` includes it, and `WireAutoSchema`
  documents the parameter on those actions.
- `BatchGetMixin` (`GET :batchGet?ids=1&ids=2`) and `BatchUpdateMixin` (`POST :batchUpdate`, one
  JSON Merge Patch and optional `ifMatch` per item) in `rn_forge.django.drf.transfer`.
  `BatchUpdateMixin` has `batch_update_requires_if_match`, `etag_codec` and
  `validate_batch_update_item(instance, data)`. `batch_resource_name` is shared with
  `BatchCreateMixin`.

### Changed

- **Breaking:** `CursorPagination` and `OrderByFilter` use every `orderBy` term, not the first. `ordering_fields` may name nullable fields and relation paths, `NULL` sorts last in both directions, and the `orderBy` OpenAPI description says it takes a comma-separated list. A view's non-primary-key default `ordering` supplies the terms when the request gives no `orderBy`. Page tokens issued before the change are rejected with 400.
- **Breaking:** `BaseModelViewSet`'s `PATCH` now takes `application/merge-patch+json` (RFC 7396) and answers `application/json` with 415 and `Accept-Patch`. `PUT` and `POST` still take `application/json`.
  - The merged document is validated as a full update; a top-level `null` sets the field to `null`, and read-only or unknown members are ignored.
  - A versioned instance enforces `If-Match` on `PATCH`, and `retrieve` and `PATCH` answer with an `ETag`.
  - New: `MergePatchMixin` and `MergePatchParser`, exported from `rn_forge.django.drf`.
- **Breaking:** the import and batch endpoints word their 422 details as `rn-forge-web` does, which `rn-forge-fastapi` also uses.
  - A request over `transfer.max_rows` on `:import`, `:batchCreate` and `:batchDelete` is a 422 problem with detail `The import exceeds the limit of N rows.` or `The batch exceeds the limit of N rows.` and no `errors` member. It was an `errors` entry with an empty pointer.
  - A `:import` request with no `file` part answers `This field is required.` at `/file`, not `No file was submitted.`.
  - A missing `requests` or `ids` member answers `This field is required.` at `/requests` or `/ids`. An empty list or a non-list still answers `A non-empty list is required.`.
  - `validateOnly` and `prefill` accept `true` or `1`, ignoring case, as before; the unsupported and unreadable `file` details are unchanged in wording.

### Removed

- **Breaking:** `rn_forge.django.utils.RequestUtils` and the DRF `RequestUtils` aliases are gone, so `RequestUtils` names only the DRF class.
  - `rn_forge.django.utils.RequestUtils.debug_request(request)` is now `rn_forge.django.views.debug_request(request)`.
  - `rn_forge.django.drf.DRFUtils` is now `rn_forge.django.drf.RequestUtils`.
  - `RequestUtils.get_request_param(request, key)` is now `RequestUtils.get_param(request, key)`.
  - `RequestUtils.get_request_data(request)` is now `RequestUtils.get_data(request)`.
  - `RequestUtils.get_request_value(request, key)` is now `RequestUtils.get_value(request, key)`.

## [0.3.0] - 2026-09-27

Released with pykit's first coordinated set of tags (release-1).

### Fixed

- `BatchCreateMixin` reports an invalid item's errors under DRF 3.18, which keys `ListSerializer` errors by item index instead of listing them.

## Earlier releases

`rn-forge-django-v0.1.0` to `rn-forge-django-v0.2.2` predate this file; their notes are on the [GitHub Releases](https://github.com/rn-forge/pykit/releases) page.
