# ✅ [DONE] B3: Scope Sub-chain milestone stats and subtree_nodes to rendered subtree tasks in build_chain_milestone_tree — *2026-11-21, Scoped Sub-chain stats and subtree_nodes to rendered subtree tasks*

- Fix `build_chain_milestone_tree()` in `src/parser.py` (`src/parser.py:2852-3070`) so that for each `Sub-chain ->` node (`is_root=False`), `done_count`, `open_count`, `total_tasks`, `progress_pct`, and `subtree_nodes` are computed exclusively from the tasks actually rendered inside that sub-chain's subtree rather than the milestone's full unfiltered transitive cone:
  - When a shared prerequisite branch (such as `D1` or `D6`) has already been emitted in an earlier sibling sub-chain of the same root `Chain`, exclude already-emitted open tasks and their already-claimed `DONE` prerequisites from subsequent sibling `Sub-chain` header stats (`[pct% | done: D, open: O]` / `[open: O]`) so header counts match the tasks displayed under that `Sub-chain` (both with and without `--all`).
  - Scope `subtree_nodes` on each `Sub-chain` node (`src/parser.py:2943-2990`, used by `_render_chain_tree_children()` in `src/commands.py:1645-1675`) to the tasks actually rendered inside that sub-chain so `--filter` / `-f` and `--highlight` / `-H` do not highlight unrelated sibling `Sub-chain` headers whose only connection to the target task was an already-emitted shared prerequisite above.
- Add regression tests in `tests/test_chain.py` covering `--tree` and `--tree --all` (plus `-f` highlighting) on a diamond/shared-prerequisite DAG where two sibling sub-chains depend on a common sub-chain with completed tasks.

# ✅ [DONE] F57: Support glob path patterns and line-range slices (path:start-end) in todo_md files (extract_task_files and cmd_files) — *2026-11-21, glob patterns and line-range slices in files*

- Depends on: F56
- In `extract_task_files()` (`src/commands.py:1005-1095`), support both glob patterns and line-range suffixes on backticked repository file references:
  - Line-range suffixes: parse trailing `:start-end`, `:line`, or `#Lstart-Lend` / `#Lline` (1-based inclusive line numbers, normalizing to `rel_path:start-end` when a range or single line is given) instead of stripping and discarding line numbers, and reject tokens where the suffix after `:` is not a valid line number/range (so cross-project task refs like `todo_md:D5` are never stripped to the compiled `todo_md` binary in repo root); deduplicate by the full `rel_path` or `rel_path:start-end` spec so multiple distinct slices of a large file can be emitted.
  - Glob patterns: allow `*`, `?`, and `[` in relative path tokens without line ranges when the token contains a path separator `/` or file extension `.` (ignoring bare prefix tokens like `D*` or `*`) and no `..` traversal segments, expanding `sorted(repo_root.glob(cand))` into matching regular files inside `repo_root` (skipping `.git` and `__pycache__`).
- In `cmd_files()` (`src/commands.py:1040-1095`), when an item specifies `:start-end`, evaluate `--max-lines`, `--max-total-lines`, `--max-bytes`, and `--max-total-bytes` against the sliced lines (`lines[start - 1 : end]`) rather than the entire file so inspected sections of large files fit within bundle size budgets, and print `rel_path:start-end` to `stdout`.
- Update `src/header.py`, `src/rules/todo_md.md` (documenting that planners record `path:start-end` line ranges for large inspected files when promoting a task to `NEXT` for `role=work`), `README.md`, and unit tests in `tests/test_commands.py`, rebuild via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F56: Format and align -h/--help output with structured Usage/Commands/Options sections and <=100-col lines — *2026-11-21, structured --help layout with aligned columns and 100-col wrapping*

- Depends on: F44
- In `src/header.py`, split the top-level `Usage:` block into a concise `Usage:` summary and a dedicated `Commands:` section followed by `Global options:`, `Quest-Log options:`, `Files:`, and `Environment variables:`.
- Align all description columns and continuation lines against the rendered binary name (`todo_md`, accounting for `{prog}` length replacement) so continuation lines (`Opts: ...`, multi-line descriptions) start at the exact same column as primary descriptions.
- Wrap all `--help` lines to at most 100 columns (and prose paragraphs to ~80 columns) and omit the redundant `queue` alias from `--help` (keeping `queue` accepted in `src/cli.py` for backward compatibility).
- Add a unit test in `tests/test_cli.py` verifying that `todo_md --help` has aligned description columns and no lines exceeding 100 characters, update `README.md` if needed, rebuild via `build.py`, and bump `VERSION` for a PATCH release.

# ❌ [CANCELED] F6: Move exported rules and bundles from src/ to agents/ — *Superseded by F63 and todo_flow:D6 (todo_md.bundle removed; agents/todo_md.md embedded at build time)*

- Depends on: F62
- Move `src/rules/todo_md.md` and `src/bundles/todo_md.bundle` to `agents/` using the unified logical bundle/rule layout once `agents_bundle` supports the root `agents/` directory (coordinated in `todo_flow`).
- Update `AGENTS.md`, `README.md`, and tests to reference the new paths under `agents/`.

# ✅ [DONE] F44: Sync with git upstream (git pull --ff-only) before mutating backlog commands — *2026-11-21*

