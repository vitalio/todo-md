# 🎯 [NEXT] F71: Extend discovery_session reuse to resolve_dependency_statuses, cross-project stage edges, and multi-task show/top-id queries

- Depends on: F64, F62
- In `src/dag.py` (`resolve_dependency_statuses()`), use `_workspace_root_cached(base_dir, explicit_dir=explicit_dir)` instead of `resolve_workspace_root()` and reuse `_ACTIVE_DISCOVERY.task_maps` (populating `task_maps[p_res]` via `collect_all_tasks(p_res)` on cache miss, matching `_task_map()` in `build_dependency_dag()`) so `_is_task_blocked()`, `_task_dependency_info()`, and `format_dependency_summary()` do not re-read `TODO*.md` on every call.
- In `src/dag.py` (`build_dependency_dag()`), pass `cur_dir` instead of `base_dir` to `lookup_external_alias(cur_dir, ws_resolved, proj_name)` inside `_resolve_ref()`, and key `shared.stage_edges` by `ws_resolved` instead of `(ws_resolved, disp_resolved)` so workspace views (`overview -w`, `list -w`) reuse orchestrator stage edges across all child projects within one `discovery_session()`.
- In `src/commands.py` (`resolve_top_task_id()`, `cmd_next_id()`), `src/render.py` (`cmd_show()`), and `src/cli.py` (`_show_tasks()`), wrap `resolve_top_task_id`, `cmd_next_id`, and `_show_tasks` in `discovery_session()` (`@_discovery_scoped`) and reuse `_ACTIVE_DISCOVERY.task_maps` in `cmd_show()` so multi-candidate `resolve_top_task_id()` checks and multi-ID `show` loops share cached project discovery and task maps.
- Expand `test_orchestrator_inbound_edges_in_queue_next_id_list_and_show` in `tests/test_deps.py` to assert `discovery_session` cache reuse across `resolve_dependency_statuses()`, cross-project `stage_edges`, `resolve_top_task_id()`, and multi-task `show`.
- Target files: `src/dag.py:resolve_dependency_statuses.._is_task_blocked`, `src/commands.py:resolve_top_task_id..cmd_next_id`, `src/render.py:cmd_show`, `src/cli.py:_show_tasks`, `tests/test_deps.py:test_orchestrator_inbound_edges_in_queue_next_id_list_and_show`.

# 🎯 [NEXT] B6: Keep ready NEXT tasks at the top of flat chains and dynamically re-rank unemitted subtrees in --tree

- In `_prepare_active_plan()` (`src/chains.py`), rank currently ready tasks
  (`initial_in_deg == 0`) ahead of blocked tasks within the same status and
  role ease so ready `NEXT` tasks (such as `F55`) precede blocked `NEXT` tasks
  (such as `F51`, `F16`) in `ranked_active`.
- In `build_chain_milestone_tree()` (`src/chains.py`), select the next child
  subtree from `direct_children` dynamically on each iteration after updating
  `emitted` (recomputing `_child_subtree_sort_key()` over unemitted nodes
  `u not in emitted`), so sibling branches that only shared an already-emitted
  high-priority ancestor do not retain a stale `min_pos` ahead of branches
  with remaining unemitted `NEXT`/`WIP` tasks.
- In `plan_execution_chains()` (`src/chains.py`) and `cmd_chain()`
  (`src/render_chain.py`), render default flat chains (without `--tree`) in
  priority-topological execution order (`base_display_nodes` from
  `ranked_active`, with any `--all` completed tasks ordered before their
  dependents) so lower-priority `NEW` tails of one branch never push ready or
  blocked `NEXT` tasks of a parallel branch down to the bottom of the chain,
  while preserving `chain_tree` DFS milestone grouping under `--tree` / `-t`.
- Target files: `src/chains.py:_prepare_active_plan..plan_execution_chains`,
  `src/render_chain.py:cmd_chain`,
  `tests/test_chain.py:test_root_anchored_chains_quest_momentum_also_in_and_all_done_tasks..test_flat_default_tree_flag_numbered_alignment_and_short_limit`.

# 🎯 [NEXT] P1: JSON output mode (`--json`)

