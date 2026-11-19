# ❌ [CANCELED] F14: Clarify in todo_md rule that backlog-only commits in plan/design/review run in the same block without a separate diff-review turn — *Avoid blanket same-block commits without diff review; checking diff prevents committing unintended backlog or index changes*

- Update the `Validation & commits` section in `src/rules/todo_md.md` to explicitly state that in `role=plan`, `role=design`, and `role=audit`/`role=review`, `todo_md` mutations can be batched and committed in the same execution block (via `-c` on the final `todo_md` command or `git add TODO*.md && git commit`) without waiting for a separate diff-review turn.
- Rebuild and reinstall `todo_md` (and keep any synced docs/tests in `tests/` green) so exported rules reflect the updated wording.

# ✅ [DONE] F41: Show downstream next tasks in todo_md chain --ready output — *2026-11-19, Show downstream unblocked targets in chain --ready output*

- Role: work
- Update the `ready` rendering branch in `cmd_chain()` (`src/commands.py`) using `dependents` from `build_execution_chain_dag()` (`src/parser.py`) so each ready row with `[unblocks N]` also displays its immediate (or downstream) unblocked targets (for example `[ready | unblocks 3 -> F54, F68, ...]` or `leads to: ...`), giving chain continuation context without leaving `--ready`.
- Keep `src/header.py` (`--help`), `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a PATCH release.

# ✅ [DONE] F40: Add --by-role execution queue mode to todo_md chain — *2026-11-19*

- Role: work
- Add a role-tiered queue planner helper (e.g. `plan_execution_chains_by_role()` in `src/parser.py`) over `build_execution_chain_dag()` that partitions active non-held tasks into four topologically sorted queues:
  1. `Queue 1 (work)`: `role == "work"` with no open transitive dependencies or all transitive dependencies also in `work`.
  2. `Queue 2 (plan)`: `role == "plan"` with no open transitive dependencies or transitive dependencies in `work`/`plan`.
  3. `Queue 3 (design)`: `role == "design"`.
  4. `Queue 4 (deferred work)`: remaining `work` tasks blocked by `plan`/`design` prerequisites (omitted when `--ready` is active).
- Add `--by-role` option to `todo_md chain` in `main()` (`src/cli.py`) and `cmd_chain()` (`src/commands.py`), reusing `_format_row()` (`[role]`, `[ready]` / `[blocked by: ...]`, `[unblocks N]`) and composing cleanly with `-w`, `--ready`, `--role`, `--limit`, and `--include-hold`.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh` if applicable), and bump `VERSION` for a MINOR release.

# ✅ [DONE] F39: Display role badges in todo_md chain and add --role filter — *2026-11-18*

- Role: work
- Update `cmd_chain()` (`src/commands.py`) to display a padded `[role]` column (reusing `_task_role_badge()` from `src/parser.py`, matching `cmd_list()` / `cmd_workspace_list()`, and leaving it blank for `MISSING` placeholders where `exists` is false) across `Chain:`, `Standalone tasks:`, and `--ready` rows while preserving `_wrap_table_row()` alignment.
- Add `--role <role>` (and `--role=<role>`) option to `todo_md chain` in `main()` (`src/cli.py`) and `cmd_chain()` (`src/commands.py`), filtering displayed tasks via `_task_matches_role()` (e.g. `todo_md chain -w --role work --ready` or `--role plan`) while keeping DAG validation and unblock context clear.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh` if applicable), and bump `VERSION` for a MINOR release.

# ✅ [DONE] F35: Wrap long descriptions into aligned table columns in list, chain, queue, and projects — *2026-11-18, Wrap tabular descriptions into aligned columns across list, chain, queue, and projects*

- Add a shared Unicode-aware column-wrapping helper in `src/parser.py` built on `_get_terminal_columns()`, `_display_width()`, and `_pad_display()` so fixed left columns remain on the first line while the trailing description column wraps at word boundaries with a hanging indent aligned to the description column start.
- Replace raw Python string width formatting (`f"{badge:<14}"`) with display-width padding (`_pad_display`) across tabular outputs so two-column status emojis align cleanly across rows.
- Apply tabular column wrapping to `todo_md list` and `todo_md list -w` (`src/parser.py`), `todo_md chain` and `todo_md chain -w` (`src/commands.py`), `todo_md queue` (`src/commands.py`), and `todo_md projects` (`src/parser.py`), falling back to a compact 4-space continuation indent when terminal width leaves fewer than 20 columns for the description column.
- Keep `todo_md list --tree` single-line truncated, full Markdown section views (`overview`, `show`, `last`, `archive`) unwrapped, and machine-readable commands (`files`, `next-id`, `last-id`, `ids`) single-line per item.
- Sync CLI help and documentation in `src/header.py` and `README.md`, rebuild/reinstall via `build.py` and `install.sh`, and add unit tests in `tests/test_todo_md.py`.

# ✅ [DONE] F32: Add --tree view to todo_md list with terminal-width title truncation — *2026-11-18, Add --tree dependency hierarchy view to list with terminal-width truncation*

- Role: work
- Depends on: F31
- Add `--tree` option to `todo_md list` in `src/cli.py`, `src/parser.py`, and `src/header.py` (`-h`/`--help`) to render active dependency chains as an indented hierarchy (`└─` / `├─`) with prerequisites placed above their blocked dependents across status buckets.
- Detect terminal width via `shutil.get_terminal_size` (with a sensible non-TTY fallback) to truncate task titles with `...` so rows stay on a single line, and fall back to compact ID-only tree lines when the terminal is too narrow to show titles cleanly.
- Update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` covering `--tree`, multi-step chains, shared dependencies, and narrow-terminal truncation and ID-only fallback.

