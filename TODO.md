# 🎯 [NEXT] B14: Fix missing-project refs, TODO_MD_PROJECTS scoping, -C/-p unblocks, and unused F89 helpers

- Depends on: F89
- Bump: `PATCH`
- In `src/dag.py` (`build_dependency_dag()`, `build_execution_chain_dag()`), format unresolved `<project>:<ID>` references (`__missing_project__`) as `<project>:<ID>` rather than leaking `__missing_project__/<project>:<ID>` or `<orch>/__missing_project__/<project>:<ID>` in `chain`, `next-id`, `list`, and `stderr` diagnostics.
- In `src/workspace.py` and `src/parser.py`, scope `TODO_MD_PROJECTS` environment resolution strictly to the active root target directory (when `explicit_dir` is not overriding it or when `TODO_MD_PROJECTS` points to a file in `base_dir`) so child repositories validated during `todo -w --check` or targeted via `-C <child>` / `-p <child>` do not inherit orchestrator status from `TODO_MD_PROJECTS`.
- In `src/dag.py` and `src/commands.py`, pass the active command `base_dir` / `explicit_dir` into `find_newly_unblocked_tasks()` on `todo --done` instead of probing `resolve_target_dir(None)` (`Path.cwd()`), so `-C <orch> --done <child>:<ID>` reports orchestrator unblocks while `-C <child> --done <ID>` from an orchestrator working directory stays isolated to `<child>`.
- Clean up dead/unused leftovers from `F89`: remove unused `resolve_project_or_dir()` and `_resolve_todo_project_entry()` in `src/workspace.py` (routing `_rewrite_project_tasks_and_deps()` in `src/commands.py` through `lookup_external_alias()` when `has_todo_projects_config(t_res)` is true), and drop unused `task` parameter on `format_dependency_summary()` in `src/render.py` and unused `ws_root` parameter on `is_orchestrator_project()` in `src/workspace.py`.
- Update unit tests in `tests/test_chain.py`, `tests/test_deps.py`, `tests/test_commands.py`, and `tests/test_cli.py`, and rebuild `./todo` via `python3 build.py`.

# 🎯 [NEXT] F88: Redesign CLI around positional filters, -f/--focused dimming, bold-yellow -s search, --<cmd> flags, REVIEW status, and multi-task -B bundles

