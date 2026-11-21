# 🎯 [NEXT] F64: Share workspace/orchestrator discovery across per-task DAG builds and include inbound blockers in workspace overview

- Depends on: F63
- Reuse workspace project and `.todo_projects` orchestrator discovery across per-task dependency DAG evaluations in `list`, `show`, `overview`, and active-task ordering, and report inbound orchestrator blockers consistently in workspace overviews (consolidates `F65`):
  - In `src/parser.py`, avoid repeating `resolve_workspace_root()`, `discover_projects()`, `discover_orchestrators_for_project()`, `collect_all_tasks()`, and orchestrator stage-edge extraction across repeated `build_dependency_dag()` / `_task_dag()` calls within a single CLI command or view render (`_order_active_tasks()`, `_is_task_blocked()`, `_task_dependency_info()`, `_inbound_blocker_items()`, `format_dependency_summary()`, `cmd_list()`, `cmd_workspace_list()`, `cmd_summary()`, `cmd_workspace_summary()`, and `cmd_show()`).
  - In `_format_task_for_summary()` (`src/parser.py:1038-1073`), pass `task=task` to `format_dependency_summary()` even when `proj_prefix` is set so `todo_md overview -w` (`cmd_workspace_summary()`) includes inbound `.todo_projects` orchestrator stage blockers in the `Dependencies (...)` line, matching `show`, `list`, and `chain`.
  - Extend `test_orchestrator_inbound_edges_in_queue_next_id_list_and_show` in `tests/test_deps.py` to verify that `overview -w` reports inbound orchestrator blockers for prefixed project tasks and clears them once the prerequisite is marked `DONE`, and verify that repeated per-task DAG queries reuse orchestrator discovery within a render pass.
- Target files: `src/parser.py:433-908`, `src/parser.py:1038-1073`, `src/parser.py:2152-2223`, `tests/test_deps.py:459-498`.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Target files for downstream implementation: `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

- Coordinate with `todo_flow:D4`: when a child repository belongs to a workspace orchestrator (`.todo_projects`), surface inbound orchestrator blockers in runtime `list` / `show` output (e.g. `[blocked via todo_flow:F2: ...]`) without storing cross-project `Depends on:` edges in the child `TODO.md`.

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Depends on: F55
- Explore and specify `-F <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo_md -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.

# 🎯 [NEXT] F62: Decompose monolithic src/parser.py and src/commands.py into focused domain modules

- Depends on: B2, B3, F57, F63 -> F64
- Refactor `src/parser.py` (3,600+ lines) and `src/commands.py` (1,800+ lines) into cohesive domain modules (~300-800 lines each) with clean layer boundaries:
  - `src/header.py` (`1-353`): imports, constants, regular expressions, `prog_name()`, and `usage_text()`.
  - `src/workspace.py` (from `src/parser.py:1-299` and `src/parser.py:1833-2139`): project and workspace root resolution (`is_todo_project()`, `resolve_target_dir()`, `resolve_workspace_root()`, `discover_projects()`, `project_label()`, `lookup_external_alias()`, `resolve_project_dir()`, `resolve_project_or_dir()`, `resolve_project_task_ref()`, `resolve_filter_task_ref()`, `.todo_projects` and nested orchestrator discovery `read_configured_todo_projects()`, `is_orchestrator_project()`, `discover_orchestrators_for_project()`, `resolve_workspace_chain_projects()`).
  - `src/parser.py` (from `src/parser.py:300-432`, `730-1043`, `1511-1629`, and `src/commands.py:1011-1102`): Markdown section parsing (`parse_tasks_in_text()`, `collect_all_tasks()`), dependency clause syntax parsing (`parse_depends_clause()`, `parse_dependency_clauses()`), role resolution (`resolve_task_role()`), file extraction (`split_line_slice()`, `split_file_spec()`, `extract_task_files()`), ID tracking (`highest_ids_in_use()`, `next_free_id()`), search (`search_tasks()`), and file validation (`validate_all()`).
  - `src/dag.py` (from `src/parser.py:433-729` and `src/parser.py:2140-3626`): unified dependency DAG construction and chain planning/ranking (`build_dependency_dag()`, `_first_actionable_in_dag()`, `_task_dependency_info()`, `build_execution_chain_dag()`, `compute_unblock_counts()`, `build_chain_milestone_tree()`, `plan_execution_chains()`, `plan_execution_chains_by_role()`, `find_newly_unblocked_tasks()`).
  - `src/render.py` (from `src/parser.py:749-792`, `921-1510`, `1630-1832`, and `src/commands.py:294-302`, `1147-1839`): terminal display width, ANSI styling, table wrapping (`_display_width()`, `_style_task_row()`, `_wrap_table_row()`), and read-only view renderers (`format_dependency_summary()`, `cmd_chain()`, `cmd_list()`, `cmd_show()`, `cmd_summary()`, `cmd_ids()`, `cmd_last()`, `cmd_last_id()`, `cmd_archive_view()`, `cmd_projects()`, `cmd_workspace_summary()`, `cmd_workspace_list()`, `cmd_workspace_check()`).
  - `src/commands.py` (from `src/commands.py:1-293`, `303-1010`, `1103-1146`): backlog file sorting, Git auto-commit helpers, and mutating/query CLI commands (`cmd_check()`, `cmd_init()`, `cmd_add()`, `cmd_edit()`, `cmd_append()`, `cmd_transition()`, `cmd_reopen()`, `resolve_top_task_id()`, `cmd_next_id()`, `cmd_files()`).
  - `src/cli.py` (`src/cli.py:1-399` and `src/cli.py:399-759`): self-update commands (`cmd_check_update()`, `cmd_update()`), CLI argument parsing (`_parse_quest_log_args()`), and `main()`.