# ✅ [DONE] F25: Detect stale completion date notes on active tasks in todo_md check — *2026-11-18, reject stale completion date notes on active tasks in check*

- Extend `validate_all` in `src/parser.py` so `todo_md check` (and automatic post-mutation validation) reports an error when an active task in `TODO.md` retains a completion date stamp (`— *YYYY-MM-DD...*`) in its heading, instructing the user to move it back to `TODO_ARCHIVE.md` or clear the stale note.
- Target files: `src/parser.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# ✅ [DONE] F34: Rank ready tasks by unblock impact in chain and print newly unblocked tasks on done — *2026-11-18, Rank ready tasks by unblock impact in chain and print newly unblocked tasks on done*

- Add `--ready` filtering and critical-path impact ranking (number of transitively unblocked downstream tasks, plus `[unblocks N]` annotations) to `todo_md chain` in `src/parser.py`, `src/cli.py`, and `src/header.py` (`-h`/`--help`) so the highest-leverage ready tasks appear first.
- Separate connected dependency chains from standalone tasks without dependencies in `todo_md chain` (`src/parser.py`) so independent tasks are not falsely joined with `->` arrows in `Chain:` headers and are grouped clearly as connected chains vs standalone tasks.
- Extend `cmd_done` in `src/commands.py` (and `src/parser.py`) to detect and print any open tasks in the current repository (and in a workspace orchestrator `.todo_projects` when present) whose dependencies just became completely `DONE` (`Unblocked: ...`).
- Keep `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` in sync.

# ✅ [DONE] F33: Add todo_md chain command for local and cross-project execution order — *2026-11-18, Add todo_md chain command for local and cross-project execution order*

- Role: work
- Add `todo_md chain [--limit N] [--include-hold]` (supporting `-w` / `--workspace` and `-C` / `--project`) in `src/parser.py`, `src/commands.py`, `src/cli.py`, and `src/header.py`.
- Build a unified dependency DAG across all open non-`HOLD` tasks in the target project (resolving transitive `<project>:<ID>` prerequisites) or across all discovered workspace projects when `-w` is set, printing a compact `A -> B -> C` chain summary followed by ordered task rows (truncated to the first `N` tasks when `--limit N` is passed).
- Exclude `HOLD` tasks and tasks transitively blocked by `HOLD` from the main chain by default, rendering frozen chains under a separate `Held branches:` section (e.g., `H1 (HOLD) -> F2 (NEW)`), and include them in the main chain when `--include-hold` is passed.
- Report clear diagnostics on dependency cycles, syntax errors, or `MISSING` / `CANCELED` blockers, and update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py`.

# ✅ [DONE] F31: Show full unblock chain and blocked WIP badge in todo_md list — *2026-11-18, Show full unblock chains and blocked WIP badges in list*

- Role: work
- Update `_task_dependency_info` in `src/parser.py` so multi-step unresolved dependency chains render the full ordered path from the ready root to the direct blocker (for example `[blocked: F21 (WIP) -> F22 (NEXT) -> F23 (WIP)]`) instead of truncating intermediate tasks with `<- start: <ID>`, while keeping `[blocked: <ID> (<STATUS>)]` for single-hop blockers.
- Update `cmd_list` and `cmd_workspace_list` in `src/parser.py` to display `⏳ [WIP]` (matching `⏳ [NEXT]`) whenever a `WIP` task has unresolved dependencies.
- Update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` to cover full chain formatting and blocked `WIP` badges.

# ✅ [DONE] F30: Emit Title header in todo_md show preamble for downstream bundle and TUI display — *2026-11-18*

- Emit `Title: <base_title>` in `cmd_show` (`src/commands.py`) immediately after `Task: <ID>`, stripping any trailing `— *note*` via `_strip_heading_note` so `Task:` stays the bare ID while `Title:` carries the clean task summary.
- Sync `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, and rebuild `todo_md` via `python3 build.py`.

