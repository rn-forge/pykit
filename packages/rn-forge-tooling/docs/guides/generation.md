# Generation

`rn_forge.tooling.generation` is the engine behind "write a repository's
standard files, and refuse to silently clobber a hand edit". It decides what a
write *would* do before doing anything, and makes a batch of writes
all-or-nothing.

## Artifacts

Every artifact declares who owns its bytes:

| Kind | Owner | Hand edits are |
| --- | --- | --- |
| `MANAGED` | the generator owns the whole file | drift |
| `SEEDED` | written once if absent, then the repository's | expected — never inspected |
| `BLOCK` | the generator owns one fenced block inside a repo-owned file | drift, inside the block only |

```python
from rn_forge.commons.fs.blocks import ManagedBlock
from rn_forge.tooling.generation import Artifact, ArtifactKind

taskfile = Artifact(path="Taskfile.yml", kind=ArtifactKind.MANAGED, content=rendered)
ignore = Artifact(
    path=".gitignore",
    kind=ArtifactKind.BLOCK,
    content=".out/\n",
    block=ManagedBlock("golden-tool"),
)
```

A block artifact's `content` is the block *body*, not the whole file: everything
outside the markers is preserved byte for byte.

## Classify, then plan, then apply

```python
from rn_forge.tooling.generation import StateEntry, apply, plan
from rn_forge.tooling.state import StateStore

store = StateStore(
    root / ".golden-tool/state.json",
    entry_type=StateEntry,
    metadata={"tool_version": version, "config_hash": config_hash},
)
entries = store.load()
planned = plan(root, artifacts, entries, force=approved_paths)
```

`plan` classifies every artifact against three things — what was rendered, what
is on disk, and what was recorded the last time it was applied:

| Situation | Action |
| --- | --- |
| absent, never applied | `CREATE` / `INSERT` |
| disk, last-applied and render agree | `UNCHANGED` |
| disk matches last-applied, render moved on | `UPDATE` |
| disk was edited since the last apply | `DRIFT` |
| something exists at a managed path nobody recorded | `CONFLICT` |
| recorded as applied, gone from disk | `MISSING` |
| a seeded file that already exists | `SKIP` |
| recorded but no longer rendered | `DELETE` / `REMOVE` / `FORGET` |

`DRIFT`, `CONFLICT` and `MISSING` are **blocking**: they abort the whole plan
before anything is written unless the caller passed that exact path in `force`.
There is no "force everything" value — approving a path approves that path.

```python
result = apply(
    root,
    planned,
    store,
    staging_dir=root / ".golden-tool/rendered",
    backup_dir=root / ".golden-tool/backups",
    entries=entries,
    verify=run_post_apply_checks,
    dry_run=options.dry_run,
)
```

Everything is rendered into `staging_dir` and every file about to be overwritten
or deleted is copied under a timestamped directory in `backup_dir` before the
first replacement happens. If a write or `verify` raises, the working tree and
the state file are restored and the exception surfaces as an `AppException`.

The state file is written last and never records itself — a baseline that hashed
its own bytes could never be consistent.

## Generators

A generator is plain Python. It must not import a CLI framework and must not
write to the working tree:

```python
class TaskfileGenerator:
    name = "tasks"

    def generate(self, context):
        return [Artifact(path="Taskfile.yml", kind=ArtifactKind.MANAGED, content=...)]
```

That keeps command-line parsing out of the API: the CLI that mounts a generator
supplies its command surface, and the generator stays callable from a test, a
script, or another tool.
