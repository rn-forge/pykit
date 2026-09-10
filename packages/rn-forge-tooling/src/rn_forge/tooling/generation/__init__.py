"""The generation engine: artifact kinds, action classification, transactional apply.

This is the runtime-neutral half of "generate a repo's standard files". It
knows how to decide *what* a write would do to a working tree and how to make
a batch of writes all-or-nothing. It does not know what a repo standard is,
where config lives, or what a template renders to — a generator supplies the
artifacts, and the caller supplies the state store, the staging and backup
directories and any force approvals.

Nothing here imports Typer or a CLI framework: a generator must be callable as
plain Python (``generator.generate(context)``) so that command-line parsing
never becomes its API.

The three modules behind this facade split the engine by what it does:
:mod:`~rn_forge.tooling.generation.artifacts` holds the vocabulary,
:mod:`~rn_forge.tooling.generation.plan` decides, and
:mod:`~rn_forge.tooling.generation.apply` writes.
"""

from rn_forge.tooling.generation.apply import apply
from rn_forge.tooling.generation.artifacts import (
    BLOCKING_ACTIONS,
    WRITE_ACTIONS,
    Action,
    ApplyResult,
    Artifact,
    ArtifactKind,
    Change,
    Generator,
    Plan,
    StateEntry,
)
from rn_forge.tooling.generation.plan import classify, plan

__all__ = [
    "BLOCKING_ACTIONS",
    "WRITE_ACTIONS",
    "Action",
    "ApplyResult",
    "Artifact",
    "ArtifactKind",
    "Change",
    "Generator",
    "Plan",
    "StateEntry",
    "apply",
    "classify",
    "plan",
]
