"""The seam between a tool and the lifecycle verbs: :class:`ToolProduct`.

A tool describes itself; :mod:`~rn_forge.tooling.install.lifecycle` owns every
algorithm around that description. Every member but the name and version has
a default, so the smallest tool is one line::

    PRODUCT = ToolProduct(name="golden-tool", version=__version__, repo="rn-forge/golden-tool")

and a tool with something to put in place, or to check, subclasses and
overrides only that::

    class GoldenTool(ToolProduct):
        def artifacts(self) -> Sequence[Link]:
            return (Link("bin/golden-tool", "bin/golden-tool"),)

        def checks(self) -> Sequence[Check]:
            return (check_config_readable,)

This is the same adapter shape a kiln module has — ``artifacts()`` and
``checks()`` — and deliberately nothing more. The risk this module guards
against is growing into an installer framework: a new member needs a second
tool that cannot be written without it.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding
from rn_forge.commons.fs.paths import PathUtils

from rn_forge.tooling.install.home import ToolHome
from rn_forge.tooling.install.release import GitHubReleases, ReleaseSource

__all__ = ["Check", "Link", "ToolProduct"]

Check = Callable[[ToolHome], Iterable[Finding]]
"""A product-specific doctor check: inspect the install, report what is true of it.

Report a passing check as an ``info`` finding rather than nothing, so ``doctor``
shows that it ran.
"""


@dataclass(frozen=True, slots=True)
class Link:
    """A symlink an install puts in place outside the version directory.

    The link points through ``current``, never at a version directory, so an
    upgrade swaps what it resolves to without touching the link.

    Args:
        path: Where the link goes, relative to ``$RNF_HOME`` — ``bin/golden-tool``.
        target: What it points at, relative to the installed version's root.
    """

    path: str
    target: str

    def __post_init__(self) -> None:
        # Normalised here rather than at use: a link outside the home, or
        # through `..` out of the version, is wrong however it is used.
        object.__setattr__(self, "path", PathUtils.normalize_relative(self.path))
        object.__setattr__(self, "target", PathUtils.normalize_relative(self.target))
        if self.path == ".":
            raise AppException("A link cannot replace the home directory itself")


@dataclass(frozen=True)
class ToolProduct:
    """An installable tool, as the lifecycle verbs see it.

    Not slotted, so a subclass can override the methods and add fields freely.

    Args:
        name: The product's name, and its directory under ``$RNF_HOME``.
        version: The version of the running code — normally the package's
            ``__version__``.
        repo: ``owner/name`` of the GitHub repository releases are tagged in.
            Used only when *release_source* is not given.
        release_source: Where releases come from. Defaults to
            :class:`GitHubReleases` of *repo*.
        state_schema_version: The version of whatever state the product keeps
            under its home. ``doctor`` reports an install recorded at another
            one; :meth:`migrate` is what moves it.
    """

    name: str
    version: str
    repo: str | None = None
    release_source: ReleaseSource | None = None
    state_schema_version: int = 1

    @property
    def source(self) -> ReleaseSource:
        """The release source to fetch from.

        Raises:
            AppException: Neither *release_source* nor *repo* was given.
        """
        if self.release_source is not None:
            return self.release_source
        if self.repo is None:
            raise AppException(
                "{} declares neither a release source nor a repository", self.name
            )
        return GitHubReleases(self.repo)

    def artifacts(self) -> Sequence[Link]:
        """What an install puts in place beside the version directory. Default: nothing."""
        return ()

    def checks(self) -> Sequence[Check]:
        """Product-specific ``doctor`` checks. Default: none."""
        return ()

    def build(self, release_root: Path, version_dir: Path) -> None:
        """Turn an extracted release into an installed version directory.

        Default: copy the tree. A Python tool overrides this to build an
        environment **in** *version_dir* — not elsewhere and then move it,
        because a virtual environment bakes its own path into its scripts.
        *version_dir* is not observed by anything until the install activates
        it, so building in place is safe.

        Args:
            release_root: The extracted release's root directory.
            version_dir: The directory to populate. Does not exist yet.
        """
        shutil.copytree(release_root, version_dir, symlinks=True)

    def migrate(self, frm: str, to: str) -> None:
        """Move the product's state from version *frm* to version *to*. Default: nothing.

        Runs after the new version is built and before it is activated. Raise
        to abandon the install; the previous version stays active.
        """
