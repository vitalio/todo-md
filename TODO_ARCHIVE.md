# ✅ [DONE] F23: Emit Task, Role, and Workdir headers in single-task show output — *2026-11-17, emit Task, Role, and Workdir headers*

- Update `cmd_show` in `src/parser.py` and single-task dispatch in `src/cli.py` so displaying an individual task (`<ID>`, `<project>:<ID>`, `show <ID|last>`) prints `Task: <ID>`, optional `Role: <role>`, and `Workdir: <absolute project directory>` followed by a blank line before `# TODO.md:<line>`.
- Resolve `Role:` from explicit `- Role: <role>` metadata in the task body (supported via `--role <role>` in `todo_md add` / `todo_md edit`), falling back by task prefix (`D` -> `design`, `F`/`B` -> `work`; omit `Role:` for unmapped prefixes when unset).
- Ensure `Workdir:` resolves to the target project root for local `<ID>`, `<project>:<ID>`, and `-C` invocations, while keeping workspace/list overview outputs unchanged.
- Sync `README.md`, `src/header.py`, `src/rules/todo_md.md`, and `tests/test_todo_md.py`, and rebuild `todo_md` via `build.py`.

# ✅ [DONE] D1: Design dependency queue and next actionable task resolution — *2026-11-17, design agreed; spec recorded in AGENTS.md and F21*

- Design CLI commands in `todo_md` to build an ordered execution queue for a
  target task (for example, `todo_md queue <ID>`) and resolve the next
  unblocked actionable task (for example, `todo_md resolve <ID>` or
  `todo_md next-id <ID>`).
- Traverse `Depends on:` edges recursively across intra-project and
  `.todo_projects` workspace tasks, filter out `DONE` and `CANCELED` tasks,
  and preserve declared `Depends on:` order so orchestrator tasks can sequence
  cross-project steps without breaking the one-way dependency boundary.
- Define output format, cycle and missing-reference error handling, and
  composition with `todo_md show` / `agents_bundle` / `run_block` pipes.
- Target files for implementation: `src/parser.py`, `src/cli.py`,
  `src/header.py`, `README.md`, `src/rules/todo_md.md`, `tests/test_*.py`.

# ✅ [DONE] F19: Print Workdir header for explicit project task references — *2026-11-17*

- In `src/parser.py` (`cmd_show`) and `src/cli.py`, when a task is addressed
  with an explicit `<project>:<ID>` reference, print `Workdir: <absolute
  project path>` followed by a blank line before the usual `# TODO.md:<line>`
  output. Without an explicit project the output stays unchanged.
- Resolve the path through `resolve_project_task_ref` so `.todo_projects`
  filtering and workspace escape checks still apply.
- Keep `README.md`, `src/header.py` (`--help`), `src/rules/todo_md.md`, and
  `tests/test_*.py` in sync.

# ✅ [DONE] F18: Connect python-stdlib and python-annotations rules in .agents_bundle — *2026-11-16, Connect python-stdlib and python-annotations rules in .agents_bundle*

- In `.agents_bundle`, remove `py_min=3.9` from `stack/python-cli` and add
  `rule vitalio/agents-rules:stack/python-stdlib` and
  `rule vitalio/agents-rules:stack/python-annotations py_min=3.9`, after the
  python-cli split is released in agents-rules and the package cache is
  refreshed.
- Keep `from __future__ import annotations` only in `build.py` and
  `src/header.py`; do not add it to modules under `src/`.
- Run `python3 -m unittest discover -s tests`; if the progress line shows
  stderr noise, capture it with `contextlib.redirect_stderr` in `tests/`.

# ✅ [DONE] F7: Cross-project workspace discovery, <project>:<ID> addressing, and Depends on support — *2026-11-16*

- Detect a todo_md-managed project by the presence of both TODO.md and TODO_ARCHIVE.md (without climbing to git rev-parse --show-toplevel when invoked in a subproject or a workspace directory without TODO.md).
- When invoked in a directory without TODO.md + TODO_ARCHIVE.md (or when -w / --workspace is passed), scan subdirectories up to a bounded depth (e.g. 3 levels, skipping hidden directories '.*' and build/vendor directories) without stopping at intermediate projects so both root projects (e.g. chrome) and nested subprojects (e.g. chrome/canary) are discovered as separate project namespaces.
- Add 'todo_md projects' to list discovered workspace projects and their open task counts, and support '-w' / '--workspace' for cross-project task overviews and queries.
- Support universal '<project>:<ID>' and '<project>' addressing across CLI commands (e.g. 'todo_md agents_bundle:F5', 'todo_md chrome/canary:F1', 'todo_md add agents-rules ...') using POSIX '/' separators on all platforms (Linux, macOS, Windows), resolving '<project>' relative to the current workspace root (parent of the current repository root or TODO_MD_WORKSPACE).
- Support '--depends <ref>[,<ref>...]' on 'todo_md add' and 'todo_md edit' (storing '- Depends on: <ref>' in the task body), validate dependency targets in 'todo_md check', and surface dependency status ([DONE] vs blocked) in task output.
- Update todo_md.bundle to run 'todo_md -w' when 'workspace=1' is passed.

