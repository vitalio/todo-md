# 🎯 [NEXT] F80: Support <alias>=<path> project mapping in .todo_projects and .todo_projects.local

- Allow entries in `.todo_projects` and `.todo_projects.local` to map a canonical project identifier to a local relative or external directory path (`<project_id>=<path>`), so `Depends on: <project_id>:<ID>` in an orchestrator's `TODO.md` resolves cleanly even when a local checkout directory has a different name or location.
- Scope `todo projects` inside an orchestrator repository (when `.todo_projects` or `.todo_projects.local` is present) strictly to the orchestrator's managed projects (plus the orchestrator itself) rather than all sibling directories in the parent workspace, and display each project's resolved directory path so `cmd todo projects` in `.context.bundle` provides an unambiguous workspace map.
- Remove the `IDs in use: ... (next free: ...)` footer from `todo show` and `todo list` output (and remove `todo ids` from embedded `agents/todo.md`) so inspection output stays focused and never tempts agents to pre-guess future task IDs before running `todo add`.
- Update embedded `agents/todo.md` to: (1) define the status readiness contract (`NEW` for unscoped tasks needing planning, `NEXT` for scoped tasks ready for execution, `WIP` for active work, `QUESTION` for tasks blocked on clarification, `HOLD` for deferred items); (2) state that `todo add` auto-assigns and prints the new `<ID>` (wire dependent tasks using the ID printed by `todo add`); (3) warn that because `,` binds tighter than `->`, `"X, A -> B, Y"` parses as `"(X, A) -> (B, Y)"` so a sequential chain alongside parallel items must be separated with `;` (`"X, Y; A -> B"`); and (4) note that `todo projects` resolves workspace project names and aliases to physical directory paths.

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

# ⚪ [NEW] D5: Design cohesive Quest-Log ANSI color palette and typography for RPG perks (FINAL, STAGE, COMBO), stats, prefixes, and statuses

- Depends on: F59 -> F60 -> F61 -> B6 -> F72 -> F83
- Inspect `_style_task_row()` (`src/render.py`) and `cmd_chain()` (`src/render_chain.py`) and design a composable ANSI styling scheme for TTY output (`use_color=True`) covering uppercase RPG perks (`FINAL`, `STAGE`, `COMBO`), numeric stats (`chain: N, done: D, ready: +M, unblocks: K` and leading chain/sub-chain header stats `<pct>% | <done>/<total> |`), task ID prefixes, and status badges.
- Render live ANSI terminal previews comparing candidate color/bold palettes and verify how token-level styling composes with existing row-level styles (`DONE` dimming, external-project dimming, and `-H` / `--highlight` emphasis) without disturbing `_wrap_table_row()` display-width calculations.

# ⚪ [NEW] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: F59 -> F60 -> F61 -> B6 -> F72 -> F83 -> D5
- Depends on: B8
- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo -r` (`--ready`) in `src/chains.py` and `src/render_chain.py`.

# ⚪ [NEW] F82: Restructure README.md to follow CLI progressive disclosure and split Quest-Log, Options, and Environment tables

- Depends on: F83
- Add a short Quest-Log and dependency (`--depends`, `todo -r`, `todo -t`, `todo -f`) scenario to `Quick Start`.
- Replace the 3,160-character single-row `todo chain` table cell and leading `git pull --ff-only` edge-case paragraph in `CLI Reference` with a dedicated `Quest-Log Views` overview plus separate `Commands`, `Global & Quest-Log Options` (including `--no-commit`), and `Environment` (`TODO_MD_*`) tables matching `todo --help` and `agents/stack/cli/docs.md`.
- Replace stale `todo <ID> | agents_bundle | run_block` pipeline example in the `todo show` row with `todo <ID> | context | run`, and format the `License` section link consistently with sibling repositories.

# ⏸️ [HOLD] P1: JSON output mode (`--json`) — *Defer machine-readable JSON output until an external client or dashboard is needed*

- Depends on: F62 -> F71 -> F72, F78
- Add a global `--json` output flag (`HELP_GLOBAL_OPTIONS` in `src/header.py`, extracted in `src/cli.py:main()` and `_parse_quest_log_args()`) to export machine-readable JSON (`json.dumps(..., ensure_ascii=False, indent=2) + "\n"`) across read-only inspection and query commands:
  - Add `serialize_task_dict()` in `src/render.py` producing a stable task object schema: `id`, `prefix`, `project` (when in workspace or cross-project view), `workdir`, `status`, `emoji`, `title` (stripped of heading note), `note` (heading note or `None`), `file`, `line`, `ready` (`bool`), `blocked` (`bool`), `depends_on` (`parse_task_dependencies()`), and `section`.
  - Support `--json` in `cmd_list()` and `cmd_workspace_list()` (`src/render.py`) returning a JSON array of matching task objects honoring `active|archive|all|<STATUS>`, `--prefix`, `--status`, `-r`/`--ready`, `--limit`, and `-w`.
  - Support `--json` in `_show_tasks()`, `cmd_show()`, and `cmd_last()` (`src/cli.py`, `src/render.py`) returning a single task JSON object for one `<ID>` / `show last` or a JSON array of task objects when multiple `<ID>...` are requested.
  - Support `--json` in `cmd_ids()` (`{"highest_ids": ..., "next_free": ...}`), `cmd_projects()` (array of `{"project": ..., "path": ..., "open": ..., "archived": ...}`), and Quest-Log `cmd_chain()` (`src/render_chain.py`, returning structured `chains`, `standalone`, `next_actionable`, or ready task lists).
- Keep `--help` (`src/header.py`), `agents/todo.md`, and `README.md` in sync, and add unit tests in `tests/test_cli.py` and `tests/test_commands.py`.