# ✅ [DONE] F20: Add global -C/--project target option across all todo_md subcommands — *2026-11-18*

- Add a global project/directory selector (`-C <dir|project>` and `--project <name>`, keeping `-p` in `add` for prefix) accepted before subcommands so any `todo_md` command (`ids`, `list`, `archive`, `last`, `last-id`, `next-id`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`, `done`, `cancel`, `show`) can target a repository from any directory.
- Resolve `-C` targets as either a filesystem directory path or a discovered workspace project name/relative path (from `.todo_projects` / workspace root), failing explicitly with a non-zero exit code when the target cannot be resolved.
- Keep `<project>:<ID>` strictly for task-level references (`show`, `edit`, `done`, `Depends on:`), and define explicit precedence (`-C`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory).
- Update `src/cli.py`, `src/header.py`, `README.md`, `src/rules/todo_md.md`, and `tests/test_todo_md.py` in sync.

# ✅ [DONE] F29: Lazy-import urllib.request in src/cli.py to reduce CLI startup latency — *2026-11-17, lazy-import urllib.request*

- Move `import urllib.request` out of top-level `src/header.py` into `fetch_remote_script` in `src/cli.py` so regular commands (`--version`, `check`, `add`, `list`, etc.) avoid importing `urllib.request`, `http.client`, and `ssl` (~21 ms startup overhead).
- Rebuild standalone `todo_md` via `python3 build.py`, verify `python3 build.py --check`, reinstall locally via `sh install.sh --yes`, and add an offline unit test in `tests/test_todo_md.py` confirming `urllib.request` is not imported on normal commands while `update` / `check-update` behavior remains intact.
- Target files: `src/header.py`, `src/cli.py`, `todo_md`, `tests/test_todo_md.py`.

# ✅ [DONE] F28: Speed up unit tests by running CLI calls in-process — *2026-11-17, in-process CLI test runner*

- Load the built `todo_md` script once per test class (e.g. in `setUpClass` via `importlib.machinery.SourceFileLoader`) and execute `main(argv)` in-process inside `tests/test_todo_md.py` with isolated `stdout`, `stderr`, `stdin`, `cwd`, and `os.environ` instead of spawning nearly 300 `subprocess.run` processes.
- Keep real `subprocess.run` coverage for executable entrypoint and environment integration tests (`-h`, `--version`, `pty` TTY error handling, `git` `--commit`, and `install.sh`).
- Verify `python3 -m unittest discover -s tests` passes cleanly with zero `ResourceWarning`s and completes in under 2 seconds.
- Target files: `tests/test_todo_md.py`.

# ✅ [DONE] F27: Order list output topologically by dependencies, highlight blocked NEXT tasks, and add --ready filter — *2026-11-17*

- Depends on: F21, F22
- Order tasks topologically within each status bucket in `_order_active_tasks_for_list` (`src/parser.py`) and `_sort_todo_file` (`src/commands.py`) so prerequisites always appear before dependent tasks regardless of `todo_md next` promotion order (falling back to file order if a cycle exists).
- Place unblocked (`ready`) tasks before tasks with open blockers within `NEXT` (and other active status buckets), and render blocked `NEXT` items with `⏳ [NEXT]` in `todo_md list` and `todo_md list -w` without altering `TODO.md` headings.
- Display dependency status badges (`[blocked: ...]` / `[deps: DONE]`) in `todo_md list -w` matching local `todo_md list`, and append the actionable root blocker (`<- start: <ID>`) when blocked by a multi-step chain.
- Add `--ready` option to `todo_md list` (`src/cli.py`, `src/commands.py`, `src/parser.py`) to filter active tasks to those with no unresolved dependencies (working across local and `-w` workspace modes).
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, and rebuild `todo_md` via `python3 build.py`.

# ✅ [DONE] F22: Remove reverse ordering of QUESTION/NEW/HOLD tasks in todo_md list — *2026-11-17*

- Remove `reversed(bucket)` for `QUESTION`, `NEW`, and `HOLD` in `_order_active_tasks_for_list` (`src/parser.py`) so `todo_md list` and `todo_md list -w` display active tasks in exact `TODO.md` file order (top to bottom).
- Preserve existing `resolve_last_task_id` behavior (`last`, `last-id`, `show last`).
- Update `test_last_last_id_and_list_options` in `tests/test_todo_md.py` (and any synced docs in `README.md` / `src/header.py` if needed).
- Rebuild `todo_md` with `python3 build.py` and verify with `python3 -m unittest discover -s tests`.

# ✅ [DONE] F21: Implement dependency sequencing (->), queue, and next-id resolution — *2026-11-17*

- Implement sequential stage syntax (`->`) alongside parallel commas (`,`) in `- Depends on:` and `--depends`: `,` binds tighter than `->` (`A, B -> C`), and multiple `- Depends on:` lines (or repeated `--depends`) represent independent branches combined with AND; do not introduce a separate `- Order:` field.
- Merge explicit `->` stage edges on the target task with transitive `- Depends on:` edges across intra-project and workspace `<project>:<ID>` tasks into a unified DAG (preserving one-way repo boundaries for cross-project orchestrators).
- Treat `DONE` as unblocking and `CANCELED` / `MISSING` as blocking; upgrade `todo_md check` (`validate_all`) to validate `,`/`->` syntax and detect transitive dependency cycles.
- Render sequential chains in `Dependencies (ready|blocked): ...` using ASCII `->` for sequential edges, `, ` for parallel siblings, and `; ` between independent clauses.
- Add `todo_md queue <ID> [--all]` to display the stable topologically sorted execution queue (hiding `DONE` by default unless `--all` is passed) with `[ready]` / `[blocked by: ...]` markers and `Next actionable: <ref>`.
- Extend `todo_md next-id [<ID>]` to accept an optional `<ID>` (or `<project>:<ID>`) and print the first unblocked actionable task ID in `<ID>`'s queue (or `<ID>` itself when all deps are `DONE`), exiting non-zero on cycles, missing/canceled blockers, or already-closed targets.
- Update `src/rules/todo_md.md` to specify the `--depends` contract (`A,B` vs `"A -> B -> C"`, no `- Order:`, one-way boundaries) and `queue` / `next-id <ID>` usage.
- Target files: `src/header.py`, `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# ✅ [DONE] F26: Display resolved task role and support --role filter in todo_md list — *2026-11-17*

- Display the resolved role (`resolve_task_role` in `src/parser.py`, e.g. `[design]`, `[work]`, or explicit `- Role:` value) in compact `cmd_list` and `cmd_workspace_list` rows (`todo_md list` and `todo_md list -w`) alongside status and location.
- Add `--role <role>` filtering to `todo_md list` and `todo_md list -w` in `src/cli.py`, `src/parser.py` (`cmd_list`, `cmd_workspace_list`), and `src/header.py` (matching case-insensitively against `resolve_task_role`).
- Keep `src/rules/todo_md.md` and `README.md` in sync, add unit tests in `tests/test_todo_md.py`, and rebuild `todo_md` via `python3 build.py`.

# ✅ [DONE] F15: Limit todo_md files preloading by line and byte budget — *2026-11-17*

- Add optional per-file and total budget flags to `todo_md files [<ID>]`
  (e.g., `--max-lines N`, `--max-total-lines N`, `--max-bytes N`) in
  `src/commands.py` (`cmd_files`), `src/cli.py`, and `src/header.py`, keeping
  bare `todo_md files [<ID>]` backward-compatible with no cap by default.
- Update `src/bundles/todo_md.bundle` (`role=execute` and `role=audit`) to
  pass sensible size limits to `todo_md files {task:}` so small target files
  are preloaded while large files are left for selective `grep`/`sed` reads.
- Clarify in `src/bundles/todo_md.bundle` (`role=plan`) and
  `src/rules/todo_md.md` that task bodies should reference target file paths
  and key symbol names (functions/classes) in backticks rather than brittle
  line ranges.
- Sync `README.md` and add unit tests in `tests/test_todo_md.py` covering
  per-file and total budget filtering.

# ✅ [DONE] F24: Forbid implicit reopening of archived tasks (--reopen and todo_md reopen) — *2026-11-17, forbid implicit reopening, add --reopen and reopen*

- Reject transitions from `TODO_ARCHIVE.md` (`DONE` or `CANCELED`) to active statuses (`WIP`, `NEXT`, `NEW`, `HOLD`, `QUESTION`) in `status` and `next` (and reject re-archiving already archived tasks in `done`, `cancel`, and `archive <ID>`) unless `--reopen` is explicitly passed, exiting non-zero with the current archived status, closing note, and a hint to use `--reopen` or `reopen <ID>`.
- Add `--reopen` support to `status` and `next`, plus a `todo_md reopen <ID> [--status <STATUS>] [-m "<note>"] [-c]` subcommand that moves the task back to `TODO.md` (default status `NEW`) and clears any prior closing note from the heading unless `-m` is supplied.
- Ensure pre-execution hooks in `src/bundles/todo_md.bundle` (`$ todo_md status {task:} WIP`) fail fast before session startup if given an archived task ID, while read/audit commands (`show`, `files`, `role=audit`) continue to work on archived tasks.
- Target files: `src/cli.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `README.md`, `tests/test_todo_md.py`.

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