- Depends on: B14
- Bump: `MINOR`
- Redesign the `todo` CLI contract across `src/cli.py`, `src/header.py`, `src/parser.py`, `src/dag.py`, `src/chains.py`, `src/render.py`, `src/render_chain.py`, `src/commands.py`, and `src/bundle.py`:
  - **`--<command>` flag contract & removal of bare subcommands**:
    - Require `--` for all action and metadata commands: `--show`, `-l` / `--list` (moving row limit to `-n N` / `--limit N`), `--overview`, `--projects`, `--ids`, `--next-id`, `--next`, `--last-id`, `--last`, `--add`, `--edit`, `--append`, `--rename`, `--status`, `--promote` (replacing mutating `todo next <ID>...` to promote tasks to `🎯 [NEXT]`), `--done`, `--cancel`, `--reopen`, `--check`, `--init`, `--update [--check | --force]`, `--uninstall`, `-V` / `--version`, `-h` / `--help`.
    - Completely forbid legacy bare positional command names (`add`, `edit`, `list`, `show`, `done`, `check`, etc., exiting `2` with a `did you mean '--<cmd>'?` hint) and remove obsolete subcommands/flags `chain`, `queue`, `search`, `top`, `check-update`, `--self-update`, and `-H` / `--highlight`.
  - **Positional selectors (`todo [PROJECT|ID|STATUS...]`) & orthogonal view modes**:
    - Any positional arguments without `--` act as combinable filters: `<project>` (from `.todo_projects`), `<ID>` / `<project>:<ID>`, and `<STATUS>` (`WIP`, `NEXT`, `QUESTION`, `NEW`, `HOLD`, `REVIEW`, `DONE`, `CANCELED`; drop synthetic positional status keywords `ACTIVE`, `ARCHIVE`, `ALL` in favor of default active scope and `--archive` / `--all` scope flags).
    - Bare `todo <ID>...` (without `-f` / `--focused` or view flags `-t` / `--tree`, `-l` / `--list`, `--overview`) renders the full task card (`--show <ID>...`).
    - View modes apply the same filter, focus (`-f`), and search (`-s`) rules: Quest-Log flat (default, active `TODO.md` tasks only), Quest-Log tree (`-t` / `--tree`, active `TODO.md` tasks only), flat status table (`-l` / `--list`, auto-selected when filtering `REVIEW`, `DONE`, `CANCELED`, or `--archive` without `--overview`), and Markdown sections (`--overview` / `--full`).
    - Scope & filter modifiers: active `TODO.md` tasks by default, `--archive` (`TODO_ARCHIVE.md` only), `--all` (`TODO.md` + `TODO_ARCHIVE.md`), `-r` / `--ready` (ready-only filter), `--prefix <P>`, `--include-hold`, `-n N` / `--limit N`, and `--numbered[=left|right]`.
  - **Contextual focus (`-f` / `--focused` / `--focus`)**:
    - Without `-f`, render only tasks/chains matching the active filter (`todo run-block` shows only `run-block` tasks; `todo -s query` shows only matching tasks).
    - With `-f` (`--focused`), render the full view (all projects/chains/rows in scope) with matched filter/search tasks in normal (white/colored) styling and all non-matching projects/tasks dimmed in gray (`\033[2;3m` / `\033[2m`): `todo run-block -f` shows `run-block` tasks in white and other projects in gray; `todo run-block:F108 -f` shows `run-block:F108` in white and all other tasks in gray (plus `Next actionable: <ref>` when focusing a single task ID); in orchestrator default view (`todo` with no project filter), all `.todo_projects` tasks render un-dimmed.
  - **In-filter search (`-s` / `--search <QUERY>`) with bold-yellow match highlighting**:
    - Search within the active project/task/status/scope filter (including inside a single task card `todo F108 -s <QUERY>`), highlighting only the matched substrings in **bold yellow (`\033[1;93m`)** while preserving row/card styling (and combining with `-f` so non-matching rows dim to gray while matched rows stay white with bold-yellow match spans).
  - **Twin query commands (`--next-id` / `--next` and `--last-id` / `--last`)**:
    - Support all positional/flag filters on `--next-id` (prints #1 ready task ID in chain order within filter) and `--next` (prints full task card for that task), as well as `--last-id` (prints top/most recent task ID matching filter, e.g. `todo WIP --last-id`, `todo run-block DONE --last-id`, `todo REVIEW --last-id`) and `--last` (prints full task card for that task).
  - **`🔎 [REVIEW]` status lifecycle, archive completion dates, badge colors & `SIGPIPE` handling**:
    - Add `🔎 [REVIEW]` at the bottom of `ACTIVE_STATUS_ORDER` in `TODO.md` (`WIP -> NEXT -> QUESTION -> NEW -> HOLD -> REVIEW`). Treat `REVIEW` tasks as satisfied prerequisites in DAG dependency resolution (unblocking downstream tasks immediately) and exclude them from active Quest-Log chains while surfacing `🔎 <N> review` in the overall Quest-Log progress header when `N > 0`.
    - `todo --done <ID>...` transitions active non-`D*`/`L*` tasks in `TODO.md` to `🔎 [REVIEW]` without adding a completion date in `TODO.md` (unless `--archive` is passed), while `todo --done <ID>...` on `REVIEW` tasks (or `D*`/`L*` tasks, or `todo --done REVIEW`) moves them to `TODO_ARCHIVE.md` as `✅ [DONE]`.
    - Automatically prepend the `YYYY-MM-DD` archive date (`— *YYYY-MM-DD[, <note>]*`) for both `✅ [DONE]` and `❌ [CANCELED]` when archiving to `TODO_ARCHIVE.md` (keeping `TODO.md` headings free of completion dates).
    - Color `✅ DONE` status badges green (`\033[32m`) and `❌ CANCELED` status badges/rows red (`\033[31m` / `\033[2;31m`), and catch `BrokenPipeError` cleanly in `main()` when piped to `head`.
  - **Universal multi-task bundle assembly (`-B` / `--bundle`)**:
    - Support `-B` / `--bundle` across any filter (`todo <ID>... -B`, `todo REVIEW -B`, `todo <project> REVIEW -B`, `todo --next -B`, `todo --last -B`, `todo <filter> -B`): auto-resolve `Workdir` to the target project directory when all matched tasks belong to one project, emit `Task: <ID1>,<ID2>,...`, emit `Prefix: <P>` and `Status: <S>` when uniform across matched tasks (so `todo REVIEW -B` emits `Status: REVIEW`), and render full task cards in the bundle prompt for `<ID>...`, `REVIEW`, `--next`, and `--last`.
  - **Grouped `-h` / `--help` layout & docs sync**:
    - Update `src/header.py` (`usage_text()`) to group `--<cmd>` signatures into `View & Search Commands:`, `Task Lifecycle Commands:`, and `Repository & System Commands:` with a unified shared description column (`HELP_MAX_LEFT`), and update `agents/todo.md`, `README.md`, `AGENTS.md`, and `tests/test_*.py`.

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Depends on: F55, F75
- Depends on: F89 -> B14
- Explore and specify `-F <path>` / `--file <path>` support across `todo` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.
- Target files for downstream implementation: `src/cli.py`, `src/workspace.py`, `src/parser.py`, `src/render.py`, `src/commands.py`, `src/header.py`, `agents/todo.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Depends on: F89 -> B14
- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references when run from an orchestrator with `.todo_projects`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Preserve the strict one-way dependency boundary (`todo-flow/docs/adr/0005-orchestrator-standard-and-dependency-boundaries.md`): child repositories remain self-contained without scanning parent directories for enclosing orchestrators; cross-project reverse dependency visibility (`Blocks: ...`) is surfaced when inspecting from the orchestrator repository.
- Target files for downstream implementation: `src/dag.py`, `src/render.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `agents/todo.md`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

# 🎯 [NEXT] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: F59 -> F60 -> F61 -> B6 -> F72 -> F83 -> D5 -> F84
- Depends on: B8
- Depends on: F89 -> B14
- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo -r` (`--ready`) in `src/chains.py` and `src/render_chain.py`.

# 🎯 [NEXT] F90: Remove legacy todo_md binary migration shims and output strings

- Depends on: F88
- Bump: `PATCH`
- Remove post-ADR-0004 legacy `todo_md` migration code across `src/`, `install.sh`, and `tests/` (retaining canonical `TODO_MD_*` environment variables):
  - `src/header.py`, `src/cli.py`, & `install.sh`: remove `LEGACY_REPO_MARKER = "todo_md-repo: vitalio/todo_md"`, `_remove_legacy_binary()`, `self_file.name == "todo_md"` target redirection in `cmd_update()`, and `todo_md` legacy binary lookup/removal in `cmd_uninstall()` and `install.sh` (updating the `mktemp` prefix in `install.sh` to `todo_install.XXXXXX`).
  - `src/render.py` & `src/render_chain.py`: replace `"No todo_md projects found under ..."` with `"No todo projects found under ..."`.
  - `tests/`: remove legacy `todo_md` binary cutover assertions in `tests/test_cli.py` and clean up stale `todo_md` / `run_block` fixture directory names and comments across `tests/test_*.py`.
- Rebuild `./todo` via `python3 build.py` and verify `python3 -m unittest` passes.

# ⏸️ [HOLD] P1: JSON output mode (`--json`) — *Defer machine-readable JSON output until an external client or dashboard is needed*

- Depends on: F62 -> F71 -> F72, F78
- Add a global `--json` output flag (`HELP_GLOBAL_OPTIONS` in `src/header.py`, extracted in `src/cli.py:main()` and `_parse_quest_log_args()`) to export machine-readable JSON (`json.dumps(..., ensure_ascii=False, indent=2) + "\n"`) across read-only inspection and query commands:
  - Add `serialize_task_dict()` in `src/render.py` producing a stable task object schema: `id`, `prefix`, `project` (when in workspace or cross-project view), `workdir`, `status`, `emoji`, `title` (stripped of heading note), `note` (heading note or `None`), `file`, `line`, `ready` (`bool`), `blocked` (`bool`), `depends_on` (`parse_task_dependencies()`), and `section`.
  - Support `--json` in `cmd_list()` and `cmd_workspace_list()` (`src/render.py`) returning a JSON array of matching task objects honoring `active|archive|all|<STATUS>`, `--prefix`, `--status`, `-r`/`--ready`, `--limit`, and `-w`.
  - Support `--json` in `_show_tasks()`, `cmd_show()`, and `cmd_last()` (`src/cli.py`, `src/render.py`) returning a single task JSON object for one `<ID>` / `show last` or a JSON array of task objects when multiple `<ID>...` are requested.
  - Support `--json` in `cmd_ids()` (`{"highest_ids": ..., "next_free": ...}`), `cmd_projects()` (array of `{"project": ..., "path": ..., "open": ..., "archived": ...}`), and Quest-Log `cmd_chain()` (`src/render_chain.py`, returning structured `chains`, `standalone`, `next_actionable`, or ready task lists).
- Keep `--help` (`src/header.py`), `agents/todo.md`, and `README.md` in sync, and add unit tests in `tests/test_cli.py` and `tests/test_commands.py`.
