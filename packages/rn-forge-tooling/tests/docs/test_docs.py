"""Tests for rn_forge.tooling.docs."""

from __future__ import annotations

import re
import sys

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.tooling.docs.policy import (
    DocsPolicy,
    NestedArea,
    NumberedArea,
    SequenceArea,
)
from rn_forge.tooling.docs import (
    NAV_BLOCK,
    Area,
    build_nav,
    check_site,
    check_structure,
    headings,
    is_external,
    links,
    load_areas,
    slugify,
    update_nav,
)
from rn_forge.tooling.docs.markdown import strip_fenced_code  # noqa: F401

AREAS = """\
areas:
  - key: adr
    title: Decisions
    nav: children
  - key: guides
    title: Guides
  - key: api
    title: API Reference
    nav: index-only
    generated: true
"""

MKDOCS = """\
site_name: demo
nav:
  # BEGIN generated nav
  # END generated nav
"""


# The rn-forge policy, as a test fixture. It lives here rather than in the
# library on purpose: `docs/structure.py` must not know what an ADR is.
POLICY = DocsPolicy(
    instruction_files=("CLAUDE.md", "AGENTS.md"),
    numbered=NumberedArea(
        path="adr",
        filename=re.compile(r"^(\d{4})-[a-z0-9-]+\.md$"),
        statuses=re.compile(r"^(proposed|accepted|deprecated|superseded by adr-\d{4})"),
        label="ADR",
        shape="<nnnn>-<slug>.md",
    ),
    sequences=(
        SequenceArea(
            path="releases",
            dirname=re.compile(r"^release-(\d+)$"),
            shape="release-<n>/",
        ),
    ),
    nested=(
        NestedArea(
            path="specs/epics",
            dirname=re.compile(r"^E(\d+)-[a-z0-9-]+$"),
            dir_shape="E<n>-<slug>/",
            page_glob="F*.md",
            page_name=re.compile(r"^F(\d+)\.(\d+)-[a-z0-9-]+\.md$"),
            page_shape="F<n>.<m>-<slug>.md",
        ),
    ),
)

# `--policy` takes an import path, so the fixture policy needs a module name
# that resolves the same way however pytest was invoked. Every package in this
# workspace has a `tests` package, so `tests.docs.test_docs` is ambiguous in a
# whole-workspace run; this alias is not.
sys.modules.setdefault("rn_forge_tooling_test_policy", sys.modules[__name__])
POLICY_REF = "rn_forge_tooling_test_policy:POLICY"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    """A minimal but valid repo: two areas, an instruction file, a nav block."""
    docs = tmp_path / "docs"
    write(docs / "_areas.yml", AREAS)
    write(docs / "_structure.md", "# Structure\n")
    write(docs / "index.md", "# Docs\n\n- [Guides](guides/index.md)\n")
    write(docs / "adr/_structure.md", "# ADR structure\n")
    write(docs / "adr/index.md", "# Decisions\n\n- [First](0001-first.md)\n")
    write(docs / "adr/0001-first.md", "# First\n\n**Status:** accepted\n")
    write(docs / "guides/_structure.md", "# Guide structure\n")
    write(docs / "guides/index.md", "# Guides\n\n- [Setup](setup.md)\n")
    write(docs / "guides/setup.md", "# Setup\n")
    write(
        tmp_path / "CLAUDE.md",
        "# Repo\n\n- [rules](docs/_structure.md)\n- [docs](docs/index.md)\n",
    )
    write(tmp_path / "AGENTS.md", "See [CLAUDE.md](CLAUDE.md).\n")
    write(tmp_path / "mkdocs.yml", MKDOCS)
    return tmp_path


def codes(findings):
    return sorted(finding.code for finding in findings)


class TestMarkdown:
    def test_links_ignores_fenced_code(self):
        assert links("[a](a.md)\n```\n[b](b.md)\n```\n") == ["a.md"]

    def test_headings_are_slugified(self):
        assert headings("# Hello, World!\n## A B\n") == {"hello-world", "a-b"}

    def test_slugify_matches_mkdocs(self):
        assert slugify("  What's *this*? ") == "whats-this"

    @pytest.mark.parametrize(
        ("link", "expected"),
        [("https://x", True), ("mailto:a@b", True), ("a.md", False)],
    )
    def test_is_external(self, link, expected):
        assert is_external(link) is expected


