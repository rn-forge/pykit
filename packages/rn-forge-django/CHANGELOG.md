# Changelog

Notable changes to `rn-forge-django`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

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
