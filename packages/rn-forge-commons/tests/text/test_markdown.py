"""Tests for rn_forge.commons.text.markdown."""

from __future__ import annotations

from rn_forge.commons.text.markdown import MarkdownUtils


class TestSlugify:
    def test_slugify(self) -> None:
        assert MarkdownUtils.slugify("Hello, World!") == "hello-world"


class TestHeadings:
    def test_repeated_headings_get_suffixes(self) -> None:
        anchors = [h.anchor for h in MarkdownUtils.headings("# a\n\n## a\n\n## a\n")]
        assert anchors == ["a", "a_1", "a_2"]

    def test_fenced_hash_is_no_heading(self) -> None:
        assert MarkdownUtils.headings("```\n# nope\n```\n") == []

    def test_setext_heading(self) -> None:
        (heading,) = MarkdownUtils.headings("Title\n=====\n")
        assert (heading.level, heading.text) == (1, "Title")

    def test_code_span_text_and_line(self) -> None:
        (heading,) = MarkdownUtils.headings("intro\n\n## Use `foo` here\n")
        assert heading.text == "Use foo here"
        assert heading.anchor == "use-foo-here"
        assert heading.line == 2

    def test_anchors(self) -> None:
        assert MarkdownUtils.anchors("# A\n\n## B c\n") == {"a", "b-c"}


class TestTitle:
    def test_first_h1(self) -> None:
        assert MarkdownUtils.title("## x\n\n# One\n\n# Two\n") == "One"

    def test_no_h1(self) -> None:
        assert MarkdownUtils.title("## x\n") is None

    def test_fenced_h1_ignored(self) -> None:
        assert MarkdownUtils.title("```\n# nope\n```\n") is None


class TestLinks:
    def test_targets_in_order(self) -> None:
        text = (
            "[a](one.md) [b][Ref] [c][] ![i](img.png) <https://x.io>\n\n"
            "[ref]: two.md\n[c]: three.md\n"
        )
        assert MarkdownUtils.links(text) == [
            "one.md",
            "two.md",
            "three.md",
            "img.png",
            "https://x.io",
        ]

    def test_code_is_ignored(self) -> None:
        assert MarkdownUtils.links("`[a](x.md)`\n\n```\n[b](y.md)\n```\n") == []

    def test_link_text_with_brackets(self) -> None:
        assert MarkdownUtils.links("[No deleted `[cli]` keys](#k)") == ["#k"]

    def test_undefined_reference_yields_nothing(self) -> None:
        assert MarkdownUtils.links("[a][missing]") == []

    def test_percent_decoded(self) -> None:
        assert MarkdownUtils.links("[a](a%20b.md)") == ["a b.md"]


class TestIsExternal:
    def test_external(self) -> None:
        assert all(
            MarkdownUtils.is_external(link)
            for link in ("https://x", "mailto:a@b", "//cdn/x.js")
        )

    def test_internal(self) -> None:
        assert not any(
            MarkdownUtils.is_external(link) for link in ("../a.md#x", "#anchor")
        )


class TestTables:
    def test_two_tables_with_positions(self) -> None:
        text = "| a | b |\n| - | - |\n| 1 | 2 |\n\ntext\n\n| c |\n| - |\n| 3 |\n| 4 |\n"
        first, second = MarkdownUtils.tables(text)
        assert (first.header, first.rows) == (("a", "b"), (("1", "2"),))
        assert (first.start, first.end) == (0, 3)
        assert second.rows == (("3",), ("4",))
        assert (second.start, second.end) == (6, 10)

    def test_fenced_table_ignored(self) -> None:
        assert MarkdownUtils.tables("```\n| a |\n| - |\n| 1 |\n```\n") == []

    def test_cells_stripped(self) -> None:
        (table,) = MarkdownUtils.tables("|   a   |\n| - |\n|  1  |\n")
        assert (table.header, table.rows) == (("a",), (("1",),))

    def test_short_row_padded(self) -> None:
        (table,) = MarkdownUtils.tables("| a | b |\n| - | - |\n| 1 |\n")
        assert table.rows == (("1", ""),)

    def test_empty_header_with_key_rows(self) -> None:
        (table,) = MarkdownUtils.tables("| | |\n| - | - |\n| **Key** | v |\n")
        assert table.header == ("", "")
        assert table.rows == (("**Key**", "v"),)


class TestStripFencedCode:
    def test_backtick_and_tilde_fences(self) -> None:
        text = "a\n```py\nx\n```\nb\n~~~\ny\n~~~\nc\n"
        assert MarkdownUtils.strip_fenced_code(text) == "a\nb\nc\n"

    def test_fence_closed_by_longer_fence(self) -> None:
        text = "a\n```\nx\n`````\nb\n"
        assert MarkdownUtils.strip_fenced_code(text) == "a\nb\n"
