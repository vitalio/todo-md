# 🎯 [NEXT] F54: Support nested .todo_projects orchestrator hierarchies and external project path aliases (e.g. ~/chrome/canary)

- In `read_configured_todo_projects()` (`src/parser.py`), recursively expand nested orchestrator projects (tracking `visited_configs: set[Path]` to prevent cycles): when a configured entry (such as `todo_flow`) has its own `.todo_projects` / `.todo_projects.local`, transitively include its child projects (`agents-rules`, `agents_bundle`, `todo_md`, `run_block`) alongside sibling projects (such as `~/chrome/canary`).
- In `discover_orchestrators_for_project()` (`src/parser.py`), walk parent orchestrators transitively to a fixed point so running `todo_md chain` inside a leaf project (`todo_md`) or intermediate orchestrator (`todo_flow`) discovers both the immediate orchestrator and any enclosing meta-orchestrator.
- Preserve configured path aliases for external projects outside `ws_root` (such as `~/chrome/canary` -> `chrome/canary` and `canary`) in `resolve_project_dir()`, `resolve_workspace_chain_projects()`, and `build_execution_chain_dag()` (`_resolve_ref()` and `_format_ref()`) so cross-project references (`chrome/canary:<ID>`) and `-C chrome/canary` resolve cleanly and format as `chrome/canary:<ID>` in `chain` / `Sub-chain` views.
- Add unit tests in `tests/test_todo_md.py` covering a 3-tier orchestrator hierarchy (`meta_orch` -> `todo_flow` -> leaf repos + external `~/chrome/canary`), update `src/rules/todo_md.md` and `README.md`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

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

# 🎯 [NEXT] F38: Unify composable task styling (external project, DONE, and multi-ID target highlight) in todo_md chain and list — *Return to NEXT*

- Depends on: F51
- Update `main()` in `src/cli.py` to accept one or more optional task references `<ID>...` (or `<project>:<ID>...`, space- or comma-separated and resolved via `resolve_project_task_ref()`) on `chain` (`todo_md chain [<ID>...] ...`) and `list` (`todo_md list [<filter>] [<ID>...] ...`).
- Define a unified, orthogonal TTY-aware ANSI styling helper (`_style_task_row()` in `src/parser.py`, active when `sys.stdout.isatty()` and `NO_COLOR` is unset, or `FORCE_COLOR` is set; plain text in pipes) so three visual modes compose simultaneously without conflict and without affecting `_display_width()` / `_wrap_table_row()` alignment:
  1. External-project task (`is_external=True`): dim italic (`\033[2;3m`, or `\033[2;3;90m` when also `DONE`).
  2. Completed task (`is_done=True`, status `✅ [DONE]`): dim gray (`\033[2;90m`).
  3. Target highlighted task (`is_highlighted=True`, matching any requested `<ID>`): bold bright yellow (`\033[1;93m`, or bold italic bright yellow `\033[1;3;93m` when also `is_external=True`, preserving the `✅ [DONE]` badge when `is_done=True` so highlight never gets swallowed by dim).
- In `cmd_chain()` (`src/commands.py`), apply `_style_task_row()` across task rows (`finales`, `chains`, `standalone`, `--ready`, `--by-role`) and `Held branches:` tokens, and highlight enclosing `Chain <N> ...:` headers when any target task belongs to that chain.
- In `cmd_list()` and `cmd_workspace_list()` (`src/parser.py`), highlight all matching target `<ID>...` rows via `_style_task_row()` (and dim `DONE` rows when listing `all` or `archive`).
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

# ⚪ [NEW] F42: Rename project to todo-markdown and CLI utility to tmd

