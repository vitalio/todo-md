# 🎯 [NEXT] F59: Unify task and chain RPG stats ([FINAL | STAGE | COMBO | chain: N, done: D, ready: +M, unblocks: K] and [<pct>% | done: D, open: O]) across Quest-Log views

- In `_prepare_active_plan()` and `plan_execution_chains()` (`src/parser.py:2720-2855` and `src/parser.py:3380-3425`), compute `done_counts` (`{u: len(done_nodes.get(u, set())) for u in active_list}`), include `-done_counts.get(u, 0)` in `_node_rank()` so partially completed chains (`done > 0`) rank ahead of unstarted branches at equal priority, and expose `done_counts` and `is_momentum_next` in the returned plan dictionary.
- In `cmd_chain()` / `_format_row()` (`src/commands.py:1255-1340`), replace legacy `[ready | N chain(s) | +M ready | unblocks K -> targets]`, `[ready | after: ...]`, and two-bracket `[ready] [unblocks K]` / `[blocked by: ... ] [unblocks K]` tags with a unified bracketed RPG stat block `[perks | key: val, ...]`:
  - Perks (uppercase, separated by ` | ` in fixed priority order):
    - `ready` (shown only in non-`--ready` views where ready and blocked rows appear together; omitted in `-r` / `--ready`),
    - `FINAL` when `done_counts[u] > 0` and `active_unblocks[u] == 0` (closing root of a chain with all prerequisites completed),
    - `STAGE` when `done_counts[u] > 0` and `active_unblocks[u] > 0` (ready intermediate sub-chain boss unlocking downstream tasks),
    - `COMBO` when `is_momentum_next.get(u, 1) == 0` (continues the most recently completed task `latest_done_task`).
  - Key-value stats (comma-separated after perks and ` | `):
    - In `-r` / `--ready` (`show_downstream=True`): `chain: <N>` (using `1` for `FINAL` tasks in `finale_set`, else `chain_counts[u]` when `> 0`), `done: <D>` (only when `D > 0`), `ready: +<M>` (when `unblocks > 0`, where `M = len(immediate_ready_targets[u])`), and `unblocks: <K>` (when `K > 0`). Omit the trailing bracket tag completely for standalone ready tasks in `-r` that have no perks and all zero stats (`chain == 0, done == 0, unblocks == 0`).
    - In non-`--ready` views (`show_downstream=False`): combine perks and stats into a single bracketed tag (`[ready | FINAL | COMBO | done: <D>]`, `[ready | STAGE | done: <D>, unblocks: <K>]`, `[ready | unblocks: <K>]`, `[ready]`, or `[blocked by: <refs> | unblocks: <K>]` / `[blocked | unblocks: <K>]`).
- In `cmd_chain()` (`src/commands.py:1570-1680`), unify `Chain <N> -> <ref>: <title>` and `Sub-chain -> <ref>: <title>` header stats to `[<pct>% | done: <D>, open: <O>]:` when `done > 0` and `[open: <O>]:` when `done == 0` (replacing parenthesized `(<total> tasks, <pct>% | <done> done, <open> open):` and `(<pct>% | <done> done, <open> open):`).
- Update `src/header.py`, `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_chain.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F57: Support glob path patterns and line-range slices (path:start-end) in todo_md files (extract_task_files and cmd_files)

- In `extract_task_files()` (`src/commands.py:1005-1095`), support both glob patterns and line-range suffixes on backticked repository file references:
  - Line-range suffixes: parse trailing `:start-end`, `:line`, or `#Lstart-Lend` / `#Lline` (1-based inclusive line numbers, normalizing to `rel_path:start-end` when a range or single line is given) instead of stripping and discarding line numbers; deduplicate by the full `rel_path` or `rel_path:start-end` spec so multiple distinct slices of a large file can be emitted.
  - Glob patterns: allow `*`, `?`, and `[` in relative path tokens without line ranges when the token contains a path separator `/` or file extension `.` (ignoring bare prefix tokens like `D*` or `*`) and no `..` traversal segments, expanding `sorted(repo_root.glob(cand))` into matching regular files inside `repo_root` (skipping `.git` and `__pycache__`).
