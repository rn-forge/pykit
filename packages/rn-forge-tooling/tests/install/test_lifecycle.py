"""Tests for rn_forge.tooling.install.lifecycle, home and release."""

from __future__ import annotations

import io
import json
import os
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.tooling.install import (
    Link,
    LocalArchive,
    ToolHome,
    ToolProduct,
    cleanup,
    doctor,
    fetch_release,
    install,
    rnf_home,
    status,
    uninstall,
    upgrade,
)
from rn_forge.tooling.install import home as home_module


def make_archive(directory: Path, version: str) -> Path:
    """A release tarball with one root directory holding bin/tool."""
    archive = directory / f"tool-{version}.tar.gz"
    payload = f"tool {version}\n".encode()
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(f"tool-{version}/bin/tool")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return archive


@dataclass
class FakeSource:
    """A release source serving archives built on demand."""

    directory: Path
    newest: str = "1.0.0"
    fail_download: bool = False

    def latest(self) -> str:
        return self.newest

    def download(self, version: str, destination: Path) -> Path:
        if self.fail_download:
            raise OSError("network down")
        return make_archive(destination, version)

    def checksum(self, version: str) -> str | None:
        return None


@dataclass(frozen=True)
class Tool(ToolProduct):
    migrations: list[tuple[str, str]] = field(default_factory=list)
    fail_migration: bool = False
    fail_build: bool = False

    def build(self, release_root: Path, version_dir: Path) -> None:
        if self.fail_build:
            version_dir.mkdir()
            raise RuntimeError("build exploded")
        super().build(release_root, version_dir)

    def artifacts(self):
        return (Link("bin/tool", "bin/tool"),)

    def checks(self):
        def check(home: ToolHome):
            yield Finding("tool.ok", Severity.INFO, "tool check ran")

        return (check,)

    def migrate(self, frm: str, to: str) -> None:
        if self.fail_migration:
            raise RuntimeError("migration exploded")
        self.migrations.append((frm, to))


@pytest.fixture
def home(tmp_path):
    return ToolHome("tool", tmp_path / "home")


@pytest.fixture
def source(tmp_path):
    releases = tmp_path / "releases"
    releases.mkdir()
    return FakeSource(releases)


def product(source, version="1.0.0", **kwargs):
    return Tool(name="tool", version=version, release_source=source, **kwargs)


class TestHome:
    def test_rnf_home_honours_the_environment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RNF_HOME", str(tmp_path))
        assert rnf_home() == tmp_path

    def test_rnf_home_defaults_when_unset_or_empty(self, monkeypatch):
        monkeypatch.setenv("RNF_HOME", "")
        assert rnf_home() == Path("~/.rn-forge").expanduser()

    @pytest.mark.parametrize("bad", ["..", "../x", "a/b", ""])
    def test_a_version_that_is_not_one_segment_is_rejected(self, home, bad):
        with pytest.raises(AppException):
            home.version_dir(bad)

    def test_activate_writes_a_relative_link(self, home):
        home.version_dir("1.0.0").mkdir(parents=True)
        home.activate("1.0.0")
        assert os.readlink(home.current) == "versions/1.0.0"
        assert home.current_version() == "1.0.0"


class TestInstall:
    def test_installs_links_and_activates(self, home, source):
        result = install(product(source), home=home)
        assert result.outcome == "installed"
        assert home.current_version() == "1.0.0"
        link = home.root / "bin/tool"
        assert link.read_text() == "tool 1.0.0\n"
        state = json.loads(home.state_path.read_text())
        assert state == {"version": "1.0.0", "schema_version": 1}
        assert not home.work_dir.exists() or not any(home.work_dir.iterdir())

    def test_the_active_version_is_not_reinstalled(self, home, source):
        install(product(source), home=home)
        assert install(product(source), home=home).outcome == "already-current"

    def test_force_reinstalls_the_active_version(self, home, source):
        install(product(source), home=home)
        assert install(product(source), home=home, force=True).outcome == "installed"
        assert home.installed_versions() == ["1.0.0"]

    def test_upgrade_migrates_and_swaps(self, home, source):
        install(product(source), home=home)
        source.newest = "2.0.0"
        tool = product(source)
        result = upgrade(tool, home=home)
        assert (result.version, result.previous) == ("2.0.0", "1.0.0")
        assert tool.migrations == [("1.0.0", "2.0.0")]
        assert (home.root / "bin/tool").read_text() == "tool 2.0.0\n"

    def test_upgrade_requires_an_install(self, home, source):
        with pytest.raises(AppException, match="not installed"):
            upgrade(product(source), home=home)

    def test_a_local_archive_installs_and_verifies(self, home, source, tmp_path):
        archive = make_archive(tmp_path, "3.0.0")
        from rn_forge.commons.fs.hashing import ContentHash

        good = LocalArchive(archive, "3.0.0", ContentHash.of_file(archive))
        install(product(source), home=home, source=good)
        assert home.current_version() == "3.0.0"

    def test_a_checksum_mismatch_is_rejected(self, tmp_path):
        archive = make_archive(tmp_path, "3.0.0")
        with pytest.raises(AppException, match="Checksum mismatch"):
            fetch_release(
                LocalArchive(archive, "3.0.0", "0" * 64), "3.0.0", tmp_path / "w"
            )


