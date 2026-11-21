# 🎯 [NEXT] B3: Scope Sub-chain milestone stats and subtree_nodes to rendered subtree tasks in build_chain_milestone_tree

- Fix `build_chain_milestone_tree()` in `src/parser.py` (`src/parser.py:2852-3070`) so that for each `Sub-chain ->` node (`is_root=False`), `done_count`, `open_count`, `total_tasks`, `progress_pct`, and `subtree_nodes` are computed exclusively from the tasks actually rendered inside that sub-chain's subtree rather than the milestone's full unfiltered transitive cone:
  - When a shared prerequisite branch (such as `D1` or `D6`) has already been emitted in an earlier sibling sub-chain of the same root `Chain`, exclude already-emitted open tasks and their already-claimed `DONE` prerequisites from subsequent sibling `Sub-chain` header stats (`[pct% | done: D, open: O]` / `[open: O]`) so header counts match the tasks displayed under that `Sub-chain` (both with and without `--all`).
  - Scope `subtree_nodes` on each `Sub-chain` node (`src/parser.py:2943-2990`, used by `_render_chain_tree_children()` in `src/commands.py:1645-1675`) to the tasks actually rendered inside that sub-chain so `--filter` / `-f` and `--highlight` / `-H` do not highlight unrelated sibling `Sub-chain` headers whose only connection to the target task was an already-emitted shared prerequisite above.
- Add regression tests in `tests/test_chain.py` covering `--tree` and `--tree --all` (plus `-f` highlighting) on a diamond/shared-prerequisite DAG where two sibling sub-chains depend on a common sub-chain with completed tasks.

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

# 🎯 [NEXT] F56: Format and align -h/--help output with structured Usage/Commands/Options sections and <=100-col lines

- Depends on: F44
- In `src/header.py`, split the top-level `Usage:` block into a concise `Usage:` summary and a dedicated `Commands:` section followed by `Global options:`, `Quest-Log options:`, `Files:`, and `Environment variables:`.
- Align all description columns and continuation lines against the rendered binary name (`todo_md`, accounting for `{prog}` length replacement) so continuation lines (`Opts: ...`, multi-line descriptions) start at the exact same column as primary descriptions.
- Wrap all `--help` lines to at most 100 columns (and prose paragraphs to ~80 columns) and omit the redundant `queue` alias from `--help` (keeping `queue` accepted in `src/cli.py` for backward compatibility).
- Add a unit test in `tests/test_cli.py` verifying that `todo_md --help` has aligned description columns and no lines exceeding 100 characters, update `README.md` if needed, rebuild via `build.py`, and bump `VERSION` for a PATCH release.

# 🎯 [NEXT] F57: Support glob path patterns and line-range slices (path:start-end) in todo_md files (extract_task_files and cmd_files)

- Depends on: F56
- In `extract_task_files()` (`src/commands.py:1005-1095`), support both glob patterns and line-range suffixes on backticked repository file references:
  - Line-range suffixes: parse trailing `:start-end`, `:line`, or `#Lstart-Lend` / `#Lline` (1-based inclusive line numbers, normalizing to `rel_path:start-end` when a range or single line is given) instead of stripping and discarding line numbers, and reject tokens where the suffix after `:` is not a valid line number/range (so cross-project task refs like `todo_md:D5` are never stripped to the compiled `todo_md` binary in repo root); deduplicate by the full `rel_path` or `rel_path:start-end` spec so multiple distinct slices of a large file can be emitted.
  - Glob patterns: allow `*`, `?`, and `[` in relative path tokens without line ranges when the token contains a path separator `/` or file extension `.` (ignoring bare prefix tokens like `D*` or `*`) and no `..` traversal segments, expanding `sorted(repo_root.glob(cand))` into matching regular files inside `repo_root` (skipping `.git` and `__pycache__`).