- Depends on: F17
- Add a pre-mutation upstream sync helper in `src/commands.py` (invoked before `cmd_init()`, `cmd_add()`, `cmd_edit()`, `cmd_append()`, `cmd_transition()`, and `cmd_reopen()` when `commit` is enabled or the working tree has no uncommitted tracked code changes): if the repository has a configured git upstream (`@{u}`), run `git pull --ff-only --quiet` before reading/assigning task IDs or mutating `TODO.md` / `TODO_ARCHIVE.md`.
- Skip upstream sync cleanly when not in a git repository, when no upstream remote is configured, or in offline unit tests (`TODO_MD_NO_GIT_PULL=1` or stubbed test environments), and fail fast with `die()` if the branch has diverged from upstream so `todo_md` never assigns duplicate task IDs or commits on top of a stale `HEAD`.
- Update `src/rules/todo_md.md`, `README.md`, and `tests/test_commands.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F17: Add CLI prefix legend (F, B, D), remove in-body - Role: overrides, and document prefix/status role resolution — *2026-11-21*

- Coordinate with `F43` and `todo_flow` `docs/adr/0001-prefix-and-status-task-role-resolution.md`:
  - Remove in-body `- Role: <role>` overrides from `resolve_task_role()` in `src/parser.py` so role resolution is strictly prefix- and status-driven (`D*` -> `design`; non-`D` `A-Z` -> `work` in `WIP`/`NEXT` and `plan` in `NEW`/`QUESTION`/`HOLD`).
  - Remove `--role` from `cmd_add()` and `cmd_edit()` in `src/commands.py` (keeping `--role` strictly as a read-only filter on `todo_md`, `chain`, `list`, and `next-id`), and update `todo_md check` (`validate_repo()` in `src/parser.py`) to reject `- Role:` lines in active `TODO.md` files with an error guiding to `D*` prefix (for `design`) or `todo_md next <ID>` (for `work`), exempting historical `TODO_ARCHIVE.md`.
  - Define a canonical prefix metadata table in `src/header.py` describing standard prefixes `F` (feature, default prefix on `add`), `B` (bugfix, priority boost in `chain`), and `D` (design, role `design`), plus custom `A-Z` domain prefixes.
  - Update `cmd_ids` in `src/parser.py` to print a compact prefix legend below `IDs in use: ...`, and summarize the prefix and status-role conventions in `src/header.py` (`--help`).
  - Document standard task ID prefixes (`F`, `B`, `D`), custom `A-Z` prefix conventions, and prefix/status role resolution in `src/rules/todo_md.md`.
  - Clarify in `src/rules/todo_md.md` and `src/bundles/todo_md.bundle` (`[if role=work]`) that `todo_md done <ID>` is executed inside the final commit step (after the edit-and-diff step is verified clean, immediately before staging and `git commit`) rather than during the edit step, and that out-of-scope findings recorded by `role=work` via `todo_md add` are written as problem/impact descriptions in default `NEW` status without `--depends` (staged into the final code commit, or committed immediately with `-c` / `--commit` if recorded after the code commit is already pushed or when no code commit follows).
  - Update `src/bundles/todo_md.bundle`:
    - In `[if role=design]`, instruct that design tasks (`D*`) are closed via `todo_md done <ID>` once architectural invariants are persisted in `AGENTS.md` (and `docs/adr/`) and follow-up implementation tasks are created.
    - In `[if role=plan]`, remove the trailing `once task <ID> is agreed, initialize a new session bundle via todo_md <ID> | agents_bundle | run_block...` instruction so planning sessions finish by committing `TODO*.md` without automatically spawning a new session unless explicitly requested by the user.
  - Rebuild and reinstall via `build.py` and `install.sh`, keep `README.md` and `tests/test_parser.py`, `tests/test_commands.py`, and `tests/test_cli.py` in sync, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F61: Omit default chain: 1 and ready: +0 from -r/--ready task stats — *2026-11-21*

- In `_format_row()` (`src/commands.py`, lines 1275-1340), when `show_downstream=True` (`-r` / `--ready` mode):
  - Append `chain: <N>` to `kv_stats` only when `n_chains > 1` (omitting `chain: 1` for single-chain tasks).
  - Append `ready: +<M>` to `kv_stats` only when `imm_count > 0` (omitting `ready: +0` when no downstream task becomes immediately ready upon completing the task, while still keeping `unblocks: <K>` when `impact > 0`).
- Update `D5` numeric stats description if needed, and update `--ready` format notes in `src/header.py`, `src/rules/todo_md.md`, `README.md`, and unit test assertions in `tests/test_chain.py` (lines 185-270 and 615-800).
- Rebuild via `build.py` and bump `VERSION` for a PATCH release.

# ✅ [DONE] F60: Render work chain finales as top-ranked Chain <N> entries and keep done: <D> exclusively on chain headers — *2026-11-21*

- Depends on: F59
- In `_prepare_active_plan()` and `plan_execution_chains()` (`src/parser.py`):
  - Include `finale_set` roots in `root_nodes` and `root_cones` so single-remaining-task `work` finales render as regular `Chain <N> -> <root_ref>: <root_title> [<pct>% | done: <D>, open: 1]:` entries (naturally receiving `chain_counts[u] == 1` and expanding completed `DONE` prerequisites under the chain header when `--all` is passed) instead of a separate `Chain finales:` section.
  - Prioritize ready `work` chain finales (`root in finale_set and len(comp_open) == 1`) at the top of chain `rank_key` in `_build_chain_entry()` (ordered among work finales by bug priority `B*`, task status `ACTIVE_STATUS_ORDER`, `-done_count`, `order_idx`, and `canon_ref`) so ready `work` finales always appear first as `Chain 1..K`.
  - Keep `finale_set` and `is_fin = 0` in `_node_rank()` so `-r` / `--ready` and `--by-role` continue to rank ready `work` finales first within their status tier while still ranking nodes internally by `-done_counts.get(u, 0)`.
- In `cmd_chain()` and `_format_row()` (`src/commands.py`):
  - Remove the standalone `Chain finales:` rendering section and `finales` list handling.
  - Omit `done: <D>` from per-task `kv_stats` in both default and `-r` / `--ready` views so `done: <D>` remains exclusively a chain/sub-chain header stat (`[<pct>% | done: <D>, open: <O>]:`), leaving task row tags with perks and task-level stats only (`[ready | FINAL]`, `[ready | FINAL | COMBO]`, `[ready | STAGE | unblocks: <K>]`, `[FINAL | chain: <N>]`, `[STAGE | chain: <N>, ready: +<M>, unblocks: <K>]`).
- Update `src/header.py`, `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_chain.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION`.

# ✅ [DONE] F59: Unify task and chain RPG stats ([FINAL | STAGE | COMBO | chain: N, done: D, ready: +M, unblocks: K] and [<pct>% | done: D, open: O]) across Quest-Log views — *2026-11-21*

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

# ✅ [DONE] F54: Support nested .todo_projects orchestrator hierarchies and external project path aliases (e.g. ~/chrome/canary) — *2026-11-21, nested .todo_projects hierarchies and external path aliases*

- In `read_configured_todo_projects()` (`src/parser.py`), recursively expand nested orchestrator projects (tracking `visited_configs: set[Path]` to prevent cycles): when a configured entry (such as `todo_flow`) has its own `.todo_projects` / `.todo_projects.local`, transitively include its child projects (`agents-rules`, `agents_bundle`, `todo_md`, `run_block`) alongside sibling projects (such as `~/chrome/canary`).
- In `discover_orchestrators_for_project()` (`src/parser.py`), walk parent orchestrators transitively to a fixed point so running `todo_md chain` inside a leaf project (`todo_md`) or intermediate orchestrator (`todo_flow`) discovers both the immediate orchestrator and any enclosing meta-orchestrator.
- Preserve configured path aliases for external projects outside `ws_root` (such as `~/chrome/canary` -> `chrome/canary` and `canary`) in `resolve_project_dir()`, `resolve_workspace_chain_projects()`, and `build_execution_chain_dag()` (`_resolve_ref()` and `_format_ref()`) so cross-project references (`chrome/canary:<ID>`) and `-C chrome/canary` resolve cleanly and format as `chrome/canary:<ID>` in `chain` / `Sub-chain` views.
- Add unit tests in `tests/test_chain.py` and `tests/test_deps.py` covering a 3-tier orchestrator hierarchy (`meta_orch` -> `todo_flow` -> leaf repos + external `~/chrome/canary`), update `src/rules/todo_md.md` and `README.md`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F58: Add -r (--ready) short flag, multi-chain & immediate-ready ranking, and explicit ready stats — *2026-11-21*

Enhance `todo_md --ready` (and add the `-r` short flag) so ready tasks are ranked by multi-chain leverage, role execution ease, Quest Momentum continuation, and immediate ready unlocks, and display explicit item-stat counters.

- Short flag `-r` for `--ready` in `src/cli.py` and `src/header.py`:
  - Accept `-r` alongside `--ready` in `_parse_quest_log_args()` (supporting `todo_md -r`, `todo_md -w -r`, `todo_md chain -r`) and in the `list` subcommand parser (`todo_md list -r`).
  - Document `-r, --ready` in `QUEST_LOG_USAGE`, `src/header.py`, `src/rules/todo_md.md`, and `README.md`.
- Multi-chain, role-ease, Quest Momentum, and immediate-ready ranking in `src/parser.py`:
  - In `_prepare_active_plan()`, resolve `latest_done_task` (or accept it from `dag`), identify active root chain cones (`out_deg == 0`, not in `finale_set`, with active or `DONE` prerequisites), and compute for every active node `u`:
    - `chain_count[u]`: number of distinct root chains whose cone includes `u`.
    - `immediate_ready_targets[u]` and `ready_unblocks[u]`: direct active dependents `v` of `u` for which `u` is the sole remaining non-`DONE` prerequisite (`[p for p in prereqs[v] if status(p) != "DONE"] == [u]`).
    - `is_momentum_next[u]`: whether `latest_done_task` is a direct or transitive `DONE` prerequisite of `u` (`0` if true, `1` otherwise) so newly unlocked steps of an in-progress branch surface at the top after `todo_md done`.
  - Update `_node_rank(u)` in `_prepare_active_plan()` to order tasks within each status tier (`ACTIVE_STATUS_ORDER`) by:
    1. `is_fin` (`0` for `finale_set`, `1` otherwise),
    2. `_resolve_node_role_ease(nodes, u)` (`work` -> `plan` -> `design`),
    3. `is_momentum_next[u]` (Quest Momentum continuation after `todo_md done`),
    4. `-chain_count[u]` (tasks shared across more chains first),
    5. `-ready_unblocks[u]` (tasks immediately unlocking more ready tasks first),
    6. `-active_unblocks[u]` (total transitive downstream open cone),
    7. `-ready_step`, `order_idx[u]`, `_canonical_task_ref_key(nodes, u)`.
  - Expose `chain_counts`, `ready_unblocks`, and `immediate_ready_targets` in `_prepare_active_plan()` and `plan_execution_chains()`.
- Explicit stat counters in `cmd_chain()` (`src/commands.py`):
  - When rendering a ready task with `show_downstream=True` and `impact > 0` (not in `finale_set`), format the status tag with explicit counters:
    `[ready | <N> chain(s) | +<M> ready | unblocks <K> -> <targets>]` (using singular `1 chain` and plural `<N> chains`), ordering immediate-ready targets ahead of still-blocked direct dependents after `->`.
- Tests in `tests/test_chain.py` and `tests/test_cli.py`:
  - Cover `-r` short flag in default view, `chain -r`, and `list -r`, multi-chain and `+M ready` priority ordering, role ease ordering (`work` ahead of `design`), Quest Momentum continuation in `-r`, and explicit stat counter formatting.

- Bidirectional DAG chain integration rule in `src/rules/todo_md.md` and `src/bundles/todo_md.bundle`:
  - Update `src/rules/todo_md.md` and the `[if role=plan]` prompt in `src/bundles/todo_md.bundle` to require checking existing open chains in both directions whenever adding or refining a task: upstream prerequisites (`--depends` on the new task) and downstream dependents (`todo_md edit <ID> --depends ...` on existing open tasks, doc/help alignment tasks, or orchestrator waves that touch the same files or build on the new capability) so new tasks are wired into chains rather than left as unintended standalone tasks.

# ✅ [DONE] F55: Unify -s/--search, -f/--filter, -H/--highlight focus toggle, and --all across .todo_projects — *2026-11-21, Unify -s/--search, -f/--filter, -H/--highlight focus toggle, and --all across .todo_projects*

- In `src/cli.py` (`_parse_quest_log_args()`, `_quest_log()`, `QUEST_LOG_USAGE`), `src/parser.py` (`_normalize_target_refs()`, `search_tasks()`), and `src/header.py`:
  - Replace `-f` / `--focus` with `-f <ID>...` / `--filter <ID>...` for filtering by task IDs (case-insensitive `<ID>` or `<project>:<ID>`, space- or comma-separated):
    - A bare `<ID>` without a project prefix (e.g. `todo_md -f F54`) matches all tasks with that ID across all projects in the active view (both unprefixed local `F54` and any `<project>:F54` across `.todo_projects` / `-w`).
    - A project-qualified `<project>:<ID>` (e.g. `todo_md -f todo_md:F54`) matches only the task `<ID>` inside that specific project (`todo_md`).
  - Keep `-s <QUERY>` / `--search <QUERY>` (`todo_md search <QUERY>`) for case-insensitive substring/regex search across task ID (`<ID>` and `<project>:<ID>`), title, and body across all projects in the active view (including all child projects configured in `.todo_projects` when running inside an orchestrator without `-w`), so `todo_md -s F54` inside `todo_flow` finds `todo_md:F54` itself as well as tasks referencing `F54`.
  - Make focusing + highlighting the default behavior when `-s` and/or `-f` is given, and make `-H` / `--highlight` a boolean focus-disabling toggle (so `todo_md -f todo_md:F54 -H`, `todo_md -f F54 -H`, and `todo_md -s F54 -H` render the full Quest-Log with matched tasks highlighted; also accept `todo_md -H <ID>...` when no `-f`/`-s` was passed as shorthand for `-f <ID>... -H`).
- Unify `--all` across Quest-Log, `-s`, and `-f` in `src/cli.py` and `src/commands.py` (`cmd_chain()`, `cmd_list()`, `cmd_workspace_list()`): `--all` always includes both active (`TODO.md`) and archived (`TODO_ARCHIVE.md`) tasks, and focused searches/filters display matched archived `DONE`/`CANCELED` tasks rather than dropping standalone archived tasks or printing the entire archive unfiltered.
- Update `AGENTS.md`, `src/rules/todo_md.md`, `src/header.py`, `README.md`, and unit tests in `tests/test_cli.py` and `tests/test_chain.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ❌ [CANCELED] F3: Clarify repository scope rule in .bundle to target the owning repository — *Already covered by src/rules/todo_md.md and agents-rules:collab/multi-repo; todo_md.bundle is slated for removal in D6*

