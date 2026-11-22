# `todo_md` — Project-Specific Agent Rules

Universal workflow, language, Git, SemVer, Python CLI, and single-file build
rules are loaded via `.agents_bundle`.

## Product Philosophy & Quest-Log UX

- Quest-log mental model: build `todo_md` around the clarity and progression
  feel of an RPG quest journal rather than a flat checklist. Every CLI view
  (`overview`, `list`, `show`, `queue`, `chain`, `done`) should immediately
  answer what is actionable now, what is locked, why it is locked, and what
  completing it unlocks next.
- At-a-glance state & unlock visibility: distinguish ready quests (`🎯 [NEXT]`,
  `[ready]`), locked quests (`⏳ [NEXT]`, `[blocked: ...]`), waiting conditions
  (`⏸️ [HOLD]`), and completed quests (`✅ [DONE]`) using compact visual
  badges, dependency chains (`->`, `├─`, `└─`), and downstream impact
  indicators (`[unblocks N]`, `Blocks: ...`).
- Progressive disclosure: keep default views compact and scannable while
  letting users drill into full quest details, dependency chains (`chain`),
  and execution paths (`queue`, `--full`) on demand.
- Default view is the Quest-Log: `todo_md` (also `todo_md -w` and `todo_md <project>`)
  renders `cmd_chain()` as flat topological chains in execution order without row
  numbers; `--tree` / `-t` adds nested `Sub-chain ->` milestone trees with 4-char
  connectors (`├── `, `└── `, `└─► `, `│   `) and `--numbered[=left|right]` adds
  period-free row numbers padded to the widest number. The Markdown overview lives
  in `todo_md overview` (and bare `todo_md --full`).
- Drill-down without leaving the Quest-Log: `--filter` / `-f <ID>...` (and positional
  `<ID>...` under `chain` / `queue`) filters by task IDs (bare `<ID>` matches across
  all projects in the active view, while `<project>:<ID>` matches only that project),
  scopes to matching chains/tasks, highlights them, and prints `Next actionable: <ref>`
  for a single ID; `--search` / `-s <QUERY>` (or `todo_md search`) searches task IDs
  (`<ID>` and `<project>:<ID>`), titles, and bodies across all projects in the active
  view (including `.todo_projects` child projects) and focuses on matches (or prints
  full sections with `--full`); `--highlight` / `-H` is a boolean toggle that disables
  focus to render the full Quest-Log with matched `-f` / `-s` tasks highlighted (and
  accepts `-H <ID>...` as shorthand for `-f <ID>... -H`); `--all` includes both active
  (`TODO.md`) and archived (`TODO_ARCHIVE.md`) tasks across Quest-Log, `-s`, and `-f`;
  and status keywords (`WIP`, `NEXT`, `QUESTION`, `NEW`, `HOLD`, `ACTIVE`, `ALL`;
  `DONE`, `CANCELED`, `archive` render the list view) filter rows. Multiple IDs
  (`todo_md F1 F2`, `show F1,F2`) print full task sections in order.
- Keep `_parse_quest_log_args()` and `_quest_log()` in `src/cli.py` as the single
  parser for the default view, `chain`, `queue`, and `search`; do not re-implement
  flag parsing per entry point.
- Unlock feedback loop: closing a quest (`todo_md done <ID>`) should report
  newly unlocked downstream quests (`Unblocked: ...`) so the next playable
  step is obvious without manually re-scanning the backlog.

## Architecture & Module Boundaries

- `src/header.py` — help tables rendered by `usage_text()` (`-h`/`--help`),
  standard library imports, version placeholder (`__VERSION__`, injected from
  `VERSION` by `build.py`), and task heading regexes.
- `src/parser.py` — `TODO.md` and `TODO_ARCHIVE.md` task parser, ID sequence
  tracking, and structural validator (`todo_md check`).
  Workspace/orchestrator discovery is shared per render pass through
  `discovery_session()` (`_discovery_scoped` on `cmd_list`, `cmd_show`,
  `cmd_summary`, `cmd_workspace_*`, `_order_active_tasks`); route new
  discovery calls through the cached wrappers and never mutate task files
  inside an active session.