- In `cmd_files()` (`src/commands.py:1040-1095`), when an item specifies `:start-end`, evaluate `--max-lines`, `--max-total-lines`, `--max-bytes`, and `--max-total-bytes` against the sliced lines (`lines[start - 1 : end]`) rather than the entire file so inspected sections of large files fit within bundle size budgets, and print `rel_path:start-end` to `stdout`.
- Update `src/header.py`, `src/rules/todo_md.md` (documenting that planners record `path:start-end` line ranges for large inspected files when promoting a task to `NEXT` for `role=work`), `README.md`, and unit tests in `tests/test_commands.py`, rebuild via `build.py`, and bump `VERSION` for a MINOR release.

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

# ⚪ [NEW] B2: Include inbound .todo_projects orchestrator dependencies in build_dependency_dag (Next actionable, next-id, list, and show)

- Fix `build_dependency_dag()` in `src/parser.py` so that when resolving dependencies for a task in a child project managed by one or more `.todo_projects` orchestrators (discovered via `discover_orchestrators_for_project()`), inbound cross-project prerequisite edges declared in orchestrator `TODO.md` files (such as `todo_flow:D4 -> todo_md:D6` inside `todo_flow:D2`) are merged into the task's dependency DAG just as `build_execution_chain_dag()` does.
- Ensure `todo_md chain -f <ID>` / `todo_md queue <ID>` (`Next actionable:` in `cmd_chain()` in `src/commands.py`), `todo_md next-id <ID>` (`cmd_next_id()` in `src/commands.py`), `_task_dependency_info()` (`cmd_list()` in `src/parser.py`), and `format_dependency_summary()` (`cmd_show()` in `src/parser.py`) all report consistent orchestrator-aware blockers and the true first unblocked actionable prerequisite (e.g., `todo_flow:D6` instead of blocked `todo_md:D6`).
- Add regression tests in `tests/test_chain.py` and `tests/test_deps.py` covering `Next actionable:`, `next-id <ID>`, `list`, and `show` for child tasks blocked exclusively via an orchestrator's sequential `- Depends on: <orch_task> -> <child>:<ID>` clause.

# ⚪ [NEW] F62: Decompose monolithic src/parser.py and src/commands.py into focused domain modules

- Depends on: B2, B3, F57
- Refactor `src/parser.py` (3,600+ lines) and `src/commands.py` (1,700+ lines) into cohesive domain modules (~300-800 lines each) with clean layer boundaries:
  - `src/header.py`: imports, constants, regular expressions, `prog_name()`, and `usage_text()`.
  - `src/workspace.py`: project and workspace root resolution (`is_todo_project()`, `resolve_target_dir()`, `resolve_workspace_root()`, `discover_projects()`, `project_label()`, `.todo_projects` and nested orchestrator discovery `read_configured_todo_projects()`, `is_orchestrator_project()`, `discover_orchestrators_for_project()`).
  - `src/parser.py`: Markdown section parsing (`parse_tasks_in_text()`, `collect_all_tasks()`), dependency clause syntax parsing (`parse_depends_clause()`, `parse_dependency_clauses()`), role resolution (`resolve_task_role()`), file extraction (`extract_task_files()`), search (`search_tasks()`), and file validation (`validate_all()`).
  - `src/dag.py`: unified dependency DAG construction and chain planning/ranking (`build_dependency_dag()`, `build_execution_chain_dag()`, `compute_unblock_counts()`, `build_chain_milestone_tree()`, `plan_execution_chains()`, `plan_execution_chains_by_role()`, `find_newly_unblocked_tasks()`).
  - `src/render.py`: terminal display width, ANSI styling, table wrapping (`_display_width()`, `_style_task_row()`, `_wrap_table_row()`), and read-only view renderers (`cmd_chain()`, `cmd_list()`, `cmd_show()`, `cmd_summary()`, `cmd_projects()`, `cmd_workspace_summary()`, `cmd_workspace_list()`, `cmd_workspace_check()`).
  - `src/commands.py`: backlog file sorting, Git auto-commit helpers, and mutating/query CLI commands (`cmd_check()`, `cmd_init()`, `cmd_add()`, `cmd_edit()`, `cmd_append()`, `cmd_transition()`, `cmd_reopen()`, `cmd_next_id()`, `cmd_files()`).
  - `src/cli.py`: self-update commands (`cmd_check_update()`, `cmd_update()`), CLI argument parsing (`_parse_quest_log_args()`), and `main()`.