# ✅ [DONE] F13: Strengthen role=execute prompt and task resolution in todo_md.bundle — *2026-11-16*

- Guard `var task=$(todo_md next-id)` with `[if task=]` in `src/bundles/todo_md.bundle` so an explicitly passed `task=<ID>` is preserved and transitioned to `WIP` rather than overwritten.
- Rewrite the `role=execute` prompt in `src/bundles/todo_md.bundle` as a direct imperative instructing the model to emit its first `run_block` in the very first reply (either applying edits, tests, and diff immediately when all target files are preloaded, or running a single batched read step when target files are missing or unspecified).
- Clarify the empty `task=` fallback prompt in `src/bundles/todo_md.bundle` to handle a task ID supplied via `-p` or propose the top task shown in the `todo_md` overview.
- Update `tests/test_todo_md.py` to assert `[if task=] var task=$(todo_md next-id)` and the updated `role=execute` prompt invariants in `src/bundles/todo_md.bundle`.

# ✅ [DONE] F9: Always expand at least one task in default todo_md overview — *2026-11-16*

- Update `cmd_summary` in `src/parser.py` so that when `full=False` and `TODO.md` has no `WIP`, `NEXT`, or `QUESTION` tasks (only `NEW` and/or `HOLD`), the first ordered task is rendered in full while subsequent `NEW`/`HOLD` tasks remain compacted.
- Keep `todo_md [--full]` documentation in sync across `src/header.py`, `src/rules/todo_md.md`, and `README.md`.
- Add unit tests in `tests/test_todo_md.py` verifying that default `todo_md` expands the first `NEW`/`HOLD` task when no higher-priority tasks exist and keeps all `NEW`/`HOLD` tasks compact when at least one `WIP`/`NEXT`/`QUESTION` task is shown in full.

# ✅ [DONE] F12: Document role-based backlog commit workflow in rules and bundle — *2026-11-16, Document role-based backlog commit workflow in rules and bundle*

- Update `src/rules/todo_md.md` (`Validation & commits` / `Status lifecycle`) to specify role-based commit behavior:
  - `role=execute`: do not pass `-c`/`--commit`; stage `TODO.md` and `TODO_ARCHIVE.md` into the final code commit so `done` is atomic with implementation.
  - `role=plan`, `role=design`, and `role=audit`: batch `todo_md` mutations without `-c` and commit `TODO*.md` in a single commit once backlog updates are finished (e.g. `-c`/`--commit` on the final `todo_md` command or `git add TODO*.md && git commit`) before starting `role=execute`.
- Update `src/bundles/todo_md.bundle` (`[if role=plan]`, `[if role=design]`, `[if role=audit]` prompts) to remind the agent to commit `TODO*.md` after recording agreed tasks.
- Rebuild standalone `todo_md` via `python3 build.py` and keep `README.md` in sync if needed.

# ✅ [DONE] F11: Capture all subprocess output in unit tests — *2026-11-16*

- Update `tests/test_todo_md.py` so every `subprocess.run(...)` call captures `stdout` and `stderr` (`capture_output=True, text=True` or a shared helper on `TestTodoMd` that includes captured output in failure diagnostics).
- Verify `python3 -m unittest discover -s tests -q` emits no extraneous `todo_md:` or subprocess output when tests pass.

# ✅ [DONE] F10: Support -b - / --body - to read task body from stdin — *2026-11-16, Support -b - / --body - to read task body from stdin*

- Treat `-b -` and `--body -` in `add`, `edit`, and `append` (`src/commands.py`) as an explicit request to read the task body from `stdin` via a shared helper.
- When `-b -` / `--body -` is passed with an interactive TTY `stdin`, fail fast with a clear error message on `stderr` and non-zero exit status instead of hanging for EOF.
- When `stdin` is non-TTY: read `stdin` (`append` still rejects empty text, `add` creates a task without a body on empty `stdin`, and `edit` updates or clears the body consistently with `-b ""`).
- Keep `-b` / `--body` documentation in sync across `src/header.py`, `src/rules/todo_md.md`, and `README.md`.
- Add unit tests in `tests/test_todo_md.py` covering `-b -` and `--body -` for `add`, `edit`, and `append` (both piped `stdin` and TTY `stdin` error handling).

# ✅ [DONE] F4: Support last/last-id selectors, list --full/--limit, and task=<ID>|last|DONE in role=audit bundle — *2026-11-15, Support last/last-id selectors, list --full/--limit, and task=<ID>|last|DONE in role=audit bundle*

