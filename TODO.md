# 🎯 [NEXT] F72: Emit Bundle-Name and declarative Files preamble headers, decouple hardcoded roles from todo_md, and drop Windows support

- Depends on: B7, F71
- Implement the Producer side of `todo_flow` `docs/adr/0003-task-targeted-bundle-architecture-and-atomic-rule-taxonomy.md`:
  - In `src/bundle.py`, emit `Bundle-Name: todo_md` and native task preamble headers `Task: <ID>`, `Prefix: <P>`, `Status: <S>`, `Title: <title>`, and `Files: <space-separated path or path:start-end specs>` (plus `Role: <role>` only when an explicit `role=<role>` CLI override is passed). Stop reading and streaming target file contents as `kind: "include"` body fragments in `todo_md`, leaving file reading and span deduplication to `agents_bundle` (`file {todo_md.files:}`).
  - Decouple `todo_md` from `agents-rules` role names: remove hardcoded `resolve_task_role()`, `PREFIX_DEFAULT_ROLES`, `STATUS_ROLES`, `ROLE_EASE_ORDER`, `ROLE_EFFORT_WEIGHTS`, `RETIRED_ROLES`, `--role`, `--by-role`, and the `[role]` table column from `src/header.py`, `src/parser.py`, `src/dag.py`, `src/chains.py`, `src/render.py`, `src/render_chain.py`, `src/commands.py`, and `src/cli.py`; rank chains and tasks natively by bugfix prefix (`B*`), status tier (`WIP` -> `NEXT` -> `QUESTION` -> `NEW` -> `HOLD`), and Quest Momentum; support native `--prefix <P>` and `--status <S>` filtering in `list`, `chain`, and `next-id`.
  - Remove `agents/todo_md_work.md` (`EMBEDDED_RULE_TODO_MD_WORK` in `build.py` and `src/header.py`) and keep `agents/todo_md.md` focused strictly on `todo_md` CLI commands, statuses, prefixes (`A-Z`, noting `L` for legislative rule tasks alongside `F`, `B`, `D`), `--depends`, and `- Target files:` without hardcoded role workflow instructions (which move to `agents-rules` `agents/adapters/todo_md.bundle`).
  - Drop Windows support: remove `install.ps1` and remove `install.ps1` / `windows-latest` references from `.github/workflows/ci.yml`, `build.py`, `README.md`, and `AGENTS.md`.
- Target files: `src/header.py`, `src/parser.py`, `src/render.py`, `src/chains.py`, `src/bundle.py`, `src/cli.py`, `agents/todo_md.md`, `AGENTS.md`, `README.md`.

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

# ⚪ [NEW] F42: Rename project to todo-md and CLI utility to todo

- Depends on: F72
- Rename project/repository references from `todo_md` to `todo-md` and CLI entrypoint from `todo_md` to `todo` (preserving `TODO.md`/`TODO_ARCHIVE.md` task-file conventions and applying agreed env-var/alias decisions from `todo_flow:D8` and ADR 0003).
- Acceptance criteria: `build.py` outputs `todo`, `install.sh` installs `todo` (plus any agreed compatibility alias), `--help`/rules/docs/tests reflect `todo-md` and `todo`, and `python3 -m unittest discover -s tests` passes.
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/header.py`, `src/workspace.py`, `src/parser.py`, `src/dag.py`, `src/chains.py`, `src/render.py`, `src/render_chain.py`, `src/commands.py`, `src/bundle.py`, `src/cli.py`, `agents/todo_md.md`, `agents/todo_md_work.md`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/helpers.py`, `tests/test_*.py`, and `.github/`.

# ⚪ [NEW] D5: Design cohesive Quest-Log ANSI color palette and typography for RPG perks (FINAL, STAGE, COMBO), stats, prefixes, and statuses

