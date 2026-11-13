"""The `rn-forge-devops` console script."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rn_forge.devops import notes, requirements


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rn-forge-devops",
        description="Release commands for the pykit workspace.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "requirements", help="check internal requirements are version ranges"
    )
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


def _requirements(root: Path) -> int:
    problems = requirements.check_requirements(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    """Run a subcommand and return its exit status.

    Args:
        argv: The arguments after the program name; `sys.argv[1:]` when omitted.
    """
    args = _parser().parse_args(argv)
    if args.command == "umbrella":
        return _umbrella(args)
    try:
        root = requirements.find_root(Path.cwd())
    except FileNotFoundError as error:
        sys.exit(str(error))
    return _requirements(root)
