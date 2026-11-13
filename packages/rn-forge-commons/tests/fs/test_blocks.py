"""Tests for rn_forge.commons.fs.blocks."""

from __future__ import annotations

import pytest
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.blocks import ManagedBlock


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

    def test_s18_7_1_1_end_indent_defaults_to_indent(self):
        assert ManagedBlock("n", indent="  ").end == "  # END n"
        assert ManagedBlock("n", indent="  ", end_indent=None).render(
            "", "- a\n"
        ) == ManagedBlock("n", indent="  ").render("", "- a\n")

    def test_s18_7_1_2_end_indent_applies_to_the_end_marker_only(self):
        block = ManagedBlock("n", indent="  ", end_indent="")
        assert block.begin == "  # BEGIN n"
        assert block.end == "# END n"

    def test_s18_7_1_3_html_end_indent(self):
        block = ManagedBlock("n", comment="<!--", indent="  ", end_indent="    ")
        assert block.end == "    <!-- END n -->"

    def test_s18_7_1_4_render_writes_begin_indented_and_end_at_the_margin(self):
        block = ManagedBlock("n", indent="  ", end_indent="")
        assert block.render("", "- a\n") == "  # BEGIN n\n- a\n# END n\n"

    def test_s18_7_1_5_end_indent_is_not_validated(self):
        ManagedBlock("n", indent="  ", end_indent="\t")
        ManagedBlock("n", end_indent="  ")

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


class TestEndIndent:
    at_margin = "  # BEGIN n\n- a\n# END n\n"
    indented = "  # BEGIN n\n- a\n  # END n\n"

    @pytest.fixture
    def block(self) -> ManagedBlock:
        return ManagedBlock("n", indent="  ", end_indent="")

    def test_s18_7_1_6_extract_reads_either_end_form(self, block):
        assert block.extract(self.at_margin) == "- a\n"
        assert block.extract(self.indented) == "- a\n"

    def test_s18_7_1_7_render_replaces_either_end_form(self, block):
        for text in (self.at_margin, self.indented):
            assert block.render(text, "- b\n") == "  # BEGIN n\n- b\n# END n\n"

    def test_s18_7_1_8_remove_and_round_trip(self, block):
        rendered = block.render("head\n", "- a\n")
        assert block.remove(rendered) == "head\n"
        assert block.render(rendered, "- a\n") == rendered

    @pytest.mark.parametrize(
        ("block", "expected"),
        [
            (ManagedBlock("n"), "head\n\n# BEGIN n\nx\n# END n\n"),
            (
                ManagedBlock("n", comment="<!--"),
                "head\n\n<!-- BEGIN n -->\nx\n<!-- END n -->\n",
            ),
            (ManagedBlock("n", indent="  "), "head\n\n  # BEGIN n\nx\n  # END n\n"),
        ],
    )
    def test_s18_7_1_9_default_output_is_unchanged(self, block, expected):
        assert block.render("head\n", "x\n") == expected


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
        block = ManagedBlock("kiln")
        with pytest.raises(AppException):
            block.extract(text)


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


class TestBytePreservation:
    def test_crlf_file_keeps_its_line_endings(self):
        block = ManagedBlock("kiln")
        text = "head\r\n# BEGIN kiln\r\nold\r\n# END kiln\r\ntail\r\n"
        rendered = block.render(text, "new\n")
        assert rendered == "head\r\n# BEGIN kiln\r\nnew\r\n# END kiln\r\ntail\r\n"
        assert block.extract(rendered) == "new\n"

    def test_crlf_file_gains_a_crlf_block(self):
        block = ManagedBlock("kiln")
        rendered = block.render("head\r\n", "a\n")
        assert rendered == "head\r\n\r\n# BEGIN kiln\r\na\r\n# END kiln\r\n"

    def test_missing_terminal_newline_is_preserved(self):
        block = ManagedBlock("kiln")
        text = "head\n# BEGIN kiln\nold\n# END kiln"
        assert block.render(text, "new\n") == "head\n# BEGIN kiln\nnew\n# END kiln"

    def test_appending_terminates_an_unterminated_file(self):
        assert ManagedBlock("kiln").render("head", "a\n") == (
            "head\n\n# BEGIN kiln\na\n# END kiln\n"
        )

    def test_tail_is_preserved_byte_for_byte(self):
        block = ManagedBlock("kiln")
        text = "a\r\nb\n# BEGIN kiln\nold\n# END kiln\n\tindented\r\n\n"
        rendered = block.render(text, "new\n")
        assert rendered.endswith("# END kiln\n\tindented\r\n\n")
        assert rendered.startswith("a\r\nb\n")

    def test_remove_drops_only_the_separator_blank_line(self):
        block = ManagedBlock("kiln")
        text = "head\n\n\n# BEGIN kiln\na\n# END kiln\ntail\n"
        assert block.remove(text) == "head\n\ntail\n"

    def test_remove_keeps_the_missing_terminal_newline(self):
        block = ManagedBlock("kiln")
        assert block.remove("head\n# BEGIN kiln\na\n# END kiln\ntail") == "head\ntail"