class TestRollback:
    def _installed_at_one(self, home, source):
        install(product(source), home=home)
        source.newest = "2.0.0"

    def _assert_still_one(self, home):
        assert home.current_version() == "1.0.0"
        assert home.installed_versions() == ["1.0.0"]
        assert (home.root / "bin/tool").read_text() == "tool 1.0.0\n"
        assert json.loads(home.state_path.read_text())["version"] == "1.0.0"

    def test_a_failed_download_changes_nothing(self, home, source):
        self._installed_at_one(home, source)
        source.fail_download = True
        with pytest.raises(AppException, match="rolled back"):
            upgrade(product(source), home=home)
        self._assert_still_one(home)

    def test_a_failed_first_install_leaves_no_version(self, home, source):
        source.fail_download = True
        with pytest.raises(AppException):
            install(product(source), home=home)
        assert home.current_version() is None
        assert home.installed_versions() == []
        assert not (home.root / "bin/tool").is_symlink()

    def test_a_failed_migration_restores_the_previous_version(self, home, source):
        self._installed_at_one(home, source)
        with pytest.raises(AppException, match="migration exploded"):
            upgrade(product(source, fail_migration=True), home=home)
        self._assert_still_one(home)

    def test_an_interrupted_swap_restores_and_reraises(self, home, source, monkeypatch):
        self._installed_at_one(home, source)

        def interrupted(link, target):
            raise KeyboardInterrupt

        monkeypatch.setattr(home_module, "atomic_symlink", interrupted)
        with pytest.raises(KeyboardInterrupt):
            upgrade(product(source), home=home)
        monkeypatch.undo()
        self._assert_still_one(home)

    def test_a_failed_reinstall_restores_the_version_directory(self, home, source):
        install(product(source), home=home)
        with pytest.raises(AppException, match="build exploded"):
            install(product(source, fail_build=True), home=home, force=True)
        assert (home.version_dir("1.0.0") / "bin/tool").read_text() == "tool 1.0.0\n"
        self._assert_still_one(home)

    def test_a_file_in_the_way_of_a_link_aborts(self, home, source):
        (home.root / "bin").mkdir(parents=True)
        (home.root / "bin/tool").write_text("mine")
        with pytest.raises(AppException, match="not a link"):
            install(product(source), home=home)
        assert (home.root / "bin/tool").read_text() == "mine"
        assert home.current_version() is None


class TestUninstallAndCleanup:
    def test_uninstall_removes_the_product_and_its_links(self, home, source):
        install(product(source), home=home)
        result = uninstall(product(source), home=home)
        assert (result.outcome, result.previous) == ("removed", "1.0.0")
        assert not home.product_dir.exists()
        assert not (home.root / "bin/tool").is_symlink()

    def test_uninstall_over_an_install_that_never_completed(self, home, source):
        (home.version_dir("1.0.0") / "bin").mkdir(parents=True)
        (home.work_dir / "1.0.0-123").mkdir(parents=True)
        assert uninstall(product(source), home=home).outcome == "removed"
        assert not home.product_dir.exists()

    def test_uninstall_leaves_a_link_it_does_not_own(self, home, source):
        install(product(source), home=home)
        link = home.root / "bin/tool"
        link.unlink()
        link.symlink_to("/somewhere/else")
        uninstall(product(source), home=home)
        assert link.is_symlink()

    def test_uninstall_of_nothing(self, home, source):
        assert uninstall(product(source), home=home).outcome == "not-installed"

    def test_cleanup_keeps_only_the_active_version(self, home, source):
        install(product(source), home=home)
        source.newest = "2.0.0"
        upgrade(product(source), home=home)
        planned = cleanup(product(source), home=home, dry_run=True)
        assert (planned.kept, planned.removed) == ("2.0.0", ["1.0.0"])
        assert home.installed_versions() == ["1.0.0", "2.0.0"]
        cleanup(product(source), home=home)
        assert home.installed_versions() == ["2.0.0"]

    def test_cleanup_needs_an_active_version(self, home, source):
        with pytest.raises(AppException):
            cleanup(product(source), home=home)


class TestStatusAndDoctor:
    def test_status_reports_running_and_installed(self, home, source):
        install(product(source), home=home)
        result = status(product(source, version="1.0.0"), home=home).as_dict()
        assert result["version"] == "1.0.0"
        assert result["installed"] == "1.0.0"
        assert result["versions"] == ["1.0.0"]

    def test_doctor_on_a_dev_checkout_warns_and_runs_product_checks(self, home, source):
        findings = doctor(product(source), home=home)
        codes = [f.code for f in findings]
        assert codes == ["install.not-installed", "tool.ok"]
        assert not any(f.is_error for f in findings)

    def test_doctor_on_a_healthy_install(self, home, source):
        install(product(source), home=home)
        codes = [f.code for f in doctor(product(source), home=home)]
        assert codes == ["install.ok", "tool.ok"]

    def test_doctor_reports_a_missing_link_and_a_schema_change(self, home, source):
        install(product(source), home=home)
        (home.root / "bin/tool").unlink()
        tool = Tool(
            name="tool", version="1.0.0", release_source=source, state_schema_version=2
        )
        errors = {f.code for f in doctor(tool, home=home) if f.is_error}
        assert errors == {"install.link-missing", "install.state-schema"}

    def test_doctor_reports_a_version_mismatch(self, home, source):
        install(product(source), home=home)
        codes = [f.code for f in doctor(product(source, version="0.9.0"), home=home)]
        assert "install.version-mismatch" in codes


def test_a_product_without_a_source_says_so():
    with pytest.raises(AppException, match="neither a release source"):
        _ = ToolProduct(name="bare", version="1").source


def test_a_link_cannot_escape_the_home():
    with pytest.raises(AppException):
        Link("../outside", "bin/tool")