class TestAreas:
    def test_loads_declared_areas(self, repo):
        areas = load_areas(repo / "docs")
        assert [area.key for area in areas] == ["adr", "guides", "api"]
        assert areas[2].generated is True
        assert areas[2].nav == "index-only"

    def test_missing_manifest_raises(self, tmp_path):
        with pytest.raises(AppException):
            load_areas(tmp_path)

    def test_unknown_nav_value_raises(self, tmp_path):
        write(tmp_path / "_areas.yml", "areas:\n  - key: guides\n    nav: sideways\n")
        with pytest.raises(AppException):
            load_areas(tmp_path)

    def test_area_round_trips_through_dict(self, repo):
        for area in load_areas(repo / "docs"):
            assert Area.from_dict(area.as_dict()) == area

    def test_a_mistyped_field_names_the_manifest_and_the_field(self, tmp_path):
        write(
            tmp_path / "_areas.yml",
            "areas:\n  - key: guides\n    optional: sometimes\n",
        )
        with pytest.raises(AppException) as error:
            load_areas(tmp_path)
        assert "_areas.yml" in str(error.value)
        assert "optional" in str(error.value)

    def test_a_missing_key_is_rejected(self, tmp_path):
        write(tmp_path / "_areas.yml", "areas:\n  - title: Guides\n")
        with pytest.raises(AppException):
            load_areas(tmp_path)


class TestCheckStructure:
    def test_a_valid_tree_has_no_findings(self, repo):
        assert check_structure(repo, repo / "docs", POLICY) == []

    def test_missing_area_is_reported(self, repo):
        for path in (repo / "docs/guides").iterdir():
            path.unlink()
        (repo / "docs/guides").rmdir()
        assert "docs.missing-area" in codes(
            check_structure(repo, repo / "docs", POLICY)
        )

    def test_generated_area_need_not_exist(self, repo):
        assert not any(
            "api" in (finding.path or "")
            for finding in check_structure(repo, repo / "docs", POLICY)
        )

    def test_missing_structure_md_is_reported(self, repo):
        (repo / "docs/guides/_structure.md").unlink()
        assert "docs.missing-structure-md" in codes(
            check_structure(repo, repo / "docs", POLICY)
        )

    def test_non_kebab_page_is_reported(self, repo):
        write(repo / "docs/guides/Not_Kebab.md", "# x\n")
        assert "docs.kebab-case" in codes(check_structure(repo, repo / "docs", POLICY))

    def test_adr_pages_are_exempt_from_the_kebab_rule(self, repo):
        assert "docs.kebab-case" not in codes(
            check_structure(repo, repo / "docs", POLICY)
        )

    def test_adr_number_gap_is_reported(self, repo):
        write(repo / "docs/adr/0003-third.md", "# Third\n\n**Status:** accepted\n")
        assert "docs.number-gap" in codes(check_structure(repo, repo / "docs", POLICY))

    def test_adr_naming_is_reported(self, repo):
        write(repo / "docs/adr/first-decision.md", "**Status:** accepted\n")
        assert "docs.naming" in codes(check_structure(repo, repo / "docs", POLICY))

    def test_missing_adr_status_is_reported(self, repo):
        write(repo / "docs/adr/0001-first.md", "# First\n")
        assert "docs.status" in codes(check_structure(repo, repo / "docs", POLICY))

    def test_superseded_status_is_allowed(self, repo):
        write(
            repo / "docs/adr/0001-first.md",
            "# First\n\n**Status:** superseded by ADR-0002 \\\n",
        )
        assert "docs.status" not in codes(check_structure(repo, repo / "docs", POLICY))

    def test_broken_link_is_reported(self, repo):
        write(repo / "docs/guides/setup.md", "# Setup\n\n[gone](missing.md)\n")
        assert "docs.broken-link" in codes(check_structure(repo, repo / "docs", POLICY))

    def test_broken_anchor_is_reported(self, repo):
        write(repo / "docs/guides/setup.md", "# Setup\n\n[x](index.md#nope)\n")
        assert "docs.broken-anchor" in codes(
            check_structure(repo, repo / "docs", POLICY)
        )

    def test_underscore_page_reference_is_reported(self, repo):
        write(repo / "docs/guides/setup.md", "# Setup\n\n[s](_structure.md)\n")
        assert "docs.underscore-referenced" in codes(
            check_structure(repo, repo / "docs", POLICY)
        )

    def test_release_and_epic_naming(self, repo):
        write(repo / "docs/releases/rel1/index.md", "# r\n")
        write(repo / "docs/specs/epics/E1-thing/F1.a-bad.md", "# f\n")
        found = codes(check_structure(repo, repo / "docs", POLICY))
        assert found.count("docs.naming") == 2

    def test_missing_areas_manifest_is_one_finding(self, repo):
        (repo / "docs/_areas.yml").unlink()
        assert codes(check_structure(repo, repo / "docs", POLICY)) == [
            "docs.areas-manifest"
        ]

    def test_instruction_pointer_must_reach_the_rules(self, repo):
        write(repo / "AGENTS.md", "# Agents\n\nNothing useful here.\n")
        assert "docs.missing-docs-pointer" in codes(
            check_structure(repo, repo / "docs", POLICY)
        )

    def test_no_instruction_file_is_reported(self, repo):
        (repo / "CLAUDE.md").unlink()
        (repo / "AGENTS.md").unlink()
        assert codes(check_structure(repo, repo / "docs", POLICY)) == [
            "docs.missing-instruction-file"
        ]


