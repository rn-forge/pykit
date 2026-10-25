# Changelog

Notable changes to `rn-forge-commons`, newest first, in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added

- `DocumentUtils.read` of a package resource; `header` and `multiline_arrays`
  on `dumps` and `write`; `DocumentUtils.multiline_arrays`; `DictUtils.as_mapping`,
  `ListUtils.as_list` and `ListUtils.as_strings`.
- `rn_forge.commons.generation`, moved from rn-forge-tooling.
- `StateStore` (`rn_forge.commons.fs.state`), moved from rn-forge-tooling.
- `rn_forge.commons.text.templates`, moved from rn-forge-tooling, with
  `autoescape` and `TemplateEngine.cached`.
- The `templates` extra.
- `rn_forge.commons.text.markdown` (`MarkdownUtils`, `MarkdownHeading`,
  `MarkdownTable`) and the `markdown` extra.
- `TemplateArtifact` and `render_artifacts` in
  `rn_forge.commons.generation.templated` (extra `templates`).
- `diff` and `disk_content` in `rn_forge.commons.generation`.

### Changed

- Plain YAML loads use libyaml (`ruamel.yaml[oldlibyaml]`); plain TOML reads
  use `tomllib`; `DocumentUtils.read` names the file in a parse error.

### Fixed

- A parser message containing a brace now raises `DocumentError`.
- A Jinja error whose message contains a brace now raises `RenderError`.

## [0.6.0] - 2026-10-16

### Removed

- Breaking: `rn_forge.commons.data.excel` and `rn_forge.commons.data.pandas`,
  and the pandas aliases `SeriesRow`, `series_value` and `series_columns` in
  `rn_forge.commons.lang.types`. They moved to `rn-forge-data`, with the same
  class names; import them from `rn_forge.data` and `rn_forge.data.pandas`.
- Breaking: the `excel` and `pandas` extras. Depend on `rn-forge-data`, or
  `rn-forge-data[pandas]`, instead.

## [0.5.0] - 2026-09-27

Released with pykit's first coordinated set of tags (release-1).

`rn-forge-commons-v0.1.0` to `rn-forge-commons-v0.2.2` predate this file; their
notes are on the [GitHub Releases](https://github.com/rn-forge/pykit/releases)
page.
