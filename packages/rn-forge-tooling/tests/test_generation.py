"""Tests for rn_forge.tooling.generation."""

from __future__ import annotations

import pytest

from rn_forge.commons.blocks import ManagedBlock
from rn_forge.commons.exceptions import AppException
from rn_forge.tooling.generation import (
    Action,
    Artifact,
    ArtifactKind,
    StateEntry,
    apply,
    classify,
    plan,
)
from rn_forge.tooling.state import StateStore

KILN_BLOCK = ManagedBlock("rn-forge kiln")


def managed(path="Taskfile.yml", content="version: '3'\n"):
    return Artifact(path=path, kind=ArtifactKind.MANAGED, content=content)


def seeded(path="docs/index.md", content="# Docs\n"):
    return Artifact(path=path, kind=ArtifactKind.SEEDED, content=content)


def block(path=".gitignore", content=".out/\n"):
    return Artifact(
        path=path, kind=ArtifactKind.BLOCK, content=content, block=KILN_BLOCK
    )


def store(tmp_path):
    return StateStore(
        tmp_path / ".rn-forge/state.json",
        entry_type=StateEntry,
        metadata={"kiln_version": "0.1.0"},
    )


def run(tmp_path, artifacts, *, force=(), verify=None, dry_run=False):
    state = store(tmp_path)
    entries = state.load()
    planned = plan(tmp_path, artifacts, entries, force=force)
    result = apply(
        tmp_path,
        planned,
        state,
        staging_dir=tmp_path / ".rn-forge/rendered",
        backup_dir=tmp_path / ".rn-forge/backups",
        entries=entries,
        verify=verify,
        dry_run=dry_run,
    )
    return result, state


def actions(result):
    return {change.path: change.action for change in result.changes}


class TestArtifact:
    def test_block_artifact_requires_a_block(self):
        with pytest.raises(ValueError):
            Artifact(path="a", kind=ArtifactKind.BLOCK, content="x")

    def test_non_block_artifact_rejects_a_block(self):
        with pytest.raises(ValueError):
            Artifact(path="a", kind=ArtifactKind.MANAGED, content="x", block=KILN_BLOCK)

    def test_block_key_includes_the_block_name(self):
        assert block().key == ".gitignore#rn-forge kiln"
        assert managed().key == "Taskfile.yml"

    def test_seeded_entry_records_no_hash(self):
        assert seeded().to_entry().content_hash is None

    def test_block_entry_records_exact_markers(self):
        entry = block().to_entry()
        assert entry.begin_marker == "# BEGIN rn-forge kiln"
        assert entry.end_marker == "# END rn-forge kiln"


