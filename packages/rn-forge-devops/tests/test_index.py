"""Tests for the PEP 503 index renderer."""

from __future__ import annotations

from rn_forge.devops.index import ReleaseFile, render_index

_COMMONS = ReleaseFile(
    "rn_forge_commons",
    "rn_forge_commons-0.7.0-py3-none-any.whl",
    "https://x/c.whl",
    "aa",
)
_COMMONS_SDIST = ReleaseFile(
    "rn-forge-commons", "rn_forge_commons-0.7.0.tar.gz", "https://x/c.tar.gz", "bb"
)
_DEVOPS = ReleaseFile(
    "rn-forge-devops", "rn_forge_devops-0.2.0-py3-none-any.whl", "https://x/d.whl", "cc"
)


def test_root_lists_projects_in_order_with_a_page_each() -> None:
    pages = render_index([_DEVOPS, _COMMONS])
    assert set(pages) == {
        "index.html",
        "rn-forge-commons/index.html",
        "rn-forge-devops/index.html",
    }
    root = pages["index.html"]
    assert root.index('href="rn-forge-commons/"') < root.index(
        'href="rn-forge-devops/"'
    )


def test_every_link_carries_its_sha256_fragment() -> None:
    page = render_index([_COMMONS_SDIST, _COMMONS])["rn-forge-commons/index.html"]
    assert (
        'href="https://x/c.whl#sha256=aa">rn_forge_commons-0.7.0-py3-none-any.whl<'
        in page
    )
    assert 'href="https://x/c.tar.gz#sha256=bb">rn_forge_commons-0.7.0.tar.gz<' in page
    assert page.index("c.whl") < page.index("c.tar.gz")


def test_names_are_normalized() -> None:
    assert "rn-forge-commons/index.html" in render_index([_COMMONS])


def test_html_special_characters_are_escaped() -> None:
    file = ReleaseFile("p", "a<b>&.whl", "https://x/?a=1&b=2", "dd")
    page = render_index([file])["p/index.html"]
    assert "a&lt;b&gt;&amp;.whl" in page
    assert "https://x/?a=1&amp;b=2#sha256=dd" in page


def test_pages_carry_the_repository_version_meta() -> None:
    for page in render_index([_COMMONS]).values():
        assert '<meta name="pypi:repository-version" content="1.0">' in page
