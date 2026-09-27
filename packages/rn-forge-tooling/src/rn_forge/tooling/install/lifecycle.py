"""Transactional install, upgrade, removal, status, and diagnostic operations."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.commons.fs.locks import atomic_symlink
from rn_forge.commons.fs.paths import PathUtils
from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.logging import AppLogger

from rn_forge.tooling.install.home import ToolHome
from rn_forge.tooling.install.product import Link, ToolProduct
from rn_forge.tooling.install.release import ReleaseSource, fetch_release

__all__ = [
    "CleanupResult",
    "InstallResult",
    "InstallStatus",
    "cleanup",
    "doctor",
    "install",
    "status",
    "uninstall",
    "upgrade",
]

_LOGGER = AppLogger.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InstallResult(DataclassMixin):
    """What ``install``, ``upgrade`` or ``uninstall`` did.

    Args:
        product: The product name.
        outcome: ``installed``, ``already-current``, ``removed`` or
            ``not-installed``.
        version: The version now active, when there is one.
        previous: The version that was active before, when there was one.
    """

    product: str
    outcome: str
    version: str | None = None
    previous: str | None = None


@dataclass(frozen=True, slots=True)
class CleanupResult(DataclassMixin):
    """What ``cleanup`` removed, or would remove.

    Args:
        product: The product name.
        kept: The active version.
        removed: The versions removed — or, on a dry run, to be removed.
        dry_run: Whether anything was actually removed.
    """

    product: str
    kept: str
    removed: list[str] = field(default_factory=list[str])
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class InstallStatus(DataclassMixin):
    """Where a product is installed, and at what version.

    Args:
        product: The product name.
        version: The version of the running code.
        home: The product's directory.
        installed: The version ``current`` points at, or ``None``.
        versions: Every version directory present.
    """

    product: str
    version: str
    home: str
    installed: str | None = None
    versions: list[str] = field(default_factory=list[str])


def install(
    product: ToolProduct,
    *,
    version: str | None = None,
    source: ReleaseSource | None = None,
    home: ToolHome | None = None,
    force: bool = False,
) -> InstallResult:
    """Install *version* of *product* and make it the active one.

    Args:
        product: The product to install.
        version: The version to install. Defaults to the source's latest.
        source: Where to fetch from. Defaults to ``product.source``.
        home: The home to install into. Defaults to the product's.
        force: Reinstall even when *version* is already active.

    Raises:
        AppException: Any step failed; everything it did has been undone.
        BaseException: An interruption, re-raised once everything is undone.
    """
    home = home or ToolHome(product.name)
    source = source or product.source
    target = version or source.latest()
    home.version_dir(target)  # validates the version before anything is written
    with home.lock():
        previous = home.current_version()
        if previous == target and not force:
            return InstallResult(product.name, "already-current", target, previous)
        _install(product, home, source, target, previous)
    _LOGGER.verbose("install: {} {} active (was {})", product.name, target, previous)
    return InstallResult(product.name, "installed", target, previous)


def upgrade(
    product: ToolProduct,
    *,
    source: ReleaseSource | None = None,
    home: ToolHome | None = None,
) -> InstallResult:
    """Install the latest version over an existing install.

    Raises:
        AppException: The product is not installed, or the install failed.
    """
    home = home or ToolHome(product.name)
    if home.current_version() is None:
        raise AppException(
            "{} is not installed under {}; install it first",
            product.name,
            home.product_dir,
        )
    return install(product, source=source, home=home)


def uninstall(product: ToolProduct, *, home: ToolHome | None = None) -> InstallResult:
    """Remove the product's links and its whole directory under the home.

    Works over an install that never completed: nothing here assumes
    ``current`` or ``state.json`` exists. A link is removed only when it still
    points where this product put it — a path someone has since replaced with
    their own file or link is left alone.
    """
    home = home or ToolHome(product.name)
    if not home.product_dir.exists():
        return InstallResult(product.name, "not-installed")
    previous = home.current_version()
    with home.lock():
        for link in product.artifacts():
            path = home.root / link.path
            if path.is_symlink() and os.readlink(path) == _link_target(home, link):
                path.unlink()
        # The lock directory lives inside; releasing it afterwards tolerates
        # its absence.
        shutil.rmtree(home.product_dir)
    return InstallResult(product.name, "removed", previous=previous)


def cleanup(
    product: ToolProduct, *, home: ToolHome | None = None, dry_run: bool = False
) -> CleanupResult:
    """Remove every installed version except the active one, and leftover scratch space.

    Raises:
        AppException: There is no active version to keep.
    """
    home = home or ToolHome(product.name)
    current = home.current_version()
    if current is None:
        raise AppException("{} has no active version to keep", product.name)
    if dry_run:
        stale = [v for v in home.installed_versions() if v != current]
        return CleanupResult(product.name, current, stale, dry_run=True)
    with home.lock():
        current = home.current_version() or current
        stale = [v for v in home.installed_versions() if v != current]
        for stale_version in stale:
            shutil.rmtree(home.version_dir(stale_version))
        shutil.rmtree(home.work_dir, ignore_errors=True)
    return CleanupResult(product.name, current, stale)


def status(product: ToolProduct, *, home: ToolHome | None = None) -> InstallStatus:
    """Report the running version and what is installed. Writes nothing."""
    home = home or ToolHome(product.name)
    return InstallStatus(
        product=product.name,
        version=product.version,
        home=str(home.product_dir),
        installed=home.current_version(),
        versions=home.installed_versions(),
    )


def doctor(product: ToolProduct, *, home: ToolHome | None = None) -> list[Finding]:
    """Inspect the install, then run the product's own checks.

    A product that is not installed is a **warning**, not an error: the same
    command runs from a development checkout, where there is nothing under
    ``$RNF_HOME`` and nothing wrong. The product's checks run either way.

    Returns:
        Every finding, product checks last. Only an ``error`` should fail the
        command.
    """
    home = home or ToolHome(product.name)
    findings = _install_findings(product, home)
    for check in product.checks():
        findings.extend(check(home))
    return findings


# -- install transaction ----------------------------------------------------


def _install(
    product: ToolProduct,
    home: ToolHome,
    source: ReleaseSource,
    target: str,
    previous: str | None,
) -> None:
    """The install transaction proper. The caller holds the lock."""
    undo: list[Callable[[], object]] = []
    work = home.work_dir / f"{target}-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    version_dir = home.version_dir(target)
    displaced = work / "displaced"
    try:
        release_root = fetch_release(source, target, work / "release")

        if version_dir.exists():
            # A reinstall: set the existing directory aside rather than
            # deleting it, so a failed rebuild can put it back.
            version_dir.rename(displaced)
            undo.append(lambda: displaced.rename(version_dir))
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        undo.append(lambda: shutil.rmtree(version_dir, ignore_errors=True))
        product.build(release_root, version_dir)

        for link in product.artifacts():
            undo.append(_place_link(home, link))

        undo.append(_restore_file(home.state_path))
        if previous is not None and previous != target:
            product.migrate(previous, target)
        PathUtils.atomic_write(
            json.dumps(
                {"version": target, "schema_version": product.state_schema_version},
                indent=2,
            )
            + "\n",
            home.state_path,
        )

        undo.append(_restore_current(home))
        home.activate(target)
    except BaseException as exc:
        for step in reversed(undo):
            step()
        if isinstance(exc, Exception):
            raise AppException(
                "Install of {} {} failed and was rolled back: {}",
                product.name,
                target,
                exc,
            ) from exc
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _link_target(home: ToolHome, link: Link) -> str:
    """What *link*'s symlink contains: a relative path through ``current``."""
    path = home.root / link.path
    return os.path.relpath(home.current / link.target, path.parent)


