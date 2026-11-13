"""Tests for rn_forge.commons.text.markdown."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from markdown_it.token import Token
from rn_forge.commons.text.markdown import _PARSER, MarkdownUtils, _structure


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


MIXED = (
    "Intro\r\n=====\r\n\r\n"
    "## Part `one`\r\n\r\n"
    "## Part *one*\r\n\r\n"
    "See [a](b%20c.md), [ref][r], ![img](p%2Fq.png) and `[no](code.md)`.\r\n\r\n"
    "[r]: other.md\r\n\r\n"
    "| H1 | H2 |\r\n| -- | -- |\r\n| x |\r\n\r\n"
    "```py\r\n# not a heading\r\n[x](y.md)\r\n```\r\n"
    "tail"
)


@pytest.fixture
def clean_cache() -> Iterator[None]:
    _structure.cache_clear()
    yield
    _structure.cache_clear()


def _all_helpers(text: str) -> tuple[object, ...]:
    return (
        MarkdownUtils.headings(text),
        MarkdownUtils.anchors(text),
        MarkdownUtils.title(text),
        MarkdownUtils.links(text),
        MarkdownUtils.tables(text),
        MarkdownUtils.strip_fenced_code(text),
    )


@pytest.mark.usefixtures("clean_cache")
class TestParseCache:
    def test_one_parse_for_all_helpers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        parse = _PARSER.parse

        def counting(src: str, *args: Any, **kwargs: Any) -> list[Token]:
            calls.append(src)
            return parse(src, *args, **kwargs)

        monkeypatch.setattr(_PARSER, "parse", counting)
        first = _all_helpers(MIXED)
        assert MarkdownUtils.strip_fenced_code(MIXED) == first[5]
        assert MarkdownUtils.tables(MIXED) == first[4]
        assert MarkdownUtils.title(MIXED) == first[2]
        assert MarkdownUtils.anchors(MIXED) == first[1]
        assert MarkdownUtils.links(MIXED) == first[3]
        assert MarkdownUtils.headings(MIXED) == first[0]
        assert calls == [MIXED]

    @pytest.mark.parametrize(
        "name", ["headings", "anchors", "title", "links", "tables", "strip_fenced_code"]
    )
    def test_any_helper_populates_cold_cache(self, name: str) -> None:
        expected = _all_helpers(MIXED)
        _structure.cache_clear()
        getattr(MarkdownUtils, name)(MIXED)
        assert _all_helpers(MIXED) == expected

    def test_mixed_document_values(self) -> None:
        for _ in range(2):  # cold, then warm
            headings = MarkdownUtils.headings(MIXED)
            assert [(h.level, h.text, h.anchor, h.line) for h in headings] == [
                (1, "Intro", "intro", 0),
                (2, "Part one", "part-one", 3),
                (2, "Part one", "part-one_1", 5),
            ]
            assert MarkdownUtils.anchors(MIXED) == {"intro", "part-one", "part-one_1"}
            assert MarkdownUtils.title(MIXED) == "Intro"
            assert MarkdownUtils.links(MIXED) == ["b c.md", "other.md", "p/q.png"]
            (table,) = MarkdownUtils.tables(MIXED)
            assert table.header == ("H1", "H2")
            assert table.rows == (("x", ""),)
            fence = "```py\r\n# not a heading\r\n[x](y.md)\r\n```\r\n"
            assert MarkdownUtils.strip_fenced_code(MIXED) == MIXED.replace(fence, "")

    def test_mutation_does_not_leak(self) -> None:
        MarkdownUtils.headings(MIXED).clear()
        MarkdownUtils.links(MIXED).clear()
        MarkdownUtils.tables(MIXED).clear()
        MarkdownUtils.anchors(MIXED).clear()
        assert len(MarkdownUtils.headings(MIXED)) == 3
        assert len(MarkdownUtils.links(MIXED)) == 3
        assert len(MarkdownUtils.tables(MIXED)) == 1
        assert len(MarkdownUtils.anchors(MIXED)) == 3

    def test_containers_are_distinct_for_empty_input(self) -> None:
        assert MarkdownUtils.headings("") is not MarkdownUtils.headings("")
        assert MarkdownUtils.links("") is not MarkdownUtils.links("")
        assert MarkdownUtils.tables("") is not MarkdownUtils.tables("")
        assert MarkdownUtils.anchors("") is not MarkdownUtils.anchors("")

    def test_changed_text_misses_and_equal_text_hits(self) -> None:
        original = "# a\n"
        assert MarkdownUtils.title(original) == "a"
        assert MarkdownUtils.title("# b\n") == "b"
        assert _structure.cache_info().misses == 2
        equal = original.encode().decode()
        assert equal == original
        assert equal is not original
        MarkdownUtils.title(equal)
        assert _structure.cache_info().misses == 2
        assert _structure.cache_info().hits == 1

    def test_bounded_and_evicted_text_reparses(self) -> None:
        for number in range(2049):
            MarkdownUtils.title(f"# t{number}\n")
        assert _structure.cache_info().currsize == 2048
        misses = _structure.cache_info().misses
        MarkdownUtils.title("# t0\n")
        assert _structure.cache_info().misses == misses + 1
