"""Tests for rn_forge.commons.findings."""

from __future__ import annotations

from rn_forge.commons.findings import Finding, Severity


class TestFinding:
    def test_defaults(self):
        finding = Finding("docs.broken-link", Severity.ERROR, "nope")
        assert finding.path is None
        assert finding.line is None
        assert finding.details == {}
        assert finding.is_error

    def test_warning_is_not_an_error(self):
        assert not Finding("x.y", Severity.WARNING, "m").is_error

    def test_str_without_location(self):
        assert str(Finding("x.y", Severity.ERROR, "m")) == "[x.y] m"

    def test_str_with_path(self):
        finding = Finding("x.y", Severity.ERROR, "m", path="docs/a.md")
        assert str(finding) == "docs/a.md: [x.y] m"

    def test_str_with_path_and_line(self):
        finding = Finding("x.y", Severity.ERROR, "m", path="docs/a.md", line=3)
        assert str(finding) == "docs/a.md:3: [x.y] m"

    def test_round_trips_through_dict(self):
        finding = Finding(
            "artifact.drift",
            Severity.ERROR,
            "changed",
            path="Taskfile.yml",
            line=1,
            details={"expected": "a", "actual": "b"},
        )
        assert Finding.from_dict(finding.as_dict()) == finding

    def test_details_are_per_instance(self):
        first = Finding("a", Severity.INFO, "m")
        first.details["k"] = 1
        assert Finding("a", Severity.INFO, "m").details == {}
