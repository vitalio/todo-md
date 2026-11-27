# 🎯 [NEXT] F88: Fold check-update into update [--check | --force], group todo -h commands, compact [opts] signatures, and unify cross-section description column

- Bump: `MINOR`
- Fold `check-update` / `--check-update` and `--self-update` into `todo update [--check | --force]` (and `--update [--check | --force]`) in `src/cli.py` and `src/header.py` per `agents/cli/lifecycle.md`:
  - Remove `"check-update"` from `KNOWN_SUBCOMMANDS` and top-level dispatch, remove the undocumented `--self-update` alias, and support `--check` and `--force` under `update` / `--update` (rejecting unknown options or combined `--check` + `--force` with exit status `2`).
- Update `src/header.py` (`HELP_COMMANDS`, `HELP_GLOBAL_OPTIONS`, `_help_table()`, `usage_text()`) to conform to the refined `agents/cli/help.md` layout contract:
  - Split `HELP_COMMANDS` into 3 thematic sections (`View & Search Commands:`, `Task Lifecycle Commands:`, `Repository & System Commands:`) and drop the repeated `{prog} ` prefix from subcommand rows (`Usage:` already shows `{prog}` invocation templates; mention bare `todo <ID>...` in `show <ID>...`, and list `update [--check | --force]` under `Repository & System Commands:`).
  - Compact overlong left-column command signatures (`archive [<ID>...] [opts]`, `rename <OLD> <NEW|P>...`, `next <ID>... [opts]`, `next-id [<ID>|--top] [opts]`) and move their command-specific flags into the right-hand description so the shared description column sits around column 34-36 (`>= 64` columns for descriptions).
  - Move `-V, --version` and `-h, --help` from `Commands:` to the end of `Global options:`, and rename `Environment variables:` to `Environment:`.
  - Compute one shared description column `col` across all tabular sections in `usage_text()` (capped by a `HELP_MAX_LEFT` budget with wrapped/overflow handling when a custom `prog_name()` exceeds the budget) so the right-hand description column never jumps horizontally between sections.
- Update `tests/test_cli.py`, `README.md`, `AGENTS.md`, and `agents/todo.md`, rebuild `./todo` via `python3 build.py`, and run `python3 -m unittest`.

# 🎯 [NEXT] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: F59 -> F60 -> F61 -> B6 -> F72 -> F83 -> D5 -> F84
- Depends on: B8
- Depends on: F89
- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo -r` (`--ready`) in `src/chains.py` and `src/render_chain.py`.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Depends on: F89
- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references when run from an orchestrator with `.todo_projects`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Preserve the strict one-way dependency boundary (`todo-flow/docs/adr/0005-orchestrator-standard-and-dependency-boundaries.md`): child repositories remain self-contained without scanning parent directories for enclosing orchestrators; cross-project reverse dependency visibility (`Blocks: ...`) is surfaced when inspecting from the orchestrator repository.
- Target files for downstream implementation: `src/dag.py`, `src/render.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `agents/todo.md`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Depends on: F55, F75, F89
- Explore and specify `-F <path>` / `--file <path>` support across `todo` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.
- Target files for downstream implementation: `src/cli.py`, `src/workspace.py`, `src/parser.py`, `src/render.py`, `src/commands.py`, `src/header.py`, `agents/todo.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

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
