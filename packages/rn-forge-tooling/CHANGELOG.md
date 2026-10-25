# Changelog

Notable changes to `rn-forge-tooling`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Removed

- Breaking: `rn_forge.tooling.templates`. Import `RenderError` and
  `TemplateEngine` from `rn_forge.commons.text.templates` (extra `templates`);
  the names are unchanged. Tooling no longer depends on `jinja2`.

## [0.2.0] - 2026-09-27

Released with pykit's first coordinated set of tags (release-1).
