# `todo-md` (`todo`) — Project-Specific Agent Rules

Universal workflow, language, Git, SemVer, Python CLI, and single-file build
rules are loaded via `.context.bundle`.

## Product Philosophy & Quest-Log UX

- Quest-log mental model: build `todo` (`todo-md`) around the clarity and progression
  feel of an RPG quest journal rather than a flat checklist. Every CLI view
  (`overview`, `list`, `show`, `queue`, `chain`, `done`) should immediately
  answer what is actionable now, what is locked, why it is locked, and what
  completing it unlocks next.
- At-a-glance state & unlock visibility: distinguish ready quests (`🎯 NEXT`,
  `🟢 ready`), locked quests (`⏳ NEXT`, `🔒 blocked by: ...`), waiting conditions
  (`⏸️ HOLD`), and completed quests (`✅ DONE`) using compact bracket-free visual
  badges, dependency chains (`->`, `├─`, `└─`), RPG perks (`🏁 FINAL`, `⚡ STAGE`,
  `🔥 COMBO`), and downstream impact indicators (`🔓 unblocks: N`, `⛓️ chain: N`,
  `🟢 ready: +M`).
- Progressive disclosure: keep default views compact and scannable while
  letting users drill into full quest details, dependency chains (`chain`),
  and execution paths (`queue`, `--full`) on demand.
- Default view is the Quest-Log: `todo` (also `todo -w` and `todo <project>`)
  renders `cmd_chain()` starting with a single-line overall game progress header
  (`<pct>% · ✅ <done>/<total> · <open> open: 🟢 <ready> ready (...) · ⏳ <blocked> blocked · ⏸️ <held> held`)
  followed by `<pct>% · <done>/<total> · Chain <N> -> <root_ref>: <root_title>:` flat
  topological chains in execution order without row numbers; `--tree` / `-t` adds nested
  `<pct>% · <done>/<total> · Sub-chain -> <m_ref>: <m_title>:` milestone trees with 4-char
  connectors (`├── `, `└── `, `└─► `, `│   `) and `--numbered[=left|right]` adds
  period-free row numbers padded to the widest number. The Markdown overview lives
  in `todo overview` (and bare `todo --full`).
- Drill-down without leaving the Quest-Log: `--filter` / `-f <ID>...` (and positional
  `<ID>...` under `chain` / `queue`) filters by task IDs (bare `<ID>` matches across
  all projects in the active view, while `<project>:<ID>` matches only that project),
  scopes to matching chains/tasks, highlights them, and prints `Next actionable: <ref>`
  for a single ID; `--search` / `-s <QUERY>` (or `todo search`) searches task IDs
  (`<ID>` and `<project>:<ID>`), titles, and bodies across all projects in the active
  view (including `.todo_projects` child projects) and focuses on matches (or prints
  full sections with `--full`); `--highlight` / `-H` is a boolean toggle that disables
  focus to render the full Quest-Log with matched `-f` / `-s` tasks highlighted (and
  accepts `-H <ID>...` as shorthand for `-f <ID>... -H`); `--all` includes both active
  (`TODO.md`) and archived (`TODO_ARCHIVE.md`) tasks across Quest-Log, `-s`, and `-f`;
  and status keywords (`WIP`, `NEXT`, `QUESTION`, `NEW`, `HOLD`, `ACTIVE`, `ALL`;
  `DONE`, `CANCELED`, `archive` render the list view) filter rows. Multiple IDs
  (`todo F1 F2`, `show F1,F2`) print full task sections in order.
- Keep `_parse_quest_log_args()` and `_quest_log()` in `src/cli.py` as the single
  parser for the default view, `chain`, `queue`, and `search`; do not re-implement
  flag parsing per entry point.
- Unlock feedback loop: closing a quest (`todo done <ID>`) should report
  newly unlocked downstream quests (`Unblocked: ...`) so the next playable
  step is obvious without manually re-scanning the backlog.

## Architecture & Module Boundaries

- `src/header.py` — help tables rendered by `usage_text()` (`-h`/`--help`),
  standard library imports, version placeholder (`__VERSION__`, injected from
  `VERSION` by `build.py`), and task heading regexes.
- `src/workspace.py` — strict one-way `.todo_projects` / `.todo_projects.local`
  (and `TODO_MD_PROJECTS`, including `<project_id>=<path>` alias mappings)
  registry resolution without parent or sibling directory scanning, and the
  per-render `discovery_session()` cache (`_discovery_scoped` on `validate_all`,
  `cmd_check`, `cmd_chain`, `build_execution_chain_dag`, `cmd_projects`,
  `find_newly_unblocked_tasks`, `cmd_list`, `cmd_show`, `cmd_summary`,
  `cmd_workspace_*`, `_order_active_tasks`); route new discovery calls through
  the cached wrappers and never mutate task files inside an active session.
