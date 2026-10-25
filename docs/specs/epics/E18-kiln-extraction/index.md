# E18 — kiln extraction

|  |  |
| -- | -- |
| **State** | New |

kiln, the rn-forge repository generator, grew plumbing that any application
reading configuration, rendering text or checking Markdown would write again. It
reads TOML through `tomllib` because `DocumentUtils` is seven times slower. It
reads YAML through PyYAML's C loader because `YamlUtils` is fourteen times
slower. It caches a `TemplateEngine` per module and wraps every render in an
`Artifact` by hand. It also parses Markdown headings, links and tables with
regular expressions. This epic makes the kit's own paths fast and complete
enough that kiln deletes those copies. It also moves template rendering and the
generation engine to commons. A web application that writes files from templates
can then plan, preview, apply and detect drift, without the CLI and installer
layers.

kiln adopts this after the release and the pin bump it requires; until then it
keeps its own code.

[Back to the work index](../../index.md)

| Feature | Scope | State |
| -- | -- | -- |
| [F18.1 — Templates, generation and state move to commons](F18.1-template-engine-in-commons.md) | `TemplateEngine` in `rn_forge.commons.text.templates` (`templates` extra), with `autoescape` and `cached`; the generation engine in `rn_forge.commons.generation`; `StateStore` in `rn_forge.commons.fs.state`; import contracts that can break. | New |
| [F18.2 — Templated artifacts and plan diffs](F18.2-templated-artifacts-and-diffs.md) | `TemplateArtifact` and `render_artifacts` in `rn_forge.commons.generation.templated`; public `disk_content` and `diff` in the generation engine. | New |
| [F18.3 — Fast, complete document reads and writes](F18.3-document-io.md) | libyaml loading; `tomllib` for plain TOML; package-resource reads; TOML header and array style; value-level typed reads; brace-safe error messages. | New |
| [F18.4 — Markdown structure](F18.4-markdown-structure.md) | `MarkdownUtils` in `rn_forge.commons.text.markdown` behind a `markdown` extra: headings and anchors, links, title, pipe tables. | New |
| [F18.5 — One pin set on the new tags](F18.5-coherent-pins.md) | Removed: F19.3 re-tags every dependent on ranges in the same cut. | Removed |

## Context

Placed as its own epic, as [E17](../E17-local-first-web-app-extraction/index.md)
was for Apollo: the features come from one consumer's review, span several
packages and are not deferred.

Placement follows [ADR-0002](../../../adr/ADR-0002.md), rule 1, as amended on
2026-10-24. Rule 3 now keeps only the command-line and installation layers in
tooling. The template engine, the generation engine, the state store and the
Markdown helpers name nothing about either, so they go to commons:

- the template engine and the Markdown helpers behind extras
  ([ADR-0003](../../../adr/ADR-0003.md));
- the generation engine outside the facade, since it needs no third-party
  package.

jinja2, Python-Markdown and markdown-it-py are light, and the generation engine
has no dependency set of its own. None of them passes
[ADR-0011](../../../adr/ADR-0011.md)'s first test for a package of its own.
`rn-forge-tooling` keeps the lifecycle verbs and install mechanics.

## Considered and rejected

- **Keep the generation engine in tooling.** It made an application that writes
  files from templates install the CLI and installer layers to get plan, diff,
  atomic apply and drift detection. Rule 1 places code by signature, not by
  today's callers.
- **A new ADR for the move.** ADR-0002's rule 1 already decides it; what
  changed is rule 3's wording, which is amended in place.
- **A `rn-forge-text` or `rn-forge-generation` package.** Each fails ADR-0011's
  first test: light dependencies, or none.
- **A docs-site link checker** (nav targets, orphans, `exclude_docs`). Its rules
  are MkDocs policy, and kiln is its only consumer.
- **A Markdown work-item reader** for epic, feature and release pages. It is
  kiln's spec model, not Markdown.
- **A `delimiters` preset on `TemplateEngine`** for YAML whose own `{{ }}`
  syntax clashes with Jinja's. The environment keywords
  `variable_start_string` and `variable_end_string` already do it, and a preset
  would only rename them ([ADR-0001](../../../adr/ADR-0001.md), rule 2).
