"""Release sources, workstation installation, and lifecycle operations."""

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
