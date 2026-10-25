# Changelog

Notable changes to `rn-forge-tooling`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Removed

- Breaking: `rn_forge.tooling.generation`, `rn_forge.tooling.state` and
  `rn_forge.tooling.templates`. Import them from `rn_forge.commons.generation`,
  `rn_forge.commons.fs.state` and `rn_forge.commons.text.templates` (extra
  `templates`); the names are unchanged. Tooling no longer depends on `jinja2`.

### Changed

- Requires its rn-forge dependencies by version range from pykit's index (ADR-0004), not by git URL.

## [0.2.0] - 2026-09-27

Released with pykit's first coordinated set of tags (release-1).