- Role: plan
- Rename project/repository references from `todo_md` to `todo-markdown` and CLI entrypoint from `todo_md` to `tmd` (preserving `TODO.md`/`TODO_ARCHIVE.md` task-file conventions and applying agreed env-var/alias decisions from the ecosystem rename design).
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/cli.py`, `src/commands.py`, `src/header.py`, `src/parser.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/test_todo_md.py`, and `.github/`.
- Acceptance criteria: `build.py` outputs `tmd`, `install.sh`/`install.ps1` install `tmd` (plus any agreed compatibility alias), `--help`/rules/bundles/docs/tests reflect `todo-markdown` and `tmd`, and `tests/test_todo_md.py` passes.

# ⚪ [NEW] F52: Build root-anchored chains with monotonic Quest Momentum ranking, [also in: ...] annotations, and --all dimmed DONE tasks

- Role: work
- Depends on: F38
- In `plan_execution_chains()` (`src/parser.py`), replace undirected weakly-connected component grouping with root-anchored chains: build one chain per terminal closing root task (sink node in the active dependency DAG with `in_degree > 0` or resolved `DONE` prerequisites outside `finale_set` and no outgoing active dependents) from its transitive prerequisite cone.
- Enforce monotonic Quest Momentum and non-decreasing chain ranking in `plan_execution_chains()` (`src/parser.py`) so completing a step via `todo_md done` never demotes the active chain:
  1. Active quest momentum (`is_active_quest`): treat a chain as actively in-flight (`tier 0`) when it contains any `🔵 [WIP]` task OR contains the most recently completed `✅ [DONE]` task from the top of `TODO_ARCHIVE.md` across the target scope (so right after `todo_md done <ID>`, the chain retains its top in-flight focus before the next step is switched to `WIP`).
  2. Started-chain status floor: once a chain has any completed prerequisite (`done_count > 0`) or any `WIP`/`NEXT` task, its status tier stays at least `NEXT` (never dropping to `NEW` when a `WIP`/`NEXT` prerequisite finishes and exposes a `⚪ [NEW]` dependent).
  3. Whole-cone invariant metrics and root tie-breaker: compute bug priority (`total_bugs = open_bugs + done_bugs`), role-weighted progress (`weighted_velocity`), and total size (`total_tasks = done_count + open_count`) across the full cone (`open ∪ done`), and tie-break by the immutable closing root key `_canonical_task_ref_key(nodes, root)` instead of `comp[0]`.
- Add `--all` (`include_done: bool = False`) support to `todo_md chain` (`src/cli.py`, `build_execution_chain_dag()`, `plan_execution_chains()`, and `cmd_chain()`): when `--all` is passed, include resolved `✅ [DONE]` prerequisite tasks inside each chain's prerequisite cone in topological order and render them in dimmed `is_done=True` style via `_style_task_row()` (composing cleanly with `is_external` and `is_highlighted` from `F38`).
- Record `root` (`tuple[Path, str]`), `root_ref`, `root_title`, and `also_in` (`dict[tuple[Path, str], list[str]]` mapping shared prerequisite nodes to other root chain refs in chain rank order) in each chain entry returned by `plan_execution_chains()`.
- Update `cmd_chain()` in `src/commands.py` to render root-anchored chain headers as `Chain <N> -> <root_ref>: <root_title> (<total> tasks, <pct>% | <done> done, <open> open):` and append `[also in: <other_root_ref>, ...]` to prerequisite rows shared across multiple root chains instead of merging independent goal chains.
- Update `src/header.py`, `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ⚪ [NEW] F53: Render nested milestone sub-chains and multi-line wrapped tree rows in todo_md chain

- Role: work
- Depends on: F52
- In `src/parser.py` and `cmd_chain()` (`src/commands.py`), detect intermediate milestone / aggregator nodes inside a chain's prerequisite cone (internal nodes that have prerequisites of their own before feeding into downstream tasks, including `DONE` prerequisites when `--all` is active) and render their prerequisite subtrees as indented `├─ Sub-chain -> <milestone_ref>: <title> (<pct>% | <done> done, <open> open):` blocks with tree connectors (`├─`, `│   `, and `└─►` on closing milestone and root rows).
- Extend `_wrap_table_row()` in `src/parser.py` with an optional tree continuation prefix (`cont_prefix`) so all chain and sub-chain tree rows wrap cleanly across multiple lines while preserving active vertical tree bars (`│   `) on wrapped continuation lines without `...` truncation in terminals or pipes.
- Preserve composable row styling (`_style_task_row()` for external-project, `DONE` under `--all`, and target highlighted tasks) across all wrapped lines and tree connectors.
- Update `src/header.py`, `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ⚪ [NEW] F50: Unify Quest-Log graph view in todo_md chain [<ID>...] [--all] with target root/leaf scoping, queue alias, and Quest-Log docs

- Role: work
- Depends on: F53
- Update `main()` in `src/cli.py` and `cmd_chain()` in `src/commands.py` so `todo_md chain [<ID>...] [--all]` coordinates target scoping and multi-ID highlighting:
  - When a single `<ID>` is passed and `<ID>` is a root or intermediate milestone task (a task with open or `DONE` prerequisites), render the hierarchical chain/sub-chain rooted at `<ID>` (hiding `DONE` tasks by default and rendering them dimmed when `--all` is passed), highlight `<ID>`, and print `Next actionable: <ref>` at the end.
  - When a single leaf task `<ID>` (no prerequisites of its own) or multiple target IDs `<ID>...` are passed, filter `todo_md chain` to the chain(s) or sections containing the target `<ID>...`, highlight all matched target IDs via `_style_task_row()` (composing with external-project and `--all` `DONE` dimming), and print `Next actionable: <ref>` when a single `<ID>` is targeted.
- Route `todo_md queue <ID> [--all]` in `src/cli.py` / `src/commands.py` as a CLI alias to `todo_md chain <ID> [--all]` (preserving error handling and exit codes for missing tasks, dependency syntax errors, and cycles).
- Expand `## Product Philosophy & Quest-Log UX` in `AGENTS.md` and add a concise Quest-Log summary in `README.md` (folding in `F37`) covering `Chain finales`, root-anchored `Chain <N> -> <root_ref>` questlines, nested `Sub-chain` milestones, `Standalone tasks`, `Held branches`, composable visual modes (external project, `--all` `DONE`, target highlight), and monotonic Quest Momentum ranking.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, `AGENTS.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.