- In `cmd_files()` (`src/commands.py:1040-1095`), when an item specifies `:start-end`, evaluate `--max-lines`, `--max-total-lines`, `--max-bytes`, and `--max-total-bytes` against the sliced lines (`lines[start - 1 : end]`) rather than the entire file so inspected sections of large files fit within bundle size budgets, and print `rel_path:start-end` to `stdout`.
- Update `src/header.py`, `src/rules/todo_md.md` (documenting that planners record `path:start-end` line ranges for large inspected files when promoting a task to `NEXT` for `role=work`), `README.md`, and unit tests in `tests/test_commands.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F44: Sync with git upstream (git pull --ff-only) before mutating backlog commands

- Add a pre-mutation upstream sync helper in `src/commands.py` (invoked before `cmd_init()`, `cmd_add()`, `cmd_edit()`, `cmd_append()`, `cmd_transition()`, and `cmd_reopen()` when `commit` is enabled or the working tree has no uncommitted tracked code changes): if the repository has a configured git upstream (`@{u}`), run `git pull --ff-only --quiet` before reading/assigning task IDs or mutating `TODO.md` / `TODO_ARCHIVE.md`.
- Skip upstream sync cleanly when not in a git repository, when no upstream remote is configured, or in offline unit tests (`TODO_MD_NO_GIT_PULL=1` or stubbed test environments), and fail fast with `die()` if the branch has diverged from upstream so `todo_md` never assigns duplicate task IDs or commits on top of a stale `HEAD`.
- Update `src/rules/todo_md.md`, `README.md`, and `tests/test_commands.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] F17: Add CLI prefix legend (F, B, D), remove in-body - Role: overrides, and document prefix/status role resolution

- Coordinate with `F43` and `todo_flow` `docs/adr/0001-prefix-and-status-task-role-resolution.md`:
  - Remove in-body `- Role: <role>` overrides from `resolve_task_role()` in `src/parser.py` so role resolution is strictly prefix- and status-driven (`D*` -> `design`; non-`D` `A-Z` -> `work` in `WIP`/`NEXT` and `plan` in `NEW`/`QUESTION`/`HOLD`).
  - Remove `--role` from `cmd_add()` and `cmd_edit()` in `src/commands.py` (keeping `--role` strictly as a read-only filter on `todo_md`, `chain`, `list`, and `next-id`), and update `todo_md check` (`validate_repo()` in `src/parser.py`) to reject `- Role:` lines in active `TODO.md` files with an error guiding to `D*` prefix (for `design`) or `todo_md next <ID>` (for `work`), exempting historical `TODO_ARCHIVE.md`.
  - Define a canonical prefix metadata table in `src/header.py` describing standard prefixes `F` (feature, default prefix on `add`), `B` (bugfix, priority boost in `chain`), and `D` (design, role `design`), plus custom `A-Z` domain prefixes.
  - Update `cmd_ids` in `src/parser.py` to print a compact prefix legend below `IDs in use: ...`, and summarize the prefix and status-role conventions in `src/header.py` (`--help`).
  - Document standard task ID prefixes (`F`, `B`, `D`), custom `A-Z` prefix conventions, and prefix/status role resolution in `src/rules/todo_md.md`.
  - Update `src/bundles/todo_md.bundle` (`[if role=design]`) so design tasks (`D*`) are closed via `todo_md done <ID>` once architectural invariants are persisted in `AGENTS.md` (and `docs/adr/`) and follow-up implementation tasks are created.
  - Rebuild and reinstall `todo_md` via `build.py` and `install.sh`, keep `README.md` and `tests/test_parser.py`, `tests/test_commands.py`, and `tests/test_cli.py` in sync, and bump `VERSION` for a MINOR release.

# 🎯 [NEXT] D3: Design explicit HOLD task review workflow and reverse dependency visibility

