# Recovering from drift

`task lint` reports:

```text
Taskfile.yml: managed artifact has drifted from the committed state
```

Someone edited a file kiln owns. There are exactly two right answers, and
choosing between them is the judgement this runbook exists for.

## 1. Find out what changed

```bash
git diff -- Taskfile.yml
task kiln:diff -- --artifact Taskfile.yml
```

`git diff` shows the edit. `task kiln:diff` shows the edit *against a fresh
render*, which also tells you whether kiln itself would now produce something
different.

## 2. Decide

- **The edit was a mistake, or a local hack.** Revert it: `task kiln:apply`
  restores the rendered bytes. Done.
- **The edit is right and the standard is wrong.** Then the change belongs in
  kiln, not here: change the template in `rn-forge/kiln`, release kiln, bump
  this repo's `[kiln] ref` in `.rn-forge/kiln/config.toml`, then run
  `task kiln:apply` here.

Never leave the third option — the edit in place, the state stale — in a branch
you intend to merge. CI is checking the committed baseline, not your intent.

## 3. If the drift is config, not content

A `config.toml` edit shows up as drift in every file the option touches. Run
`task kiln:apply` and review the whole diff at once.