- Add `todo_md last-id [<STATUS|archive>]` (defaulting to `NEW`) to print the resolved `<ID>` to stdout (or exit 1 if none): bottom-most task in group for `NEW`/`HOLD`/`QUESTION` (most recently added), top-most task in group for `WIP`/`NEXT`, and top-most matching task in `TODO_ARCHIVE.md` for `DONE`/`CANCELED`/`archive`.
- Add `todo_md last [<STATUS|archive>]` and `todo_md show last [<STATUS|archive>]` (defaulting to `NEW`) to resolve the target `<ID>` via `last-id` and render full `todo_md <ID>` output (`# <file>:<line>`, full section, and `IDs in use` footer).
- Extend `todo_md list [filter]` with `--limit N` (`-n N`) and `--full` (render full task sections instead of compact one-line rows), ordering `NEW`/`HOLD`/`QUESTION` newest-first like `TODO_ARCHIVE.md`.
- Update `src/bundles/todo_md.bundle` under `[if role=audit]` to resolve `task=last` or `task=DONE` via `var task=$(todo_md last-id DONE)` and, when `task` is non-empty, run `$ todo_md {task:}` and `include $(todo_md files {task:})` with a targeted task audit prompt; remove the obsolete intermediate-plan instruction from `[if role=execute]`.
- Keep `src/header.py`, `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` in sync.

# ✅ [DONE] F8: Auto-resolve top WIP/NEXT task, extract task target files, and support piping to agents_bundle — *2026-11-15, Add top task ID and target file extraction commands and update workflow bundle*

- Add CLI helpers (e.g. `todo_md --top` / `todo_md next-id` to print the top `WIP` or `NEXT` task ID, and `todo_md --files <ID>` to list existing repository file paths referenced in backticks in task `<ID>`) and support piping `todo_md [<ID>] | agents_bundle | run_block`.
- Update `src/bundles/todo_md.bundle` (and `agents/bundles/todo_md.bundle` per F6) so that:
  - in `role=plan`, the prompt instructs recording target file paths in the task body and preloading them when initializing the execution session (`agents_bundle role=execute task=<ID> <file ...> | run_block`);
  - in `role=execute` (and `role=work`), when `task` is omitted it automatically resolves to the top `WIP` or `NEXT` task ID so `Task: <ID>` is always recorded in the session header, transitions the task to `WIP`, prints `todo_md <ID>`, auto-includes the task's referenced project files into the bundle, and instructs the agent to proceed directly to edit, test, and diff in step 1 when all target files are already preloaded.

# ✅ [DONE] F5: Default mutating commands to no-commit (opt-in --commit), auto-group TODO.md by status, and auto-transition task=<ID> to WIP in role=execute — *2026-11-15, Release v0.7.0*

- Make mutating todo_md commands ('add', 'edit', 'append', 'status', 'next', 'done', 'cancel', 'init') validate and write 'TODO.md'/'TODO_ARCHIVE.md' without auto-committing by default; add '--commit' / '-c' for explicit git commits (keeping '--no-commit' as a no-op alias for backwards compatibility).
- Auto-order active tasks in 'TODO.md' by status priority ('WIP' -> 'NEXT' -> 'QUESTION' -> 'NEW' -> 'HOLD') on every mutation while preserving relative order within each status group, and prepend newly archived tasks ('DONE', 'CANCELED') to the top of 'TODO_ARCHIVE.md'.
- Always render backlog tasks ('NEW', 'HOLD') in compact view in 'todo_md' summary output (regardless of total task count unless '--full' is passed), while expanding 'WIP', 'NEXT', and 'QUESTION' tasks in full.
- Define clear status lifecycle rules in 'src/rules/todo_md.md' and 'src/bundles/todo_md.bundle': 'NEW' is the default backlog status (compact view), 'NEXT' is promoted in 'role=plan' for prioritized ready tasks (expanded view), 'WIP' is set automatically by 'todo_md.bundle' when starting 'role=execute task=<ID>', and 'done' is run before the final commit in 'role=execute' so backlog updates are committed atomically with code changes.
- In 'src/bundles/todo_md.bundle' under '[if role=execute]' and '[if task!=]', transition '{task:}' to 'WIP' before printing '$ todo_md {task:}'.

# ✅ [DONE] F1: Task status transition subcommands (`done` / `status`) — *implemented in v0.1.0*

Add `todo_md done <ID>` and `todo_md status <ID> <STATUS>` to automatically
update a task's status badge or move a completed task from `TODO.md` to `TODO_ARCHIVE.md`.

# ✅ [DONE] F2: Add src/rules/todo_md.md and src/bundles/todo_md.bundle and remove --agents CLI flag — *2026-11-14*