- Update `MODULE_ORDER` in `build.py`, regenerate standalone `./todo_md`, align `AGENTS.md` module descriptions, and verify all unit tests in `tests/test_*.py` pass without behavioral regressions.

# ⚪ [NEW] P1: JSON output mode (`--json`)

- Depends on: F62
Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F63: Implement context-bundle-protocol v1 producer, embedded agents/todo_md.md rule, and curated file/slice includes

- Depends on: F62
- Implement the Producer side of `context-bundle-protocol` v1 per `todo_flow` `docs/adr/0002-context-bundle-protocol-and-self-contained-producers.md`:
  - Move `src/rules/todo_md.md` to `agents/todo_md.md`, delete `src/bundles/todo_md.bundle`, remove all role-specific prompts (`Mode: DESIGN/PLANNING/WORK/REVIEW`), and embed `agents/todo_md.md` into `src/header.py` (`EMBEDDED_RULE_TODO_MD`) via `build.py` (with source-tree fallback to `agents/todo_md.md` in `get_embedded_todo_rule()`).
  - Add `--bundle` (`TODO_MD_BUNDLE=1`), `--plain` (`TODO_MD_PLAIN=1`), and `--no-files` flags; auto-detect bundle protocol emission on `todo_md <ID>` (`show <ID>`, `last`), `todo_md [-w]`, and `todo_md overview [--full] [-w]` when `sys.stdout` is a FIFO pipe (`stat.S_ISFIFO`) and its `st_dev:st_ino` does not match `RUN_BLOCK_STEP_STDOUT_INO` (and when `IN_RUN_BLOCK=1` is set without `RUN_BLOCK_STEP_STDOUT_INO`, emit plain step output unless `--bundle` is passed).
  - In bundle mode, emit `Bundle-Protocol: 1`, `Bundle-Command`, `Bundle-Boundary: <nonce>`, `Bundle-Expose: Role, Task, Title`, context headers (`Task`, `Title`, `Role`, `Workdir`), `===== Rules =====` containing `{"kind": "rule", "id": "todo_md:todo_md", "chain": ["todo_md"]}`, preloaded `{"kind": "include", "name": "<rel_path>[:<start>-<end>]", "chain": ["todo_md"]}` fragments for backticked files and `path:start-end` slices within default size budgets (`<= 400` lines per file/slice, `<= 1200` total lines, `<= 32768` bytes; skipped when `--no-files` is passed), and `===== Prompt =====` containing `{"kind": "task", "id": "<ID>", "name": "<file>:<ID>", "chain": ["todo_md"]}` (or `{"kind": "context", "name": "todo_md", "chain": ["todo_md"]}`).
  - Update `agents/todo_md.md` to document the two-tier task-detail contract (`NEW` backlog tasks use file paths and symbol names in backticks; `NEXT` tasks promoted by `role=plan` include `path:start-end` slices for files `> 400` lines) and instruct `role=work` to run `todo_md status <ID> WIP` in step 1 when starting a `NEXT` task and `todo_md done <ID>` inside the final commit step.
  - Target files: `src/header.py`, `src/parser.py`, `src/render.py`, `src/commands.py`, `src/cli.py`, `agents/todo_md.md`, `build.py`, `AGENTS.md`, `README.md`, `tests/helpers.py`, `tests/test_cli.py`, `tests/test_commands.py`.