- Depends on: F59 -> F60 -> F61 -> B6 -> F72
- Inspect `_style_task_row()` (`src/render.py`) and `cmd_chain()` (`src/render_chain.py`) and design a composable ANSI styling scheme for TTY output (`use_color=True`) covering uppercase RPG perks (`FINAL`, `STAGE`, `COMBO`), numeric stats (`chain: N, done: D, ready: +M, unblocks: K` and leading chain/sub-chain header stats `[<pct>% | <done>/<total>]`), task ID prefixes, and status badges.
- Render live ANSI terminal previews comparing candidate color/bold palettes and verify how token-level styling composes with existing row-level styles (`DONE` dimming, external-project dimming, and `-H` / `--highlight` emphasis) without disturbing `_wrap_table_row()` display-width calculations.

# ⚪ [NEW] D6: Design repo-exclusive parallel execution lanes and critical-path metrics in Quest-Log

- Depends on: B6
- Model parallel task execution under the repo-exclusivity invariant (at most one active task per repository at a time):
  - Compute parallel wavefront width (`threads: <K>`) across ready tasks by grouping ready tasks by repository and selecting the top-ranked actionable task per repository as a parallel execution lane (`Lane 1..K`).
  - Compute parallel critical-path steps for chains and orchestrator waves as `max(dag_depth, max_repo_open_count)` and surface parallelism metrics on chain headers and `todo_md -r` (`--ready`) in `src/chains.py` and `src/render_chain.py`.
  - Detect target-file overlaps via `extract_task_files()` (`src/parser.py`) across unlinked open tasks within the same repository in `src/chains.py` and `src/render.py` to assist planners in consolidating or sequencing tasks that touch the same files.

# ⏸️ [HOLD] P1: JSON output mode (`--json`) — *Defer machine-readable JSON output until an external client or dashboard is needed*

- Depends on: F62 -> F71 -> F72
- Add a global `--json` output flag (`HELP_GLOBAL_OPTIONS` in `src/header.py`, extracted in `src/cli.py:main()` and `_parse_quest_log_args()`) to export machine-readable JSON (`json.dumps(..., ensure_ascii=False, indent=2) + "\n"`) across read-only inspection and query commands:
  - Add `serialize_task_dict()` in `src/render.py` producing a stable task object schema: `id`, `prefix`, `project` (when in workspace or cross-project view), `workdir`, `status`, `emoji`, `title` (stripped of heading note), `note` (heading note or `None`), `file`, `line`, `ready` (`bool`), `blocked` (`bool`), `depends_on` (`parse_task_dependencies()`), `target_files` (`extract_task_files()`), and `section`.
  - Support `--json` in `cmd_list()` and `cmd_workspace_list()` (`src/render.py`) returning a JSON array of matching task objects honoring `active|archive|all|<STATUS>`, `--prefix`, `--status`, `-r`/`--ready`, `--limit`, and `-w`.
  - Support `--json` in `_show_tasks()`, `cmd_show()`, and `cmd_last()` (`src/cli.py`, `src/render.py`) returning a single task JSON object for one `<ID>` / `show last` or a JSON array of task objects when multiple `<ID>...` are requested.
  - Support `--json` in `cmd_ids()` (`{"highest_ids": ..., "next_free": ...}`), `cmd_projects()` (array of `{"project": ..., "path": ..., "open": ..., "archived": ...}`), and Quest-Log `cmd_chain()` (`src/render_chain.py`, returning structured `chains`, `standalone`, `next_actionable`, or ready task lists).
- Keep `--help` (`src/header.py`), `agents/todo_md.md`, and `README.md` in sync, and add unit tests in `tests/test_cli.py` and `tests/test_commands.py`.
- Target files: `src/header.py:HELP_GLOBAL_OPTIONS..usage_text`, `src/render.py:cmd_ids..cmd_workspace_list`, `src/render_chain.py:cmd_chain`, `src/cli.py:_parse_quest_log_args..main`, `agents/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_commands.py`.
