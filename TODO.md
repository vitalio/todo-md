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

# 🎯 [NEXT] F90: Remove legacy todo_md binary migration shims and output strings

- Depends on: F88
- Bump: `PATCH`
- Remove post-ADR-0004 legacy `todo_md` migration code across `src/`, `install.sh`, and `tests/` (retaining canonical `TODO_MD_*` environment variables):
  - `src/header.py`, `src/cli.py`, & `install.sh`: remove `LEGACY_REPO_MARKER = "todo_md-repo: vitalio/todo_md"`, `_remove_legacy_binary()`, `self_file.name == "todo_md"` target redirection in `cmd_update()`, and `todo_md` legacy binary lookup/removal in `cmd_uninstall()` and `install.sh` (updating the `mktemp` prefix in `install.sh` to `todo_install.XXXXXX`).
  - `src/render.py` & `src/render_chain.py`: replace `"No todo_md projects found under ..."` with `"No todo projects found under ..."`.
  - `tests/`: remove legacy `todo_md` binary cutover assertions in `tests/test_cli.py` and clean up stale `todo_md` / `run_block` fixture directory names and comments across `tests/test_*.py`.
- Rebuild `./todo` via `python3 build.py` and verify `python3 -m unittest` passes.

# 🎯 [NEXT] F93: Implement repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: D6
- Depends on: F88 -> F90
- Bump: `MINOR`
- Implement repo-exclusive parallel execution lanes (`Lane 1..K`, `threads: K`) and chain critical-path step metrics (`steps = max(dag_depth, max_repo_open_count)`) in `src/chains.py`, `src/render_chain.py`, and `src/render.py`:
  - **Repo-exclusive lane model (`src/chains.py`)**:
    - Group active ready tasks (and active `WIP` tasks) by resolved repository path (`proj_dir.resolve()`) in global `plan_execution_chains()` rank order.
    - Assign the top-ranked actionable task per repository (or the repository's active `WIP` task) to parallel execution lane `Lane 1..K` (`wavefront_threads = K`), and assign subsequent ready tasks in the same repository their per-repository queue position (`repo_queue_pos = 2, 3, ...`).
    - For each execution chain `comp_open`, compute `dag_depth` (longest directed open-node path length along `act_prereqs` within `comp_open`), `max_repo_open_count` (maximum open tasks belonging to a single repository in `comp_open`), and `critical_path_steps = max(dag_depth, max_repo_open_count)`.
  - **Progressive Quest-Log rendering (`src/render_chain.py`, `src/render.py`)**:
    - Overall progress header: when `wavefront_threads > 1` (multi-repository workspace/orchestrator views with parallel ready lanes), surface `🧵 <K> lanes` inside the `🟢 <ready> ready (...)` segment.
    - Chain headers: when `critical_path_steps < open_count` (indicating parallel compression within the chain), render `<pct>% · <done>/<total> · ⚡ <steps> steps · Chain <N> -> <root_ref>: <root_title>:` (omitting redundant step counts in single-lane linear chains where `steps == open_count`).
    - Ready view (`todo -r` / `--ready`): annotate each repository's primary lane task with `[🧵 Lane <1..K>]` and same-repository queued ready tasks with `[⏳ repo #<pos>]` when multiple ready tasks or multiple lanes exist.
- Update `agents/todo.md`, `README.md`, and add unit tests in `tests/test_chain.py`.

# 🎯 [NEXT] F92: Implement reverse dependency visibility (Blocks: ...) and explicit HOLD review workflow

- Depends on: D3
- Depends on: F88 -> F90
- Bump: `MINOR`
- Implement reverse dependency visibility (`Blocks: ...`) and explicit `HOLD` review support across `src/dag.py`, `src/render.py`, `src/bundle.py`, `src/header.py`, `agents/todo.md`, and `README.md`:
  - **Reverse dependency summary (`src/dag.py`, `src/render.py`)**:
    - Add `format_blocked_dependents_summary(base_dir, task_id, explicit_dir=...)` backed by the cached `build_execution_chain_dag()` in `discovery_session()`.
    - Collect open downstream dependents (excluding satisfied/terminal `DONE`, `CANCELED`, and `REVIEW` tasks) both locally and across `.todo_projects` when invoked from an orchestrator (preserving the strict one-way boundary where child repositories never scan parent directories).
    - In task cards (`--show` / `todo <ID>`, `--overview`, and full-card `-B` prompts), render `Blocks (<N> open): <ref> <emoji> [<STATUS>], ...` (or `Blocks (<N> direct, <M> transitive): <ref> <emoji> [<STATUS>], ...` when transitive open dependents exceed direct open dependents) immediately below `Dependencies (...):` (or standalone when the task has no prerequisites of its own).
    - In flat table views (`-l` / `--list`, e.g. `todo HOLD -l`), append a compact `[blocks: <ref1>, <ref2>]` suffix on `HOLD` rows that block open tasks.
  - **Explicit `HOLD` review bundle & workflow (`src/bundle.py`, `agents/todo.md`)**:
    - In `src/bundle.py`, include `HOLD` filter bundles (`todo HOLD -B`, `todo <project> HOLD -B`) among full-card bundle modes (alongside `<ID>...`, `REVIEW`, `--next`, `--last`) so `todo HOLD -B` emits every held task's full Markdown section, waiting note, `Dependencies:`, and `Blocks:` summary in the bundle prompt.
    - Document the explicit `HOLD` review contract and transition rules in `agents/todo.md` and `README.md`: promote satisfied, fully scoped tasks to `🎯 [NEXT]` (`--promote <ID> -m ...`), move satisfied unscoped tasks to `⚪ [NEW]` (`--status <ID> NEW -m ...`), or update waiting notes in place (`--status <ID> HOLD -m ...`).
- Add unit tests in `tests/test_deps.py`, `tests/test_commands.py`, and `tests/test_bundle.py`.

# 🎯 [NEXT] F91: Implement standalone task file mode (-F / --file) and automatic active/archive file creation

- Depends on: D2
- Depends on: F88 -> F90
- Bump: `MINOR`
- Implement `-F <path>` / `--file <path>` and automatic active/archive task file creation across `src/workspace.py`, `src/parser.py`, `src/dag.py`, `src/render.py`, `src/render_chain.py`, `src/commands.py`, `src/cli.py`, and `src/header.py`:
  - **Canonical file-pair resolution (`src/workspace.py`)**:
    - Without `-F`: resolve `(base_dir / "TODO.md", base_dir / "TODO_ARCHIVE.md")` under `PWD` or `-C <dir>` (`TODO_MD_CWD`).
    - With `-F <path>` / `--file <path>`: require explicit `-F` / `--file` (never guess positional `.md` arguments). If `<path>` is an existing directory (or ends with `/`), resolve `(<path>/TODO.md, <path>/TODO_ARCHIVE.md)`; if `<path>` is a file named `TODO.md` (case-insensitive), pair it with sibling `TODO_ARCHIVE.md`; for any other filename `<stem>.md` (or `<name>`), pair it with sibling `<stem>_ARCHIVE.md` (or `<name>_ARCHIVE.md`) in the same parent directory.
    - When `-F <path>` is combined with `-C <dir>` (or `TODO_MD_PROJECTS`), resolve cross-project `<project>:<ID>` dependency references against the configured `.todo_projects` registry of `-C <dir>` / `TODO_MD_PROJECTS` while reading and mutating the `-F <path>` task file pair (preserving the strict one-way discovery boundary from `F89`).
  - **Automatic file creation & archive-optional reads (`src/commands.py`, `src/parser.py`)**:
    - On first use via `--init` or `--add` (both in default directory mode and `-F <path>` mode), automatically create parent directories if needed and initialize both the active task file and its paired archive file if they do not exist yet.
    - On archiving transitions (`--done` moving a `REVIEW` / `D*` / `L*` task or `--done --archive`, and `--cancel`), automatically create the paired archive file (`TODO_ARCHIVE.md` or `<stem>_ARCHIVE.md`) beside the active file if absent and move the task section there.
    - Allow all read-only views, `--check`, and in-file mutations (`--edit`, `--append`, `--rename`, `--status`, `--promote`, and first-step `--done` transitioning to `🔎 [REVIEW]`) to succeed even when the paired archive file does not exist on disk (treating the archive as empty without creating an empty file on read-only operations).
    - Skip Git `_sync_upstream()` and `_git_commit_todo()` auto-commit hooks when operating on a `-F <path>` file outside a Git work tree or non-standard filename unless explicitly tracked.
- Update `src/header.py` (`-h` / `--help`), `agents/todo.md`, `README.md`, and add unit tests in `tests/test_cli.py`, `tests/test_parser.py`, and `tests/test_commands.py`.

# ⏸️ [HOLD] P1: JSON output mode (`--json`) — *Defer machine-readable JSON output until an external client or dashboard is needed*

- Depends on: F62 -> F71 -> F72, F78
- Add a global `--json` output flag (`HELP_GLOBAL_OPTIONS` in `src/header.py`, extracted in `src/cli.py:main()` and `_parse_quest_log_args()`) to export machine-readable JSON (`json.dumps(..., ensure_ascii=False, indent=2) + "\n"`) across read-only inspection and query commands:
  - Add `serialize_task_dict()` in `src/render.py` producing a stable task object schema: `id`, `prefix`, `project` (when in workspace or cross-project view), `workdir`, `status`, `emoji`, `title` (stripped of heading note), `note` (heading note or `None`), `file`, `line`, `ready` (`bool`), `blocked` (`bool`), `depends_on` (`parse_task_dependencies()`), and `section`.
  - Support `--json` in `cmd_list()` and `cmd_workspace_list()` (`src/render.py`) returning a JSON array of matching task objects honoring `active|archive|all|<STATUS>`, `--prefix`, `--status`, `-r`/`--ready`, `--limit`, and `-w`.
  - Support `--json` in `_show_tasks()`, `cmd_show()`, and `cmd_last()` (`src/cli.py`, `src/render.py`) returning a single task JSON object for one `<ID>` / `show last` or a JSON array of task objects when multiple `<ID>...` are requested.
  - Support `--json` in `cmd_ids()` (`{"highest_ids": ..., "next_free": ...}`), `cmd_projects()` (array of `{"project": ..., "path": ..., "open": ..., "archived": ...}`), and Quest-Log `cmd_chain()` (`src/render_chain.py`, returning structured `chains`, `standalone`, `next_actionable`, or ready task lists).
- Keep `--help` (`src/header.py`), `agents/todo.md`, and `README.md` in sync, and add unit tests in `tests/test_cli.py` and `tests/test_commands.py`.
