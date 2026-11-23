# 🎯 [NEXT] F73: Forbid cross-project Depends on references in non-orchestrator repositories in todo_md check

- In `validate_all()` (`src/parser.py`), reject cross-project `<project>:<ID>` references (`PROJECT_TASK_RE`) in `- Depends on:` when the current repository is not an orchestrator (`not has_local_todo_projects_config(base_dir)`), reporting a clear error message instructing to keep cross-project dependencies in the workspace orchestrator repository (`.todo_projects`).
- Allow cross-project `<project>:<ID>` dependencies in `validate_all()` only when the repository has a local `.todo_projects` or `.todo_projects.local` configuration.
- Update `agents/todo_md.md`, `README.md`, and unit tests in `tests/test_deps.py` to cover the one-way dependency boundary enforcement in `todo_md check` (and post-mutation validation on `add` / `edit`), and rebuild `./todo_md` via `python3 build.py`.

# 🎯 [NEXT] F42: Rename project to todo-md and CLI utility to todo

- Depends on: F72, F75, F77, F78, F79
- Rename project/repository references from `todo_md` to `todo-md` (`vitalio/todo-md`) and CLI entrypoint to `todo` per `todo_flow:D8` (`docs/adr/0004-ecosystem-rename-and-cutover.md`):
  - Emit `Bundle-Name: vitalio/todo-md`, embedded rule `agents/todo.md` with `{cmd:todo}` substitution (`id: "vitalio/todo-md:todo"`, `chain: ["vitalio/todo-md"]`), and repo marker `# todo-md-repo: vitalio/todo-md`.
  - Preserve `TODO.md` / `TODO_ARCHIVE.md` / `.todo_projects` conventions and `TODO_MD_*` environment variables.
  - Replace any existing `todo_md` binary in `$INSTALL_DIR` during `install.sh` / `update`, add `--uninstall` (`todo uninstall` / `todo --uninstall` and `install.sh --uninstall`), rename the GitHub repository `vitalio/todo_md` -> `vitalio/todo-md` and update local `git remote` URL, and run `python3 build.py && ./install.sh --yes` to migrate the local machine.
- Acceptance criteria: GitHub repo is `vitalio/todo-md`, `build.py` outputs `todo`, `install.sh` installs `todo` and removes legacy `todo_md`, `--uninstall` removes the installed binary, and `python3 -m unittest discover -s tests` passes.

- Trim `agents/todo.md` (and update the string assertions in `tests/test_cli.py` and `tests/test_bundle.py`) so the embedded rule states only the minimal machine-facing `todo` CLI and dependency contract without dumping every `--help` display flag (`--numbered`, `--include-hold`), `Bundle-Name` transport header details, or legacy `agents_bundle | run_block` examples.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Coordinate with `todo_flow:D4`: when a child repository belongs to a workspace orchestrator (`.todo_projects`), surface inbound orchestrator blockers in runtime `list` / `show` output (e.g. `[blocked via todo_flow:F2: ...]`) without storing cross-project `Depends on:` edges in the child `TODO.md`.
- Target files for downstream implementation: `src/dag.py`, `src/render.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `agents/todo_md.md`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Depends on: F55, F75
- Explore and specify `-F <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo_md -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.
- Target files for downstream implementation: `src/cli.py`, `src/workspace.py`, `src/parser.py`, `src/render.py`, `src/commands.py`, `src/header.py`, `agents/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

# ⚪ [NEW] D5: Design cohesive Quest-Log ANSI color palette and typography for RPG perks (FINAL, STAGE, COMBO), stats, prefixes, and statuses

- Depends on: F59 -> F60 -> F61 -> B6 -> F72
- Inspect `_style_task_row()` (`src/render.py`) and `cmd_chain()` (`src/render_chain.py`) and design a composable ANSI styling scheme for TTY output (`use_color=True`) covering uppercase RPG perks (`FINAL`, `STAGE`, `COMBO`), numeric stats (`chain: N, done: D, ready: +M, unblocks: K` and leading chain/sub-chain header stats `[<pct>% | <done>/<total>]`), task ID prefixes, and status badges.
- Render live ANSI terminal previews comparing candidate color/bold palettes and verify how token-level styling composes with existing row-level styles (`DONE` dimming, external-project dimming, and `-H` / `--highlight` emphasis) without disturbing `_wrap_table_row()` display-width calculations.

# ⚪ [NEW] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: B6
- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo_md -r` (`--ready`) in `src/chains.py` and `src/render_chain.py`.

# ⏸️ [HOLD] P1: JSON output mode (`--json`) — *Defer machine-readable JSON output until an external client or dashboard is needed*

- Depends on: F62 -> F71 -> F72, F78
- Add a global `--json` output flag (`HELP_GLOBAL_OPTIONS` in `src/header.py`, extracted in `src/cli.py:main()` and `_parse_quest_log_args()`) to export machine-readable JSON (`json.dumps(..., ensure_ascii=False, indent=2) + "\n"`) across read-only inspection and query commands:
  - Add `serialize_task_dict()` in `src/render.py` producing a stable task object schema: `id`, `prefix`, `project` (when in workspace or cross-project view), `workdir`, `status`, `emoji`, `title` (stripped of heading note), `note` (heading note or `None`), `file`, `line`, `ready` (`bool`), `blocked` (`bool`), `depends_on` (`parse_task_dependencies()`), and `section`.
  - Support `--json` in `cmd_list()` and `cmd_workspace_list()` (`src/render.py`) returning a JSON array of matching task objects honoring `active|archive|all|<STATUS>`, `--prefix`, `--status`, `-r`/`--ready`, `--limit`, and `-w`.
  - Support `--json` in `_show_tasks()`, `cmd_show()`, and `cmd_last()` (`src/cli.py`, `src/render.py`) returning a single task JSON object for one `<ID>` / `show last` or a JSON array of task objects when multiple `<ID>...` are requested.
  - Support `--json` in `cmd_ids()` (`{"highest_ids": ..., "next_free": ...}`), `cmd_projects()` (array of `{"project": ..., "path": ..., "open": ..., "archived": ...}`), and Quest-Log `cmd_chain()` (`src/render_chain.py`, returning structured `chains`, `standalone`, `next_actionable`, or ready task lists).
- Keep `--help` (`src/header.py`), `agents/todo_md.md`, and `README.md` in sync, and add unit tests in `tests/test_cli.py` and `tests/test_commands.py`.