- Update the repository scope instruction in `src/bundles/todo_md.bundle` (extending what is already in `src/rules/todo_md.md`) to remind agents that each task belongs in its owning repository's `TODO.md` (via `-C`/`<project>` or `<project>:<ID>`), never an unrelated backlog.
- Document task dependencies using `Depends on: <ID>` (same project) or `Depends on: <project>:<ID>` (cross-project orchestrator references, e.g. `agents_bundle:F5`) cleanly in `src/bundles/todo_md.bundle` / `README.md`.

# ✅ [DONE] F50: Unify Quest-Log as default todo_md view with flat chains by default, --tree 4-char connectors, --numbered, multi-ID show, --search, and filters — *2026-11-20*

- Role: work
- Depends on: F53
- Flat topological chains by default, `--tree` / `-t` 4-char connectors, and `--numbered` in `cmd_chain()` (`src/commands.py`):
  - By default (without `--tree`), render each root chain `Chain <N> -> <root_ref>: <root_title> (<total> tasks, <pct>% | <done> done, <open> open):` as a flat topological sequence of tasks in execution order (without tree connectors or nested `Sub-chain ->` headers).
  - When `--tree` (or `-t`) is passed, render the hierarchical milestone tree with nested `Sub-chain ->` headers and 4-character tree connectors (`├── `, `└── `, and `└─► ` for closing tasks) matching the 4-character level indentation (`│   `, `    `) so closing tasks align flush with sibling tasks at the same tree level.
  - Omit row ordinal numbers by default across all Quest-Log sections (`Chain finales:`, `Chain <N> -> ...`, `Standalone tasks:`, `--ready`, and `--by-role`).
  - Add `--numbered` (`--numbered[=left|right]`, default `left`) to render period-free row numbers padded to `num_w = len(str(total_rows))`: `left` (`f"{idx:<{num_w}} {ref}"`) aligns numbers flush after the prefix/connector and pads single-digit numbers before `<ref>` so both numbers and task IDs align vertically; `right` (`f"{idx:>{num_w}} {ref}"`) right-aligns numbers with leading spaces before `<ref>`.
  - Support `-l N` / `--limit N` for row limits (keeping `-n N` as a backward-compatible integer limit alias).
- Default `todo_md` Quest-Log view, multi-ID `show`, `--search`, and unified filters in `main()` (`src/cli.py`, `src/commands.py`, `src/parser.py`):
  - Make `todo_md` with no subcommand (as well as `todo_md -w` and `todo_md <project>`) invoke the Quest-Log view (`cmd_chain`) by default, while `todo_md --full` (or `todo_md overview`) renders the expanded Markdown overview (`cmd_summary` / `cmd_workspace_summary`).
  - Support multiple task IDs in `todo_md <ID1> [<ID2>...]` and `todo_md show <ID1> [<ID2>...]` (space- or comma-separated, including `<project>:<ID>`) to display full task details (`cmd_show`) sequentially separated by a blank line.
  - Add `--search <QUERY>` / `-s <QUERY>` (and `todo_md search <QUERY>`) to search task IDs, titles, and bodies (case-insensitive substring or regex; searching `TODO.md` by default and including `TODO_ARCHIVE.md` when `--all` or an archive/DONE/CANCELED status filter is active): scope and highlight matching tasks in the Quest-Log view by default, or print their full task sections when combined with `--full`.
  - Support `--focus <ID>...` / `-f <ID>...` (and positional `<ID>...` under explicit `todo_md chain [<ID>...]`) to scope the Quest-Log output to the chain(s)/sub-chain(s)/sections containing `<ID>...`, highlight all matched target IDs via `_style_task_row()`, and print `Next actionable: <ref>` when a single `<ID>` is focused.
  - Support `--highlight <ID>...` / `-H <ID>...` to render the full unfiltered Quest-Log while highlighting the specified target `<ID>...`.
  - Support top-level Quest-Log and status filters directly on `todo_md [opts]` and `todo_md chain [opts]` (`--tree` / `-t`, `--status <STATUS>` or status filter keyword `WIP|NEXT|QUESTION|NEW|HOLD|DONE|CANCELED|archive|active|all`, `--all`, `--ready`, `--by-role`, `--role <role>`, `-l N` / `--limit N`, `--numbered[=left|right]`, `--include-hold`), and route `todo_md queue <ID> [--all]` as a CLI alias to `todo_md chain <ID> [--all]`.
- Update the `[if role=plan]` prompt in `src/bundles/todo_md.bundle` to instruct the Planner to decompose or compose (consolidate) work into self-contained tasks in `TODO.md` depending on file, test, and documentation cohesion (refining or merging into an existing open task when changes touch the same files/tests).
- Documentation & tests:
  - Expand `## Product Philosophy & Quest-Log UX` in `AGENTS.md` and update `README.md`, `src/header.py` (`--help`), and `src/rules/todo_md.md` to document the default flat-chain Quest-Log view, `--tree` 4-char connectors, `--numbered`, multi-ID `show`, `--search`, `--focus`/`--highlight`, and status filters.
  - Update and expand unit tests in `tests/test_chain.py` and `tests/test_cli.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F53: Render nested milestone sub-chains and multi-line wrapped tree rows in todo_md chain — *2026-11-20, Render nested milestone sub-chains and multi-line wrapped tree rows in todo_md chain*

- Role: work
- Depends on: F52
- In `src/parser.py` and `cmd_chain()` (`src/commands.py`), detect intermediate milestone / aggregator nodes inside a chain's prerequisite cone (internal nodes that have prerequisites of their own before feeding into downstream tasks, including `DONE` prerequisites when `--all` is active) and render their prerequisite subtrees as indented `├─ Sub-chain -> <milestone_ref>: <title> (<pct>% | <done> done, <open> open):` blocks with tree connectors (`├─`, `│   `, and `└─►` on closing milestone and root rows).
- Extend `_wrap_table_row()` in `src/parser.py` with an optional tree continuation prefix (`cont_prefix`) so all chain and sub-chain tree rows wrap cleanly across multiple lines while preserving active vertical tree bars (`│   `) on wrapped continuation lines without `...` truncation in terminals or pipes.
- Preserve composable row styling (`_style_task_row()` for external-project, `DONE` under `--all`, and target highlighted tasks) across all wrapped lines and tree connectors.
- Update `src/header.py`, `src/rules/todo_md.md`, `README.md`, and `tests/test_chain.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F49: Split monolithic test_todo_md.py into modular tests/test_*.py with tests/helpers.py and full returncode diagnostics — *2026-11-20, Split monolithic test_todo_md.py into modular tests/test_*.py with tests/helpers.py and full returncode diagnostics*

- Role: work
- Create `tests/helpers.py` with `ROOT`, `SCRIPT`, `INSTALL_SH`, and a shared base class `TodoMdTestCase(unittest.TestCase)` that caches the loaded `./todo_md` module once at import/class setup and provides `setUp()`, `tearDown()`, `_table_rows()`, `_assert_ok()`, `_run_subprocess()`, `_run_in_process()`, and `_run()`.
- Update the remaining `self.assertEqual(r.returncode, 0)` assertions that lack a `msg=` argument to either pass `check=True` to `self._run(...)` or include `msg=r.stderr` / `self._assert_ok()`.
- Programmatically slice all 33 `test_*` methods from `tests/test_todo_md.py` via `ast.parse()` (`node.lineno`..`node.end_lineno`) without re-emitting test bodies in chat into focused test modules:
  - `tests/test_cli.py` (`test_help_version_and_agents`, `test_lazy_urllib_import_and_offline_update`, `test_global_project_selector_and_precedence`, `test_install_sh`)
  - `tests/test_parser.py` (`test_init_summary_priority_smart_truncation_and_check`, `test_summary_expands_first_task_when_only_new_or_hold`, `test_single_task_headers_role_and_workdir`, `test_files_budget_options`, `test_check_detects_stale_completion_date_note_on_active_tasks`, `test_tabular_column_wrapping_and_emoji_alignment`, `test_composable_task_styling_in_chain_and_list`)
  - `tests/test_commands.py` (`test_add_edit_append_cli`, `test_status_ordering_and_archive_prepend`, `test_git_default_no_commit_and_opt_in_commit`, `test_next_id_files_and_pipe_output`, `test_last_last_id_and_list_options`, `test_body_dash_stdin_and_tty_error`, `test_forbid_implicit_reopen_and_reopen_command`, `test_list_role_display_and_filter`, `test_list_rejects_retired_tree_flag`)
  - `tests/test_deps.py` (`test_workspace_discovery_addressing_and_depends`, `test_dependency_sequencing_queue_next_id_and_cycles`, `test_list_topo_order_blocked_next_badges_and_ready_filter`, `test_done_prints_newly_unblocked_local_and_orchestrator_tasks`)
  - `tests/test_chain.py` (`test_chain_command_local_workspace_hold_and_diagnostics`, `test_chain_critical_path_ranking_ready_filter_and_standalone_grouping`, `test_chain_role_badges_and_role_filter`, `test_chain_by_role_queues_and_composition`, `test_chain_ready_downstream_targets`, `test_chain_finales_section_ranking_and_after_tags`, `test_chain_rpg_progress_transitive_done_bug_and_role_ranking`, `test_chain_todo_projects_orchestrator_dag_child_scoping_cwd_refs_and_ansi_dimming`, `test_root_anchored_chains_quest_momentum_also_in_and_all_done_tasks`)
- Remove monolithic `tests/test_todo_md.py`, document the modular `tests/` layout in `AGENTS.md`, and verify `python3 -m unittest discover -s tests` runs all 33 tests with zero warnings.

