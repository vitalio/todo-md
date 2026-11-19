# 🎯 [NEXT] B1: Filter todo_md next-id by --role and readiness and pass --role work in todo_md.bundle

- Role: work
- Update `resolve_top_task_id()` and `cmd_next_id()` (`src/commands.py`) and CLI parsing in `main()` (`src/cli.py`) to accept `--role <role>` (and `--role=<role>`) on `todo_md next-id`, and ensure `resolve_top_task_id()` skips tasks with unresolved `- Depends on:` blockers as well as tasks not matching `--role` when specified.
- Update `src/bundles/todo_md.bundle` (`[if role=work]`) to invoke `var task=$(todo_md next-id --role work)` so `role=work` never auto-selects or transitions `design` or `plan` tasks (or blocked tasks) to `WIP`.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh`), and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F44: Sync with git upstream (git pull --ff-only) before mutating backlog commands

- Role: work
- Add a pre-mutation upstream sync helper in `src/commands.py` (invoked before `cmd_init()`, `cmd_add()`, `cmd_edit()`, `cmd_append()`, `cmd_transition()`, and `cmd_reopen()` when `commit` is enabled or the working tree has no uncommitted tracked code changes): if the repository has a configured git upstream (`@{u}`), run `git pull --ff-only --quiet` before reading/assigning task IDs or mutating `TODO.md` / `TODO_ARCHIVE.md`.
- Skip upstream sync cleanly when not in a git repository, when no upstream remote is configured, or in offline unit tests (`TODO_MD_NO_GIT_PULL=1` or stubbed test environments), and fail fast with `die()` if the branch has diverged from upstream so `todo_md` never assigns duplicate task IDs or commits on top of a stale `HEAD`.
- Update `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F38: Highlight a target task ID in todo_md chain and todo_md list output — *Return to NEXT*

- Update `main()` in `src/cli.py` to accept an optional task reference `<ID>` (or `<project>:<ID>`, resolved via `resolve_project_task_ref()`) on `chain` (`todo_md chain [<ID>] ...`) and `list` (both `todo_md list <ID> ...` when the positional argument matches a task ID and `todo_md list <filter> <ID> ...`).
- Add a TTY-aware ANSI highlight helper in `src/parser.py` / `src/commands.py` (active when `sys.stdout.isatty()` and `NO_COLOR` is unset, or `FORCE_COLOR` is set; plain text in pipes), ensuring `_display_width()` / `_wrap_table_row()` alignment is unaffected by ANSI escape sequences.
- In `cmd_chain()` (`src/commands.py`), highlight the target task brightly in bold across `Chain: ...` headers, task rows (`chains`, `standalone`, `--ready`), and `Held branches:` paths.
- In `cmd_list()` and `cmd_workspace_list()` (`src/parser.py`), highlight matching task rows brightly in bold in both table mode and `--tree` view.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F17: Add CLI prefix legend (F, B, D) and document prefix conventions and design lifecycle

- Define a single canonical prefix metadata table in `src/header.py` (alongside `PREFIX_DEFAULT_ROLES`) mapping standard prefixes `F` (feature, default, role `work`), `B` (bugfix, role `work`), and `D` (design, role `design`) to their descriptions and default roles.
- Update `cmd_ids` in `src/parser.py` to print a compact prefix legend (explaining `F`, `B`, `D`, and noting any custom `A-Z` prefixes in use) below `IDs in use: ...`, and summarize the standard prefixes in `src/header.py` (`--help`).
- Document standard task ID prefixes (`F`, `B`, `D`) and custom `A-Z` prefix conventions in `src/rules/todo_md.md`.
- Update `src/bundles/todo_md.bundle` (`[if role=design]`) so design tasks (`D*`) are closed via `todo_md done <ID>` once architectural invariants are persisted in `AGENTS.md` and follow-up `F*` implementation tasks are created.
- Rebuild and reinstall `todo_md` via `build.py` and `install.sh`, keep `README.md` and `tests/test_todo_md.py` in sync, and bump `VERSION` for a PATCH release.

- Document in `src/rules/todo_md.md` (and `src/bundles/todo_md.bundle` planning prompt) that non-`D` tasks (`F`/`B`/custom) still lacking backticked target files, a chosen approach, or acceptance criteria must be created/edited with `--role plan` explicitly rather than leaving the default `work` role.

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
- Expand `## Product Philosophy & Quest-Log UX` in `AGENTS.md` to define `Chain finales` (ready finale quests whose prerequisite chain is already `DONE`, surfaced first for maximum completion payoff), `chain` (questlines / guild storylines), `standalone` (side quests), `Held branches` (locked branches waiting on `HOLD` conditions), and chain ranking rules (prioritized by status `WIP`/`NEXT`, chain-finale completion payoff, and `[unblocks N]` impact in `plan_execution_chains()`, not by chain length).
- Add a concise Quest-Log summary in `README.md` explaining `chain`, `queue`, and `done` progression for users (keeping `src/rules/todo_md.md` lean without narrative metaphors).

# ⚪ [NEW] D4: Design named execution chains, milestone sub-grouping, and questline clarity in todo_md chain

- Role: design
- Explore adding human-readable names to `todo_md chain` headers (both automatic derivation from a chain's terminal goal task title when unique and an optional explicit `- Chain: <name>` / `--chain` metadata field as override) instead of printing only long `A -> B -> C` ID lists.
- Evaluate splitting or labeling large merged weakly-connected components (such as multi-wave orchestrator DAGs) by milestone/goal sub-chains (`wave` / `queue`-style subtrees) and distinguishing quick `work` side-quests from `design` tasks in `Standalone tasks:`.
- Define optional filtering by chain name (`todo_md chain "<name>"`) and coordinate questline naming conventions with `AGENTS.md` Quest-Log UX (`F37`) and orchestrator wave summaries.
- Target files for downstream implementation: `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# ⚪ [NEW] F42: Rename project to todo-markdown and CLI utility to tmd

- Role: plan
- Rename project/repository references from `todo_md` to `todo-markdown` and CLI entrypoint from `todo_md` to `tmd` (preserving `TODO.md`/`TODO_ARCHIVE.md` task-file conventions and applying agreed env-var/alias decisions from the ecosystem rename design).
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/cli.py`, `src/commands.py`, `src/header.py`, `src/parser.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/test_todo_md.py`, and `.github/`.
- Acceptance criteria: `build.py` outputs `tmd`, `install.sh`/`install.ps1` install `tmd` (plus any agreed compatibility alias), `--help`/rules/bundles/docs/tests reflect `todo-markdown` and `tmd`, and `tests/test_todo_md.py` passes.

# ⚪ [NEW] F43: Default unannotated non-design tasks to plan instead of inferring work

- Remove implicit `"F": "work"` and `"B": "work"` defaults from `PREFIX_DEFAULT_ROLES` and `resolve_task_role()` (`src/header.py`, `src/parser.py`): `todo_md` must never infer or emit `Role: work` unless `- Role: work` is explicitly set on the task.
- Default unannotated non-`D` tasks (where `- Role:` is omitted and prefix is not `D`) to `plan` (keeping `D` -> `design` unless overridden), so raw or unvetted `NEW` tasks route to planning instead of `Queue 1 (work)` in `cmd_chain()` / `plan_execution_chains()`.
- Require explicit `- Role: work` (`--role work` via `todo_md add` or `todo_md edit`) once a task is decomposed and ready for execution; coordinate with `F17` (`cmd_ids` prefix legend and `src/rules/todo_md.md` documentation).
- Update `src/header.py`, `src/parser.py`, `src/commands.py`, `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.