- Depends on: F62 -> F71
- Add a global `--json` output flag (`HELP_GLOBAL_OPTIONS` in `src/header.py`, extracted in `src/cli.py:main()` and `_parse_quest_log_args()`) to export machine-readable JSON (`json.dumps(..., ensure_ascii=False, indent=2) + "\n"`) across read-only inspection and query commands:
  - Add `serialize_task_dict()` in `src/render.py` producing a stable task object schema: `id`, `project` (when in workspace or cross-project view), `workdir`, `status`, `emoji`, `role` (`resolve_task_role()`), `title` (stripped of heading note), `note` (heading note or `None`), `file`, `line`, `ready` (`bool`), `blocked` (`bool`), `depends_on` (`parse_task_dependencies()`), `target_files` (`extract_task_files()`), and `section`.
  - Support `--json` in `cmd_list()` and `cmd_workspace_list()` (`src/render.py`) returning a JSON array of matching task objects honoring `active|archive|all|<STATUS>`, `--role`, `-r`/`--ready`, `--limit`, and `-w`.
  - Support `--json` in `_show_tasks()`, `cmd_show()`, and `cmd_last()` (`src/cli.py`, `src/render.py`) returning a single task JSON object for one `<ID>` / `show last` or a JSON array of task objects when multiple `<ID>...` are requested.
  - Support `--json` in `cmd_ids()` (`{"highest_ids": ..., "next_free": ...}`), `cmd_projects()` (array of `{"project": ..., "path": ..., "open": ..., "archived": ...}`), and Quest-Log `cmd_chain()` (`src/render_chain.py`, returning structured `chains`, `standalone`, `next_actionable`, or role/ready task lists).
- Keep `--help` (`src/header.py`), `agents/todo_md.md`, and `README.md` in sync, and add unit tests in `tests/test_cli.py` and `tests/test_commands.py`.
- Target files: `src/header.py:HELP_GLOBAL_OPTIONS..usage_text`, `src/render.py:cmd_ids..cmd_workspace_list`, `src/render_chain.py:cmd_chain`, `src/cli.py:_parse_quest_log_args..main`, `agents/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_commands.py`.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Coordinate with `todo_flow:D4`: when a child repository belongs to a workspace orchestrator (`.todo_projects`), surface inbound orchestrator blockers in runtime `list` / `show` output (e.g. `[blocked via todo_flow:F2: ...]`) without storing cross-project `Depends on:` edges in the child `TODO.md`.
- Target files for downstream implementation: `src/dag.py`, `src/render.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `agents/todo_md.md`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Depends on: F55
- Explore and specify `-F <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo_md -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.
- Target files for downstream implementation: `src/cli.py`, `src/workspace.py`, `src/parser.py`, `src/render.py`, `src/commands.py`, `src/header.py`, `agents/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

# ⚪ [NEW] F42: Rename project to todo-markdown and CLI utility to tmd

- Rename project/repository references from `todo_md` to `todo-markdown` and CLI entrypoint from `todo_md` to `tmd` (preserving `TODO.md`/`TODO_ARCHIVE.md` task-file conventions and applying agreed env-var/alias decisions from the ecosystem rename design).
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/header.py`, `src/workspace.py`, `src/parser.py`, `src/dag.py`, `src/chains.py`, `src/render.py`, `src/render_chain.py`, `src/commands.py`, `src/bundle.py`, `src/cli.py`, `agents/todo_md.md`, `agents/todo_md_work.md`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/helpers.py`, `tests/test_*.py`, and `.github/`.
- Acceptance criteria: `build.py` outputs `tmd`, `install.sh`/`install.ps1` install `tmd` (plus any agreed compatibility alias), `--help`/rules/docs/tests reflect `todo-markdown` and `tmd`, and `python3 -m unittest discover -s tests` passes.

# ⚪ [NEW] D5: Design cohesive Quest-Log ANSI color palette and typography for RPG perks (FINAL, STAGE, COMBO), stats, roles, and statuses

- Depends on: F59 -> F60 -> F61 -> B6
- Inspect `_style_task_row()` (`src/render.py`) and `cmd_chain()` (`src/render_chain.py`) and design a composable ANSI styling scheme for TTY output (`use_color=True`) covering uppercase RPG perks (`FINAL`, `STAGE`, `COMBO`), numeric stats (`chain: N, done: D, ready: +M, unblocks: K` and chain header `[<pct>% | done: D, open: O]`), role badges (`[work]`, `[plan]`, `[design]`), and status badges.
- Render live ANSI terminal previews comparing candidate color/bold palettes and verify how token-level styling composes with existing row-level styles (`DONE` dimming, external-project dimming, and `-H` / `--highlight` emphasis) without disturbing `_wrap_table_row()` display-width calculations.

# ⚪ [NEW] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: B6
- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo_md -r` (`--ready`) in `src/chains.py` and `src/render_chain.py`.
  - Detect target-file overlaps via `extract_task_files()` (`src/parser.py`) across unlinked open tasks within the same repository in `src/chains.py` and `src/render.py` to assist planners in consolidating or sequencing tasks that touch the same files.
