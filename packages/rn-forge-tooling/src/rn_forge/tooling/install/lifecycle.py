"""Transactional install, upgrade, removal, status, and diagnostic operations."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.commons.fs.locks import atomic_symlink
from rn_forge.commons.fs.paths import PathUtils
from rn_forge.commons.lang.dataclasses import DataclassMixin
from rn_forge.commons.logging import AppLogger
from rn_forge.tooling.install.archive import extract_archive
from rn_forge.tooling.install.home import (
    ENV_SCHEMA,
    EnvWrite,
    ToolHome,
    env_hint,
    env_schema,
    write_env,
)
from rn_forge.tooling.install.product import Link, ToolProduct
from rn_forge.tooling.install.release import (
    GitHubReleases,
    ReleaseSource,
    fetch_release,
)

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
        env: What the install did to ``env.sh`` (an :class:`EnvWrite` value),
            or ``None`` when nothing was installed.
        hint: How to source ``env.sh``, when ``bin/`` is not on ``PATH`` after
            an install; ``None`` otherwise.
    """

    product: str
    outcome: str
    version: str | None = None
    previous: str | None = None
    env: str | None = None
    hint: str | None = None


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
        ref: What the install was asked for: a branch, tag or commit SHA, or
            the release tag. ``None`` when nothing is recorded.
        commit: The installed commit's SHA for a ref install, else ``None``.
        package_version: The package version recorded at install, or ``None``.
    """

    product: str
    version: str
    home: str
    installed: str | None = None
    versions: list[str] = field(default_factory=list[str])
    ref: str | None = None
    commit: str | None = None
    package_version: str | None = None


def install(
    product: ToolProduct,
    *,
    version: str | None = None,
    source: ReleaseSource | None = None,
    home: ToolHome | None = None,
    force: bool = False,
    ref: str | None = None,
) -> InstallResult:
    """Install *version* of *product*, or the commit *ref* names, and make it active.

    Args:
        product: The product to install.
        version: The version to install. Defaults to the source's latest.
            Not combined with *ref*.
        source: Where to fetch from. Defaults to ``product.source``.
        home: The home to install into. Defaults to the product's.
        force: Reinstall even when *version* is already active.
        ref: A branch, tag or commit SHA of the source's GitHub repository.
            The install is recorded under the first 12 characters of the
            commit.

    Raises:
        AppException: Both *version* and *ref* were given, *ref* was given
            for a source that is not a :class:`GitHubReleases`, the product's
            ``preflight`` refused, or a step failed; all undo steps were
            attempted, with any recovery failures and retained displaced
            version's path reported.
        BaseException: An interruption, re-raised after recovery with any
            recovery failures and retained path logged at error level.
    """
    home = home or ToolHome(product.name)
    product.preflight()
    source = source or product.source
    sha: str | None = None
    if ref is not None:
        if version is not None:
            raise AppException("A version and a ref cannot be combined")
        if not isinstance(source, GitHubReleases):
            raise AppException(
                "{} cannot install a ref: its source is not a GitHub repository",
                product.name,
            )
        sha = source.resolve(ref)
        target = sha[:12]
    else:
        target = version or source.latest()
    home.version_dir(target)  # validates the version before anything is written
    with home.lock():
        previous = home.current_version()
        if previous == target and not force:
            return InstallResult(
                product.name,
                "already-current",
                target,
                previous,
                hint=env_hint(home.root),
            )
        env = _install(product, home, source, target, previous, ref, sha)
    _LOGGER.verbose("install: {} {} active (was {})", product.name, target, previous)
    return InstallResult(
        product.name,
        "installed",
        target,
        previous,
        env=env.value,
        hint=env_hint(home.root),
    )


def upgrade(
    product: ToolProduct,
    *,
    source: ReleaseSource | None = None,
    home: ToolHome | None = None,
) -> InstallResult:
    """Move an existing install forward.

    A ref install re-resolves its recorded ref and installs that commit, or
    returns ``already-current`` when it has not moved. Any other install moves
    to the source's latest version.

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
    recorded = _recorded(product, home)
    ref, commit = recorded.get("ref"), recorded.get("commit")
    if isinstance(ref, str) and ref and isinstance(commit, str) and commit:
        return install(product, source=source, home=home, ref=ref)
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
        if home.work_dir.is_dir():
            for entry in home.work_dir.iterdir():
                if entry.is_dir() and (entry / "displaced").exists():
                    _LOGGER.warning(  # noqa: PLE1205  # brace-style log format
                        "Keeping retained transaction directory {}", entry
                    )
                elif entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
    return CleanupResult(product.name, current, stale)


