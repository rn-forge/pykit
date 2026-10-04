# Changelog

Notable changes to `rn-forge-sqlalchemy`, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Changed

- **Breaking:** `keyset` orders and resumes by every `orderBy` term, with `NULL` last in both directions, so a term's column may be nullable. It ordered by one term and required a non-null column.
- **Breaking:** `next_page_token(sort_value, entity_id, terms)` is now `next_page_token(row_values, entity_id, terms)`, with one value per term. Tokens issued before the change are rejected with 400.

## [0.1.0] - 2026-09-27

First release.
