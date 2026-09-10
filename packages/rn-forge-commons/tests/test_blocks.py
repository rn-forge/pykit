"""Tests for rn_forge.commons.blocks."""

from __future__ import annotations

import pytest

from rn_forge.commons.blocks import ManagedBlock
from rn_forge.commons.exceptions import AppException


class TestMarkers:
    def test_hash_markers(self):
        block = ManagedBlock("rn-forge kiln")
        assert block.begin == "# BEGIN rn-forge kiln"
        assert block.end == "# END rn-forge kiln"

    def test_html_markers(self):
        block = ManagedBlock("rn-forge kiln", comment="<!--")
        assert block.begin == "<!-- BEGIN rn-forge kiln -->"
        assert block.end == "<!-- END rn-forge kiln -->"

    def test_indent_applies_to_markers_only(self):
        block = ManagedBlock("generated nav", indent="  ")
        assert block.begin == "  # BEGIN generated nav"
        assert (
            block.render("", "- a\n")
            == "  # BEGIN generated nav\n- a\n  # END generated nav\n"
        )

    def test_rejects_empty_name(self):
        with pytest.raises(ValueError):
            ManagedBlock("  ")

    def test_rejects_unknown_comment_style(self):
        with pytest.raises(ValueError):
            ManagedBlock("x", comment="//")


class TestRender:
    def test_appends_when_absent(self):
        block = ManagedBlock("kiln")
        result = block.render("repo line\n", "a\nb\n")
        assert result == "repo line\n\n# BEGIN kiln\na\nb\n# END kiln\n"

    def test_appends_to_empty_file_without_leading_blank(self):
        assert ManagedBlock("kiln").render("", "a\n") == "# BEGIN kiln\na\n# END kiln\n"

    def test_replaces_body_and_preserves_surroundings(self):
        block = ManagedBlock("kiln")
        text = "head\n# BEGIN kiln\nold\n# END kiln\ntail\n"
        assert (
            block.render(text, "new\n") == "head\n# BEGIN kiln\nnew\n# END kiln\ntail\n"
        )

    def test_empty_body_leaves_adjacent_markers(self):
        block = ManagedBlock("kiln")
        assert block.render("", "") == "# BEGIN kiln\n# END kiln\n"

    def test_round_trips(self):
        block = ManagedBlock("kiln", comment="<!--")
        text = block.render("# Title\n", "content\n")
        assert block.extract(text) == "content\n"
        assert block.remove(text) == "# Title\n"

    def test_render_is_idempotent(self):
        block = ManagedBlock("kiln")
        once = block.render("head\n", "a\n")
        assert block.render(once, "a\n") == once


class TestExtract:
    def test_missing_block_is_none(self):
        assert ManagedBlock("kiln").extract("nothing here\n") is None

    def test_empty_block_is_empty_string(self):
        assert ManagedBlock("kiln").extract("# BEGIN kiln\n# END kiln\n") == ""

    def test_ignores_a_different_block(self):
        text = "# BEGIN other\nx\n# END other\n"
        assert ManagedBlock("kiln").extract(text) is None


class TestMalformed:
    @pytest.mark.parametrize(
        "text",
        [
            "# BEGIN kiln\nbody\n",
            "body\n# END kiln\n",
            "# BEGIN kiln\na\n# END kiln\n# BEGIN kiln\nb\n# END kiln\n",
            "# END kiln\nbody\n# BEGIN kiln\n",
        ],
    )
    def test_malformed_markers_raise(self, text):
        with pytest.raises(AppException):
            ManagedBlock("kiln").extract(text)


class TestRemove:
    def test_absent_block_returns_text_unchanged(self):
        assert ManagedBlock("kiln").remove("a\n") == "a\n"

    def test_drops_the_blank_line_before_the_block(self):
        block = ManagedBlock("kiln")
        text = block.render("head\n", "a\n")
        assert block.remove(text) == "head\n"

    def test_removing_the_only_content_yields_empty(self):
        block = ManagedBlock("kiln")
        assert block.remove("# BEGIN kiln\na\n# END kiln\n") == ""
