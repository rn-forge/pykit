# Docs checks

Every rn-forge repository lays its documentation out the same way: a small set
of *areas* declared in `docs/_areas.yml`, each with an `index.md` and a
`_structure.md`, navigated from one generated block in `mkdocs.yml`.

`rn_forge.tooling.docs` is the single implementation of the checks that enforce
that, and `rn-forge-docs` is the command a Taskfile wires up:

```bash
rn-forge-docs structure     # the tree matches docs/_areas.yml
rn-forge-docs check         # links, anchors, nav targets, orphan pages
rn-forge-docs nav --check   # the nav block is current
rn-forge-docs nav           # regenerate it
```

Each exits non-zero on an error-severity finding and accepts `--json`.

## The area model

```yaml
areas:
  - key: adr
    title: Decisions
  - key: guides
    title: Guides
  - key: api
    title: API Reference
    nav: index-only
    generated: true
```

The keys are deliberately not a fixed list: the manifest is seeded into a repo
and then owned by it, so a repo may declare an area this package has never heard
of. `optional` areas may be absent; `generated` areas are produced by a
generator (mkdocstrings, TypeDoc) and are navigated only when present, never
checked.

## Nav order

Inside an area, pages are ordered: the area's `index.md` first, then the pages
its `index.md` links to in the order it links them, then everything else
alphabetically. An index page is therefore how a human overrides nav order,
which keeps ordering out of the config file.

`mkdocs.yml` is repository-owned with one generated block in it, so the nav is
rendered through a `ManagedBlock` (`rn-forge-commons`) and
content outside the markers survives byte for byte.

## Using the checks directly

Every check returns
`Finding` (`rn-forge-commons`) objects, so a caller renders
or serialises them the same way whichever check produced them:

```python
from rn_forge.tooling.docs import check_site, check_structure

findings = [*check_structure(root, root / "docs"), *check_site(root)]
failed = any(finding.is_error for finding in findings)
```
