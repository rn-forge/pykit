"""Workstation install mechanics, and the lifecycle verbs built on them.

The *mechanics* of installing a release safely are identical between the
rn-forge tools and are owned here: where a tool lives under ``$RNF_HOME``
(:mod:`~rn_forge.tooling.install.home`), fetching and verifying a release
(:mod:`~rn_forge.tooling.install.release`), extracting a bundle
(:mod:`~rn_forge.tooling.install.archive`), and the transactional
``install``/``upgrade``/``uninstall``/``cleanup``/``status``/``doctor`` verbs
(:mod:`~rn_forge.tooling.install.lifecycle`). A tool supplies only a
:class:`~rn_forge.tooling.install.product.ToolProduct` describing itself.

The cross-process lock and the atomic symlink these are built on carry no
installer policy in their signatures and live in
:mod:`rn_forge.commons.fs.locks`.
"""

from rn_forge.tooling.install.archive import extract_archive
from rn_forge.tooling.install.home import ToolHome, rnf_home
from rn_forge.tooling.install.lifecycle import (
    CleanupResult,
    InstallResult,
    InstallStatus,
    cleanup,
    doctor,
    install,
    status,
    uninstall,
    upgrade,
)
from rn_forge.tooling.install.product import Check, Link, ToolProduct
from rn_forge.tooling.install.release import (
    GitHubReleases,
    LocalArchive,
    ReleaseSource,
    fetch_release,
)

__all__ = [
    "Check",
    "CleanupResult",
    "GitHubReleases",
    "InstallResult",
    "InstallStatus",
    "Link",
    "LocalArchive",
    "ReleaseSource",
    "ToolHome",
    "ToolProduct",
    "cleanup",
    "doctor",
    "extract_archive",
    "fetch_release",
    "install",
    "rnf_home",
    "status",
    "uninstall",
    "upgrade",
]
