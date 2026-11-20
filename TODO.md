# 🎯 [NEXT] F51: Retire todo_md list --tree so todo_md list stays a flat table and todo_md chain is the single tree view

- Remove `--tree` option parsing from `list` in `main()` (`src/cli.py`) and remove the `tree: bool = False` branch from `cmd_list()` and `cmd_workspace_list()` in `src/parser.py`.
- Remove dead `--tree` helpers and constants (`_build_tree_entries()`, `_render_tree_lines()`, `_truncate_display()`, `MIN_TREE_TITLE_COLS`) from `src/parser.py` / `src/header.py`.
- Update `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` to remove `list --tree` references, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F49: Include diagnostic stdout/stderr msg context across all returncode assertions in tests/test_todo_md.py

- Role: work
- In `tests/test_todo_md.py` (`TestTodoMd`), update the remaining `self.assertEqual(r.returncode, 0)` assertions that lack a `msg=` argument to either pass `check=True` to `self._run(...)` (which invokes `self._assert_ok()` with full `stdout` and `stderr` diagnostics) or include `msg=r.stderr` / `self._assert_ok()`.
- Verify `python3 -m unittest discover -s tests` passes with zero warnings and full diagnostic coverage per `stack/python-cli`.

# 🎯 [NEXT] F44: Sync with git upstream (git pull --ff-only) before mutating backlog commands

- Role: work
- Add a pre-mutation upstream sync helper in `src/commands.py` (invoked before `cmd_init()`, `cmd_add()`, `cmd_edit()`, `cmd_append()`, `cmd_transition()`, and `cmd_reopen()` when `commit` is enabled or the working tree has no uncommitted tracked code changes): if the repository has a configured git upstream (`@{u}`), run `git pull --ff-only --quiet` before reading/assigning task IDs or mutating `TODO.md` / `TODO_ARCHIVE.md`.
- Skip upstream sync cleanly when not in a git repository, when no upstream remote is configured, or in offline unit tests (`TODO_MD_NO_GIT_PULL=1` or stubbed test environments), and fail fast with `die()` if the branch has diverged from upstream so `todo_md` never assigns duplicate task IDs or commits on top of a stale `HEAD`.
- Update `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F17: Add CLI prefix legend (F, B, D) and document prefix conventions and design lifecycle

- Role: work
- Coordinate with `F43` (`todo_flow` `docs/adr/0001-task-role-assignment-and-status-fallback.md`):
  - Define a canonical prefix metadata table in `src/header.py` describing standard prefixes `F` (feature, default prefix on `add`), `B` (bugfix, priority boost in `chain`), and `D` (design, default role `design`), plus custom `A-Z` domain prefixes (where all non-`D` prefixes resolve to `plan` in `NEW`/`QUESTION`/`HOLD` and `work` in `WIP`/`NEXT` unless overridden by `- Role: <role>`).
  - Update `cmd_ids` in `src/parser.py` to print a compact prefix legend (explaining `F`, `B`, `D`, and noting any custom `A-Z` prefixes in use) below `IDs in use: ...`, and summarize the prefix and status-role conventions in `src/header.py` (`--help`).
  - Document standard task ID prefixes (`F`, `B`, `D`), custom `A-Z` prefix conventions, status-aware role resolution, and when to pass `--role` explicitly in `src/rules/todo_md.md`.
  - Update `src/bundles/todo_md.bundle` (`[if role=design]`) so design tasks (`D*`) are closed via `todo_md done <ID>` once architectural invariants are persisted in `AGENTS.md` (and `docs/adr/`) and follow-up implementation tasks are created.
  - Rebuild and reinstall `todo_md` via `build.py` and `install.sh`, keep `README.md` and `tests/test_todo_md.py` in sync, and bump `VERSION` for a PATCH release.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Role: design
- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Target files for downstream implementation: `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `README.md`, `tests/test_todo_md.py`.