class TestClassify:
    def test_managed_absent_without_entry_is_create(self, tmp_path):
        assert classify(tmp_path, managed(), None) is Action.CREATE

    def test_managed_absent_with_entry_is_missing(self, tmp_path):
        assert classify(tmp_path, managed(), managed().to_entry()) is Action.MISSING

    def test_managed_present_without_entry_is_conflict(self, tmp_path):
        (tmp_path / "Taskfile.yml").write_text("hand made\n")
        assert classify(tmp_path, managed(), None) is Action.CONFLICT

    def test_unchanged(self, tmp_path):
        artifact = managed()
        (tmp_path / "Taskfile.yml").write_text(artifact.content)
        assert classify(tmp_path, artifact, artifact.to_entry()) is Action.UNCHANGED

    def test_update_when_render_moved_on(self, tmp_path):
        old = managed(content="old\n")
        (tmp_path / "Taskfile.yml").write_text(old.content)
        assert classify(tmp_path, managed(content="new\n"), old.to_entry()) is (
            Action.UPDATE
        )

    def test_drift_when_disk_was_edited(self, tmp_path):
        artifact = managed()
        (tmp_path / "Taskfile.yml").write_text("edited\n")
        assert classify(tmp_path, artifact, artifact.to_entry()) is Action.DRIFT

    def test_seeded_present_is_skip_whatever_the_content(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs/index.md").write_text("rewritten by the repo\n")
        assert classify(tmp_path, seeded(), None) is Action.SKIP

    def test_block_absent_is_insert(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        assert classify(tmp_path, block(), None) is Action.INSERT

    def test_block_present_without_entry_is_conflict(self, tmp_path):
        artifact = block()
        (tmp_path / ".gitignore").write_text(KILN_BLOCK.render("", artifact.content))
        assert classify(tmp_path, artifact, None) is Action.CONFLICT

    def test_block_body_edited_is_drift(self, tmp_path):
        artifact = block()
        (tmp_path / ".gitignore").write_text(KILN_BLOCK.render("", "edited\n"))
        assert classify(tmp_path, artifact, artifact.to_entry()) is Action.DRIFT


class TestPlan:
    def test_duplicate_keys_are_rejected(self, tmp_path):
        with pytest.raises(AppException):
            plan(tmp_path, [managed(), managed()], {})

    def test_blocking_change_stops_the_plan(self, tmp_path):
        (tmp_path / "Taskfile.yml").write_text("hand made\n")
        planned = plan(tmp_path, [managed()], {})
        assert [c.action for c in planned.blocking] == [Action.CONFLICT]
        with pytest.raises(AppException):
            planned.check()

    def test_forcing_a_path_approves_only_that_path(self, tmp_path):
        (tmp_path / "Taskfile.yml").write_text("hand made\n")
        (tmp_path / "other.yml").write_text("hand made\n")
        artifacts = [managed(), managed(path="other.yml")]
        planned = plan(tmp_path, artifacts, {}, force=["Taskfile.yml"])
        assert [c.path for c in planned.blocking] == ["other.yml"]


class TestApply:
    def test_creates_and_records(self, tmp_path):
        result, state = run(tmp_path, [managed(), seeded(), block()])
        assert actions(result) == {
            "Taskfile.yml": Action.CREATE,
            "docs/index.md": Action.CREATE,
            ".gitignore": Action.INSERT,
        }
        assert (tmp_path / "Taskfile.yml").read_text() == "version: '3'\n"
        assert KILN_BLOCK.extract((tmp_path / ".gitignore").read_text()) == ".out/\n"
        assert set(state.load()) == {
            "Taskfile.yml",
            "docs/index.md",
            ".gitignore#rn-forge kiln",
        }
        assert state.metadata == {"kiln_version": "0.1.0"}

    def test_second_apply_is_all_unchanged(self, tmp_path):
        artifacts = [managed(), seeded(), block()]
        run(tmp_path, artifacts)
        result, _ = run(tmp_path, artifacts)
        assert set(actions(result).values()) == {Action.UNCHANGED, Action.SKIP}

    def test_block_insert_preserves_the_file_body(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block()])
        text = (tmp_path / ".gitignore").read_text()
        assert text.startswith("repo line\n")
        assert KILN_BLOCK.extract(text) == ".out/\n"

    def test_update_rewrites_the_file(self, tmp_path):
        run(tmp_path, [managed(content="v1\n")])
        result, _ = run(tmp_path, [managed(content="v2\n")])
        assert actions(result) == {"Taskfile.yml": Action.UPDATE}
        assert (tmp_path / "Taskfile.yml").read_text() == "v2\n"

    def test_dry_run_writes_nothing(self, tmp_path):
        result, state = run(tmp_path, [managed()], dry_run=True)
        assert result.dry_run
        assert not (tmp_path / "Taskfile.yml").exists()
        assert state.load() == {}

    def test_unapproved_drift_aborts_before_writing(self, tmp_path):
        run(tmp_path, [managed(content="v1\n"), seeded()])
        (tmp_path / "Taskfile.yml").write_text("edited\n")
        with pytest.raises(AppException):
            run(tmp_path, [managed(content="v2\n"), seeded(content="other\n")])
        assert (tmp_path / "Taskfile.yml").read_text() == "edited\n"

    def test_forced_drift_is_overwritten(self, tmp_path):
        run(tmp_path, [managed(content="v1\n")])
        (tmp_path / "Taskfile.yml").write_text("edited\n")
        run(tmp_path, [managed(content="v2\n")], force=["Taskfile.yml"])
        assert (tmp_path / "Taskfile.yml").read_text() == "v2\n"

    def test_stale_managed_artifact_is_deleted_and_backed_up(self, tmp_path):
        run(tmp_path, [managed(), managed(path="tasks/old.yml", content="old\n")])
        result, state = run(tmp_path, [managed()])
        assert actions(result)["tasks/old.yml"] is Action.DELETE
        assert not (tmp_path / "tasks/old.yml").exists()
        assert "tasks/old.yml" not in state.load()
        assert result.backup_dir is not None
        assert (result.backup_dir / "tasks/old.yml").read_text() == "old\n"

    def test_stale_block_is_removed_and_the_body_kept(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block()])
        result, state = run(tmp_path, [])
        assert actions(result)[".gitignore"] is Action.REMOVE
        assert (tmp_path / ".gitignore").read_text() == "repo line\n"
        assert state.load() == {}

    def test_stale_seeded_artifact_is_forgotten_not_deleted(self, tmp_path):
        run(tmp_path, [seeded()])
        result, state = run(tmp_path, [])
        assert actions(result)["docs/index.md"] is Action.FORGET
        assert (tmp_path / "docs/index.md").exists()
        assert state.load() == {}

    def test_edited_stale_artifact_is_drift_not_deletion(self, tmp_path):
        run(tmp_path, [managed()])
        (tmp_path / "Taskfile.yml").write_text("edited\n")
        with pytest.raises(AppException):
            run(tmp_path, [])
        assert (tmp_path / "Taskfile.yml").read_text() == "edited\n"

    def test_failed_verify_rolls_back_creations_and_updates(self, tmp_path):
        run(tmp_path, [managed(content="v1\n")])

        def boom():
            raise RuntimeError("post-apply check failed")

        with pytest.raises(AppException):
            run(
                tmp_path,
                [managed(content="v2\n"), managed(path="new.yml", content="new\n")],
                verify=boom,
            )
        assert (tmp_path / "Taskfile.yml").read_text() == "v1\n"
        assert not (tmp_path / "new.yml").exists()
        assert store(tmp_path).load()["Taskfile.yml"].content_hash is not None