def _place_link(home: ToolHome, link: Link) -> Callable[[], None]:
    """Put *link* in place and return how to undo it.

    Raises:
        AppException: Something other than a symlink is already at the path —
            a file a person put there is not ours to replace.
    """
    path = home.root / link.path
    path.parent.mkdir(parents=True, exist_ok=True)
    PathUtils.assert_within(home.root, path.parent)
    if path.exists() and not path.is_symlink():
        raise AppException("{} exists and is not a link; not replacing it", path)
    before = os.readlink(path) if path.is_symlink() else None
    atomic_symlink(path, _link_target(home, link))

    def restore() -> None:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            atomic_symlink(path, before)

    return restore


def _restore_file(path: Path) -> Callable[[], None]:
    """Snapshot *path*'s bytes now and return how to put them back."""
    before = path.read_bytes() if path.is_file() else None

    def restore() -> None:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            PathUtils.atomic_write(before, path)

    return restore


def _restore_current(home: ToolHome) -> Callable[[], None]:
    """Snapshot where ``current`` points now and return how to point it back."""
    before = os.readlink(home.current) if home.current.is_symlink() else None

    def restore() -> None:
        if before is None:
            home.current.unlink(missing_ok=True)
        else:
            atomic_symlink(home.current, before)

    return restore


# -- doctor -------------------------------------------------------------------


def _install_findings(product: ToolProduct, home: ToolHome) -> list[Finding]:
    """What is true of the install itself, before any product check."""
    current = home.current_version()
    if current is None:
        return [
            Finding(
                "install.not-installed",
                Severity.WARNING,
                f"{product.name} is not installed under {home.product_dir}",
                path=str(home.product_dir),
            )
        ]

    findings: list[Finding] = []
    if not home.current.resolve().is_dir():
        findings.append(
            Finding(
                "install.current-broken",
                Severity.ERROR,
                f"current points at {current}, which is not installed",
                path=str(home.current),
            )
        )
    if current != product.version:
        findings.append(
            Finding(
                "install.version-mismatch",
                Severity.WARNING,
                f"running {product.version}, but {current} is installed",
                details={"running": product.version, "installed": current},
            )
        )
    findings.extend(_state_findings(product, home))
    for link in product.artifacts():
        path = home.root / link.path
        if not path.is_symlink() or os.readlink(path) != _link_target(home, link):
            findings.append(
                Finding(
                    "install.link-missing",
                    Severity.ERROR,
                    f"{link.path} does not link to {link.target}",
                    path=str(path),
                )
            )
        elif not path.exists():
            findings.append(
                Finding(
                    "install.link-broken",
                    Severity.ERROR,
                    f"{link.path} links to {link.target}, which does not exist",
                    path=str(path),
                )
            )
    if not findings:
        findings.append(
            Finding(
                "install.ok",
                Severity.INFO,
                f"{product.name} {current} is installed",
                path=str(home.product_dir),
            )
        )
    return findings


def _state_findings(product: ToolProduct, home: ToolHome) -> list[Finding]:
    """Whether ``state.json`` is readable and at the product's schema version."""
    try:
        recorded = json.loads(home.state_path.read_text(encoding="utf-8"))
        schema = int(recorded["schema_version"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [
            Finding(
                "install.state-unreadable",
                Severity.WARNING,
                f"cannot read the install state: {error}",
                path=str(home.state_path),
            )
        ]
    if schema != product.state_schema_version:
        return [
            Finding(
                "install.state-schema",
                Severity.ERROR,
                f"state is at schema {schema}, this version expects "
                f"{product.state_schema_version}; reinstall to migrate it",
                path=str(home.state_path),
                details={
                    "recorded": schema,
                    "expected": product.state_schema_version,
                },
            )
        ]
    return []
