# 🔵 [WIP] F50: Unify Quest-Log chain as default todo_md view with 4-char tree connectors, optional --numbered rows, multi-ID show, and target/status filters

- Role: work
- Depends on: F53
- Tree connector alignment & row numbering in `cmd_chain()` (`src/commands.py`):
  - Replace 3-character tree connectors (`├─ `, `└─ `) with 4-character connectors (`├── `, `└── `) matching the 4-character closing connector (`└─► `) and 4-character level indentation (`│   `, `    `) so closing tasks align flush with sibling tasks at the same tree level.
  - Omit row ordinal numbers by default across `todo_md chain` sections (`<tree_prefix><ref>` in trees and `<ref>` in `Chain finales:`, `Standalone tasks:`, `--ready`, and `--by-role`).
  - Add `--numbered` (`--numbered[=left|right]`, default `left`) to render period-free row numbers padded to `num_w = len(str(total_rows))`: `left` (`f"{idx:<{num_w}} {ref}"`) aligns numbers flush after the tree connector and pads single-digit numbers before `<ref>` so both numbers and task IDs align vertically; `right` (`f"{idx:>{num_w}} {ref}"`) right-aligns numbers with leading spaces before `<ref>`.
  - Support `-l N` / `--limit N` for row limits (keeping `-n N` as a backward-compatible integer limit alias).
- Default `todo_md` Quest-Log view, multi-ID `show`, and unified filters in `main()` (`src/cli.py`, `src/commands.py`, `src/parser.py`):
  - Make `todo_md` with no subcommand (as well as `todo_md -w` and `todo_md <project>`) invoke the Quest-Log view (`cmd_chain`) by default, while `todo_md --full` (or `todo_md overview`) renders the expanded Markdown overview (`cmd_summary` / `cmd_workspace_summary`).
  - Support multiple task IDs in `todo_md <ID1> [<ID2>...]` and `todo_md show <ID1> [<ID2>...]` (space- or comma-separated, including `<project>:<ID>`) to display full task details (`cmd_show`) sequentially separated by a blank line.
  - Support `--focus <ID>...` / `-f <ID>...` (and positional `<ID>...` under explicit `todo_md chain [<ID>...]`) to scope the Quest-Log output to the chain(s)/sub-chain(s)/sections containing `<ID>...`, highlight all matched target IDs via `_style_task_row()`, and print `Next actionable: <ref>` when a single `<ID>` is focused.
  - Support `--highlight <ID>...` / `-H <ID>...` to render the full unfiltered Quest-Log while highlighting the specified target `<ID>...`.
  - Support top-level Quest-Log and status filters directly on `todo_md [opts]` and `todo_md chain [opts]` (`--status <STATUS>` or status filter keyword `WIP|NEXT|QUESTION|NEW|HOLD|DONE|CANCELED|archive|active|all`, `--all`, `--ready`, `--by-role`, `--role <role>`, `-l N` / `--limit N`, `--numbered[=left|right]`, `--include-hold`), and route `todo_md queue <ID> [--all]` as a CLI alias to `todo_md chain <ID> [--all]`.
- Documentation & tests:
  - Expand `## Product Philosophy & Quest-Log UX` in `AGENTS.md` and update `README.md`, `src/header.py` (`--help`), and `src/rules/todo_md.md` to document the default Quest-Log view, 4-char connectors, `--numbered`, multi-ID `show`, `--focus`/`--highlight`, and status filters.
  - Update and expand unit tests in `tests/test_chain.py` and `tests/test_cli.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

- Update the `[if role=plan]` prompt in `src/bundles/todo_md.bundle` to instruct the Planner to decompose or compose (consolidate) work into self-contained tasks in `TODO.md` depending on file, test, and documentation cohesion (refining or merging into an existing open task when changes touch the same files/tests).

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