- Coordinate with `todo_flow:D4`: when a child repository belongs to a workspace orchestrator (`.todo_projects`), surface inbound orchestrator blockers in runtime `list` / `show` output (e.g. `[blocked via todo_flow:F2: ...]`) without storing cross-project `Depends on:` edges in the child `TODO.md`.

# 🎯 [NEXT] D2: Design standalone task file mode (-f / --file) for shortlists and ad-hoc task files

- Role: design
- Explore and specify `-f <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md`.
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo_md -f <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.

# 🎯 [NEXT] F38: Highlight a target task ID in todo_md chain and todo_md list output — *Return to NEXT*

- Depends on: F51
- Update `main()` in `src/cli.py` to accept an optional task reference `<ID>` (or `<project>:<ID>`, resolved via `resolve_project_task_ref()`) on `chain` (`todo_md chain [<ID>] ...`) and `list` (both `todo_md list <ID> ...` when the positional argument matches a task ID and `todo_md list <filter> <ID> ...`).
- Add a TTY-aware ANSI highlight helper (`ANSI_HIGHLIGHT_ON` and `_style_ansi_lines()`) in `src/parser.py` / `src/commands.py` (active when `sys.stdout.isatty()` and `NO_COLOR` is unset, or `FORCE_COLOR` is set; plain text in pipes), ensuring `_display_width()` / `_wrap_table_row()` alignment is unaffected by ANSI escape sequences.
- In `cmd_chain()` (`src/commands.py`), highlight the target task brightly in bold across task rows (`finales`, `chains`, `standalone`, `--ready`, `--by-role`) and `Held branches:` paths (and highlight the enclosing `Chain <N> ...:` header when the target task belongs to that chain).
- In `cmd_list()` and `cmd_workspace_list()` (`src/parser.py`), highlight matching task rows brightly in bold in table mode.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ⚪ [NEW] P1: JSON output mode (`--json`)

- Role: plan
Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F3: Clarify repository scope rule in .bundle to target the owning repository

- Update the repository scope instruction in `src/bundles/todo_md.bundle` (extending what is already in `src/rules/todo_md.md`) to remind agents that each task belongs in its owning repository's `TODO.md` (via `-C`/`<project>` or `<project>:<ID>`), never an unrelated backlog.
- Document task dependencies using `Depends on: <ID>` (same project) or `Depends on: <project>:<ID>` (cross-project orchestrator references, e.g. `agents_bundle:F5`) cleanly in `src/bundles/todo_md.bundle` / `README.md`.

# ⚪ [NEW] F6: Move exported rules and bundles from src/ to agents/

- Move `src/rules/todo_md.md` and `src/bundles/todo_md.bundle` to `agents/` using the unified logical bundle/rule layout once `agents_bundle` supports the root `agents/` directory (coordinated in `todo_flow`).
- Update `AGENTS.md`, `README.md`, and tests to reference the new paths under `agents/`.

# ⚪ [NEW] F37: Document Quest-Log chain, side-quest, and priority concepts in AGENTS.md and README.md

- Role: work
- Expand `## Product Philosophy & Quest-Log UX` in `AGENTS.md` to define `Chain finales` (ready finale quests whose prerequisite chain is already `DONE`, surfaced first for maximum completion payoff), numbered `Chain <N>` questlines with RPG progress stats (`<total> tasks, <pct>% | <done> done, <open> open`), `Standalone tasks` (side quests ordered by bugs `B*` first, role execution ease `work` -> `plan` -> `design`, then status), `Held branches` (locked branches waiting on `HOLD` conditions), and non-decreasing chain value ranking (bugs, role ease, status, and total open + `DONE` tasks in `plan_execution_chains()`).
- Add a concise Quest-Log summary in `README.md` explaining `chain`, `queue`, and `done` progression for users (keeping `src/rules/todo_md.md` lean without narrative metaphors).

# ⚪ [NEW] F42: Rename project to todo-markdown and CLI utility to tmd