- `src/commands.py` — task lifecycle subcommands (`init`, `add`, `edit`,
  `append`, `status`, `next`, `done`, `cancel`, `list`, `archive`, `ids`,
  `check`). Keep `agents/todo_md.md`, `-h`/`--help`, and `README.md` in sync
  in the same commit whenever commands or flags change.
- `agents/todo_md.md` — agent rule embedded into the compiled `todo_md` by
  `build.py` (`EMBEDDED_RULE_TODO_MD`, `get_embedded_todo_rule()`) and emitted
  as `todo_md:todo_md` in bundle mode for every role except `work`; it is pure
  Markdown (no conditional directives) and holds the full backlog reference.
- `agents/todo_md_work.md` — compact `role=work` rule embedded as
  `EMBEDDED_RULE_TODO_MD_WORK`; `get_embedded_todo_rule(role)` picks it only for
  `work`. It tells the agent to run `todo_md status <ID> WIP` in its first step.
- `src/bundle.py` — `context-bundle-protocol` v1 producer (`BundleOptions`,
  `bundle_mode_enabled()`, `emit_task_bundle()`, `emit_context_bundle()`):
  FIFO auto-detection, `role=<role>` override (`Role:` header and rule
  selection), and rule/include/task/context fragments; it never mutates
  `TODO.md`. Target files come only from `select_task_files()` and
  `extract_task_files()` in `src/commands.py`
  (`- Target files:` bullets); keep the stream shape aligned with `todo_flow`
  `docs/adr/0002-context-bundle-protocol-and-self-contained-producers.md`.
- `src/cli.py` — CLI argument routing and self-update (`update`,
  `check-update`).
- `tests/helpers.py` & `tests/test_*.py` — shared in-process/subprocess test
  harness (`TodoMdTestCase`) and modular unit test suites (`test_cli.py`,
  `test_parser.py`, `test_commands.py`, `test_deps.py`, `test_chain.py`,
  `test_bundle.py`).

## Task Roles & Prefixes

- Task roles are derived only from the ID prefix and status in
  `resolve_task_role()`; never reintroduce in-body `- Role:` overrides or a
  `--role` option on mutating commands (`--role` stays a read-only filter).
- Prefix metadata (`PREFIX_INFO`, `DEFAULT_TASK_PREFIX`) and status roles
  (`STATUS_ROLES`) live in `src/header.py`; `todo_md ids` renders the legend
  from them via `prefix_legend_lines()`, so keep `--help`, `README.md`, and
  `agents/todo_md.md` aligned with those tables.

## Dependency Graph & Sequencing Contract

- Single source of truth: express both prerequisites and execution order in
  `- Depends on:` lines (and `--depends`); do not duplicate order in a
  separate `- Order:` field.
- Syntax: `,` separates parallel items within a stage, `->` separates sequential
  stages (`,` binds tighter than `->`, e.g. `A, B -> C`), and multiple
  `- Depends on:` lines represent independent branches combined with AND.
- Unified DAG: dependency resolution merges explicit `->` stage edges on the
  target task with transitive `- Depends on:` edges inside referenced tasks
  (preserving one-way cross-repo boundaries when orchestrators sequence child
  tasks). `build_dependency_dag()` also merges inbound stage edges declared
  in `.todo_projects` orchestrator tasks, so `queue`, `next-id`, `list`, and
  `show` agree with `chain`; `--ready` ranks tasks by their best parent chain
  index before local chain counts.
- Validation & execution: `todo_md check` detects syntax errors, missing refs,
  and transitive cycles; `DONE` unblocks while `CANCELED` or `MISSING` blocks;
  `todo_md queue <ID>` shows the ordered queue and `todo_md next-id <ID>`
  prints the first unblocked task ID for pipe composition.
