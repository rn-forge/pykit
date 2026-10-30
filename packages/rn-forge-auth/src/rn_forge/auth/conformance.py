"""The security controls every framework binding must demonstrate.

:data:`CASES` has one case per row of the design's security-controls table.
Each binding's test suite tags tests with a case ID and fails when a case has
none, so a control added here is a control both bindings must show.

A test shows a control by carrying ``@pytest.mark.security_control("<id>")``,
on a function, a method or a class; :func:`tagged_tests` finds those marks in a
suite's source without importing it.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["CASES", "SecurityControlCase", "case_by_id", "tagged_tests"]


@dataclass(frozen=True)
class SecurityControlCase:
    """One security control.

    Attributes:
        id: A stable identifier, used as the argument of a test's
            ``security_control`` marker.
        control: What the control requires.
        enforced_by: Where the control is enforced.
    """

    id: str
    control: str
    enforced_by: str


CASES: Final[tuple[SecurityControlCase, ...]] = (
    SecurityControlCase(
        "oidc-response-checks",
        "state, nonce, PKCE S256, iss response check, UserInfo sub match",
        "OIDC adapter (Authlib) and transaction store",
    ),
    SecurityControlCase(
        "token-profiles",
        "Separate access-token, ID-token and logout-token profiles",
        "Token validation",
    ),
    SecurityControlCase(
        "one-time-transactions",
        "One-time login transactions bound to the browser",
        "Transaction store and transaction cookie",
    ),
    SecurityControlCase(
        "return-to-relative",
        "return_to accepts relative paths only, checked against configured prefixes",
        "Protocol adapter, before the redirect",
    ),
    SecurityControlCase(
        "no-tokens-in-urls-or-logs",
        "No tokens in URLs, browser storage or logs",
        "BFF design; logging filters",
    ),
    SecurityControlCase(
        "one-credential-per-request",
        "One credential per request; no fallback after an invalid bearer token",
        "Framework binding",
    ),
    SecurityControlCase(
        "session-lifecycle",
        "Session ID rotation, idle and absolute timeouts, session versions, "
        "revoked sid values",
        "Framework session binding and supported storage",
    ),
    SecurityControlCase(
        "csrf-and-origin",
        "CSRF token bound to the session, and an origin check, on unsafe methods",
        "CSRF",
    ),
    SecurityControlCase(
        "bearer-scope-ceiling",
        "Scope ceiling on bearer principals",
        "Principal construction",
    ),
    SecurityControlCase(
        "problem-responses",
        "401 and 403 as RFC 9457 problems, with no detail on verification failures",
        "rn-forge-web contract",
    ),
    SecurityControlCase(
        "rate-limiting",
        "Rate limiting on /auth/login/password and callback endpoints",
        "Framework binding, with configurable limits",
    ),
    SecurityControlCase(
        "audit-events",
        "Audit events: login success and failure, logout, account provisioned, "
        "rejected or disabled, authorization denied",
        "AppLogger audit channel",
    ),
    SecurityControlCase(
        "jwks-rotation",
        "JWKS key rotation",
        "PyJWT's PyJWKClient, which refetches for an unknown kid at most once "
        "per cooldown",
    ),
)


def case_by_id(case_id: str) -> SecurityControlCase:
    """Return the case with ID *case_id*.

    Raises:
        KeyError: No case has that ID.
    """
    for case in CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)


def tagged_tests(root: Path) -> dict[str, list[str]]:
    """Find the tests that carry a ``security_control`` marker under *root*.

    Args:
        root: A directory of test modules, searched recursively.

    Returns:
        Each tagged case ID, including an ID no case has, mapped to the
        ``<file>::<class or function>`` names that carry it.
    """
    found: defaultdict[str, list[str]] = defaultdict(list)
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for case_id in _security_control_ids(node):
                    found[case_id].append(f"{path.relative_to(root)}::{node.name}")
    return dict(found)


def _security_control_ids(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> Iterator[str]:
    for decorator in node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "security_control"
        ):
            for argument in decorator.args:
                if isinstance(argument, ast.Constant) and isinstance(
                    argument.value, str
                ):
                    yield argument.value