class TestNav:
    def test_index_link_order_wins_over_alphabetical(self, repo):
        write(repo / "docs/guides/alpha.md", "# Alpha\n")
        write(
            repo / "docs/guides/index.md",
            "# Guides\n\n- [Setup](setup.md)\n- [Alpha](alpha.md)\n",
        )
        body = build_nav(repo / "docs")
        assert body.index("guides/setup.md") < body.index("guides/alpha.md")

    def test_generated_area_is_skipped_when_absent(self, repo):
        assert "api/index.md" not in build_nav(repo / "docs")

    def test_index_only_area_lists_only_its_index(self, repo):
        write(repo / "docs/api/index.md", "# API\n")
        write(repo / "docs/api/module.md", "# Module\n")
        body = build_nav(repo / "docs")
        assert "  - API Reference: api/index.md\n" in body
        assert "api/module.md" not in body

    def test_titles_use_acronyms(self, repo):
        write(repo / "docs/guides/cli-api.md", "# x\n")
        assert "CLI API: guides/cli-api.md" in build_nav(repo / "docs")

    def test_update_nav_reports_staleness_without_writing(self, repo):
        before = (repo / "mkdocs.yml").read_text()
        updated, changed = update_nav(repo / "mkdocs.yml", repo / "docs")
        assert changed
        assert (repo / "mkdocs.yml").read_text() == before
        assert NAV_BLOCK.extract(updated) == build_nav(repo / "docs")

    def test_update_nav_is_idempotent(self, repo):
        updated, _ = update_nav(repo / "mkdocs.yml", repo / "docs")
        (repo / "mkdocs.yml").write_text(updated)
        assert update_nav(repo / "mkdocs.yml", repo / "docs")[1] is False

    def test_content_outside_the_block_is_preserved(self, repo):
        updated, _ = update_nav(repo / "mkdocs.yml", repo / "docs")
        assert updated.startswith("site_name: demo\nnav:\n")

    def test_missing_markers_raise(self, repo):
        write(repo / "mkdocs.yml", "site_name: demo\nnav: []\n")
        with pytest.raises(AppException):
            update_nav(repo / "mkdocs.yml", repo / "docs")


class TestCheckSite:
    @pytest.fixture
    def navved(self, repo):
        updated, _ = update_nav(repo / "mkdocs.yml", repo / "docs")
        (repo / "mkdocs.yml").write_text(updated)
        return repo

    def test_a_navigated_tree_has_no_findings(self, navved):
        assert check_site(navved) == []

    def test_orphan_page_is_reported(self, navved):
        write(navved / "docs/guides/orphan.md", "# Orphan\n")
        assert "docs.orphan-page" in codes(check_site(navved))

    def test_nav_target_that_does_not_exist_is_reported(self, navved):
        (navved / "docs/guides/setup.md").unlink()
        assert "docs.nav-missing-page" in codes(check_site(navved))

    def test_broken_link_is_reported(self, navved):
        write(navved / "docs/guides/setup.md", "# Setup\n\n[gone](missing.md)\n")
        assert "docs.broken-link" in codes(check_site(navved))

    def test_gitignored_generated_subtree_is_skipped(self, navved):
        write(navved / ".gitignore", "docs/api/\n")
        write(navved / "docs/guides/setup.md", "# Setup\n\n[api](../api/index.md)\n")
        assert check_site(navved) == []

    def test_underscore_pages_do_not_need_navigating(self, navved):
        assert "docs.orphan-page" not in codes(check_site(navved))