- Update `MODULE_ORDER` in `build.py`, regenerate standalone `./todo_md`, align `AGENTS.md` module descriptions, and verify all unit tests in `tests/test_*.py` pass without behavioral regressions.
- Target files: `build.py`, `AGENTS.md`, `src/header.py`, `src/parser.py:1-360`, `src/commands.py:1-310`, `src/cli.py:1-399`.

# ⚪ [NEW] F42: Rename project to todo-markdown and CLI utility to tmd

- Rename project/repository references from `todo_md` to `todo-markdown` and CLI entrypoint from `todo_md` to `tmd` (preserving `TODO.md`/`TODO_ARCHIVE.md` task-file conventions and applying agreed env-var/alias decisions from the ecosystem rename design).
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/cli.py`, `src/commands.py`, `src/header.py`, `src/parser.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/helpers.py`, `tests/test_*.py`, and `.github/`.
- Acceptance criteria: `build.py` outputs `tmd`, `install.sh`/`install.ps1` install `tmd` (plus any agreed compatibility alias), `--help`/rules/bundles/docs/tests reflect `todo-markdown` and `tmd`, and `python3 -m unittest discover -s tests` passes.

# ⚪ [NEW] D5: Design cohesive Quest-Log ANSI color palette and typography for RPG perks (FINAL, STAGE, COMBO), stats, roles, and statuses

- Depends on: F59 -> F60 -> F61
- Inspect `_style_task_row()` (`src/commands.py:1170-1340`) and design a composable ANSI styling scheme for TTY output (`use_color=True`) covering uppercase RPG perks (`FINAL`, `STAGE`, `COMBO`), numeric stats (`chain: N, done: D, ready: +M, unblocks: K` and chain header `[<pct>% | done: D, open: O]`), role badges (`[work]`, `[plan]`, `[design]`), and status badges.
- Render live ANSI terminal previews comparing candidate color/bold palettes and verify how token-level styling composes with existing row-level styles (`DONE` dimming, external-project dimming, and `-H` / `--highlight` emphasis) without disturbing `_wrap_table_row()` display-width calculations.

# ⚪ [NEW] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo_md -r` (`--ready`).
  - Detect target-file overlaps via `extract_task_files()` across unlinked open tasks within the same repository in `src/commands.py` to assist planners in consolidating or sequencing tasks that touch the same files.

# ⚪ [NEW] P1: JSON output mode (`--json`)

- Depends on: F62
Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F66: Active backlog tasks reference removed src/rules/todo_md.md and src/bundles/todo_md.bundle

- `D3`, `D2`, `F42`, and `F62` in `TODO.md` still list `src/rules/todo_md.md` and `src/bundles/todo_md.bundle` among their target files, but the rule now lives in `agents/todo_md.md` and the bundle file was removed.
- Impact: `todo_md files` silently skips the missing paths for these tasks, so planned work sessions will not preload the agent rule file.
