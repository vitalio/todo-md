# 🎯 [NEXT] F54: Support nested .todo_projects orchestrator hierarchies and external project path aliases (e.g. ~/chrome/canary)

- In `read_configured_todo_projects()` (`src/parser.py`), recursively expand nested orchestrator projects (tracking `visited_configs: set[Path]` to prevent cycles): when a configured entry (such as `todo_flow`) has its own `.todo_projects` / `.todo_projects.local`, transitively include its child projects (`agents-rules`, `agents_bundle`, `todo_md`, `run_block`) alongside sibling projects (such as `~/chrome/canary`).
- In `discover_orchestrators_for_project()` (`src/parser.py`), walk parent orchestrators transitively to a fixed point so running `todo_md chain` inside a leaf project (`todo_md`) or intermediate orchestrator (`todo_flow`) discovers both the immediate orchestrator and any enclosing meta-orchestrator.
- Preserve configured path aliases for external projects outside `ws_root` (such as `~/chrome/canary` -> `chrome/canary` and `canary`) in `resolve_project_dir()`, `resolve_workspace_chain_projects()`, and `build_execution_chain_dag()` (`_resolve_ref()` and `_format_ref()`) so cross-project references (`chrome/canary:<ID>`) and `-C chrome/canary` resolve cleanly and format as `chrome/canary:<ID>` in `chain` / `Sub-chain` views.
- Add unit tests in `tests/test_chain.py` and `tests/test_deps.py` covering a 3-tier orchestrator hierarchy (`meta_orch` -> `todo_flow` -> leaf repos + external `~/chrome/canary`), update `src/rules/todo_md.md` and `README.md`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F44: Sync with git upstream (git pull --ff-only) before mutating backlog commands

- Role: work
- Add a pre-mutation upstream sync helper in `src/commands.py` (invoked before `cmd_init()`, `cmd_add()`, `cmd_edit()`, `cmd_append()`, `cmd_transition()`, and `cmd_reopen()` when `commit` is enabled or the working tree has no uncommitted tracked code changes): if the repository has a configured git upstream (`@{u}`), run `git pull --ff-only --quiet` before reading/assigning task IDs or mutating `TODO.md` / `TODO_ARCHIVE.md`.
- Skip upstream sync cleanly when not in a git repository, when no upstream remote is configured, or in offline unit tests (`TODO_MD_NO_GIT_PULL=1` or stubbed test environments), and fail fast with `die()` if the branch has diverged from upstream so `todo_md` never assigns duplicate task IDs or commits on top of a stale `HEAD`.
- Update `src/rules/todo_md.md`, `README.md`, and `tests/test_commands.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F17: Add CLI prefix legend (F, B, D) and document prefix conventions and design lifecycle

- Role: work
- Coordinate with `F43` (`todo_flow` `docs/adr/0001-task-role-assignment-and-status-fallback.md`):
  - Define a canonical prefix metadata table in `src/header.py` describing standard prefixes `F` (feature, default prefix on `add`), `B` (bugfix, priority boost in `chain`), and `D` (design, default role `design`), plus custom `A-Z` domain prefixes (where all non-`D` prefixes resolve to `plan` in `NEW`/`QUESTION`/`HOLD` and `work` in `WIP`/`NEXT` unless overridden by `- Role: <role>`).
  - Update `cmd_ids` in `src/parser.py` to print a compact prefix legend (explaining `F`, `B`, `D`, and noting any custom `A-Z` prefixes in use) below `IDs in use: ...`, and summarize the prefix and status-role conventions in `src/header.py` (`--help`).
  - Document standard task ID prefixes (`F`, `B`, `D`), custom `A-Z` prefix conventions, status-aware role resolution, and when to pass `--role` explicitly in `src/rules/todo_md.md`.
  - Update `src/bundles/todo_md.bundle` (`[if role=design]`) so design tasks (`D*`) are closed via `todo_md done <ID>` once architectural invariants are persisted in `AGENTS.md` (and `docs/adr/`) and follow-up implementation tasks are created.
  - Rebuild and reinstall `todo_md` via `build.py` and `install.sh`, keep `README.md` and `tests/test_parser.py` and `tests/test_cli.py` in sync, and bump `VERSION` for a PATCH release.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Role: design
- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Target files for downstream implementation: `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

- Coordinate with `todo_flow:D4`: when a child repository belongs to a workspace orchestrator (`.todo_projects`), surface inbound orchestrator blockers in runtime `list` / `show` output (e.g. `[blocked via todo_flow:F2: ...]`) without storing cross-project `Depends on:` edges in the child `TODO.md`.

# 🎯 [NEXT] D2: Design standalone task file mode (-f / --file) for shortlists and ad-hoc task files

- Role: design
- Explore and specify `-f <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md`.
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo_md -f <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.

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
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/cli.py`, `src/commands.py`, `src/header.py`, `src/parser.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/helpers.py`, `tests/test_*.py`, and `.github/`.
- Acceptance criteria: `build.py` outputs `tmd`, `install.sh`/`install.ps1` install `tmd` (plus any agreed compatibility alias), `--help`/rules/bundles/docs/tests reflect `todo-markdown` and `tmd`, and `python3 -m unittest discover -s tests` passes.

# ⚪ [NEW] F50: Unify Quest-Log graph view in todo_md chain [<ID>...] [--all] with target root/leaf scoping, queue alias, and Quest-Log docs

- Role: work
- Depends on: F53
- Update `main()` in `src/cli.py` and `cmd_chain()` in `src/commands.py` so `todo_md chain [<ID>...] [--all]` coordinates target scoping and multi-ID highlighting:
  - When a single `<ID>` is passed and `<ID>` is a root or intermediate milestone task (a task with open or `DONE` prerequisites), render the hierarchical chain/sub-chain rooted at `<ID>` (hiding `DONE` tasks by default and rendering them dimmed when `--all` is passed), highlight `<ID>`, and print `Next actionable: <ref>` at the end.
  - When a single leaf task `<ID>` (no prerequisites of its own) or multiple target IDs `<ID>...` are passed, filter `todo_md chain` to the chain(s) or sections containing the target `<ID>...`, highlight all matched target IDs via `_style_task_row()` (composing with external-project and `--all` `DONE` dimming), and print `Next actionable: <ref>` when a single `<ID>` is targeted.
- Route `todo_md queue <ID> [--all]` in `src/cli.py` / `src/commands.py` as a CLI alias to `todo_md chain <ID> [--all]` (preserving error handling and exit codes for missing tasks, dependency syntax errors, and cycles).
- Expand `## Product Philosophy & Quest-Log UX` in `AGENTS.md` and add a concise Quest-Log summary in `README.md` (folding in `F37`) covering `Chain finales`, root-anchored `Chain <N> -> <root_ref>` questlines, nested `Sub-chain` milestones, `Standalone tasks`, `Held branches`, composable visual modes (external project, `--all` `DONE`, target highlight), and monotonic Quest Momentum ranking.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, `AGENTS.md`, and `tests/test_chain.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.
