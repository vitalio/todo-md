# 🎯 [NEXT] F86: Rank next-id via ready chain order across orchestrator/workspace and fix trailing-backslash inline code check

- Bump: `PATCH`
- In `cmd_next_id()` and `resolve_top_task_id()` (`src/render.py`, `src/cli.py`, `src/header.py`), rank ready tasks using `build_execution_chain_dag()` and `plan_execution_chains(..., ready_only=True)` (`src/dag.py`, `src/chains.py`) instead of scanning only the local `TODO.md` top-down, so `todo next-id` (and `todo --top`) always prints the #1 highest-priority ready task matching `todo -r -l 1`:
  - Automatically span configured `.todo_projects` when run inside an orchestrator repository (or all workspace projects when `-w` / `--workspace` is passed), printing `<project>:<ID>` for child-repository tasks (e.g. `todo-md:F85`) and bare `<ID>` for local tasks so `todo -B "$(todo next-id)" | context | run` works out of the box.
  - Honor `--prefix <P>`, `--status <S>`, and optional target `<ID>` / `<project>:<ID>` queue scoping consistently across standalone, orchestrator, and `-w` modes.
- In `_mask_section_inline_code()` (`src/parser.py`), remove the `ch == "\\"` escape branch inside open inline code spans (`open_tick_len > 0`) so valid CommonMark code spans ending with a backslash (such as `` `\` `` or `` `\\` ``) close cleanly instead of raising a false `unpaired inline backtick` error in `todo check`.
- Add unit tests in `tests/test_chain.py`, `tests/test_cli.py`, and `tests/test_parser.py`, update `README.md` and `agents/todo.md`, and rebuild `./todo` via `python3 build.py`.

# 🎯 [NEXT] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: F59 -> F60 -> F61 -> B6 -> F72 -> F83 -> D5 -> F84
- Depends on: B8
- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo -r` (`--ready`) in `src/chains.py` and `src/render_chain.py`.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Coordinate with `todo-flow:D4`: when a child repository belongs to a workspace orchestrator (`.todo_projects`), surface inbound orchestrator blockers in runtime `list` / `show` output (e.g. `[blocked via todo-flow:F2: ...]`) without storing cross-project `Depends on:` edges in the child `TODO.md`.
- Target files for downstream implementation: `src/dag.py`, `src/render.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `agents/todo.md`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Depends on: F55, F75
- Explore and specify `-F <path>` / `--file <path>` support across `todo` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.
- Target files for downstream implementation: `src/cli.py`, `src/workspace.py`, `src/parser.py`, `src/render.py`, `src/commands.py`, `src/header.py`, `agents/todo.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

# ⏸️ [HOLD] P1: JSON output mode (`--json`) — *Defer machine-readable JSON output until an external client or dashboard is needed*

- Depends on: F62 -> F71 -> F72, F78
- Add a global `--json` output flag (`HELP_GLOBAL_OPTIONS` in `src/header.py`, extracted in `src/cli.py:main()` and `_parse_quest_log_args()`) to export machine-readable JSON (`json.dumps(..., ensure_ascii=False, indent=2) + "\n"`) across read-only inspection and query commands:
  - Add `serialize_task_dict()` in `src/render.py` producing a stable task object schema: `id`, `prefix`, `project` (when in workspace or cross-project view), `workdir`, `status`, `emoji`, `title` (stripped of heading note), `note` (heading note or `None`), `file`, `line`, `ready` (`bool`), `blocked` (`bool`), `depends_on` (`parse_task_dependencies()`), and `section`.
  - Support `--json` in `cmd_list()` and `cmd_workspace_list()` (`src/render.py`) returning a JSON array of matching task objects honoring `active|archive|all|<STATUS>`, `--prefix`, `--status`, `-r`/`--ready`, `--limit`, and `-w`.
  - Support `--json` in `_show_tasks()`, `cmd_show()`, and `cmd_last()` (`src/cli.py`, `src/render.py`) returning a single task JSON object for one `<ID>` / `show last` or a JSON array of task objects when multiple `<ID>...` are requested.
  - Support `--json` in `cmd_ids()` (`{"highest_ids": ..., "next_free": ...}`), `cmd_projects()` (array of `{"project": ..., "path": ..., "open": ..., "archived": ...}`), and Quest-Log `cmd_chain()` (`src/render_chain.py`, returning structured `chains`, `standalone`, `next_actionable`, or ready task lists).
- Keep `--help` (`src/header.py`), `agents/todo.md`, and `README.md` in sync, and add unit tests in `tests/test_cli.py` and `tests/test_commands.py`.
