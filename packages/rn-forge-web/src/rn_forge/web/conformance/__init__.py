"""The scenario table both framework packages are tested against.

This is the only thing in the package that can catch Django and FastAPI
drifting apart. Every other test asserts one side against the primitives;
nothing else asserts that the two stacks emit the *same JSON* for the same
situation, so without this the first divergence surfaces in an application's
integration testing — or in a UI.

Why it lives here, as data
--------------------------

It cannot live in ``rn-forge-django`` or ``rn-forge-fastapi``: either one would
need the other installed. And it cannot import both into *this* package's
tests, because that breaks the boundary rule the package rests on. So this
package ships the scenarios as **framework-free data**, and each framework
package ships a driver that runs its own stack through them. The table is the
specification; the drivers are two independent proofs against it.

A driver is about fifteen lines: build the app, issue :attr:`ConformanceCase.request`,
:func:`redact` the response body, assert against the expectations.

The rules
---------

- **A case is added in the same change as the decision it encodes.** A phase
  that settles a status code and does not add its case has not finished.
- **Drivers assert equality to this table, never to each other's output.** Two
  stacks agreeing on the wrong thing is not conformance.
- **:func:`redact` is the only place that knows what may legitimately vary.**
  If a driver needs its own redaction, the shape is not actually shared, and
  that is the finding.
- The table ships in the package rather than in ``tests/``, because the
  framework packages import it. It is public API.
"""

from __future__ import annotations

from rn_forge.web.conformance.cases import CASES, case_by_id, cases_for
from rn_forge.web.conformance.types import (
    REDACTED,
    VARIABLE_MEMBERS,
    ConformanceArea,
    ConformanceCase,
    RequestSpec,
    redact,
)

__all__ = [
    "CASES",
    "REDACTED",
    "VARIABLE_MEMBERS",
    "ConformanceArea",
    "ConformanceCase",
    "RequestSpec",
    "case_by_id",
    "cases_for",
    "redact",
]