- Specify how `HOLD` tasks expose downstream blocked dependents (`Blocks: ...` in `show` / `list HOLD`, including cross-project references under `-w`) so reviewers see what unblocks when a `HOLD` condition is met.
- Design an opt-in, explicitly invoked workflow (and any supporting CLI filter/command or bundle/rule trigger) for auditing `HOLD` tasks against repository/environment state without running automatically on unrelated agent turns.
- Define status transition rules when a `HOLD` condition is satisfied (`NEW` vs `NEXT`) versus still waiting (updating notes in place).
- Target files for downstream implementation: `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `README.md`, `tests/test_deps.py`, `tests/test_commands.py`.

- Coordinate with `todo_flow:D4`: when a child repository belongs to a workspace orchestrator (`.todo_projects`), surface inbound orchestrator blockers in runtime `list` / `show` output (e.g. `[blocked via todo_flow:F2: ...]`) without storing cross-project `Depends on:` edges in the child `TODO.md`.

# 🎯 [NEXT] D2: Design standalone task file mode (-F / --file) for shortlists and ad-hoc task files

- Depends on: F55
- Explore and specify `-F <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md` (keeping `-f` reserved for `--filter`).
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_cli.py`, `tests/test_parser.py`, `tests/test_commands.py`.

- Shortlist/chain export workflow: evaluate supporting an exported or agent-generated shortlist Markdown file (e.g. a custom prioritized sequence or `chain` snapshot) that users can inspect, filter, and step through with `todo_md -F <path>` while resolving `<project>:<ID>` references against `TODO_MD_WORKSPACE`.

# 🎯 [NEXT] F56: Format and align -h/--help output with structured Usage/Commands/Options sections and <=100-col lines

- Depends on: F17, F44, F55, F57, F58, F59
- In `src/header.py`, split the top-level `Usage:` block into a concise `Usage:` summary and a dedicated `Commands:` section followed by `Global options:`, `Quest-Log options:`, `Files:`, and `Environment variables:`.
- Align all description columns and continuation lines against the rendered binary name (`todo_md`, accounting for `{prog}` length replacement) so continuation lines (`Opts: ...`, multi-line descriptions) start at the exact same column as primary descriptions.
- Wrap all `--help` lines to at most 100 columns (and prose paragraphs to ~80 columns) and omit the redundant `queue` alias from `--help` (keeping `queue` accepted in `src/cli.py` for backward compatibility).
- Add a unit test in `tests/test_cli.py` verifying that `todo_md --help` has aligned description columns and no lines exceeding 100 characters, update `README.md` if needed, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a PATCH release.

# ⚪ [NEW] P1: JSON output mode (`--json`)

- Depends on: F54, F55, F58
Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F6: Move exported rules and bundles from src/ to agents/

- Move `src/rules/todo_md.md` and `src/bundles/todo_md.bundle` to `agents/` using the unified logical bundle/rule layout once `agents_bundle` supports the root `agents/` directory (coordinated in `todo_flow`).
- Update `AGENTS.md`, `README.md`, and tests to reference the new paths under `agents/`.

# ⚪ [NEW] F42: Rename project to todo-markdown and CLI utility to tmd

- Rename project/repository references from `todo_md` to `todo-markdown` and CLI entrypoint from `todo_md` to `tmd` (preserving `TODO.md`/`TODO_ARCHIVE.md` task-file conventions and applying agreed env-var/alias decisions from the ecosystem rename design).
- Target files: `build.py`, `install.sh`, `install.ps1`, `src/cli.py`, `src/commands.py`, `src/header.py`, `src/parser.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `.agents_bundle`, `AGENTS.md`, `README.md`, `VERSION`, `tests/helpers.py`, `tests/test_*.py`, and `.github/`.
- Acceptance criteria: `build.py` outputs `tmd`, `install.sh`/`install.ps1` install `tmd` (plus any agreed compatibility alias), `--help`/rules/bundles/docs/tests reflect `todo-markdown` and `tmd`, and `python3 -m unittest discover -s tests` passes.

# ⚪ [NEW] D5: Design cohesive Quest-Log ANSI color palette and typography for RPG perks (FINAL, STAGE, COMBO), stats, roles, and statuses

- Depends on: F59
- Inspect `_style_task_row()` (`src/commands.py:1170-1340`) and design a composable ANSI styling scheme for TTY output (`use_color=True`) covering uppercase RPG perks (`FINAL`, `STAGE`, `COMBO`), numeric stats (`chain: N, done: D, ready: +M, unblocks: K` and chain header `[<pct>% | done: D, open: O]`), role badges (`[work]`, `[plan]`, `[design]`), and status badges.
- Render live ANSI terminal previews comparing candidate color/bold palettes and verify how token-level styling composes with existing row-level styles (`DONE` dimming, external-project dimming, and `-H` / `--highlight` emphasis) without disturbing `_wrap_table_row()` display-width calculations.