# ✅ [DONE] F52: Build root-anchored chains with monotonic Quest Momentum ranking, [also in: ...] annotations, and --all dimmed DONE tasks — *2026-11-20*

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

# ✅ [DONE] F38: Unify composable task styling (external project, DONE, and multi-ID target highlight) in todo_md chain and list — *2026-11-20, Unify composable task styling in chain and list*

- Depends on: F51
- Update `main()` in `src/cli.py` to accept one or more optional task references `<ID>...` (or `<project>:<ID>...`, space- or comma-separated and resolved via `resolve_project_task_ref()`) on `chain` (`todo_md chain [<ID>...] ...`) and `list` (`todo_md list [<filter>] [<ID>...] ...`).
- Define a unified, orthogonal TTY-aware ANSI styling helper (`_style_task_row()` in `src/parser.py`, active when `sys.stdout.isatty()` and `NO_COLOR` is unset, or `FORCE_COLOR` is set; plain text in pipes) so three visual modes compose simultaneously without conflict and without affecting `_display_width()` / `_wrap_table_row()` alignment:
  1. External-project task (`is_external=True`): dim italic (`\033[2;3m`, or `\033[2;3;90m` when also `DONE`).
  2. Completed task (`is_done=True`, status `✅ [DONE]`): dim gray (`\033[2;90m`).
  3. Target highlighted task (`is_highlighted=True`, matching any requested `<ID>`): bold bright yellow (`\033[1;93m`, or bold italic bright yellow `\033[1;3;93m` when also `is_external=True`, preserving the `✅ [DONE]` badge when `is_done=True` so highlight never gets swallowed by dim).
- In `cmd_chain()` (`src/commands.py`), apply `_style_task_row()` across task rows (`finales`, `chains`, `standalone`, `--ready`, `--by-role`) and `Held branches:` tokens, and highlight enclosing `Chain <N> ...:` headers when any target task belongs to that chain.
- In `cmd_list()` and `cmd_workspace_list()` (`src/parser.py`), highlight all matching target `<ID>...` rows via `_style_task_row()` (and dim `DONE` rows when listing `all` or `archive`).
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ❌ [CANCELED] F37: Document Quest-Log chain, side-quest, and priority concepts in AGENTS.md and README.md — *Merged into F50*

- Role: work
- Depends on: F50
- Expand `## Product Philosophy & Quest-Log UX` in `AGENTS.md` to define `Chain finales` (ready `work` finale quests whose prerequisite chain is already `DONE`, surfaced first for maximum completion payoff), root-anchored `Chain <N> -> <root_ref>: <root_title>` questlines with nested `Sub-chain` milestones and RPG progress stats (`<total> tasks, <pct>% | <done> done, <open> open`), `Standalone tasks` (side quests ordered by bugs `B*` first, role execution ease `work` -> `plan` -> `design`, then status), `Held branches` (locked branches waiting on `HOLD` conditions), and monotonic Quest Momentum ranking (in-flight `WIP` or most-recently-completed `DONE` affinity, started-chain status floor, whole-cone bug/effort metrics, and immutable root tie-breaker in `plan_execution_chains()`).
- Add a concise Quest-Log summary in `README.md` explaining `chain`, `queue`, and `done` progression for users (keeping `src/rules/todo_md.md` lean without narrative metaphors).

# ✅ [DONE] F51: Retire todo_md list --tree so todo_md list stays a flat table and todo_md chain is the single tree view — *2026-11-20, Retire list --tree and dead tree helpers*

- Remove `--tree` option parsing from `list` in `main()` (`src/cli.py`) and remove the `tree: bool = False` branch from `cmd_list()` and `cmd_workspace_list()` in `src/parser.py`.
- Remove dead `--tree` helpers and constants (`_build_tree_entries()`, `_render_tree_lines()`, `_truncate_display()`, `MIN_TREE_TITLE_COLS`) from `src/parser.py` / `src/header.py`.
- Update `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` to remove `list --tree` references, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F43: Implement status-aware task role fallback, promotion transition, and role validation — *2026-11-20*

- Role: work
- Implement the status-aware role assignment and validation contract from `todo_flow` (`docs/adr/0001-task-role-assignment-and-status-fallback.md`):
  1. Status-aware role fallback (`src/header.py`, `src/parser.py`): set `PREFIX_DEFAULT_ROLES = {"D": "design"}` (removing `"F": "work"` and `"B": "work"`). Update `resolve_task_role(task_id, section_text, status=...)` (and callers across `show`, `list`, `chain`, `next-id`) so explicit `- Role: <role>` always wins (normalized to lowercase); when omitted, `D*` resolves to `"design"`, and any non-`D` prefix (`F`, `B`, or custom `A-Z`) resolves to `"work"` when status is `WIP` or `NEXT` and to `"plan"` when status is `NEW`, `QUESTION`, or `HOLD`. Ensure `todo_md <ID>` (`show`) always emits `Role: <role>` in its preamble.
  2. Promotion transition & CLI role normalization (`src/commands.py`): normalize `--role` values in `_normalize_role_arg()` to lowercase and validate against `^[a-z][a-z0-9_-]*$` (rejecting retired roles `execute` and `audit` with a clear hint to use `work` or `review`). When promoting a task to `NEXT` via `todo_md next <ID>` (or `todo_md status <ID> NEXT`), remove an existing `- Role: plan` line from the task body so the promoted non-`D` task resolves to `work` automatically.
  3. Active backlog validation (`validate_all()` in `src/parser.py`): in `TODO.md` (excluding historical `TODO_ARCHIVE.md`), report an error if a task contains multiple `- Role:` lines, a `- Role:` value not matching `^[a-z][a-z0-9_-]*$`, or a retired role name (`execute` -> `work`, `audit` -> `review`).
  4. Pipe deduplication & rule sync (`src/bundles/todo_md.bundle`, `src/rules/todo_md.md`): guard `$ todo_md {task:}` with `[if piped!=1]` in `src/bundles/todo_md.bundle` so `todo_md <ID> | agents_bundle | run_block` does not print the task twice, and document the status-aware role fallback, `todo_md next <ID>` transition, and role-agnostic pipe auto-consumption in `src/rules/todo_md.md` and `README.md`.
- Update `tests/test_todo_md.py`, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F48: Integrate .todo_projects orchestrator DAG into todo_md chain and dim external-project tasks in project-scoped views — *2026-11-20, Integrate .todo_projects orchestrator DAG into todo_md chain and dim external-project tasks*

- Role: work
- When `todo_md chain` runs inside an orchestrator repository containing `.todo_projects` (or `.todo_projects.local` / `TODO_MD_PROJECTS`), automatically build execution chains across the orchestrator and all configured projects from `.todo_projects` by default (without requiring `-w`), and filter `todo_md chain -w` discovery to `.todo_projects` when present.
- When `todo_md chain` targets a child project (either run directly inside `<child>` or via `todo_md -C <child> chain` / `--project <child>`), automatically discover any workspace orchestrator whose `.todo_projects` lists `<child>` and merge the orchestrator's cross-project dependency edges into `build_execution_chain_dag()` (`src/parser.py`) so child tasks (such as `run_block:F72`) reflect their real orchestrator prerequisites (`[blocked by: todo_flow:D8, todo_flow:F4]`) and join their full chain instead of appearing as `[ready]` standalone tasks.
- In project-scoped `cmd_chain()` views (`src/commands.py`), filter displayed `Chain finales:`, `Chain 1..N`, `Standalone tasks:`, `Ready tasks:`, `Queues:`, and `Held branches:` to only chains and tasks containing at least one task from the target project.
- Format task references in `build_execution_chain_dag()` / `cmd_chain()` relative to the caller's actual current working directory (`Path.cwd().resolve()`): omit the `<project>:` prefix for tasks belonging to `Path.cwd()` when run directly inside that project directory (`F72`), and keep the `<project>:<ID>` prefix (`run_block:F72`) when targeting the project from outside via `-C` / `--project` so IDs are always ready for copy-paste in the current shell directory.
- Visually distinguish target-project tasks from external-project tasks inside displayed chains: render tasks belonging to the target project in normal/bright text, and dim tasks from other repositories in the same chain using ANSI dim styling (`\033[2m...\033[0m` when `sys.stdout.isatty()` and `NO_COLOR` is unset, or `FORCE_COLOR` is set; plain text in pipes) without shifting `_display_width()` / `_wrap_table_row()` column alignment (coordinating with `F38`).
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F47: Restrict Chain finales to work tasks and rank chains by role-weighted velocity (work=1, plan=2, design=5) — *2026-11-20, Restrict Chain finales to work tasks and rank chains by role-weighted velocity*

