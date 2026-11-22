# Description: Compact todo_md execution rule for role=work
- Task management (`todo_md`: `TODO.md`, `TODO_ARCHIVE.md`, `role=work`):
  - Always inspect and modify `TODO.md` and `TODO_ARCHIVE.md` via `todo_md`
    (never via `cat` or manual file edits). Repository scope only: record each
    task in the `TODO.md` of the repository it belongs to.
  - Start the task in the first `run_block` step: `todo_md status <ID> WIP`
    (without `-c` / `--commit`) unless it is already `WIP`; `todo_md <ID>`
    never changes status.
  - Close the active task via `todo_md done <ID>` inside the final guarded
    commit step (after the edit-and-diff step is verified clean, immediately
    before staging and `git commit`, never during the edit step). Do not pass
    `-c` / `--commit`; stage `TODO.md` and `TODO_ARCHIVE.md` into the final
    code commit so backlog updates are committed atomically with code changes.
  - Record out-of-scope findings via
    `todo_md add "<title>" -b "<problem_and_impact>"` in default `NEW` status
    without `--depends`; stage them into the final code commit (or pass `-c` /
    `--commit` when recorded after the code commit is already pushed or when no
    code commit follows). Run `todo_md -h` for full CLI flags and options.