- Role: plan
- Rename project/repository references from `todo_md` to `todo-markdown` and CLI entrypoint from `todo_md` to `tmd` (preserving `TODO.md`/`TODO_ARCHIVE.md` task-file conventions and applying agreed env-var/alias decisions from the ecosystem rename design).
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/cli.py`, `src/commands.py`, `src/header.py`, `src/parser.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/test_todo_md.py`, and `.github/`.
- Acceptance criteria: `build.py` outputs `tmd`, `install.sh`/`install.ps1` install `tmd` (plus any agreed compatibility alias), `--help`/rules/bundles/docs/tests reflect `todo-markdown` and `tmd`, and `tests/test_todo_md.py` passes.

# ⚪ [NEW] F52: Build root-anchored chains per terminal closing task in plan_execution_chains with [also in: ...] shared annotations

- Role: work
- Depends on: F38
- In `plan_execution_chains()` (`src/parser.py`), replace undirected weakly-connected component grouping with root-anchored chains: build one chain per terminal closing root task (sink node in the active dependency DAG with `in_degree > 0` or resolved `DONE` prerequisites outside `finale_set` and no outgoing active dependents) from its transitive prerequisite cone.
- Record `root` (`tuple[Path, str]`), `root_ref`, `root_title`, and `also_in` (`dict[tuple[Path, str], list[str]]` mapping shared prerequisite nodes to other root chain refs in chain rank order) in each chain entry returned by `plan_execution_chains()`.
- Update `cmd_chain()` in `src/commands.py` to render root-anchored chain headers as `Chain <N> -> <root_ref>: <root_title> (<total> tasks, <pct>% | <done> done, <open> open):` and append `[also in: <other_root_ref>, ...]` to prerequisite rows shared across multiple root chains instead of merging independent goal chains.
- Update `src/header.py`, `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ⚪ [NEW] F53: Render nested milestone sub-chains and multi-line wrapped tree rows in todo_md chain

- Role: work
- Depends on: F52
- In `src/parser.py` and `cmd_chain()` (`src/commands.py`), detect intermediate milestone / aggregator nodes inside a chain's prerequisite cone (internal nodes that have active prerequisites of their own before feeding into downstream tasks) and render their prerequisite subtrees as indented `├─ Sub-chain -> <milestone_ref>: <title> (<pct>% | <done> done, <open> open):` blocks with tree connectors (`├─`, `│   `, and `└─►` on closing milestone and root rows).
- Extend `_wrap_table_row()` in `src/parser.py` with an optional tree continuation prefix (`cont_prefix`) so all chain and sub-chain tree rows wrap cleanly across multiple lines while preserving active vertical tree bars (`│   `) on wrapped continuation lines without `...` truncation in terminals or pipes.
- Update `src/header.py`, `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ⚪ [NEW] F50: Unify todo_md queue <ID> into todo_md chain [<ID>] [--all] with target root/leaf scoping and Next actionable footer

- Role: work
- Depends on: F53
- Update `main()` in `src/cli.py` and `cmd_chain()` in `src/commands.py` so `todo_md chain [<ID>] [--all]` accepts an optional task reference `<ID>` (or `<project>:<ID>`) and `--all`:
  - When `<ID>` is a root or intermediate milestone task (a task with open or `DONE` prerequisites), render only the hierarchical chain/sub-chain rooted at `<ID>` (including `DONE` prerequisite tasks when `--all` is passed) and print `Next actionable: <ref>` at the end.
  - When `<ID>` is a leaf task (no prerequisites of its own), filter `todo_md chain <ID>` to the chain(s) or section containing `<ID>`, highlight `<ID>` per `F38`, and print `Next actionable: <ref>` at the end.
- Route `todo_md queue <ID> [--all]` in `src/cli.py` / `src/commands.py` as a CLI alias to `todo_md chain <ID> [--all]` (preserving error handling and exit codes for missing tasks, dependency syntax errors, and cycles).
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.
