# 🎯 [NEXT] F56: Format and align -h/--help output with structured Usage/Commands/Options sections and <=100-col lines

- In `src/header.py`, split the top-level `Usage:` block into a concise `Usage:` summary and a dedicated `Commands:` section followed by `Global options:`, `Quest-Log options:`, `Files:`, and `Environment variables:`.
- Align all description columns and continuation lines against the rendered binary name (`todo_md`, accounting for `{prog}` length replacement) so continuation lines (`Opts: ...`, multi-line descriptions) start at the exact same column as primary descriptions.
- Wrap all `--help` lines to at most 100 columns (and prose paragraphs to ~80 columns) and omit the redundant `queue` alias from `--help` (keeping `queue` accepted in `src/cli.py` for backward compatibility).
- Add a unit test in `tests/test_cli.py` verifying that `todo_md --help` has aligned description columns and no lines exceeding 100 characters, update `README.md` if needed, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a PATCH release.

# 🎯 [NEXT] F55: Unify -s/--search, -f/--filter, -H/--highlight focus toggle, and --all across .todo_projects

- In `src/cli.py` (`_parse_quest_log_args()`, `_quest_log()`, `QUEST_LOG_USAGE`) and `src/header.py`:
  - Replace `-f` / `--focus` with `-f <ID>...` / `--filter <ID>...` for filtering by task IDs (case-insensitive `<ID>` or `<project>:<ID>`, space- or comma-separated).
  - Keep `-s <QUERY>` / `--search <QUERY>` (`todo_md search <QUERY>`) for case-insensitive substring/regex search across task titles, bodies, and `<project>:<ID>`.
  - Make focusing + highlighting the default behavior when `-s` and/or `-f` is given, and make `-H` / `--highlight` a focus-disabling toggle (rendering the full list with matched tasks highlighted; also accept `todo_md -H <ID>...` as shorthand for `-f <ID>... -H`).
  - Expand `_quest_log()` search and bare-ID resolution across all projects in the active view (including `.todo_projects` when running inside an orchestrator without `-w`) in `src/cli.py` and `_normalize_target_refs()` in `src/parser.py`, so `todo_md -f F57`, `todo_md -f F57 -H`, and `todo_md -s append` inside `todo_flow` match child-project tasks such as `run_block:F57`.
- Unify `--all` across Quest-Log, `-s`, and `-f` in `src/cli.py` and `src/commands.py` (`cmd_chain()`, `cmd_list()`, `cmd_workspace_list()`): `--all` always includes both active (`TODO.md`) and archived (`TODO_ARCHIVE.md`) tasks, and focused searches/filters display matched archived `DONE`/`CANCELED` tasks rather than dropping standalone archived tasks or printing the entire archive unfiltered.
- Update `AGENTS.md`, `src/rules/todo_md.md`, `src/header.py`, `README.md`, and unit tests in `tests/test_cli.py` and `tests/test_chain.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

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

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Role: design
- Explore and specify `-F <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo_md -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.

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
