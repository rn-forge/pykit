"""Tests for rn_forge.commons.generation."""

from __future__ import annotations

import json

import pytest
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.fs.blocks import ManagedBlock
from rn_forge.commons.fs.documents import DocumentUtils
from rn_forge.commons.fs.state import StateStore
from rn_forge.commons.generation import (
    Action,
    Artifact,
    ArtifactKind,
    Change,
    StateEntry,
    apply,
    classify,
    diff,
    plan,
)

KILN_BLOCK = ManagedBlock("rn-forge kiln")


def managed(path="Taskfile.yml", content="version: '3'\n"):
    return Artifact(path=path, kind=ArtifactKind.MANAGED, content=content)


def seeded(path="docs/index.md", content="# Docs\n"):
    return Artifact(path=path, kind=ArtifactKind.SEEDED, content=content)


def block(path=".gitignore", content=".out/\n"):
    return Artifact(
        path=path, kind=ArtifactKind.BLOCK, content=content, block=KILN_BLOCK
    )


def keys(path="settings.json", values=None):
    return Artifact(
        path=path,
        kind=ArtifactKind.KEYS,
        content="",
        keys={"editor.theme": "dark"} if values is None else values,
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
        artifacts = [managed(), managed()]
        with pytest.raises(AppException):
            plan(tmp_path, artifacts, {})

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


class TestDiff:
    @staticmethod
    def only_change(tmp_path, artifact):
        return plan(tmp_path, [artifact], {}).changes[0]

    def test_managed_change_diffs_disk_to_render(self, tmp_path):
        (tmp_path / "Taskfile.yml").write_text("version: '2'\n")
        change = self.only_change(tmp_path, managed())
        text = diff(tmp_path, change)
        assert "--- Taskfile.yml" in text
        assert "+++ Taskfile.yml" in text
        assert "-version: '2'" in text
        assert "+version: '3'" in text

    def test_identical_content_is_empty(self, tmp_path):
        (tmp_path / "Taskfile.yml").write_text("version: '3'\n")
        change = self.only_change(tmp_path, managed())
        assert diff(tmp_path, change) == ""

    def test_absent_file_diffs_from_empty(self, tmp_path):
        text = diff(tmp_path, self.only_change(tmp_path, managed()))
        body = [
            line
            for line in text.splitlines()
            if not line.startswith(("+++", "---", "@@"))
        ]
        assert body
        assert all(line.startswith("+") for line in body)

    def test_block_diffs_only_the_body(self, tmp_path):
        old = KILN_BLOCK.render("outside text\n", "old body\n")
        (tmp_path / ".gitignore").write_text(old)
        text = diff(tmp_path, self.only_change(tmp_path, block(content="new body\n")))
        assert "-old body" in text
        assert "+new body" in text
        assert "outside text" not in text

    def test_change_without_artifact_is_empty(self, tmp_path):
        stale = Change(
            key="k", path="a", kind=ArtifactKind.MANAGED, action=Action.DELETE
        )
        assert diff(tmp_path, stale) == ""


class TestApply:
    def test_written_lists_only_paths_whose_bytes_changed(self, tmp_path):
        run(tmp_path, [managed(path="a.yml"), managed(path="b.yml"), seeded()])

        result, _ = run(
            tmp_path,
            [managed(path="a.yml", content="v2\n"), managed(path="b.yml"), seeded()],
        )

        assert result.written == ("a.yml",)

    def test_written_covers_create_delete_remove_and_excludes_forget(self, tmp_path):
        run(
            tmp_path,
            [
                managed(path="old.yml"),
                block(),
                seeded(),
            ],
        )

        result, _ = run(tmp_path, [managed(path="new.yml")])

        assert result.written == ("new.yml", ".gitignore", "old.yml")

    def test_dry_run_reports_nothing_written(self, tmp_path):
        artifacts = [managed(), seeded(), block()]

        result, _ = run(tmp_path, artifacts, dry_run=True)

        assert result.written == ()
        assert len(result.changes) == len(artifacts)

    def test_forced_drift_is_reported_written(self, tmp_path):
        artifacts = [managed(path="drift.yml"), managed(path="unchanged.yml")]
        run(tmp_path, artifacts)
        (tmp_path / "drift.yml").write_text("edited\n")

        result, _ = run(tmp_path, artifacts, force=["drift.yml"])

        assert result.written == ("drift.yml",)

    def test_reporting_adds_no_writes(self, tmp_path):
        artifacts = [managed(), block()]
        run(tmp_path, artifacts)

        def snapshot():
            state_paths = {
                tmp_path / ".rn-forge/state.json",
                tmp_path / ".rn-forge/state.lock",
                *tmp_path.glob(".rn-forge/backups/*/.rn-forge/state.json"),
            }
            return {
                path.relative_to(tmp_path): (
                    path.read_bytes(),
                    path.stat().st_mtime_ns,
                )
                for path in tmp_path.rglob("*")
                if path.is_file() and path not in state_paths
            }

        before = snapshot()
        run(tmp_path, artifacts)
        after = snapshot()

        assert after == before

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

    def test_unterminated_block_content_is_unchanged_on_second_apply(self, tmp_path):
        artifacts = [block(content="value")]
        run(tmp_path, artifacts)
        result, _ = run(tmp_path, artifacts)
        assert actions(result) == {".gitignore": Action.UNCHANGED}

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
        artifacts = [managed(content="v2\n"), seeded(content="other\n")]
        with pytest.raises(AppException):
            run(tmp_path, artifacts)
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

        artifacts = [managed(content="v2\n"), managed(path="new.yml", content="new\n")]
        with pytest.raises(AppException):
            run(tmp_path, artifacts, verify=boom)
        assert (tmp_path / "Taskfile.yml").read_text() == "v1\n"
        assert not (tmp_path / "new.yml").exists()
        assert store(tmp_path).load()["Taskfile.yml"].content_hash is not None


OTHER_BLOCK = ManagedBlock("rn-forge docs")


def other_block(path=".gitignore", content="docs/.cache/\n"):
    return Artifact(
        path=path, kind=ArtifactKind.BLOCK, content=content, block=OTHER_BLOCK
    )


class TestSeveralBlocksInOneFile:
    """Two generators owning two blocks of one file must both survive a run."""

    def test_two_inserts_in_one_file(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block(), other_block()])
        text = (tmp_path / ".gitignore").read_text()
        assert KILN_BLOCK.extract(text) == ".out/\n"
        assert OTHER_BLOCK.extract(text) == "docs/.cache/\n"
        assert text.startswith("repo line\n")

    def test_two_updates_in_one_file(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block(), other_block()])
        result, _ = run(
            tmp_path,
            [block(content=".build/\n"), other_block(content="site/\n")],
        )
        assert [c.action for c in result.changes] == [Action.UPDATE, Action.UPDATE]
        text = (tmp_path / ".gitignore").read_text()
        assert KILN_BLOCK.extract(text) == ".build/\n"
        assert OTHER_BLOCK.extract(text) == "site/\n"

    def test_written_lists_a_file_once_for_several_blocks(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block(), other_block()])

        result, _ = run(
            tmp_path,
            [block(content=".build/\n"), other_block(content="site/\n")],
        )

        assert result.written == (".gitignore",)

    def test_removing_one_block_while_updating_the_other(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block(), other_block()])
        result, state = run(tmp_path, [block(content=".build/\n")])
        assert {c.action for c in result.changes} == {Action.UPDATE, Action.REMOVE}
        text = (tmp_path / ".gitignore").read_text()
        assert KILN_BLOCK.extract(text) == ".build/\n"
        assert OTHER_BLOCK.extract(text) is None
        assert text.startswith("repo line\n")
        assert set(state.load()) == {".gitignore#rn-forge kiln"}

    def test_rolls_back_to_the_original_file_not_a_half_written_one(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block(), other_block()])
        before = (tmp_path / ".gitignore").read_text()

        def boom():
            raise RuntimeError("nope")

        artifacts = [block(content=".build/\n"), other_block(content="site/\n")]
        with pytest.raises(AppException):
            run(tmp_path, artifacts, verify=boom)
        assert (tmp_path / ".gitignore").read_text() == before

    def test_whole_file_and_block_ownership_of_one_path_is_rejected(self, tmp_path):
        artifacts = [managed(path="notes.md"), block(path="notes.md")]
        with pytest.raises(AppException):
            run(tmp_path, artifacts)


