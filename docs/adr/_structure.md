# adr/ — what belongs here

## Belongs here

A durable architectural choice that constrains future implementations. Each ADR
answers one question: what was chosen, why, and what tradeoff follows. Decisions
about a dependency's internals belong to that dependency's project.

A feature of the product is not a decision. If the page describes what the repo
does, it belongs in `architecture/`, or in `specs/` while it is still to be
built; if it describes a constraint every future implementation must respect, it
belongs here.

## Does not belong here

| Instead of | Put it in |
| -- | -- |
| Product scope, supported combinations, rollout work | `specs/` |
| Implementation details and local design choices | the owning feature's `## Design` |
| Exact names, signatures, paths or fields | the reference, or the code's doc comments |
| How implemented components fit together | `architecture/` |
| Review transcripts, obsolete drafts and evidence | version history and the commit message |

## Naming and shape

- Use `ADR-<nnnn>.md` and list its title in `index.md`. The title states the
  decision, not the topic.
- Open with one line:
  `**Status:** <proposed|accepted|deprecated> (<date>) · **Scope:** <what the decision binds>`.
- Then these sections, in this order. The first three are what a reader sees on
  opening the file, and are read every time:
    1. `## Decision` — the choice, with only the context needed to state it.
    1. `## Consequences` — what follows, including the costs accepted.
    1. `## Influences` — links to the specs, reference sections and architecture
       this decision constrains.
    1. `## Alternatives considered` — credible options, each with the named
       failure that ruled it out.
    1. `## Background` — the history that still explains the choice. Optional;
       include it only when a reader would otherwise mistake taste for evidence,
       or when the decision was made before it was recorded here — then it gives
       both dates and the decision's source.
- Budget the first three sections at 300 words or fewer; that is the part read
  on every open. `Alternatives considered` and `Background` are as long as the
  evidence needs, with 600 words a soft total. There is no hard cap — a tight
  cap is what turns measured costs into abstractions.
- Name concrete costs. "1,454 lines of committed checker scripts" is a decision
  record; "duplication" is a summary of one.
- Keep specifications in their own home and link to them.

## Changing this area

New decisions take the next number. Keep identifiers stable during routine
revisions; an explicit consolidation may delete or renumber records, but must
update every reference and the index together.

Rewrite a revised decision to state the current choice, and keep what changed
under `Background` as a dated sentence. Do not append earlier versions or review
narratives.

Move scope and design material to its owning spec rather than preserving it as
an ADR. An answered open question becomes a decision here only when it has a
durable architectural consequence; otherwise record it on the feature.
