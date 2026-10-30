"""Every security control in `rn_forge.auth.conformance` has a test in this suite.

A test shows a control by carrying `@pytest.mark.security_control("<id>")`.
"""

from pathlib import Path

import pytest
from rn_forge.auth.conformance import CASES, tagged_tests

pytestmark = pytest.mark.unit


def test_every_security_control_has_a_tagged_test():
    tagged = tagged_tests(Path(__file__).parent)

    assert [case.id for case in CASES if case.id not in tagged] == []


def test_no_test_names_an_unknown_security_control():
    tagged = tagged_tests(Path(__file__).parent)

    assert sorted(set(tagged) - {case.id for case in CASES}) == []