- Role: work
- Define `ROLE_EFFORT_WEIGHTS` in `src/header.py` mapping task roles to expected implementation-task equivalents (`"work": 1`, `"plan": 2`, `"design": 5`, with unknown/unannotated roles defaulting to `5`) alongside `ROLE_EASE_ORDER`.
- Restrict `finale_set` and `Chain finales:` in `_prepare_active_plan()` and `plan_execution_chains()` (`src/parser.py`) strictly to ready leaf tasks (`active_unblocks == 0`) that have completed `DONE` prerequisites (`done_prereqs` or `done_nodes`) AND resolve to `role == "work"`. Within `Chain finales:`, sort by bug priority (`B*` first), active status tier, descending `done_count` (`-len(done_nodes)` so finales of longer completed chains rank above 2-task chains), `order_idx`, and canonical task ref.
- Keep standalone tasks with no open or completed dependencies (`open_count == 1` and `done_count == 0`) in `Standalone tasks:` regardless of role (`work`, `plan`, or `design`).
- When a connected component has `open_count == 1` and `done_count >= 1` (`total_tasks >= 2`) but its sole remaining open task has role `plan` or `design` (not `work`), place it in regular numbered chains (`Chain 1..N`) instead of `Chain finales:`, while preserving the `[ready | after: ...]` tag in `cmd_chain()` (`src/commands.py`) for any ready task with completed `DONE` prerequisites and no downstream open dependents.
- Update `_build_chain_entry()` in `src/parser.py` to compute role-weighted remaining effort for each chain (`remaining_effort = sum(_resolve_node_role_weight(nodes, u) for u in comp)` using `work=1`, `plan=2`, `design=5`) and incorporate role-weighted completion velocity / effort (`-done_count / (done_count + remaining_effort)` and `remaining_effort`) into `rank_key` so chains burdened by `design` or `plan` tasks rank lower than fast `work` chains.
- Update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` (`test_chain_finales_section_ranking_and_after_tags`, `test_chain_rpg_progress_transitive_done_bug_and_role_ranking`), rebuild `./todo_md` via `build.py`, and bump `VERSION` for a MINOR release.

# ✅ [DONE] F46: Number execution chains with RPG progress stats and rank chains and standalone tasks by bugs, role ease, and total value — *2026-11-20, Numbered RPG progress chain headers and deterministic bug/role/value chain ranking*

- Role: work
- In `build_execution_chain_dag()` (`src/parser.py`), recursively traverse `- Depends on:` clauses of `DONE` prerequisites (across both local `TODO_ARCHIVE.md` and cross-project `<project>:<ID>` archives in `-w` workspace mode) while excluding `CANCELED` and `MISSING` tasks, recording the transitive `DONE` node set (`done_nodes`) for each active task and connected chain component.
- Make connected-component traversal and DAG ordering in `build_execution_chain_dag()` and `plan_execution_chains()` (`src/parser.py`) strictly deterministic by sorting `undirected` neighbors and tie-breakers with a canonical task reference key rather than relying on Python `set` iteration order.
- Compute non-decreasing chain value and RPG progress metrics for each chain in `plan_execution_chains()` (`src/parser.py`): `open_count`, `done_count` (unique transitive `DONE` tasks linked to the chain), `total_tasks = done_count + open_count`, `progress_pct = round(100 * done_count / total_tasks)`, bug metrics (`ready` `B*` count, `total_bugs = open_bugs + done_bugs`, minimum dependency distance to an open `B*` task), and role execution ease (`work` < `plan` < `design` < other, based on the ready step role and remaining open task roles).
- Rank chains deterministically in `plan_execution_chains()` by: (1) bug priority (ready `B*` task, `total_bugs`, shortest distance to open `B*`), (2) role execution ease (`work` before `plan` before `design`), (3) highest active status (`WIP` -> `NEXT` -> `QUESTION` -> `NEW`), (4) non-decreasing chain value (`-total_tasks`) and completion progress (`-done_count`), and (5) canonical `ref`.
- Sort `Standalone tasks:` (and `Chain finales:`) in `plan_execution_chains()` (`src/parser.py`) with bug tasks (`B*`, matched on task `id` in both local and `-w` `<project>:<ID>` modes) always at the top, then by role ease (`work` -> `plan` -> `design` -> other), then by status (`WIP` -> `NEXT` -> `QUESTION` -> `NEW` -> `HOLD`), then `order_idx` and canonical `ref`.
- In `cmd_chain()` (`src/commands.py`), replace verbose duplicate `Chain: A -> B -> C` headers with numbered RPG progress headers `Chain <N> (<total> tasks, <pct>% | <done> done, <open> open):`.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh`), and bump `VERSION` for a MINOR release.

# ✅ [DONE] B1: Filter todo_md next-id by --role and readiness and pass --role work in todo_md.bundle — *2026-11-20*

- Role: work
- Update `resolve_top_task_id()` and `cmd_next_id()` (`src/commands.py`) and CLI parsing in `main()` (`src/cli.py`) to accept `--role <role>` (and `--role=<role>`) on `todo_md next-id`, and ensure `resolve_top_task_id()` skips tasks with unresolved `- Depends on:` blockers as well as tasks not matching `--role` when specified.
- Update `src/bundles/todo_md.bundle` (`[if role=work]`) to invoke `var task=$(todo_md next-id --role work)` so `role=work` never auto-selects or transitions `design` or `plan` tasks (or blocked tasks) to `WIP`.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh`), and bump `VERSION` for a MINOR release.

# ❌ [CANCELED] D4: Design named execution chains, milestone sub-grouping, and questline clarity in todo_md chain — *Superseded by F46 numbered RPG progress headers and invariant chain value ranking*

- Role: design
- Explore adding human-readable names to `todo_md chain` headers (both automatic derivation from a chain's terminal goal task title when unique and an optional explicit `- Chain: <name>` / `--chain` metadata field as override) instead of printing only long `A -> B -> C` ID lists.
- Evaluate splitting or labeling large merged weakly-connected components (such as multi-wave orchestrator DAGs) by milestone/goal sub-chains (`wave` / `queue`-style subtrees) and distinguishing quick `work` side-quests from `design` tasks in `Standalone tasks:`.
- Define optional filtering by chain name (`todo_md chain "<name>"`) and coordinate questline naming conventions with `AGENTS.md` Quest-Log UX (`F37`) and orchestrator wave summaries.
- Target files for downstream implementation: `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# ✅ [DONE] F45: Show chain finales with all dependencies resolved first in todo_md chain — *2026-11-20, Surface chain finales first with [ready | after: ...] in todo_md chain*

- Role: work
- Track resolved (`DONE`) prerequisites per active node (`done_prereqs`) in `build_execution_chain_dag()` (`src/parser.py`) when traversing `- Depends on:` clauses instead of discarding them without trace.
- In `_prepare_active_plan()` and `plan_execution_chains()` (`src/parser.py`), classify single-node active components (`len(comp) == 1`) that have resolved `DONE` prerequisites and no open blockers into a dedicated `finales` list (separate from `standalone` tasks that never had dependencies), and rank ready chain finales first within their status tier in `_node_rank()` across default `chain`, `--ready`, and `--by-role` modes.
- In `cmd_chain()` (`src/commands.py`), render `Chain finales:` as the very first section (before `Chain: ...` and `Standalone tasks:`), format their status tag as `[ready | after: <ref>, ...]` (showing up to 3 resolved prerequisite refs with `...` truncation) across `chain`, `--ready`, and `--by-role`, and apply `--role` and `--limit` filters consistently starting from `Chain finales:`.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh`), and bump `VERSION` for a MINOR release.

# ✅ [DONE] F36: Remove bundle vitalio/run_block from .agents_bundle — *2026-11-19*

- Remove `bundle vitalio/run_block` from `.agents_bundle` once `run_block` embeds its own block execution rules.

# ✅ [DONE] F16: Migrate workflow bundle and docs from role=execute and role=audit to role=work and role=review — *2026-11-19, migrated workflow bundle, rules, and tests to role=work and role=review*

- Update `src/bundles/todo_md.bundle`, `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` to use `role=work` and `role=review` instead of `role=execute` and `role=audit` once the role rename lands in `agents-rules` (coordinated in `todo_flow`, preserving legacy aliases only if needed during transition).
- Rebuild and reinstall `todo_md` and release a PATCH version.

# ❌ [CANCELED] F14: Clarify in todo_md rule that backlog-only commits in plan/design/review run in the same block without a separate diff-review turn — *Avoid blanket same-block commits without diff review; checking diff prevents committing unintended backlog or index changes*

- Update the `Validation & commits` section in `src/rules/todo_md.md` to explicitly state that in `role=plan`, `role=design`, and `role=audit`/`role=review`, `todo_md` mutations can be batched and committed in the same execution block (via `-c` on the final `todo_md` command or `git add TODO*.md && git commit`) without waiting for a separate diff-review turn.
- Rebuild and reinstall `todo_md` (and keep any synced docs/tests in `tests/` green) so exported rules reflect the updated wording.

# ✅ [DONE] F41: Show downstream next tasks in todo_md chain --ready output — *2026-11-19, Show downstream unblocked targets in chain --ready output*

- Role: work
- Update the `ready` rendering branch in `cmd_chain()` (`src/commands.py`) using `dependents` from `build_execution_chain_dag()` (`src/parser.py`) so each ready row with `[unblocks N]` also displays its immediate (or downstream) unblocked targets (for example `[ready | unblocks 3 -> F54, F68, ...]` or `leads to: ...`), giving chain continuation context without leaving `--ready`.
- Keep `src/header.py` (`--help`), `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py`, and bump `VERSION` for a PATCH release.

# ✅ [DONE] F40: Add --by-role execution queue mode to todo_md chain — *2026-11-19*

- Role: work
- Add a role-tiered queue planner helper (e.g. `plan_execution_chains_by_role()` in `src/parser.py`) over `build_execution_chain_dag()` that partitions active non-held tasks into four topologically sorted queues:
  1. `Queue 1 (work)`: `role == "work"` with no open transitive dependencies or all transitive dependencies also in `work`.
  2. `Queue 2 (plan)`: `role == "plan"` with no open transitive dependencies or transitive dependencies in `work`/`plan`.
  3. `Queue 3 (design)`: `role == "design"`.
  4. `Queue 4 (deferred work)`: remaining `work` tasks blocked by `plan`/`design` prerequisites (omitted when `--ready` is active).
- Add `--by-role` option to `todo_md chain` in `main()` (`src/cli.py`) and `cmd_chain()` (`src/commands.py`), reusing `_format_row()` (`[role]`, `[ready]` / `[blocked by: ...]`, `[unblocks N]`) and composing cleanly with `-w`, `--ready`, `--role`, `--limit`, and `--include-hold`.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh` if applicable), and bump `VERSION` for a MINOR release.

# ✅ [DONE] F39: Display role badges in todo_md chain and add --role filter — *2026-11-18*

