# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Role: design
- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Target files for downstream implementation: `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `README.md`, `tests/test_todo_md.py`.

# 🎯 [NEXT] F33: Add todo_md chain command for local and cross-project execution order

- Role: work
- Add `todo_md chain [--limit N] [--include-hold]` (supporting `-w` / `--workspace` and `-C` / `--project`) in `src/parser.py`, `src/commands.py`, `src/cli.py`, and `src/header.py`.
- Build a unified dependency DAG across all open non-`HOLD` tasks in the target project (resolving transitive `<project>:<ID>` prerequisites) or across all discovered workspace projects when `-w` is set, printing a compact `A -> B -> C` chain summary followed by ordered task rows (truncated to the first `N` tasks when `--limit N` is passed).
- Exclude `HOLD` tasks and tasks transitively blocked by `HOLD` from the main chain by default, rendering frozen chains under a separate `Held branches:` section (e.g., `H1 (HOLD) -> F2 (NEW)`), and include them in the main chain when `--include-hold` is passed.
- Report clear diagnostics on dependency cycles, syntax errors, or `MISSING` / `CANCELED` blockers, and update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py`.

# 🎯 [NEXT] F31: Show full unblock chain and blocked WIP badge in todo_md list

- Role: work
- Update `_task_dependency_info` in `src/parser.py` so multi-step unresolved dependency chains render the full ordered path from the ready root to the direct blocker (for example `[blocked: F21 (WIP) -> F22 (NEXT) -> F23 (WIP)]`) instead of truncating intermediate tasks with `<- start: <ID>`, while keeping `[blocked: <ID> (<STATUS>)]` for single-hop blockers.
- Update `cmd_list` and `cmd_workspace_list` in `src/parser.py` to display `⏳ [WIP]` (matching `⏳ [NEXT]`) whenever a `WIP` task has unresolved dependencies.
- Update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` to cover full chain formatting and blocked `WIP` badges.

# 🎯 [NEXT] D2: Design standalone task file mode (-f / --file) for shortlists and ad-hoc task files

- Role: design
- Explore and specify `-f <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md`.
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# 🎯 [NEXT] F25: Detect stale completion date notes on active tasks in todo_md check

- Extend `validate_all` in `src/parser.py` so `todo_md check` (and automatic post-mutation validation) reports an error when an active task in `TODO.md` retains a completion date stamp (`— *YYYY-MM-DD...*`) in its heading, instructing the user to move it back to `TODO_ARCHIVE.md` or clear the stale note.
- Target files: `src/parser.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# 🎯 [NEXT] F32: Add --tree view to todo_md list with terminal-width title truncation

- Role: work
- Depends on: F31
- Add `--tree` option to `todo_md list` in `src/cli.py`, `src/parser.py`, and `src/header.py` (`-h`/`--help`) to render active dependency chains as an indented hierarchy (`└─` / `├─`) with prerequisites placed above their blocked dependents across status buckets.
- Detect terminal width via `shutil.get_terminal_size` (with a sensible non-TTY fallback) to truncate task titles with `...` so rows stay on a single line, and fall back to compact ID-only tree lines when the terminal is too narrow to show titles cleanly.
- Update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` covering `--tree`, multi-step chains, shared dependencies, and narrow-terminal truncation and ID-only fallback.

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