def status(product: ToolProduct, *, home: ToolHome | None = None) -> InstallStatus:
    """Report the running version and what is installed. Writes nothing."""
    home = home or ToolHome(product.name)
    recorded = _recorded(product, home)
    return InstallStatus(
        product=product.name,
        version=product.version,
        home=str(home.product_dir),
        installed=home.current_version(),
        versions=home.installed_versions(),
        ref=_text(recorded, "ref"),
        commit=_text(recorded, "commit"),
        package_version=_text(recorded, "version"),
    )


def doctor(product: ToolProduct, *, home: ToolHome | None = None) -> list[Finding]:
    """Inspect the install, then run the product's own checks.

    A product that is not installed is a **warning**, not an error: the same
    command runs from a development checkout, where there is nothing under
    ``$RNF_HOME`` and nothing wrong. The ``home.*`` rows are warnings for the
    same reason: a development checkout has no hooked-up home. Both they and
    the product's checks run either way.

    Returns:
        Every finding, product checks last. Only an ``error`` should fail the
        command.
    """
    home = home or ToolHome(product.name)
    findings = _install_findings(product, home) + _home_findings(home)
    for check in product.checks():
        findings.extend(check(home))
    return findings


# -- install transaction ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Prepared:
    """A transaction's work directory and verified, extracted release root."""

    work: Path
    release_root: Path


def _install(
    product: ToolProduct,
    home: ToolHome,
    source: ReleaseSource,
    target: str,
    previous: str | None,
    ref: str | None,
    sha: str | None,
) -> EnvWrite:
    """Prepare and activate a release or commit. The caller holds the lock."""
    prepared = _prepare(product, home, source, target, sha)
    undo: list[tuple[str, Callable[[], object]]] = []
    retained = False
    try:
        return _activate(
            product, home, source, prepared, target, previous, ref, sha, undo
        )
    except BaseException as exc:
        failures = _recover(undo)
        retained = prepared.work.joinpath("displaced").exists()
        _failure(product, target, exc, failures, prepared.work, retained)
        raise
    finally:
        if not retained:
            shutil.rmtree(prepared.work, ignore_errors=True)


def _prepare(
    product: ToolProduct,
    home: ToolHome,
    source: ReleaseSource,
    target: str,
    sha: str | None,
) -> _Prepared:
    """Download, verify and extract a release or commit; remove its work directory on failure."""
    work: Path | None = None
    try:
        home.work_dir.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=f"{target}-", dir=home.work_dir))
        if sha is None:
            root = fetch_release(source, target, work / "release")
        else:
            assert isinstance(source, GitHubReleases)  # noqa: S101  # checked by install
            (work / "release").mkdir()
            archive = source.download_commit(sha, work / "release")
            root = extract_archive(archive, work / "release" / "extracted")
        return _Prepared(work, root)
    except BaseException as exc:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
        _failure(product, target, exc, [], work, False)
        raise


def _activate(
    product: ToolProduct,
    home: ToolHome,
    source: ReleaseSource,
    prepared: _Prepared,
    target: str,
    previous: str | None,
    ref: str | None,
    sha: str | None,
    undo: list[tuple[str, Callable[[], object]]],
) -> EnvWrite:
    """Build and activate a release, appending recovery steps to *undo*.

    Returns:
        What was done to ``env.sh``.
    """
    version_dir = home.version_dir(target)
    displaced = prepared.work / "displaced"
    if version_dir.exists():
        # A failed reinstall must be able to put the existing directory back.
        version_dir.rename(displaced)
        undo.append(
            ("restore displaced version", lambda: displaced.rename(version_dir))
        )
    version_dir.parent.mkdir(parents=True, exist_ok=True)
    undo.append(
        (
            f"remove versions/{target}",
            lambda: shutil.rmtree(version_dir, ignore_errors=True),
        )
    )
    product.build(prepared.release_root, version_dir)

    for link in product.artifacts():
        undo.append((f"restore link {link.path}", _place_link(home, link)))

    undo.append(("restore env.sh", _restore_file(home.env_path)))
    env = write_env(home.root)

    undo.append(("restore state.json", _restore_file(home.state_path)))
    if previous is not None and previous != target:
        product.migrate(previous, target)
    PathUtils.atomic_write(
        json.dumps(
            {
                "version": target if sha is None else _source_version(prepared, target),
                "ref": ref if ref is not None else _tag(source, target),
                "commit": sha,
                "schema_version": product.state_schema_version,
            },
            indent=2,
        )
        + "\n",
        home.state_path,
    )

    undo.append(("restore current", _restore_current(home)))
    home.activate(target)
    return env