- Role: work
- Update `cmd_chain()` (`src/commands.py`) to display a padded `[role]` column (reusing `_task_role_badge()` from `src/parser.py`, matching `cmd_list()` / `cmd_workspace_list()`, and leaving it blank for `MISSING` placeholders where `exists` is false) across `Chain:`, `Standalone tasks:`, and `--ready` rows while preserving `_wrap_table_row()` alignment.
- Add `--role <role>` (and `--role=<role>`) option to `todo_md chain` in `main()` (`src/cli.py`) and `cmd_chain()` (`src/commands.py`), filtering displayed tasks via `_task_matches_role()` (e.g. `todo_md chain -w --role work --ready` or `--role plan`) while keeping DAG validation and unblock context clear.
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, rebuild `./todo_md` via `build.py` (and reinstall via `install.sh` if applicable), and bump `VERSION` for a MINOR release.

# ✅ [DONE] F35: Wrap long descriptions into aligned table columns in list, chain, queue, and projects — *2026-11-18, Wrap tabular descriptions into aligned columns across list, chain, queue, and projects*

- Add a shared Unicode-aware column-wrapping helper in `src/parser.py` built on `_get_terminal_columns()`, `_display_width()`, and `_pad_display()` so fixed left columns remain on the first line while the trailing description column wraps at word boundaries with a hanging indent aligned to the description column start.
- Replace raw Python string width formatting (`f"{badge:<14}"`) with display-width padding (`_pad_display`) across tabular outputs so two-column status emojis align cleanly across rows.
- Apply tabular column wrapping to `todo_md list` and `todo_md list -w` (`src/parser.py`), `todo_md chain` and `todo_md chain -w` (`src/commands.py`), `todo_md queue` (`src/commands.py`), and `todo_md projects` (`src/parser.py`), falling back to a compact 4-space continuation indent when terminal width leaves fewer than 20 columns for the description column.
- Keep `todo_md list --tree` single-line truncated, full Markdown section views (`overview`, `show`, `last`, `archive`) unwrapped, and machine-readable commands (`files`, `next-id`, `last-id`, `ids`) single-line per item.
- Sync CLI help and documentation in `src/header.py` and `README.md`, rebuild/reinstall via `build.py` and `install.sh`, and add unit tests in `tests/test_todo_md.py`.

# ✅ [DONE] F32: Add --tree view to todo_md list with terminal-width title truncation — *2026-11-18, Add --tree dependency hierarchy view to list with terminal-width truncation*

- Role: work
- Depends on: F31
- Add `--tree` option to `todo_md list` in `src/cli.py`, `src/parser.py`, and `src/header.py` (`-h`/`--help`) to render active dependency chains as an indented hierarchy (`└─` / `├─`) with prerequisites placed above their blocked dependents across status buckets.
- Detect terminal width via `shutil.get_terminal_size` (with a sensible non-TTY fallback) to truncate task titles with `...` so rows stay on a single line, and fall back to compact ID-only tree lines when the terminal is too narrow to show titles cleanly.
- Update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` covering `--tree`, multi-step chains, shared dependencies, and narrow-terminal truncation and ID-only fallback.

# ✅ [DONE] F25: Detect stale completion date notes on active tasks in todo_md check — *2026-11-18, reject stale completion date notes on active tasks in check*

- Extend `validate_all` in `src/parser.py` so `todo_md check` (and automatic post-mutation validation) reports an error when an active task in `TODO.md` retains a completion date stamp (`— *YYYY-MM-DD...*`) in its heading, instructing the user to move it back to `TODO_ARCHIVE.md` or clear the stale note.
- Target files: `src/parser.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# ✅ [DONE] F34: Rank ready tasks by unblock impact in chain and print newly unblocked tasks on done — *2026-11-18, Rank ready tasks by unblock impact in chain and print newly unblocked tasks on done*

- Add `--ready` filtering and critical-path impact ranking (number of transitively unblocked downstream tasks, plus `[unblocks N]` annotations) to `todo_md chain` in `src/parser.py`, `src/cli.py`, and `src/header.py` (`-h`/`--help`) so the highest-leverage ready tasks appear first.
- Separate connected dependency chains from standalone tasks without dependencies in `todo_md chain` (`src/parser.py`) so independent tasks are not falsely joined with `->` arrows in `Chain:` headers and are grouped clearly as connected chains vs standalone tasks.
- Extend `cmd_done` in `src/commands.py` (and `src/parser.py`) to detect and print any open tasks in the current repository (and in a workspace orchestrator `.todo_projects` when present) whose dependencies just became completely `DONE` (`Unblocked: ...`).
- Keep `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` in sync.

# ✅ [DONE] F33: Add todo_md chain command for local and cross-project execution order — *2026-11-18, Add todo_md chain command for local and cross-project execution order*

- Role: work
- Add `todo_md chain [--limit N] [--include-hold]` (supporting `-w` / `--workspace` and `-C` / `--project`) in `src/parser.py`, `src/commands.py`, `src/cli.py`, and `src/header.py`.
- Build a unified dependency DAG across all open non-`HOLD` tasks in the target project (resolving transitive `<project>:<ID>` prerequisites) or across all discovered workspace projects when `-w` is set, printing a compact `A -> B -> C` chain summary followed by ordered task rows (truncated to the first `N` tasks when `--limit N` is passed).
- Exclude `HOLD` tasks and tasks transitively blocked by `HOLD` from the main chain by default, rendering frozen chains under a separate `Held branches:` section (e.g., `H1 (HOLD) -> F2 (NEW)`), and include them in the main chain when `--include-hold` is passed.
- Report clear diagnostics on dependency cycles, syntax errors, or `MISSING` / `CANCELED` blockers, and update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py`.

# ✅ [DONE] F31: Show full unblock chain and blocked WIP badge in todo_md list — *2026-11-18, Show full unblock chains and blocked WIP badges in list*

- Role: work
- Update `_task_dependency_info` in `src/parser.py` so multi-step unresolved dependency chains render the full ordered path from the ready root to the direct blocker (for example `[blocked: F21 (WIP) -> F22 (NEXT) -> F23 (WIP)]`) instead of truncating intermediate tasks with `<- start: <ID>`, while keeping `[blocked: <ID> (<STATUS>)]` for single-hop blockers.
- Update `cmd_list` and `cmd_workspace_list` in `src/parser.py` to display `⏳ [WIP]` (matching `⏳ [NEXT]`) whenever a `WIP` task has unresolved dependencies.
- Update `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` to cover full chain formatting and blocked `WIP` badges.

# ✅ [DONE] F30: Emit Title header in todo_md show preamble for downstream bundle and TUI display — *2026-11-18*

- Emit `Title: <base_title>` in `cmd_show` (`src/commands.py`) immediately after `Task: <ID>`, stripping any trailing `— *note*` via `_strip_heading_note` so `Task:` stays the bare ID while `Title:` carries the clean task summary.
- Sync `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, and rebuild `todo_md` via `python3 build.py`.

# ✅ [DONE] F20: Add global -C/--project target option across all todo_md subcommands — *2026-11-18*

