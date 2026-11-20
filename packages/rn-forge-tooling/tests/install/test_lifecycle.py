"""Tests for rn_forge.tooling.install.lifecycle, home and release."""

from __future__ import annotations

import io
import json
import os
import tarfile
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.findings import Finding, Severity
from rn_forge.commons.fs.hashing import ContentHash
from rn_forge.tooling.install import (
    GitHubReleases,
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
from rn_forge.tooling.install import lifecycle as lifecycle_module
from rn_forge.tooling.install.home import render_env


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


SHA = "0123456789abcdef0123456789abcdef01234567"


SHA2 = "fedcba9876543210fedcba9876543210fedcba98"


def make_commit_archive(sha: str = SHA) -> bytes:
    """A commit tarball: one root directory with bin/tool and a pyproject.toml."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, payload in (
            (f"r-{sha}/bin/tool", b"tool main\n"),
            (f"r-{sha}/pyproject.toml", b'[project]\nversion = "1.1.0.dev0"\n'),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class _GitHubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        heads: dict[str, str] = self.server.heads  # type: ignore[attr-defined]
        prefix = "/repos/o/r/commits/"
        archive = "/o/r/archive/"
        if self.path.startswith(prefix) and (
            self.path[len(prefix) :] in heads
            or self.path[len(prefix) :] in heads.values()
        ):
            ref = self.path[len(prefix) :]
            body = json.dumps({"sha": heads.get(ref, ref)}).encode()
        elif self.path.startswith(archive) and self.path.endswith(".tar.gz"):
            sha = self.path[len(archive) : -len(".tar.gz")]
            if sha not in heads.values():
                self.send_error(404)
                return
            body = make_commit_archive(sha)
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def heads():
    """The fake GitHub's branches and tags, ref to commit."""
    return {"main": SHA, "v1.0.0": SHA}


@pytest.fixture
def github(heads):
    """A GitHubReleases for ``o/r`` served by a local fake GitHub."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GitHubHandler)
    server.heads = heads  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield GitHubReleases("o/r", api_url=url, web_url=url)
    server.shutdown()
    server.server_close()
    thread.join()


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
    def test_install_writes_env_sh(self, home, source):
        result = install(product(source), home=home)
        assert home.env_path.read_text() == render_env(home.root)
        assert result.env == "written"

    def test_installs_links_and_activates(self, home, source):
        result = install(product(source), home=home)
        assert result.outcome == "installed"
        assert home.current_version() == "1.0.0"
        link = home.root / "bin/tool"
        assert link.read_text() == "tool 1.0.0\n"
        state = json.loads(home.state_path.read_text())
        assert state == {
            "version": "1.0.0",
            "ref": "1.0.0",
            "commit": None,
            "schema_version": 1,
        }
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
        tool = product(source)
        with pytest.raises(AppException, match="not installed"):
            upgrade(tool, home=home)

    def test_a_local_archive_installs_and_verifies(self, home, source, tmp_path):
        archive = make_archive(tmp_path, "3.0.0")
        from rn_forge.commons.fs.hashing import ContentHash

        good = LocalArchive(archive, "3.0.0", ContentHash.of_file(archive))
        install(product(source), home=home, source=good)
        assert home.current_version() == "3.0.0"

    def test_a_checksum_mismatch_is_rejected(self, tmp_path):
        archive = make_archive(tmp_path, "3.0.0")
        bad = LocalArchive(archive, "3.0.0", "0" * 64)
        with pytest.raises(AppException, match="Checksum mismatch"):
            fetch_release(bad, "3.0.0", tmp_path / "w")


class TestRollback:
    def _fail_activation(self, home, source, monkeypatch):
        def boom(self, version):
            raise RuntimeError("activation exploded")

        monkeypatch.setattr(ToolHome, "activate", boom)
        with pytest.raises(AppException, match="activation exploded"):
            install(product(source), home=home)

    def test_a_failed_install_removes_the_env_sh_it_created(
        self, home, source, monkeypatch
    ):
        self._fail_activation(home, source, monkeypatch)
        assert not home.env_path.exists()

    def test_a_failed_install_restores_the_previous_env_sh(
        self, home, source, monkeypatch
    ):
        home.root.mkdir(parents=True)
        old = "# rn-forge home environment, schema 0. Old.\n"
        home.env_path.write_text(old)
        self._fail_activation(home, source, monkeypatch)
        assert home.env_path.read_text() == old

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
        tool = product(source)
        with pytest.raises(AppException, match="rolled back"):
            upgrade(tool, home=home)
        self._assert_still_one(home)

    def test_a_failed_first_install_leaves_no_version(self, home, source):
        source.fail_download = True
        tool = product(source)
        with pytest.raises(AppException):
            install(tool, home=home)
        assert home.current_version() is None
        assert home.installed_versions() == []
        assert not (home.root / "bin/tool").is_symlink()

    def test_a_failed_migration_restores_the_previous_version(self, home, source):
        self._installed_at_one(home, source)
        tool = product(source, fail_migration=True)
        with pytest.raises(AppException, match="migration exploded"):
            upgrade(tool, home=home)
        self._assert_still_one(home)

    def test_an_interrupted_swap_restores_and_reraises(self, home, source, monkeypatch):
        self._installed_at_one(home, source)

        def interrupted(link, target):
            raise KeyboardInterrupt

        monkeypatch.setattr(home_module, "atomic_symlink", interrupted)
        tool = product(source)
        with pytest.raises(KeyboardInterrupt):
            upgrade(tool, home=home)
        monkeypatch.undo()
        self._assert_still_one(home)

    def test_a_failed_reinstall_restores_the_version_directory(self, home, source):
        install(product(source), home=home)
        tool = product(source, fail_build=True)
        with pytest.raises(AppException, match="build exploded"):
            install(tool, home=home, force=True)
        assert (home.version_dir("1.0.0") / "bin/tool").read_text() == "tool 1.0.0\n"
        self._assert_still_one(home)

    def test_a_file_in_the_way_of_a_link_aborts(self, home, source):
        (home.root / "bin").mkdir(parents=True)
        (home.root / "bin/tool").write_text("mine")
        tool = product(source)
        with pytest.raises(AppException, match="not a link"):
            install(tool, home=home)
        assert (home.root / "bin/tool").read_text() == "mine"
        assert home.current_version() is None


class TestPreparation:
    def test_a_checksum_mismatch_leaves_the_prior_install_usable(
        self, home, source, tmp_path
    ):
        TestRollback()._installed_at_one(home, source)
        bad = LocalArchive(make_archive(tmp_path, "2.0.0"), "2.0.0", "0" * 64)
        target = product(source, fail_build=True)
        with pytest.raises(AppException, match="Checksum mismatch"):
            install(target, home=home, source=bad)
        TestRollback()._assert_still_one(home)
        assert not home.version_dir("2.0.0").exists()

    def test_a_malformed_archive_leaves_the_prior_install_usable(
        self, home, source, tmp_path
    ):
        TestRollback()._installed_at_one(home, source)
        archive = tmp_path / "malformed.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for root in ("one", "two"):
                info = tarfile.TarInfo(f"{root}/bin/tool")
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))
        target = product(source)
        local = LocalArchive(archive, "2.0.0")
        with pytest.raises(AppException, match="exactly one root directory"):
            install(target, home=home, source=local)
        TestRollback()._assert_still_one(home)

    def test_an_interrupted_download_restores_nothing_and_reraises(
        self, home, source, monkeypatch
    ):
        TestRollback()._installed_at_one(home, source)

        def interrupted(version, destination):
            raise KeyboardInterrupt

        def unexpected_recovery(*args):
            pytest.fail("preparation must not restore install state")

        monkeypatch.setattr(source, "download", interrupted)
        monkeypatch.setattr(lifecycle_module, "_restore_file", unexpected_recovery)
        monkeypatch.setattr(lifecycle_module, "_restore_current", unexpected_recovery)
        target = product(source)
        with pytest.raises(KeyboardInterrupt):
            install(target, home=home)
        TestRollback()._assert_still_one(home)
        assert not any(home.work_dir.iterdir())

    def test_preparation_runs_under_the_lock(self, home, source, monkeypatch):
        download = source.download
        errors = []

        def under_lock(version, destination):
            with (
                pytest.raises(AppException) as excinfo,
                ToolHome("tool", home.root).lock(timeout=0.1),
            ):
                pass
            errors.append(excinfo.value)
            return download(version, destination)

        monkeypatch.setattr(source, "download", under_lock)
        assert install(product(source), home=home).outcome == "installed"
        assert len(errors) == 1

    def test_a_release_is_downloaded_and_hashed_once(
        self, home, source, tmp_path, monkeypatch
    ):
        archive = make_archive(tmp_path, "2.0.0")
        local = LocalArchive(archive, "2.0.0", ContentHash.of_file(archive))
        download = LocalArchive.download
        of_file = ContentHash.of_file
        counts = {"downloads": 0, "hashes": 0}

        def counted_download(self, version, destination):
            counts["downloads"] += 1
            return download(self, version, destination)

        def counted_hash(path):
            counts["hashes"] += 1
            return of_file(path)

        monkeypatch.setattr(LocalArchive, "download", counted_download)
        monkeypatch.setattr(ContentHash, "of_file", staticmethod(counted_hash))
        install(product(source), home=home, source=local)
        assert counts == {"downloads": 1, "hashes": 1}

    def test_a_failed_preparation_never_builds_or_migrates(self, home, source):
        TestRollback()._installed_at_one(home, source)
        source.fail_download = True
        target = product(source, fail_migration=True, fail_build=True)
        with pytest.raises(AppException, match="network down"):
            install(target, home=home)
        TestRollback()._assert_still_one(home)


class TestRecoveryFailure:
    def test_a_failed_undo_step_does_not_stop_remaining_recovery(
        self, home, source, monkeypatch
    ):
        install(product(source), home=home)
        source.newest = "2.0.0"
        migration_error = RuntimeError("migration exploded")
        tool = product(source)

        def fail_migration(self, frm, to):
            raise migration_error

        monkeypatch.setattr(Tool, "migrate", fail_migration)
        atomic_symlink = lifecycle_module.atomic_symlink
        calls = 0

        def fail_restore(link, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("undo failed")
            return atomic_symlink(link, target)

        monkeypatch.setattr(lifecycle_module, "atomic_symlink", fail_restore)
        with pytest.raises(
            AppException,
            match="migration exploded.*recovery is incomplete.*restore link",
        ) as excinfo:
            upgrade(tool, home=home)
        assert excinfo.value.__cause__ is migration_error
        assert not home.version_dir("2.0.0").exists()
        assert json.loads(home.state_path.read_text())["version"] == "1.0.0"

    def test_a_failed_restoration_keeps_the_displaced_version(
        self, home, source, monkeypatch
    ):
        install(product(source), home=home)
        rename = Path.rename

        def fail_restore(path, target):
            if path.name == "displaced":
                raise OSError("restore failed")
            return rename(path, target)

        monkeypatch.setattr(Path, "rename", fail_restore)
        target = product(source, fail_build=True)
        with pytest.raises(AppException, match="recovery is incomplete") as excinfo:
            install(target, home=home, force=True)
        binaries = list(home.work_dir.glob("*/displaced/bin/tool"))
        assert len(binaries) == 1
        assert binaries[0].read_text() == "tool 1.0.0\n"
        assert home.work_dir in binaries[0].parents
        assert str(binaries[0].parents[2]) in str(excinfo.value)

    def test_an_interrupted_install_with_failed_restoration_keeps_the_displaced_version(
        self, home, source, monkeypatch, caplog
    ):
        install(product(source), home=home)
        rename = Path.rename

        def fail_restore(path, target):
            if path.name == "displaced":
                raise OSError("restore failed")
            return rename(path, target)

        def interrupt(self, version):
            raise KeyboardInterrupt

        monkeypatch.setattr(Path, "rename", fail_restore)
        monkeypatch.setattr(ToolHome, "activate", interrupt)
        target = product(source)
        with pytest.raises(KeyboardInterrupt):
            install(target, home=home, force=True)
        binaries = list(home.work_dir.glob("*/displaced/bin/tool"))
        assert len(binaries) == 1
        assert binaries[0].read_text() == "tool 1.0.0\n"
        assert "restore displaced version" in caplog.text
        assert str(binaries[0].parents[2]) in caplog.text

    @pytest.mark.parametrize("boundary", ["link", "state", "activate"])
    def test_a_failure_at_each_mutation_boundary_restores_the_previous_version(
        self, boundary, home, source, monkeypatch
    ):
        TestRollback()._installed_at_one(home, source)
        if boundary == "link":
            original = lifecycle_module.atomic_symlink
            calls = 0

            def fail_once(link, target):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("mutation failed")
                return original(link, target)

            monkeypatch.setattr(lifecycle_module, "atomic_symlink", fail_once)
        elif boundary == "state":
            original = lifecycle_module.PathUtils.atomic_write
            calls = 0

            def fail_once(content, path):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("mutation failed")
                return original(content, path)

            monkeypatch.setattr(lifecycle_module.PathUtils, "atomic_write", fail_once)
        else:
            original = ToolHome.activate
            calls = 0

            def fail_once(self, version):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("mutation failed")
                return original(self, version)

            monkeypatch.setattr(ToolHome, "activate", fail_once)
        target = product(source)
        with pytest.raises(AppException, match="rolled back"):
            upgrade(target, home=home)
        TestRollback()._assert_still_one(home)


class TestUninstallAndCleanup:
    def test_cleanup_keeps_a_retained_directory(self, home, source):
        install(product(source), home=home)
        retained = home.work_dir / "1.0.0-a"
        disposable = home.work_dir / "2.0.0-b"
        (retained / "displaced").mkdir(parents=True)
        (disposable / "release").mkdir(parents=True)
        cleanup(product(source), home=home)
        assert retained.exists()
        assert not disposable.exists()

    def test_a_later_install_keeps_a_retained_directory(self, home, source):
        install(product(source), home=home)
        retained_file = home.work_dir / f"1.0.0-{os.getpid()}" / "displaced" / "keep"
        retained_file.parent.mkdir(parents=True)
        retained_file.touch()
        install(product(source), home=home, force=True)
        assert retained_file.exists()

    def test_uninstall_removes_the_product_and_its_links(self, home, source):
        install(product(source), home=home)
        result = uninstall(product(source), home=home)
        assert (result.outcome, result.previous) == ("removed", "1.0.0")
        assert not home.product_dir.exists()
        assert not (home.root / "bin/tool").is_symlink()

    def test_uninstall_leaves_the_home_files(self, home, source):
        install(product(source), home=home)
        home.completions_dir.mkdir()
        uninstall(product(source), home=home)
        assert home.env_path.is_file()
        assert (home.root / "bin").is_dir()
        assert home.completions_dir.is_dir()

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
        tool = product(source)
        with pytest.raises(AppException):
            cleanup(tool, home=home)


class TestGitHubRefs:
    @pytest.mark.parametrize("ref", ["main", "v1.0.0", SHA])
    def test_resolve_returns_the_commit(self, github, ref):
        assert github.resolve(ref) == SHA

    def test_download_commit_writes_the_archive(self, github, tmp_path):
        archive = github.download_commit(SHA, tmp_path)
        assert archive == tmp_path / f"{SHA}.tar.gz"
        assert tarfile.is_tarfile(archive)

    def test_an_unknown_ref_is_named(self, github):
        with pytest.raises(AppException, match="nope"):
            github.resolve("nope")


class TestRefInstall:
    def test_a_branch_installs_under_its_short_commit(self, home, github):
        result = install(product(github), ref="main", home=home)
        assert result.version == SHA[:12]
        assert (home.versions_dir / SHA[:12]).is_dir()
        assert home.current_version() == SHA[:12]
        assert json.loads(home.state_path.read_text()) == {
            "version": "1.1.0.dev0",
            "ref": "main",
            "commit": SHA,
            "schema_version": 1,
        }

    def test_an_unknown_ref_leaves_the_home_untouched(self, home, github):
        target = product(github)
        with pytest.raises(AppException):
            install(target, ref="nope", home=home)
        assert not (home.product_dir / "versions").exists()
        assert not home.state_path.exists()

    def test_version_and_ref_together_are_rejected(self, home, github):
        target = product(github)
        with pytest.raises(AppException):
            install(target, version="1.0.0", ref="main", home=home)

    def test_a_ref_needs_a_github_source(self, home, source):
        target = product(source)
        with pytest.raises(AppException, match="cannot install a ref"):
            install(target, ref="main", home=home)
        assert not home.state_path.exists()

    def test_a_release_install_records_its_tag(self, home, source):
        install(product(source), home=home)
        state = json.loads(home.state_path.read_text())
        assert state["ref"] == "1.0.0"
        assert state["commit"] is None


class TestUpgrade:
    def test_a_branch_install_moves_to_the_new_commit(self, home, github, heads):
        install(product(github), ref="main", home=home)
        heads["main"] = SHA2
        result = upgrade(product(github), home=home)
        assert (result.outcome, result.version) == ("installed", SHA2[:12])
        assert result.previous == SHA[:12]
        state = json.loads(home.state_path.read_text())
        assert (state["ref"], state["commit"]) == ("main", SHA2)

    def test_an_unmoved_branch_is_already_current(self, home, github):
        install(product(github), ref="main", home=home)
        assert upgrade(product(github), home=home).outcome == "already-current"
        assert home.installed_versions() == [SHA[:12]]

    def test_a_release_install_still_moves_to_the_newest_release(self, home, source):
        install(product(source), home=home)
        home.state_path.write_text(
            json.dumps({"version": "1.0.0", "schema_version": 1})
        )
        source.newest = "2.0.0"
        assert upgrade(product(source), home=home).version == "2.0.0"


class TestStatusAndDoctor:
    def test_status_of_a_ref_install_carries_ref_and_commit(self, home, github):
        install(product(github), ref="main", home=home)
        result = status(product(github), home=home)
        assert (result.ref, result.commit) == ("main", SHA)
        assert result.package_version == "1.1.0.dev0"
        assert result.installed == SHA[:12]

    def test_status_of_a_release_install_has_no_commit(self, home, source):
        install(product(source), home=home)
        result = status(product(source), home=home)
        assert (result.ref, result.commit) == ("1.0.0", None)

    def test_status_of_a_pre_ref_state_reads_as_a_release(self, home, source):
        install(product(source), home=home)
        home.state_path.write_text(
            json.dumps({"version": "1.0.0", "schema_version": 1})
        )
        result = status(product(source), home=home)
        assert (result.ref, result.commit) == ("1.0.0", None)

    def test_a_ref_install_with_a_matching_package_version_has_no_mismatch(
        self, home, github
    ):
        install(product(github), ref="main", home=home)
        codes = [
            f.code for f in doctor(product(github, version="1.1.0.dev0"), home=home)
        ]
        assert codes == ["install.ok", "tool.ok"]

    def test_the_mismatch_names_the_recorded_version(self, home, github):
        install(product(github), ref="main", home=home)
        findings = doctor(product(github, version="0.9.0"), home=home)
        (found,) = [f for f in findings if f.code == "install.version-mismatch"]
        assert found.details == {"running": "0.9.0", "installed": "1.1.0.dev0"}

    def test_doctor_falls_back_to_the_directory_without_a_recorded_version(
        self, home, source
    ):
        install(product(source), home=home)
        home.state_path.write_text(json.dumps({"schema_version": 1}))
        codes = [f.code for f in doctor(product(source), home=home)]
        assert "install.version-mismatch" not in codes
        assert "install.state-unreadable" not in codes

    def test_state_without_ref_still_reports(self, home, source):
        install(product(source), home=home)
        home.state_path.write_text(
            json.dumps({"version": "1.0.0", "schema_version": 1})
        )
        assert status(product(source), home=home).installed == "1.0.0"
        codes = [f.code for f in doctor(product(source), home=home)]
        assert "install.state-unreadable" not in codes

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


def test_a_default_product_has_nothing_to_preflight():
    assert ToolProduct(name="bare", version="1").preflight() is None


def test_a_link_cannot_escape_the_home():
    with pytest.raises(AppException):
        Link("../outside", "bin/tool")