class TestKeys:
    @pytest.mark.parametrize("name", ["settings.json", "config.toml"])
    def test_s27_1_1_1_create_from_absent_file(self, tmp_path, name):
        values = {"editor.theme": "dark", "a.b.c": [1, 2]}
        result, _ = run(tmp_path, [keys(name, values)])
        assert actions(result) == {name: Action.CREATE}
        assert DocumentUtils.read(tmp_path / name) == {
            "editor": {"theme": "dark"},
            "a": {"b": {"c": [1, 2]}},
        }
        again, _ = run(tmp_path, [keys(name, values)])
        assert actions(again) == {name: Action.UNCHANGED}

    def test_s27_1_1_2_insert_keeps_unowned_json_keys(self, tmp_path):
        (tmp_path / "settings.json").write_text('{"editor": {"font": 12}, "x": 1}')
        result, _ = run(tmp_path, [keys()])
        assert actions(result) == {"settings.json": Action.INSERT}
        assert DocumentUtils.read(tmp_path / "settings.json") == {
            "editor": {"font": 12, "theme": "dark"},
            "x": 1,
        }

    def test_s27_1_1_2_insert_keeps_toml_comments_byte_for_byte(self, tmp_path):
        original = '# top comment\n[tool]\nname = "x"  # note\n'
        (tmp_path / "config.toml").write_text(original)
        result, _ = run(tmp_path, [keys("config.toml")])
        assert actions(result) == {"config.toml": Action.INSERT}
        text = (tmp_path / "config.toml").read_text()
        assert text.startswith(original)
        assert DocumentUtils.read(tmp_path / "config.toml")["editor"] == {
            "theme": "dark"
        }

    def test_s27_1_1_3_unowned_key_added_by_hand_is_unchanged(self, tmp_path):
        run(tmp_path, [keys()])
        path = tmp_path / "settings.json"
        data = json.loads(path.read_text())
        data["mine"] = True
        path.write_text(json.dumps(data))
        result, _ = run(tmp_path, [keys()])
        assert actions(result) == {"settings.json": Action.UNCHANGED}

    def test_s27_1_1_4_owned_value_changed_by_hand_is_drift(self, tmp_path):
        run(tmp_path, [keys()])
        path = tmp_path / "settings.json"
        path.write_text('{"editor": {"theme": "light"}}')
        with pytest.raises(AppException):
            run(tmp_path, [keys()])
        assert json.loads(path.read_text())["editor"]["theme"] == "light"
        result, _ = run(tmp_path, [keys()], force=["settings.json"])
        assert actions(result) == {"settings.json": Action.DRIFT}
        assert json.loads(path.read_text())["editor"]["theme"] == "dark"
        assert list((tmp_path / ".rn-forge/backups").glob("*/settings.json"))

    def test_s27_1_1_5_list_appended_by_hand_is_drift(self, tmp_path):
        artifact = keys(values={"a.list": [1, 2]})
        run(tmp_path, [artifact])
        path = tmp_path / "settings.json"
        path.write_text('{"a": {"list": [1, 2, 3]}}')
        planned = plan(tmp_path, [artifact], store(tmp_path).load())
        assert [c.action for c in planned.changes] == [Action.DRIFT]

    def test_s27_1_1_6_dropped_path_is_removed_and_pruned(self, tmp_path):
        run(tmp_path, [keys(values={"editor.theme": "dark", "a.b": 1})])
        result, state = run(tmp_path, [keys()])
        assert actions(result) == {"settings.json": Action.UPDATE}
        assert DocumentUtils.read(tmp_path / "settings.json") == {
            "editor": {"theme": "dark"}
        }
        assert state.load()["settings.json"].key_paths == ("editor.theme",)

    def test_s27_1_1_7_no_keys_artifact_plans_remove(self, tmp_path):
        (tmp_path / "settings.json").write_text('{"x": 1}')
        run(tmp_path, [keys()])
        result, state = run(tmp_path, [])
        assert actions(result) == {"settings.json": Action.REMOVE}
        assert DocumentUtils.read(tmp_path / "settings.json") == {"x": 1}
        assert state.load() == {}

    def test_s27_1_1_7_removing_every_key_keeps_the_file(self, tmp_path):
        run(tmp_path, [keys()])
        run(tmp_path, [])
        assert DocumentUtils.read(tmp_path / "settings.json") == {}

    def test_s27_1_1_8_deleted_file_is_missing(self, tmp_path):
        run(tmp_path, [keys()])
        (tmp_path / "settings.json").unlink()
        planned = plan(tmp_path, [keys()], store(tmp_path).load())
        assert [c.action for c in planned.changes] == [Action.MISSING]

    def test_s27_1_1_9_validation(self):
        with pytest.raises(ValueError, match="settings.json"):
            Artifact(path="settings.json", kind=ArtifactKind.KEYS, content="")
        with pytest.raises(ValueError, match="settings.json"):
            Artifact(path="settings.json", kind=ArtifactKind.KEYS, content="", keys={})
        with pytest.raises(ValueError, match="settings.json"):
            Artifact(
                path="settings.json",
                kind=ArtifactKind.KEYS,
                content="x",
                keys={"a": 1},
            )
        with pytest.raises(ValueError, match="settings.json"):
            Artifact(
                path="settings.json",
                kind=ArtifactKind.MANAGED,
                content="x",
                keys={"a": 1},
            )
        with pytest.raises(ValueError, match="settings.yaml"):
            keys("settings.yaml")

    def test_s27_1_1_10_keys_and_block_on_one_path_is_rejected(self, tmp_path):
        with pytest.raises(AppException, match="settings.json"):
            run(tmp_path, [keys(), block(path="settings.json")])

    def test_s27_1_1_10_keys_and_managed_on_one_path_is_rejected(self, tmp_path):
        with pytest.raises(AppException, match="Duplicate"):
            run(tmp_path, [keys(), managed(path="settings.json")])

    def test_s27_1_1_11_managed_entry_at_a_keys_path_conflicts(self, tmp_path):
        run(tmp_path, [managed(path="settings.json", content='{"other": 1}\n')])
        with pytest.raises(AppException):
            run(tmp_path, [keys()])
        result, _ = run(tmp_path, [keys()], force=["settings.json"])
        assert actions(result) == {"settings.json": Action.CONFLICT}
        assert DocumentUtils.read(tmp_path / "settings.json") == {
            "other": 1,
            "editor": {"theme": "dark"},
        }

    def test_s27_1_1_12_path_through_a_non_table_rolls_back(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text('{"editor": 5}')
        with pytest.raises(AppException, match="editor.theme"):
            run(tmp_path, [keys()])
        assert path.read_text() == '{"editor": 5}'
        assert store(tmp_path).load() == {}

    def test_s27_1_1_14_diff_shows_changes_with_entries(self, tmp_path):
        old = keys(values={"editor.theme": "dark", "a.b": 1, "z": 0})
        run(tmp_path, [old])
        new = keys(values={"editor.theme": "light", "z": 0})
        entries = store(tmp_path).load()
        change = plan(tmp_path, [new], entries).changes[0]
        assert change.action is Action.UPDATE
        text = diff(tmp_path, change, entries=entries)
        assert '-    "theme": "dark"' in text
        assert '+    "theme": "light"' in text
        assert '-  "a": {' in text
        assert '   "z": 0' in text


class TestBytePreservingWrites:
    def test_crlf_file_is_not_reformatted(self, tmp_path):
        (tmp_path / ".gitignore").write_bytes(b"repo line\r\nsecond\r\n")
        run(tmp_path, [block()])
        raw = (tmp_path / ".gitignore").read_bytes()
        assert raw.startswith(b"repo line\r\nsecond\r\n")
        assert b"repo line\n" not in raw

    def test_file_without_a_terminal_newline_keeps_its_body(self, tmp_path):
        (tmp_path / ".gitignore").write_bytes(b"repo line")
        run(tmp_path, [block()])
        assert (tmp_path / ".gitignore").read_bytes().startswith(b"repo line\n\n")

    def test_a_second_run_over_a_crlf_file_is_unchanged(self, tmp_path):
        (tmp_path / ".gitignore").write_bytes(b"repo line\r\n")
        run(tmp_path, [block()])
        result, _ = run(tmp_path, [block()])
        assert actions(result) == {".gitignore": Action.UNCHANGED}


class TestPathContainment:
    @pytest.mark.parametrize(
        "path", ["/etc/passwd", "../escaped.yml", "nested/../../escaped.yml"]
    )
    def test_absolute_and_traversing_paths_are_rejected(self, tmp_path, path):
        root = tmp_path / "repo"
        root.mkdir()
        artifacts = [managed(path=path)]
        with pytest.raises(AppException):
            run(root, artifacts)
        assert not (tmp_path / "escaped.yml").exists()

    def test_a_symlink_out_of_the_repo_is_rejected(self, tmp_path):
        root = tmp_path / "repo"
        (root / "link").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / "link").rmdir()
        (root / "link").symlink_to(outside, target_is_directory=True)
        artifacts = [managed(path="link/escaped.yml")]
        with pytest.raises(AppException):
            run(root, artifacts)
        assert not (outside / "escaped.yml").exists()

    def test_a_stale_entry_pointing_outside_the_repo_is_rejected(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        state = store(root)
        state.replace_all(
            {
                "../escaped.yml": StateEntry(
                    path="../escaped.yml", kind=ArtifactKind.MANAGED, content_hash="x"
                )
            }
        )
        entries = state.load()
        with pytest.raises(AppException):
            plan(root, [], entries)


class TestInterruption:
    def test_keyboard_interrupt_rolls_back_and_propagates(self, tmp_path):
        run(tmp_path, [managed(content="v1\n")])

        def interrupt():
            raise KeyboardInterrupt

        artifacts = [managed(content="v2\n"), managed(path="new.yml", content="new\n")]
        with pytest.raises(KeyboardInterrupt):
            run(tmp_path, artifacts, verify=interrupt)
        assert (tmp_path / "Taskfile.yml").read_text() == "v1\n"
        assert not (tmp_path / "new.yml").exists()
        assert store(tmp_path).load()["Taskfile.yml"].content_hash is not None


class TestForcedStaleDrift:
    def test_forcing_an_edited_stale_file_deletes_it(self, tmp_path):
        run(tmp_path, [managed(), managed(path="tasks/old.yml", content="old\n")])
        (tmp_path / "tasks/old.yml").write_text("edited\n")
        result, state = run(tmp_path, [managed()], force=["tasks/old.yml"])
        assert actions(result)["tasks/old.yml"] is Action.DRIFT
        assert not (tmp_path / "tasks/old.yml").exists()
        assert "tasks/old.yml" not in state.load()
        assert result.backup_dir is not None
        assert (result.backup_dir / "tasks/old.yml").read_text() == "edited\n"

    def test_forcing_an_edited_stale_block_removes_only_that_block(self, tmp_path):
        (tmp_path / ".gitignore").write_text("repo line\n")
        run(tmp_path, [block(), other_block()])
        text = (tmp_path / ".gitignore").read_text()
        (tmp_path / ".gitignore").write_text(OTHER_BLOCK.render(text, "hand edit\n"))
        result, state = run(tmp_path, [block()], force=[".gitignore#rn-forge docs"])
        assert {c.action for c in result.changes} == {Action.UNCHANGED, Action.DRIFT}
        final = (tmp_path / ".gitignore").read_text()
        assert OTHER_BLOCK.extract(final) is None
        assert KILN_BLOCK.extract(final) == ".out/\n"
        assert final.startswith("repo line\n")
        assert set(state.load()) == {".gitignore#rn-forge kiln"}


class TestStateEntryParsing:
    """The state file is hand-editable, so an entry is validated on load."""

    def test_round_trips_through_dict(self):
        entry = StateEntry(
            path="tasks/x.yml", kind=ArtifactKind.MANAGED, content_hash="abc"
        )
        assert StateEntry.from_dict(entry.as_dict()) == entry

    def test_kind_is_rebuilt_as_the_enum_member(self):
        entry = StateEntry.from_dict({"path": "p", "kind": "managed"})
        assert entry.kind is ArtifactKind.MANAGED

    def test_a_mistyped_field_is_rejected(self):
        with pytest.raises(AppException, match="Invalid StateEntry"):
            StateEntry.from_dict({"path": "p", "kind": "managed", "content_hash": 7})

    def test_an_unknown_kind_is_rejected(self):
        with pytest.raises(AppException, match="Invalid StateEntry"):
            StateEntry.from_dict({"path": "p", "kind": "sideways"})

    def test_a_missing_required_field_is_rejected(self):
        with pytest.raises(AppException, match="Invalid StateEntry"):
            StateEntry.from_dict({"path": "p"})

    def test_s27_1_1_13_state_without_key_paths_loads_and_plans_as_before(
        self, tmp_path
    ):
        artifact = managed()
        (tmp_path / "Taskfile.yml").write_text(artifact.content)
        entry = StateEntry.from_dict(
            {
                "path": "Taskfile.yml",
                "kind": "managed",
                "content_hash": artifact.content_hash,
            }
        )
        assert classify(tmp_path, artifact, entry) is Action.UNCHANGED

    def test_key_paths_round_trip_through_json(self):
        entry = keys().to_entry()
        loaded = StateEntry.from_dict(json.loads(json.dumps(entry.as_dict())))
        assert loaded == entry
        assert loaded.key_paths == ("editor.theme",)
