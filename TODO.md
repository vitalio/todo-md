# 🔵 [WIP] B2: Include inbound .todo_projects orchestrator dependencies in build_dependency_dag and align --ready (-r) ranking with top chain priority

- Fix `build_dependency_dag()` in `src/parser.py:433-645` so that when resolving dependencies for a task in a child project managed by one or more `.todo_projects` orchestrators (discovered via `discover_orchestrators_for_project()` in `src/parser.py:2029-2290`), inbound cross-project prerequisite edges declared in orchestrator task files (such as `todo_flow:D4 -> todo_md:D6` inside `todo_flow:D2`) are merged into the task's dependency DAG just as `build_execution_chain_dag()` does.
- Ensure `todo_md chain -f <ID>` / `todo_md queue <ID>` (`Next actionable:` in `cmd_chain()` in `src/commands.py:1380-1560`), `todo_md next-id <ID>` (`cmd_next_id()` in `src/commands.py:944-1010`), `_task_dependency_info()` (`cmd_list()` in `src/parser.py:646-792`), and `format_dependency_summary()` (`cmd_show()` in `src/parser.py:646-792`) all report consistent orchestrator-aware blockers and the true first unblocked actionable prerequisite (e.g., `todo_flow:D4` instead of blocked `todo_md:D6`).
- Align `--ready` (`-r`) task ranking in `plan_execution_chains()` (`src/parser.py:3078-3375`) with top chain priority (`best_chain_rank`): compute ranked `chain_entries` (`Chain 1..K`) before ordering `ready_only` tasks and include each ready task's best (minimum) parent chain index (`best_chain_rank`, ahead of local `-chain_counts`/`-done_counts`/`-unblocks`) so all ready tasks advancing `Chain 1` rank ahead of tasks belonging only to lower-ranked chains (`Chain 2..K`) without needing artificial intra-repo dependency edges.
- Update `agents/todo_md.md` (or `src/rules/todo_md.md`) and add regression tests in `tests/test_chain.py:1750-2087` and `tests/test_deps.py:1-260` covering `Next actionable:`, `next-id <ID>`, `list`, `show`, and `--ready` (`-r`) chain-priority ordering.
- Target files: `src/parser.py:433-645`, `src/parser.py:646-792`, `src/parser.py:2029-2290`, `src/parser.py:3078-3375`, `src/commands.py:944-1010`, `src/commands.py:1380-1560`, `tests/test_deps.py:1-260`, `tests/test_chain.py:1750-2087`.

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

# 🎯 [NEXT] F63: Implement context-bundle-protocol v1 producer, '- Target files:' symbol/line slice preload, and embedded agents/todo_md.md rule

- Depends on: B2
- Implement the Producer side of `context-bundle-protocol` v1 per `todo_flow` `docs/adr/0002-context-bundle-protocol-and-self-contained-producers.md`:
  - Move `src/rules/todo_md.md` to `agents/todo_md.md`, delete `src/bundles/todo_md.bundle`, remove all role-specific prompts (`Mode: DESIGN/PLANNING/WORK/REVIEW`), and embed `agents/todo_md.md` into `src/header.py` (`EMBEDDED_RULE_TODO_MD`) via `build.py` (with source-tree fallback to `agents/todo_md.md` in `get_embedded_todo_rule()`).
  - Restrict `extract_task_files()` (`src/commands.py:1060-1102`) to parse backticked specs strictly from `- Target files:` bullet lines in the task section (returning an empty list when no `- Target files:` line is present so incidental mentions like `TODO.md` in prose are never preloaded):
    - Support drift-proof symbol slices `path:symbol` and `path:start_symbol..end_symbol` alongside numeric `path:start-end` slices, dynamically resolving `def`/`class`/top-level symbol spans on disk into current 1-based `path:start-end` ranges at `todo_md files` / `todo_md <ID>` runtime so parallel or out-of-order task edits never invalidate slices.
    - Normalize multiple specs for the same file by dropping slices when the whole file is listed and merging overlapping or contained `start-end` ranges.
  - Add `--bundle` (`TODO_MD_BUNDLE=1`), `--plain` (`TODO_MD_PLAIN=1`), `--no-files`, and `--no-wip` flags; auto-detect bundle protocol emission on `todo_md <ID>` (`show <ID>`, `last`), `todo_md [-w]`, and `todo_md overview [--full] [-w]` when `sys.stdout` is a FIFO pipe (`stat.S_ISFIFO`) and its `st_dev:st_ino` does not match `RUN_BLOCK_STEP_STDOUT_INO` (and when `IN_RUN_BLOCK=1` is set without `RUN_BLOCK_STEP_STDOUT_INO`, emit plain step output unless `--bundle` is passed).
  - Session start `WIP` transition in bundle mode: when `todo_md <ID>` emits a `context-bundle-protocol` stream for a single active task in `TODO.md` whose resolved role is `work` or `design` (`NEXT` tasks and `D*` tasks in `NEW` or `NEXT`) and whose status is not yet `WIP` (unless `--no-wip` is passed), automatically transition that task to `🔵 [WIP]` on disk before rendering the `"task"` fragment so the active session is immediately visible as `WIP`. Plain TTY/step calls, `--no-wip`, archived tasks, and `NEW` non-`D` tasks (`role=plan`) do not mutate status on disk.
  - In bundle mode, emit `Bundle-Protocol: 1`, `Bundle-Command`, `Bundle-Boundary: <nonce>`, `Bundle-Expose: Role, Task, Title`, context headers (`Task`, `Title`, `Role`, `Workdir`), `===== Rules =====` containing `{"kind": "rule", "id": "todo_md:todo_md", "chain": ["todo_md"]}`, preloaded `{"kind": "include", "name": "<rel_path>[:<start>-<end>]", "chain": ["todo_md"]}` fragments for `- Target files:` entries within default size budgets (`<= 400` lines per file/slice, `<= 1200` total lines, `<= 32768` bytes; skipped when `--no-files` is passed), and `===== Prompt =====` containing `{"kind": "task", "id": "<ID>", "name": "<file>:<ID>", "chain": ["todo_md"]}` (or `{"kind": "context", "name": "todo_md", "chain": ["todo_md"]}`).
  - Update `agents/todo_md.md` to document the `- Target files:` contract (`path:symbol`, `path:sym1..sym2`, and `path:start-end` slices for files `> 400` lines; omitting `TODO*.md`/`AGENTS.md`), automatic `WIP` transition on bundle session start for `work` and `design` tasks, and running `todo_md done <ID>` inside the final commit step.
- Target files: `src/header.py`, `src/commands.py:1025-1155`, `src/cli.py:379-759`, `agents/todo_md.md`, `build.py`, `README.md`, `tests/helpers.py`, `tests/test_parser.py:245-305`, `tests/test_commands.py:190-235`, `tests/test_commands.py:655-729`, `tests/test_cli.py:1-260`.

# 🎯 [NEXT] F62: Decompose monolithic src/parser.py and src/commands.py into focused domain modules

- Depends on: B2, B3, F57, F63
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
