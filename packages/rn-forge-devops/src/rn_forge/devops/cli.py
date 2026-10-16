"""The `rn-forge-devops` console script."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rn_forge.devops import ci, github, uv


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
        "sonar-target",
        help="print the `$GITHUB_OUTPUT` line with the Sonar branch argument",
    )
    return parser


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

    try:
        workspace = uv.load_workspace(uv.find_root(Path.cwd()))
    except FileNotFoundError as error:
        sys.exit(str(error))
    return _run(workspace, args)