def _text(recorded: dict[str, Any], key: str) -> str | None:
    """*key*'s value when it is a non-empty string."""
    value = recorded.get(key)
    return value if isinstance(value, str) and value else None


def _recorded(product: ToolProduct, home: ToolHome) -> dict[str, Any]:
    """``state.json``'s object, or ``{}`` when it cannot be read.

    A state with no ``ref`` was recorded as a release install: its ``ref`` is
    the release tag and its ``commit`` is ``None``.
    """
    try:
        state = json.loads(home.state_path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    if not isinstance(state, dict):
        return {}
    recorded = cast(dict[str, Any], state)
    if "ref" not in recorded:
        version = _text(recorded, "version") or home.current_version()
        if version is not None:
            try:
                source: ReleaseSource | None = product.source
            except AppException:
                source = None
            recorded["ref"] = version if source is None else _tag(source, version)
        recorded["commit"] = None
    return recorded


def _tag(source: ReleaseSource, target: str) -> str:
    """The tag a release install came from."""
    if isinstance(source, GitHubReleases):
        return source.tag_prefix + target
    return target


def _source_version(prepared: _Prepared, default: str) -> str:
    """``[project] version`` of the extracted tree, or *default* when absent."""
    try:
        with (prepared.release_root / "pyproject.toml").open("rb") as stream:
            return str(tomllib.load(stream)["project"]["version"])
    except OSError, KeyError, TypeError, ValueError:
        return default


def _recover(
    undo: list[tuple[str, Callable[[], object]]],
) -> list[tuple[str, Exception]]:
    """Attempt every undo step in reverse order and return recovery failures."""
    failures: list[tuple[str, Exception]] = []
    for label, step in reversed(undo):
        try:
            step()
        except Exception as error:  # noqa: BLE001 - attempt every undo step
            failures.append((label, error))
    return failures


def _failure(
    product: ToolProduct,
    target: str,
    exc: BaseException,
    failures: list[tuple[str, Exception]],
    work: Path | None,
    retained: bool,
) -> None:
    """Raise an install error, or log incomplete recovery for an interruption."""
    if failures:
        details = "; ".join(f"{label}: {error}" for label, error in failures)
        if retained:
            details += f"; the previous version is kept at {work}"
        if isinstance(exc, Exception):
            raise AppException(
                "Install of {} {} failed: {}; recovery is incomplete: {}",
                product.name,
                target,
                exc,
                details,
            ) from exc
        _LOGGER.error(  # noqa: PLE1205  # brace-style log format
            "Install of {} {} failed: {}; recovery is incomplete: {}",
            product.name,
            target,
            exc,
            details,
        )
    if isinstance(exc, Exception):
        raise AppException(
            "Install of {} {} failed and was rolled back: {}",
            product.name,
            target,
            exc,
        ) from exc


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


def _home_findings(home: ToolHome) -> list[Finding]:
    """What is true of the shell's hookup to the home: ``env.sh`` and ``PATH``."""
    findings: list[Finding] = []
    if not home.env_path.is_file():
        findings.append(
            Finding(
                "home.env-missing",
                Severity.WARNING,
                f"{home.env_path} does not exist; any install writes it",
                path=str(home.env_path),
            )
        )
    else:
        recorded = env_schema(home.root)
        if recorded is not None and recorded < ENV_SCHEMA:
            findings.append(
                Finding(
                    "home.env-stale",
                    Severity.WARNING,
                    f"{home.env_path} is at schema {recorded}, this version "
                    f"writes {ENV_SCHEMA}; any install rewrites it",
                    path=str(home.env_path),
                    details={"recorded": recorded, "expected": ENV_SCHEMA},
                )
            )
    hint = env_hint(home.root)
    if hint is not None:
        findings.append(
            Finding(
                "home.not-on-path",
                Severity.WARNING,
                hint,
                path=str(home.root / "bin"),
            )
        )
    return findings


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
    installed = _text(_recorded(product, home), "version") or current
    if installed != product.version:
        findings.append(
            Finding(
                "install.version-mismatch",
                Severity.WARNING,
                f"running {product.version}, but {installed} is installed",
                details={"running": product.version, "installed": installed},
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
