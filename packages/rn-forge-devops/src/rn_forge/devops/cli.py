"""The `rn-forge-devops` console script."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rn_forge.devops import ci, github, index, notes, releases, requirements, uv


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rn-forge-devops",
        description="Plan and run a workspace's CI pipeline from its own manifests.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="print `$GITHUB_OUTPUT` lines for the run")
    plan.add_argument("base", nargs="?", default="", metavar="BASE")
    releasable = commands.add_parser(
        "releasable", help="print the NAMEs whose checks all passed"
    )
    releasable.add_argument("ok_dir", metavar="OK_DIR")
    releasable.add_argument("names", nargs="*", metavar="NAME")
    commands.add_parser(
        "released", help="print `name dir module version` per tag at HEAD"
    )
    smoke = commands.add_parser(
        "smoke", help="install one extra from built wheels and import it"
    )
    smoke.add_argument("package", metavar="PACKAGE")
    smoke.add_argument("extra", nargs="?", default="", metavar="EXTRA")
    commands.add_parser(
        "adapters", help="check each declared adapter has a module and an extra"
    )
    commands.add_parser(
        "requirements", help="check internal requirements are version ranges"
    )
    commands.add_parser(
        "sonar-target",
        help="print the `$GITHUB_OUTPUT` line with the Sonar branch argument",
    )
    index_command = commands.add_parser(
        "index", help="write a PEP 503 simple index of a repository's release files"
    )
    index_command.add_argument("--repo", required=True, metavar="OWNER/NAME")
    index_command.add_argument("--out", required=True, metavar="DIR")
    notes_command = commands.add_parser(
        "notes", help="print a changelog version's section"
    )
    notes_command.add_argument("changelog", metavar="CHANGELOG")
    notes_command.add_argument("version", metavar="VERSION")
    umbrella = commands.add_parser(
        "umbrella",
        help="write the pending umbrella release's notes; tags are read from stdin",
    )
    umbrella.add_argument("releases_dir", metavar="RELEASES_DIR")
    umbrella.add_argument("body_file", metavar="BODY_FILE")
    umbrella.add_argument("--site-url", required=True, metavar="URL")
    return parser


def _within_cwd(raw: str) -> Path | None:
    path = Path(raw).resolve()
    return path if path.is_relative_to(Path.cwd().resolve()) else None


def _notes(args: argparse.Namespace) -> int:
    changelog = _within_cwd(args.changelog)
    if changelog is None:
        print(f"{args.changelog} is outside the working directory", file=sys.stderr)
        return 1
    text = changelog.read_text(encoding="utf-8")
    try:
        print(notes.changelog_section(text, args.version))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def _umbrella(args: argparse.Namespace) -> int:
    releases_dir = _within_cwd(args.releases_dir)
    if releases_dir is None:
        print(f"{args.releases_dir} is outside the working directory", file=sys.stderr)
        return 1
    body_file = _within_cwd(args.body_file)
    if body_file is None:
        print(f"{args.body_file} is outside the working directory", file=sys.stderr)
        return 1
    # `git ls-remote --tags --refs` lines: `<sha>\trefs/tags/<name>`.
    tags = {
        line.split("refs/tags/", 1)[1].strip()
        for line in sys.stdin.read().splitlines()
        if "refs/tags/" in line
    }
    found = notes.pending_umbrella(releases_dir, tags, args.site_url)
    if found is not None:
        body_file.write_text(found.body, encoding="utf-8")
        print(f"tag={found.tag}")
        print(f"title={found.title}")
    return 0


def _index(args: argparse.Namespace) -> int:
    files = releases.release_files(args.repo)
    pages = index.render_index(files)
    out = Path(args.out).resolve()
    for relative, content in pages.items():
        path = (out / relative).resolve()
        if not path.is_relative_to(out):
            print(f"page {relative!r} escapes {args.out}", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    projects = len(pages) - 1
    print(f"wrote {projects} projects and {len(files)} files to {args.out}")
    return 0


def _releasable(workspace: ci.Workspace, args: argparse.Namespace) -> int:
    ok, blocked = ci.releasable(workspace.packages, Path(args.ok_dir), args.names)
    for name in blocked:
        print(
            f"not releasing {name}: a check or a prerequisite failed", file=sys.stderr
        )
    for name in ok:
        print(name)
    return 0


def _adapters(workspace: ci.Workspace) -> int:
    problems = uv.check_adapters(workspace)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


def _requirements(root: Path) -> int:
    problems = requirements.check_requirements(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


def _run(workspace: ci.Workspace, args: argparse.Namespace) -> int:
    command: str = args.command
    if command == "plan":
        for line in github.output_lines(ci.plan(workspace, args.base)):
            print(line)
    elif command == "releasable":
        return _releasable(workspace, args)
    elif command == "adapters":
        return _adapters(workspace)
    elif command == "released":
        for found in ci.released(workspace):
            print(*found)
    else:
        return uv.smoke(workspace, args.package, args.extra)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run a subcommand and return its exit status.

    Args:
        argv: The arguments after the program name; `sys.argv[1:]` when omitted.
    """
    args = _parser().parse_args(argv)
    if args.command == "sonar-target":
        try:
            print(github.sonar_target())
        except ValueError as error:
            sys.exit(str(error))
        return 0
    if args.command == "index":
        return _index(args)
    if args.command == "notes":
        return _notes(args)
    if args.command == "umbrella":
        return _umbrella(args)

    try:
        root = uv.find_root(Path.cwd())
        if args.command == "requirements":
            return _requirements(root)
        workspace = uv.load_workspace(root)
    except FileNotFoundError as error:
        sys.exit(str(error))
    return _run(workspace, args)
