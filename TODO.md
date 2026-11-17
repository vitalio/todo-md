# 🎯 [NEXT] F26: Display resolved task role and support --role filter in todo_md list

- Display the resolved role (`resolve_task_role` in `src/parser.py`, e.g. `[design]`, `[work]`, or explicit `- Role:` value) in compact `cmd_list` and `cmd_workspace_list` rows (`todo_md list` and `todo_md list -w`) alongside status and location.
- Add `--role <role>` filtering to `todo_md list` and `todo_md list -w` in `src/cli.py`, `src/parser.py` (`cmd_list`, `cmd_workspace_list`), and `src/header.py` (matching case-insensitively against `resolve_task_role`).
- Keep `src/rules/todo_md.md` and `README.md` in sync, add unit tests in `tests/test_todo_md.py`, and rebuild `todo_md` via `python3 build.py`.

# 🎯 [NEXT] F20: Add global -C/--project target option across all todo_md subcommands

- Add a global project/directory selector (`-C <dir|project>` and `--project <name>`, keeping `-p` in `add` for prefix) accepted before subcommands so any `todo_md` command (`ids`, `list`, `archive`, `last`, `last-id`, `next-id`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`, `done`, `cancel`, `show`) can target a repository from any directory.
- Resolve `-C` targets as either a filesystem directory path or a discovered workspace project name/relative path (from `.todo_projects` / workspace root), failing explicitly with a non-zero exit code when the target cannot be resolved.
- Keep `<project>:<ID>` strictly for task-level references (`show`, `edit`, `done`, `Depends on:`), and define explicit precedence (`-C`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory).
- Update `src/cli.py`, `src/header.py`, `README.md`, `src/rules/todo_md.md`, and `tests/test_todo_md.py` in sync.

# 🎯 [NEXT] D2: Design standalone task file mode (-f / --file) for shortlists and ad-hoc task files

- Role: design
- Explore and specify `-f <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md`.
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# 🎯 [NEXT] F25: Detect stale completion date notes on active tasks in todo_md check

- Extend `validate_all` in `src/parser.py` so `todo_md check` (and automatic post-mutation validation) reports an error when an active task in `TODO.md` retains a completion date stamp (`— *YYYY-MM-DD...*`) in its heading, instructing the user to move it back to `TODO_ARCHIVE.md` or clear the stale note.
- Target files: `src/parser.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# 🎯 [NEXT] F21: Implement dependency sequencing (->), queue, and next-id resolution

- Implement sequential stage syntax (`->`) alongside parallel commas (`,`) in `- Depends on:` and `--depends`: `,` binds tighter than `->` (`A, B -> C`), and multiple `- Depends on:` lines (or repeated `--depends`) represent independent branches combined with AND; do not introduce a separate `- Order:` field.
- Merge explicit `->` stage edges on the target task with transitive `- Depends on:` edges across intra-project and workspace `<project>:<ID>` tasks into a unified DAG (preserving one-way repo boundaries for cross-project orchestrators).
- Treat `DONE` as unblocking and `CANCELED` / `MISSING` as blocking; upgrade `todo_md check` (`validate_all`) to validate `,`/`->` syntax and detect transitive dependency cycles.
- Render sequential chains in `Dependencies (ready|blocked): ...` using ASCII `->` for sequential edges, `, ` for parallel siblings, and `; ` between independent clauses.
- Add `todo_md queue <ID> [--all]` to display the stable topologically sorted execution queue (hiding `DONE` by default unless `--all` is passed) with `[ready]` / `[blocked by: ...]` markers and `Next actionable: <ref>`.
- Extend `todo_md next-id [<ID>]` to accept an optional `<ID>` (or `<project>:<ID>`) and print the first unblocked actionable task ID in `<ID>`'s queue (or `<ID>` itself when all deps are `DONE`), exiting non-zero on cycles, missing/canceled blockers, or already-closed targets.
- Update `src/rules/todo_md.md` to specify the `--depends` contract (`A,B` vs `"A -> B -> C"`, no `- Order:`, one-way boundaries) and `queue` / `next-id <ID>` usage.
- Target files: `src/header.py`, `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# 🎯 [NEXT] F22: Remove reverse ordering of QUESTION/NEW/HOLD tasks in todo_md list

- Remove `reversed(bucket)` for `QUESTION`, `NEW`, and `HOLD` in `_order_active_tasks_for_list` (`src/parser.py`) so `todo_md list` and `todo_md list -w` display active tasks in exact `TODO.md` file order (top to bottom).
- Preserve existing `resolve_last_task_id` behavior (`last`, `last-id`, `show last`).
- Update `test_last_last_id_and_list_options` in `tests/test_todo_md.py` (and any synced docs in `README.md` / `src/header.py` if needed).
- Rebuild `todo_md` with `python3 build.py` and verify with `python3 -m unittest discover -s tests`.

# ⚪ [NEW] P1: JSON output mode (`--json`)

Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F3: Clarify repository scope rule in .bundle to target the owning repository

- Update the repository scope instruction in .bundle and todo_md.md (and synced documentation if applicable) to state explicitly that each task must be recorded in the TODO.md of the repository it belongs to (targeting that project via <project>:<ID> or running todo_md in that target project), never in an unrelated project's backlog.
- Document task dependencies using 'Depends on: <ID>' (same project) or 'Depends on: <project>:<ID>' (cross-project, e.g. agents_bundle:F5 or chrome/canary:F1) in the task body.

# ⚪ [NEW] F6: Move exported rules and bundles from src/ to agents/

- Depends on: agents_bundle:F7, agents_bundle:F15
- Move `src/rules/todo_md.md` and `src/bundles/todo_md.bundle` to `agents/` using the unified logical bundle/rule layout once `agents_bundle` supports it.
- Update `AGENTS.md`, `README.md`, and tests to reference the new paths under `agents/`.

# ⚪ [NEW] F14: Clarify in todo_md rule that backlog-only commits in plan/design/audit run in the same block without a separate diff-review turn

- Update the `Validation & commits` section in `src/rules/todo_md.md` to explicitly state that in `role=plan`, `role=design`, and `role=audit`, `todo_md` mutations can be batched and committed in the same execution block (via `-c` on the final `todo_md` command or `git add TODO*.md && git commit`) without waiting for a separate diff-review turn.
- Rebuild and reinstall `todo_md` (and keep any synced docs/tests in `tests/` green) so exported rules reflect the updated wording.

# ⚪ [NEW] F16: Migrate workflow bundle and docs from role=execute and role=audit to role=work and role=review

- Depends on: agents-rules:F9, agents-rules:F16
- Update `src/bundles/todo_md.bundle`, `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` to use `role=work` and `role=review` instead of `role=execute` and `role=audit` (preserving legacy aliases only if needed during transition).
- Rebuild and reinstall `todo_md` and release a PATCH version.

# ⚪ [NEW] F17: Document task prefix conventions (F, B, D) and design-task lifecycle in todo_md rule and bundle

- Document standard task ID prefixes in `src/rules/todo_md.md`: `F` (feature / default), `B` (bugfix / defect), and `D` (design / architectural exploration / raw idea routed to `role=design` before decomposition into `F` tasks).
- Update `src/bundles/todo_md.bundle` (`[if role=design]`) so design tasks (`D*`) are closed via `todo_md done <ID>` once architectural invariants are persisted in `AGENTS.md` and follow-up `F*` implementation tasks are created.
- Rebuild and reinstall `todo_md`, keep `README.md` and `tests/test_todo_md.py` in sync, and release a PATCH version.
