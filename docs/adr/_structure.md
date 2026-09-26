# adr/ — what belongs here

## Belongs here

A durable architectural choice that constrains future work across pykit packages. Each ADR answers one question: what was chosen, why, and what tradeoff follows.

## Does not belong here

| Instead of | Put it in |
| --- | --- |
| Work, status or open questions | `specs/` |
| How implemented packages fit together | `architecture/`, or the package's docs |
| History and evidence | `plans/context.md` |

## Naming and shape

- `ADR-<nnnn>.md`, listed in `index.md`. The title states the decision, not the topic. Pykit's sequence is independent of kiln's.
- Open with one line: `**Status:** <proposed|accepted|deprecated> (<decision date>) · **Scope:** <what it binds>`.
- Then `## Decision`, `## Consequences`, `## Influences`, `## Alternatives considered` and `## Background`. Background gives the decision date's source and the date it was recorded here, when they differ.

## Changing this area

New decisions take the next number. Rewrite a revised decision to state the current choice, and record what changed in Background as a dated sentence. An answered open question becomes an ADR only when it has a durable cross-package consequence; otherwise record it on the feature.