class TestDocsCli:
    @pytest.fixture(autouse=True)
    def _rich_console(self):
        from rn_forge.commons.runtime.console import OutputMode, console

        console.set_mode(OutputMode.RICH)
        yield
        console.set_mode(OutputMode.RICH)

    @pytest.fixture
    def runner(self):
        from typer.testing import CliRunner

        return CliRunner()

    @pytest.fixture
    def cli(self):
        from rn_forge.tooling.cli.docs import app

        return app

    def test_structure_passes_on_a_valid_tree(self, runner, cli, repo):
        result = runner.invoke(
            cli, ["structure", "--policy", POLICY_REF, "--root", str(repo)]
        )
        assert result.exit_code == 0

    def test_structure_fails_and_reports_the_code(self, runner, cli, repo):
        (repo / "docs/guides/_structure.md").unlink()
        result = runner.invoke(
            cli, ["structure", "--policy", POLICY_REF, "--root", str(repo)]
        )
        assert result.exit_code == 1

    def test_json_output_carries_the_findings(self, runner, cli, repo):
        import json

        (repo / "docs/guides/_structure.md").unlink()
        result = runner.invoke(
            cli, ["--json", "structure", "--policy", POLICY_REF, "--root", str(repo)]
        )
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["findings"][0]["code"] == "docs.missing-structure-md"

    def test_nav_check_fails_when_stale_then_passes_after_writing(
        self, runner, cli, repo
    ):
        assert (
            runner.invoke(cli, ["nav", "--root", str(repo), "--check"]).exit_code == 1
        )
        assert runner.invoke(cli, ["nav", "--root", str(repo)]).exit_code == 0
        assert (
            runner.invoke(cli, ["nav", "--root", str(repo), "--check"]).exit_code == 0
        )

    def test_check_passes_once_the_nav_is_current(self, runner, cli, repo):
        runner.invoke(cli, ["nav", "--root", str(repo)])
        assert runner.invoke(cli, ["check", "--root", str(repo)]).exit_code == 0

    def test_nav_json_reports_a_stale_check(self, runner, cli, repo):
        import json

        result = runner.invoke(cli, ["--json", "nav", "--root", str(repo), "--check"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload == {
            "path": str(repo / "mkdocs.yml"),
            "stale": True,
            "written": False,
            "checked": True,
        }

    def test_nav_json_reports_the_rewrite(self, runner, cli, repo):
        import json

        result = runner.invoke(cli, ["--json", "nav", "--root", str(repo)])
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["written"] is True
        assert payload["stale"] is True
        assert "generated nav" in (repo / "mkdocs.yml").read_text()


class TestMarkdownAgreesWithTheRenderer:
    def test_non_ascii_heading_slug_matches_the_renderer(self):
        assert slugify("Résumé") == "resume"
        assert headings("# Résumé\n") == {"resume"}

    def test_repeated_headings_get_the_renderer_suffixes(self):
        text = "## Consequences\n\n## Consequences\n\n## Consequences\n"
        assert headings(text) == {"consequences", "consequences_1", "consequences_2"}

    def test_headings_inside_fenced_code_are_not_headings(self):
        text = "# Real\n\n```bash\n# not a heading\n```\n"
        assert headings(text) == {"real"}

    def test_trailing_hashes_are_not_part_of_the_slug(self):
        assert headings("## Closed ##\n") == {"closed"}

    def test_reference_links_resolve_through_their_definition(self):
        text = "See [the guide][g] and [setup][].\n\n[g]: guides/index.md\n[setup]: setup.md\n"
        assert links(text) == ["guides/index.md", "setup.md"]

    def test_a_reference_with_no_definition_is_not_a_link(self):
        assert links("See [nothing][missing].\n") == []

    def test_tilde_fences_are_stripped_too(self):
        assert links("~~~\n[x](inside.md)\n~~~\n\n[y](outside.md)\n") == ["outside.md"]