- `src/parser.py` — pure `TODO.md` / `TODO_ARCHIVE.md` parsing: task sections,
  dependency clause syntax, prefix matching, ID tracking, search, and the
  structural validator `validate_all()` (`todo check`); no terminal output.
- `src/dag.py` — unified dependency DAG (`build_dependency_dag()`,
  `build_execution_chain_dag()`), blocked-state info, and unblock detection.
- `src/chains.py` — execution chain planning and ranking
  (`plan_execution_chains()`, `build_chain_milestone_tree()`,
  `_order_active_tasks()`).
- `src/render.py` — terminal width, ANSI styling, table wrapping, and the
  read-only view and query renderers (`cmd_list`, `cmd_show`, `cmd_summary`,
  `cmd_ids`, `cmd_last`, `cmd_projects`, `cmd_workspace_*`,
  `resolve_top_task_id`, `cmd_next_id`); `src/render_chain.py`
  holds the Quest-Log `cmd_chain()` renderer.
- `src/commands.py` — backlog sorting, Git auto-commit helpers, and the
  mutating/validation subcommands (`init`, `add`, `edit`, `append`, `rename`,
  `status`, `next`, `reopen`, `done`, `cancel`, `archive`, `check`). Keep
  `agents/todo.md`, `-h`/`--help`, and `README.md` in sync in the same
  commit whenever commands or flags change.
- `agents/todo.md` — agent rule embedded into the compiled `todo` by
  `build.py` (`EMBEDDED_RULE_TODO`, `get_embedded_todo_rule()`) and emitted
  as `vitalio/todo-md:todo` in bundle mode; it is pure Markdown and holds the
  `todo` CLI and data-format contract (`{cmd:todo}`) without hardcoded role workflow
  instructions.
- `src/bundle.py` — `context-bundle-protocol` v1 producer (`BundleOptions`,
  `bundle_mode_enabled()`, `emit_task_bundle()`, `emit_context_bundle()`):
  explicit `-B` / `--bundle` (or `TODO_MD_BUNDLE=1`, unless overridden by
  `--plain` / `TODO_MD_PLAIN=1`) activation, `Bundle-Name: vitalio/todo-md`,
  native task preamble headers (`Task`, `Prefix`, `Status`, `Title`, `Workdir`,
  plus `Role` only on explicit `role=<role>` CLI override), and canonical
  `rule` and `prompt` fragments without streaming `include` file contents; it
  never mutates `TODO.md`.
- `src/cli.py` — CLI argument routing and self-update (`update`,
  `check-update`).
- `tests/helpers.py` & `tests/test_*.py` — shared in-process/subprocess test
  harness (`TodoMdTestCase`) and modular unit test suites (`test_cli.py`,
  `test_parser.py`, `test_commands.py`, `test_deps.py`, `test_chain.py`,
  `test_bundle.py`).

## Task Prefixes & Role Decoupling

- `todo-md` is decoupled from `agents-rules` role names and file preloading: do
  not reintroduce hardcoded role tables, `resolve_task_role()`, `--role`,
  `--by-role`, or in-body `- Role:` / `- Target files:` lines; filter views
  natively with `--prefix` and `--status`.
- Prefix metadata (`PREFIX_INFO`, `DEFAULT_TASK_PREFIX`) lives in
  `src/header.py`; `todo ids` renders the legend from it via
  `prefix_legend_lines()`, so keep `--help`, `README.md`, and
  `agents/todo.md` aligned with that table.

## Dependency Graph & Sequencing Contract

- Single source of truth: express both prerequisites and execution order in
  `- Depends on:` lines (and `--depends`); do not duplicate order in a
  separate `- Order:` field.
- Syntax: `,` separates parallel items within a stage, `->` separates sequential
  stages (`,` binds tighter than `->`, e.g. `A, B -> C`), and `;` (or multiple
  `--depends` / `- Depends on:` lines) separates independent branches combined
  with AND.
- Unified DAG & strict one-way boundary: dependency resolution merges explicit
  `->` stage edges on the target task with transitive `- Depends on:` edges
  inside referenced tasks. Multi-project scope exists strictly when
  `.todo_projects`, `.todo_projects.local`, or `TODO_MD_PROJECTS` is configured:
  child repositories remain 100% self-contained (never scanning parent or
  sibling directories, discovering enclosing orchestrators, or mutating external
  orchestrator files), while cross-project blockers and stage edges are
  inspected from the orchestrator repository (`-w`, `-p <project>`, and
  `<project>:<ID>` require `.todo_projects`). `--ready` ranks tasks by their
  best parent chain index before local chain counts.
- Validation & execution: `todo check` detects syntax errors, missing refs,
  and transitive cycles; `DONE` unblocks while `CANCELED` or `MISSING` blocks;
  `todo queue <ID>` shows the ordered queue and `todo next-id <ID>`
  prints the first unblocked task ID for pipe composition.