- Add a global project/directory selector (`-C <dir|project>` and `--project <name>`, keeping `-p` in `add` for prefix) accepted before subcommands so any `todo_md` command (`ids`, `list`, `archive`, `last`, `last-id`, `next-id`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`, `done`, `cancel`, `show`) can target a repository from any directory.
- Resolve `-C` targets as either a filesystem directory path or a discovered workspace project name/relative path (from `.todo_projects` / workspace root), failing explicitly with a non-zero exit code when the target cannot be resolved.
- Keep `<project>:<ID>` strictly for task-level references (`show`, `edit`, `done`, `Depends on:`), and define explicit precedence (`-C`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory).
- Update `src/cli.py`, `src/header.py`, `README.md`, `src/rules/todo_md.md`, and `tests/test_todo_md.py` in sync.

# ✅ [DONE] F29: Lazy-import urllib.request in src/cli.py to reduce CLI startup latency — *2026-11-17, lazy-import urllib.request*

- Move `import urllib.request` out of top-level `src/header.py` into `fetch_remote_script` in `src/cli.py` so regular commands (`--version`, `check`, `add`, `list`, etc.) avoid importing `urllib.request`, `http.client`, and `ssl` (~21 ms startup overhead).
- Rebuild standalone `todo_md` via `python3 build.py`, verify `python3 build.py --check`, reinstall locally via `sh install.sh --yes`, and add an offline unit test in `tests/test_todo_md.py` confirming `urllib.request` is not imported on normal commands while `update` / `check-update` behavior remains intact.
- Target files: `src/header.py`, `src/cli.py`, `todo_md`, `tests/test_todo_md.py`.

# ✅ [DONE] F28: Speed up unit tests by running CLI calls in-process — *2026-11-17, in-process CLI test runner*

- Load the built `todo_md` script once per test class (e.g. in `setUpClass` via `importlib.machinery.SourceFileLoader`) and execute `main(argv)` in-process inside `tests/test_todo_md.py` with isolated `stdout`, `stderr`, `stdin`, `cwd`, and `os.environ` instead of spawning nearly 300 `subprocess.run` processes.
- Keep real `subprocess.run` coverage for executable entrypoint and environment integration tests (`-h`, `--version`, `pty` TTY error handling, `git` `--commit`, and `install.sh`).
- Verify `python3 -m unittest discover -s tests` passes cleanly with zero `ResourceWarning`s and completes in under 2 seconds.
- Target files: `tests/test_todo_md.py`.

# ✅ [DONE] F27: Order list output topologically by dependencies, highlight blocked NEXT tasks, and add --ready filter — *2026-11-17*

- Depends on: F21, F22
- Order tasks topologically within each status bucket in `_order_active_tasks_for_list` (`src/parser.py`) and `_sort_todo_file` (`src/commands.py`) so prerequisites always appear before dependent tasks regardless of `todo_md next` promotion order (falling back to file order if a cycle exists).
- Place unblocked (`ready`) tasks before tasks with open blockers within `NEXT` (and other active status buckets), and render blocked `NEXT` items with `⏳ [NEXT]` in `todo_md list` and `todo_md list -w` without altering `TODO.md` headings.
- Display dependency status badges (`[blocked: ...]` / `[deps: DONE]`) in `todo_md list -w` matching local `todo_md list`, and append the actionable root blocker (`<- start: <ID>`) when blocked by a multi-step chain.
- Add `--ready` option to `todo_md list` (`src/cli.py`, `src/commands.py`, `src/parser.py`) to filter active tasks to those with no unresolved dependencies (working across local and `-w` workspace modes).
- Keep `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py` in sync, and rebuild `todo_md` via `python3 build.py`.

# ✅ [DONE] F22: Remove reverse ordering of QUESTION/NEW/HOLD tasks in todo_md list — *2026-11-17*

- Remove `reversed(bucket)` for `QUESTION`, `NEW`, and `HOLD` in `_order_active_tasks_for_list` (`src/parser.py`) so `todo_md list` and `todo_md list -w` display active tasks in exact `TODO.md` file order (top to bottom).
- Preserve existing `resolve_last_task_id` behavior (`last`, `last-id`, `show last`).
- Update `test_last_last_id_and_list_options` in `tests/test_todo_md.py` (and any synced docs in `README.md` / `src/header.py` if needed).
- Rebuild `todo_md` with `python3 build.py` and verify with `python3 -m unittest discover -s tests`.

# ✅ [DONE] F21: Implement dependency sequencing (->), queue, and next-id resolution — *2026-11-17*

- Implement sequential stage syntax (`->`) alongside parallel commas (`,`) in `- Depends on:` and `--depends`: `,` binds tighter than `->` (`A, B -> C`), and multiple `- Depends on:` lines (or repeated `--depends`) represent independent branches combined with AND; do not introduce a separate `- Order:` field.
- Merge explicit `->` stage edges on the target task with transitive `- Depends on:` edges across intra-project and workspace `<project>:<ID>` tasks into a unified DAG (preserving one-way repo boundaries for cross-project orchestrators).
- Treat `DONE` as unblocking and `CANCELED` / `MISSING` as blocking; upgrade `todo_md check` (`validate_all`) to validate `,`/`->` syntax and detect transitive dependency cycles.
- Render sequential chains in `Dependencies (ready|blocked): ...` using ASCII `->` for sequential edges, `, ` for parallel siblings, and `; ` between independent clauses.
- Add `todo_md queue <ID> [--all]` to display the stable topologically sorted execution queue (hiding `DONE` by default unless `--all` is passed) with `[ready]` / `[blocked by: ...]` markers and `Next actionable: <ref>`.
- Extend `todo_md next-id [<ID>]` to accept an optional `<ID>` (or `<project>:<ID>`) and print the first unblocked actionable task ID in `<ID>`'s queue (or `<ID>` itself when all deps are `DONE`), exiting non-zero on cycles, missing/canceled blockers, or already-closed targets.
- Update `src/rules/todo_md.md` to specify the `--depends` contract (`A,B` vs `"A -> B -> C"`, no `- Order:`, one-way boundaries) and `queue` / `next-id <ID>` usage.
- Target files: `src/header.py`, `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# ✅ [DONE] F26: Display resolved task role and support --role filter in todo_md list — *2026-11-17*

- Display the resolved role (`resolve_task_role` in `src/parser.py`, e.g. `[design]`, `[work]`, or explicit `- Role:` value) in compact `cmd_list` and `cmd_workspace_list` rows (`todo_md list` and `todo_md list -w`) alongside status and location.
- Add `--role <role>` filtering to `todo_md list` and `todo_md list -w` in `src/cli.py`, `src/parser.py` (`cmd_list`, `cmd_workspace_list`), and `src/header.py` (matching case-insensitively against `resolve_task_role`).
- Keep `src/rules/todo_md.md` and `README.md` in sync, add unit tests in `tests/test_todo_md.py`, and rebuild `todo_md` via `python3 build.py`.

# ✅ [DONE] F15: Limit todo_md files preloading by line and byte budget — *2026-11-17*

- Add optional per-file and total budget flags to `todo_md files [<ID>]`
  (e.g., `--max-lines N`, `--max-total-lines N`, `--max-bytes N`) in
  `src/commands.py` (`cmd_files`), `src/cli.py`, and `src/header.py`, keeping
  bare `todo_md files [<ID>]` backward-compatible with no cap by default.
- Update `src/bundles/todo_md.bundle` (`role=execute` and `role=audit`) to
  pass sensible size limits to `todo_md files {task:}` so small target files
  are preloaded while large files are left for selective `grep`/`sed` reads.
- Clarify in `src/bundles/todo_md.bundle` (`role=plan`) and
  `src/rules/todo_md.md` that task bodies should reference target file paths
  and key symbol names (functions/classes) in backticks rather than brittle
  line ranges.
- Sync `README.md` and add unit tests in `tests/test_todo_md.py` covering
  per-file and total budget filtering.

# ✅ [DONE] F24: Forbid implicit reopening of archived tasks (--reopen and todo_md reopen) — *2026-11-17, forbid implicit reopening, add --reopen and reopen*

- Reject transitions from `TODO_ARCHIVE.md` (`DONE` or `CANCELED`) to active statuses (`WIP`, `NEXT`, `NEW`, `HOLD`, `QUESTION`) in `status` and `next` (and reject re-archiving already archived tasks in `done`, `cancel`, and `archive <ID>`) unless `--reopen` is explicitly passed, exiting non-zero with the current archived status, closing note, and a hint to use `--reopen` or `reopen <ID>`.
- Add `--reopen` support to `status` and `next`, plus a `todo_md reopen <ID> [--status <STATUS>] [-m "<note>"] [-c]` subcommand that moves the task back to `TODO.md` (default status `NEW`) and clears any prior closing note from the heading unless `-m` is supplied.
- Ensure pre-execution hooks in `src/bundles/todo_md.bundle` (`$ todo_md status {task:} WIP`) fail fast before session startup if given an archived task ID, while read/audit commands (`show`, `files`, `role=audit`) continue to work on archived tasks.
- Target files: `src/cli.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `src/bundles/todo_md.bundle`, `README.md`, `tests/test_todo_md.py`.

# ✅ [DONE] F23: Emit Task, Role, and Workdir headers in single-task show output — *2026-11-17, emit Task, Role, and Workdir headers*

- Update `cmd_show` in `src/parser.py` and single-task dispatch in `src/cli.py` so displaying an individual task (`<ID>`, `<project>:<ID>`, `show <ID|last>`) prints `Task: <ID>`, optional `Role: <role>`, and `Workdir: <absolute project directory>` followed by a blank line before `# TODO.md:<line>`.
- Resolve `Role:` from explicit `- Role: <role>` metadata in the task body (supported via `--role <role>` in `todo_md add` / `todo_md edit`), falling back by task prefix (`D` -> `design`, `F`/`B` -> `work`; omit `Role:` for unmapped prefixes when unset).
- Ensure `Workdir:` resolves to the target project root for local `<ID>`, `<project>:<ID>`, and `-C` invocations, while keeping workspace/list overview outputs unchanged.
- Sync `README.md`, `src/header.py`, `src/rules/todo_md.md`, and `tests/test_todo_md.py`, and rebuild `todo_md` via `build.py`.

# ✅ [DONE] D1: Design dependency queue and next actionable task resolution — *2026-11-17, design agreed; spec recorded in AGENTS.md and F21*

- Design CLI commands in `todo_md` to build an ordered execution queue for a
  target task (for example, `todo_md queue <ID>`) and resolve the next
  unblocked actionable task (for example, `todo_md resolve <ID>` or
  `todo_md next-id <ID>`).
- Traverse `Depends on:` edges recursively across intra-project and
  `.todo_projects` workspace tasks, filter out `DONE` and `CANCELED` tasks,
  and preserve declared `Depends on:` order so orchestrator tasks can sequence
  cross-project steps without breaking the one-way dependency boundary.
- Define output format, cycle and missing-reference error handling, and
  composition with `todo_md show` / `agents_bundle` / `run_block` pipes.
- Target files for implementation: `src/parser.py`, `src/cli.py`,
  `src/header.py`, `README.md`, `src/rules/todo_md.md`, `tests/test_*.py`.

# ✅ [DONE] F19: Print Workdir header for explicit project task references — *2026-11-17*

- In `src/parser.py` (`cmd_show`) and `src/cli.py`, when a task is addressed
  with an explicit `<project>:<ID>` reference, print `Workdir: <absolute
  project path>` followed by a blank line before the usual `# TODO.md:<line>`
  output. Without an explicit project the output stays unchanged.
- Resolve the path through `resolve_project_task_ref` so `.todo_projects`
  filtering and workspace escape checks still apply.
- Keep `README.md`, `src/header.py` (`--help`), `src/rules/todo_md.md`, and
  `tests/test_*.py` in sync.

# ✅ [DONE] F18: Connect python-stdlib and python-annotations rules in .agents_bundle — *2026-11-16, Connect python-stdlib and python-annotations rules in .agents_bundle*

- In `.agents_bundle`, remove `py_min=3.9` from `stack/python-cli` and add
  `rule vitalio/agents-rules:stack/python-stdlib` and
  `rule vitalio/agents-rules:stack/python-annotations py_min=3.9`, after the
  python-cli split is released in agents-rules and the package cache is
  refreshed.
- Keep `from __future__ import annotations` only in `build.py` and
  `src/header.py`; do not add it to modules under `src/`.
- Run `python3 -m unittest discover -s tests`; if the progress line shows
  stderr noise, capture it with `contextlib.redirect_stderr` in `tests/`.

# ✅ [DONE] F7: Cross-project workspace discovery, <project>:<ID> addressing, and Depends on support — *2026-11-16*

- Detect a todo_md-managed project by the presence of both TODO.md and TODO_ARCHIVE.md (without climbing to git rev-parse --show-toplevel when invoked in a subproject or a workspace directory without TODO.md).
- When invoked in a directory without TODO.md + TODO_ARCHIVE.md (or when -w / --workspace is passed), scan subdirectories up to a bounded depth (e.g. 3 levels, skipping hidden directories '.*' and build/vendor directories) without stopping at intermediate projects so both root projects (e.g. chrome) and nested subprojects (e.g. chrome/canary) are discovered as separate project namespaces.
- Add 'todo_md projects' to list discovered workspace projects and their open task counts, and support '-w' / '--workspace' for cross-project task overviews and queries.
- Support universal '<project>:<ID>' and '<project>' addressing across CLI commands (e.g. 'todo_md agents_bundle:F5', 'todo_md chrome/canary:F1', 'todo_md add agents-rules ...') using POSIX '/' separators on all platforms (Linux, macOS, Windows), resolving '<project>' relative to the current workspace root (parent of the current repository root or TODO_MD_WORKSPACE).
- Support '--depends <ref>[,<ref>...]' on 'todo_md add' and 'todo_md edit' (storing '- Depends on: <ref>' in the task body), validate dependency targets in 'todo_md check', and surface dependency status ([DONE] vs blocked) in task output.
- Update todo_md.bundle to run 'todo_md -w' when 'workspace=1' is passed.

# ✅ [DONE] F13: Strengthen role=execute prompt and task resolution in todo_md.bundle — *2026-11-16*

- Guard `var task=$(todo_md next-id)` with `[if task=]` in `src/bundles/todo_md.bundle` so an explicitly passed `task=<ID>` is preserved and transitioned to `WIP` rather than overwritten.
- Rewrite the `role=execute` prompt in `src/bundles/todo_md.bundle` as a direct imperative instructing the model to emit its first `run_block` in the very first reply (either applying edits, tests, and diff immediately when all target files are preloaded, or running a single batched read step when target files are missing or unspecified).
- Clarify the empty `task=` fallback prompt in `src/bundles/todo_md.bundle` to handle a task ID supplied via `-p` or propose the top task shown in the `todo_md` overview.
- Update `tests/test_todo_md.py` to assert `[if task=] var task=$(todo_md next-id)` and the updated `role=execute` prompt invariants in `src/bundles/todo_md.bundle`.

# ✅ [DONE] F9: Always expand at least one task in default todo_md overview — *2026-11-16*

- Update `cmd_summary` in `src/parser.py` so that when `full=False` and `TODO.md` has no `WIP`, `NEXT`, or `QUESTION` tasks (only `NEW` and/or `HOLD`), the first ordered task is rendered in full while subsequent `NEW`/`HOLD` tasks remain compacted.
- Keep `todo_md [--full]` documentation in sync across `src/header.py`, `src/rules/todo_md.md`, and `README.md`.
- Add unit tests in `tests/test_todo_md.py` verifying that default `todo_md` expands the first `NEW`/`HOLD` task when no higher-priority tasks exist and keeps all `NEW`/`HOLD` tasks compact when at least one `WIP`/`NEXT`/`QUESTION` task is shown in full.

# ✅ [DONE] F12: Document role-based backlog commit workflow in rules and bundle — *2026-11-16, Document role-based backlog commit workflow in rules and bundle*

- Update `src/rules/todo_md.md` (`Validation & commits` / `Status lifecycle`) to specify role-based commit behavior:
  - `role=execute`: do not pass `-c`/`--commit`; stage `TODO.md` and `TODO_ARCHIVE.md` into the final code commit so `done` is atomic with implementation.
  - `role=plan`, `role=design`, and `role=audit`: batch `todo_md` mutations without `-c` and commit `TODO*.md` in a single commit once backlog updates are finished (e.g. `-c`/`--commit` on the final `todo_md` command or `git add TODO*.md && git commit`) before starting `role=execute`.
- Update `src/bundles/todo_md.bundle` (`[if role=plan]`, `[if role=design]`, `[if role=audit]` prompts) to remind the agent to commit `TODO*.md` after recording agreed tasks.
- Rebuild standalone `todo_md` via `python3 build.py` and keep `README.md` in sync if needed.

# ✅ [DONE] F11: Capture all subprocess output in unit tests — *2026-11-16*

- Update `tests/test_todo_md.py` so every `subprocess.run(...)` call captures `stdout` and `stderr` (`capture_output=True, text=True` or a shared helper on `TestTodoMd` that includes captured output in failure diagnostics).
- Verify `python3 -m unittest discover -s tests -q` emits no extraneous `todo_md:` or subprocess output when tests pass.

# ✅ [DONE] F10: Support -b - / --body - to read task body from stdin — *2026-11-16, Support -b - / --body - to read task body from stdin*

- Treat `-b -` and `--body -` in `add`, `edit`, and `append` (`src/commands.py`) as an explicit request to read the task body from `stdin` via a shared helper.
- When `-b -` / `--body -` is passed with an interactive TTY `stdin`, fail fast with a clear error message on `stderr` and non-zero exit status instead of hanging for EOF.
- When `stdin` is non-TTY: read `stdin` (`append` still rejects empty text, `add` creates a task without a body on empty `stdin`, and `edit` updates or clears the body consistently with `-b ""`).
- Keep `-b` / `--body` documentation in sync across `src/header.py`, `src/rules/todo_md.md`, and `README.md`.
- Add unit tests in `tests/test_todo_md.py` covering `-b -` and `--body -` for `add`, `edit`, and `append` (both piped `stdin` and TTY `stdin` error handling).

# ✅ [DONE] F4: Support last/last-id selectors, list --full/--limit, and task=<ID>|last|DONE in role=audit bundle — *2026-11-15, Support last/last-id selectors, list --full/--limit, and task=<ID>|last|DONE in role=audit bundle*

- Add `todo_md last-id [<STATUS|archive>]` (defaulting to `NEW`) to print the resolved `<ID>` to stdout (or exit 1 if none): bottom-most task in group for `NEW`/`HOLD`/`QUESTION` (most recently added), top-most task in group for `WIP`/`NEXT`, and top-most matching task in `TODO_ARCHIVE.md` for `DONE`/`CANCELED`/`archive`.
- Add `todo_md last [<STATUS|archive>]` and `todo_md show last [<STATUS|archive>]` (defaulting to `NEW`) to resolve the target `<ID>` via `last-id` and render full `todo_md <ID>` output (`# <file>:<line>`, full section, and `IDs in use` footer).
- Extend `todo_md list [filter]` with `--limit N` (`-n N`) and `--full` (render full task sections instead of compact one-line rows), ordering `NEW`/`HOLD`/`QUESTION` newest-first like `TODO_ARCHIVE.md`.
- Update `src/bundles/todo_md.bundle` under `[if role=audit]` to resolve `task=last` or `task=DONE` via `var task=$(todo_md last-id DONE)` and, when `task` is non-empty, run `$ todo_md {task:}` and `include $(todo_md files {task:})` with a targeted task audit prompt; remove the obsolete intermediate-plan instruction from `[if role=execute]`.
- Keep `src/header.py`, `src/parser.py`, `src/commands.py`, `src/cli.py`, `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` in sync.

# ✅ [DONE] F8: Auto-resolve top WIP/NEXT task, extract task target files, and support piping to agents_bundle — *2026-11-15, Add top task ID and target file extraction commands and update workflow bundle*

- Add CLI helpers (e.g. `todo_md --top` / `todo_md next-id` to print the top `WIP` or `NEXT` task ID, and `todo_md --files <ID>` to list existing repository file paths referenced in backticks in task `<ID>`) and support piping `todo_md [<ID>] | agents_bundle | run_block`.
- Update `src/bundles/todo_md.bundle` (and `agents/bundles/todo_md.bundle` per F6) so that:
  - in `role=plan`, the prompt instructs recording target file paths in the task body and preloading them when initializing the execution session (`agents_bundle role=execute task=<ID> <file ...> | run_block`);
  - in `role=execute` (and `role=work`), when `task` is omitted it automatically resolves to the top `WIP` or `NEXT` task ID so `Task: <ID>` is always recorded in the session header, transitions the task to `WIP`, prints `todo_md <ID>`, auto-includes the task's referenced project files into the bundle, and instructs the agent to proceed directly to edit, test, and diff in step 1 when all target files are already preloaded.

# ✅ [DONE] F5: Default mutating commands to no-commit (opt-in --commit), auto-group TODO.md by status, and auto-transition task=<ID> to WIP in role=execute — *2026-11-15, Release v0.7.0*

- Make mutating todo_md commands ('add', 'edit', 'append', 'status', 'next', 'done', 'cancel', 'init') validate and write 'TODO.md'/'TODO_ARCHIVE.md' without auto-committing by default; add '--commit' / '-c' for explicit git commits (keeping '--no-commit' as a no-op alias for backwards compatibility).
- Auto-order active tasks in 'TODO.md' by status priority ('WIP' -> 'NEXT' -> 'QUESTION' -> 'NEW' -> 'HOLD') on every mutation while preserving relative order within each status group, and prepend newly archived tasks ('DONE', 'CANCELED') to the top of 'TODO_ARCHIVE.md'.
- Always render backlog tasks ('NEW', 'HOLD') in compact view in 'todo_md' summary output (regardless of total task count unless '--full' is passed), while expanding 'WIP', 'NEXT', and 'QUESTION' tasks in full.
- Define clear status lifecycle rules in 'src/rules/todo_md.md' and 'src/bundles/todo_md.bundle': 'NEW' is the default backlog status (compact view), 'NEXT' is promoted in 'role=plan' for prioritized ready tasks (expanded view), 'WIP' is set automatically by 'todo_md.bundle' when starting 'role=execute task=<ID>', and 'done' is run before the final commit in 'role=execute' so backlog updates are committed atomically with code changes.
- In 'src/bundles/todo_md.bundle' under '[if role=execute]' and '[if task!=]', transition '{task:}' to 'WIP' before printing '$ todo_md {task:}'.

# ✅ [DONE] F1: Task status transition subcommands (`done` / `status`) — *implemented in v0.1.0*

Add `todo_md done <ID>` and `todo_md status <ID> <STATUS>` to automatically
update a task's status badge or move a completed task from `TODO.md` to `TODO_ARCHIVE.md`.

# ✅ [DONE] F2: Add src/rules/todo_md.md and src/bundles/todo_md.bundle and remove --agents CLI flag — *2026-11-14*
