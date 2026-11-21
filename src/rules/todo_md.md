# Description: Structured Markdown task management (TODO.md and TODO_ARCHIVE.md) via todo_md
- Task management (`{cmd:todo_md}`: `TODO.md`, `TODO_ARCHIVE.md`): Always
  inspect and modify `TODO.md` and `TODO_ARCHIVE.md` via `{cmd:todo_md}` (never
  via `cat` or manual file edits). Repository scope only: record each task in
  the `TODO.md` of the repository it belongs to, never in an unrelated
  repository's backlog.
  - Status lifecycle, role fallback & pipe launch: `TODO.md` keeps active tasks
    ordered by status (`🔵 [WIP]` -> `🎯 [NEXT]` -> `❓ [QUESTION]` ->
    `⚪ [NEW]` -> `⏸️ [HOLD]`), and `TODO_ARCHIVE.md` keeps closed tasks
    (`✅ [DONE]`, `❌ [CANCELED]`) newest-first. `NEW` is the default backlog
    status (rendered in compact view by `{cmd:todo_md}`), `NEXT` is promoted in
    `role=plan` for prioritized ready tasks (expanded view), `WIP` is set
    automatically when starting `role=work task=<ID>`, and `done` is run
    inside the final commit step in `role=work` (after the edit-and-diff step
    is verified clean, immediately before staging and `git commit`, never
    during the edit step) so backlog updates are committed atomically with
    code changes. Task roles are never stored in task bodies and are derived
    from the ID prefix and status: `D*` resolves to `design` in any status
    and any non-`D` prefix (`F`, `B`, or custom `A-Z`) resolves to `plan` in
    `NEW`/`QUESTION`/`HOLD` and to `work` in `WIP`/`NEXT`; `{cmd:todo_md} check`
    rejects `- Role:` lines in active `TODO.md` tasks (use a `D*` prefix for
    design, or `{cmd:todo_md} next <ID>` to promote to work).
    Promoting a task via `{cmd:todo_md} next <ID>` (or
    `{cmd:todo_md} status <ID> NEXT`) strips an existing `- Role: plan` line so
    promoted non-`D` tasks transition to `work` automatically, and
    `{cmd:todo_md} <ID>` always emits `Role: <role>` in its preamble for
    role-agnostic pipe auto-consumption
    (`{cmd:todo_md} <ID> | agents_bundle | run_block`).
  - Task ID prefixes: `F` is a feature (default prefix on `add`), `B` is a
    bugfix (ranked ahead of other tasks in `chain`), and `D` is a design task
    (role `design`); any other single `A-Z` letter is a custom domain prefix
    whose role follows the status rule above. `{cmd:todo_md} ids` prints the
    IDs in use together with this legend. Close design tasks via
    `{cmd:todo_md} done <ID>` once their invariants are persisted in
    `AGENTS.md` (and `docs/adr/`) and follow-up implementation tasks exist.
  - Target selection: pass `-C <dir|project>` or `--project <name>` before
    any `{cmd:todo_md}` subcommand (`ids`, `list`, `archive`, `last`, `last-id`,
    `next-id`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`,
    `done`, `cancel`, `show`) to target a repository directory or discovered
    workspace project from any working directory (keep `-p` in `add` for ID
    prefix and `<project>:<ID>` strictly for task-level references; precedence:
    `-C`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory).
  - Inspect: `{cmd:todo_md} [opts] [-w]` (default Quest-Log view of the repository or workspace, see `chain` below;
    `{cmd:todo_md} overview [--full] [-w]` or `{cmd:todo_md} --full` prints the Markdown overview or cross-project workspace
    overview: full `WIP`/`NEXT`/`QUESTION`, or first `NEW`/`HOLD` task when none
    exist, + compact backlog; supports `<project>:<ID>` and `<project>` addressing),
    `{cmd:todo_md} projects` (list workspace projects and open counts), `{cmd:todo_md} <ID>[,<ID>...] [<ID>...]` /
    `{cmd:todo_md} show <ID>[,<ID>...] [<ID>...]` / `{cmd:todo_md} show last [<STATUS|archive>]` (multiple IDs, including
    `<project>:<ID>`, are shown sequentially separated by a blank line; prints `Task:`, `Title:`, `Role:`,
    and `Workdir:` headers before `# TODO*.md:<line>`),
    `{cmd:todo_md} last [<STATUS|archive>]` (default: `NEW`),
    `{cmd:todo_md} last-id [<STATUS|archive>]` (default: `NEW`),
    `{cmd:todo_md} list [active|archive|all|<STATUS>] [<ID>...] [--role <role>] [-r|--ready] [--limit N] [--full]`
    (orders each status bucket with ready tasks first and prerequisites before dependents;
    renders blocked `WIP`/`NEXT` items as `⏳ [WIP]` / `⏳ [NEXT]` and multi-step chains as full
    ordered paths `[blocked: A (<STATUS>) -> B (<STATUS>)]`; highlights any target `<ID>...`
    and dims `DONE` rows in TTY views;
    `--ready` filters active tasks to those with no unresolved dependencies),
    `{cmd:todo_md} archive`, `{cmd:todo_md} ids`,
    `{cmd:todo_md} queue <ID> [--all]` (alias for `{cmd:todo_md} chain <ID> [--all]`: focused Quest-Log of the chain containing `<ID>`;
    hides `DONE` unless `--all` is passed; prints `[ready]` / `[blocked by: ...]`
    and `Next actionable: <ref>`),
    `{cmd:todo_md} chain [<ID>...] [--all] [--by-role] [--role <role>] [--ready] [-l N|--limit N] [--include-hold] [--tree] [--numbered[=left|right]] [--status <STATUS>] [-f <ID>...|--filter <ID>...] [-H|--highlight [<ID>...]] [-s <QUERY>|--search <QUERY>]`
    (local, `.todo_projects` orchestrator, or `-w` workspace root-anchored RPG progress chains
    `Chain <N> -> <root_ref>: <root_title> [<pct>% | done: <D>, open: <O>]:` (or `[open: <O>]:` when `done == 0`),
    ranking ready `work` chain finales (`[ready | FINAL]`) first as top `Chain 1..K` entries
    as flat topological rows by default (no row numbers; `--numbered[=left|right]` adds period-free numbers), or with `--tree` / `-t`
    nested `├── Sub-chain -> <milestone_ref>: <title> [<pct>% | done: <D>, open: <O>]:`
    milestone trees (4-char connectors `├── `, `└── `, `└─► `, `│   `) and standalone tasks, appending
    `[also in: <other_root_ref>, ...]` to
    prerequisite rows shared across multiple root chains, including resolved
    `DONE` prerequisites in topological order when `--all` is passed, merging
    `.todo_projects` orchestrator dependency edges (expanding nested orchestrators transitively and keeping path aliases such as `~/chrome/canary` -> `chrome/canary:<ID>` for external projects) into child project views,
    formatting IDs relative to `cwd`, applying composable TTY styling for
    external-project tasks, `DONE` tasks, and target `<ID>...` highlights,
    showing padded `[role]` badges and unified `[ready | FINAL | STAGE | COMBO | unblocks: <K>]` / `[blocked by: <refs> | unblocks: <K>]` tags (keeping `done: <D>` exclusively on chain and sub-chain headers), and enforcing monotonic
    Quest Momentum ranking by ready `work` finale priority, bug priority `B*`, role execution ease, active
    quest momentum / started-chain status floor, role-weighted velocity
    `work=1, plan=2, design=5`, whole-cone size, and closing root tie-breaker;
    `--by-role`
    partitions active
    tasks into
    topologically sorted role queues: `Queue 1 (work)` with only `work`
    transitive deps, `Queue 2 (plan)` with `work`/`plan` transitive deps,
    `Queue 3 (design)`, and `Queue 4 (deferred work)` for `work` blocked by
    `plan`/`design` [omitted with `--ready`]; `--role <role>` filters displayed
    tasks while preserving DAG validation and unblock context; `--ready` / `-r` filters
    to ready tasks ranked by role ease, Quest Momentum continuation, multi-chain count, completed prerequisite count, and immediate ready unlocks,
    shown as `[FINAL | STAGE | COMBO | chain: <N>, ready: +<M>, unblocks: <K>]` (`chain: <N>` only when `N > 1`, `ready: +<M>` only when `M > 0`; tag omitted on zero-stat standalone tasks); excludes `HOLD` and tasks transitively
    blocked by `HOLD` into `Held branches:` unless `--include-hold` is passed;
    reports diagnostics on cycles, syntax errors, or `MISSING` / `CANCELED`
    blockers; `--filter` / `-f <ID>...` (and positional `<ID>...` under `chain`) filters by task IDs
    (bare `<ID>` matches across all projects in the active view, while `<project>:<ID>` matches only that
    project), scopes output to chains/tasks containing `<ID>...`, highlights them, and prints
    `Next actionable: <ref>` for a single ID; `--search` / `-s <QUERY>` (or `{cmd:todo_md} search <QUERY>`)
    searches task IDs (`<ID>` and `<project>:<ID>`), titles, and bodies across all projects in the active
    view (including `.todo_projects` child projects; `TODO.md` only unless `--all` or an archive status is
    set) and focuses the Quest-Log on matches, or prints full sections with `--full`; `--highlight` / `-H`
    is a boolean focus-disabling toggle that renders the full Quest-Log with matched `-f` / `-s` tasks
    highlighted (and accepts `-H <ID>...` as shorthand for `-f <ID>... -H`); `--all` includes both active
    `TODO.md` and archived `TODO_ARCHIVE.md` tasks across Quest-Log, `-s`, and `-f`; status filters work as
    `--status <STATUS>` or a bare `WIP|NEXT|QUESTION|NEW|HOLD|ACTIVE|ALL` keyword (`DONE|CANCELED|archive`
    render the list view) on `{cmd:todo_md} [opts]` and `{cmd:todo_md} chain [opts]`),
    `{cmd:todo_md} next-id [<ID>] [--role <role>]` (`--top`, top ready `WIP`/`NEXT`
    ID matching optional `--role`, or with `<ID>`/`<project>:<ID>` prints the
    first unblocked actionable ID in `<ID>`'s queue, exiting non-zero on cycles,
    missing/canceled blockers, or closed targets),
    `{cmd:todo_md} files [<ID>] [--max-lines N] [--max-total-lines N] [--max-bytes N] [--max-total-bytes N]`
    (existing backtick-referenced repo files within optional size budgets;
    reference target file paths and key symbol names in backticks in task
    bodies rather than brittle line ranges)
  - Create: `{cmd:todo_md} add [<PROJECT>] [<PREFIX>] "<title>" [-p <PREFIX>] [--next] [--status WIP|NEXT|NEW|HOLD|QUESTION] [-m "<note>"] [-b "<body_md>"|-] [--depends <spec>] [-c|--commit]`
    (auto-assigns `<ID>`, default prefix `F`; pass body via `-b`, `-b -` for `stdin`, or piped `stdin`;
    `{cmd:todo_md} init "<idea>"` bootstraps a new `TODO.md`)
  - Update: `{cmd:todo_md} edit <ID> [-t "<title>"] [-m "<note>"] [-b "<body_md>"|-] [--depends <spec>] [-c|--commit]`,
    `{cmd:todo_md} append <ID> [-b "<text>"|-] [-c|--commit]`
  - Dependencies (`--depends` and `- Depends on:`): use `,` for parallel items
    within a stage (`A,B`) and `->` for sequential stages (`"A -> B -> C"`,
    with `,` binding tighter than `->` as in `"A, B -> C"`); repeat
    `--depends` or add multiple `- Depends on:` lines for independent branches
    combined with AND; do not introduce a separate `- Order:` field;
    cross-project orchestrator dependencies (`<project>:<ID>`) preserve one-way
    repo boundaries without modifying child repos
  - Chain integration (both directions): whenever adding or refining a task,
    check existing open chains upstream (`--depends` on the new task) and
    downstream (`{cmd:todo_md} edit <ID> --depends ...` on existing open tasks,
    doc/help alignment tasks, or orchestrator waves that touch the same files
    or build on the new capability) so new tasks are wired into chains rather
    than left as unintended standalone tasks
  - Transition: `{cmd:todo_md} status <ID> <WIP|NEXT|NEW|HOLD|QUESTION> [-m "<note>"] [--reopen] [-c|--commit]`,
    `{cmd:todo_md} next <ID> [-m "<note>"] [--reopen] [-c|--commit]` (promote to `🎯 [NEXT]` and strip `- Role: plan`),
    `{cmd:todo_md} reopen <ID> [--status <STATUS>] [-m "<note>"] [-c|--commit]` (reopen archived task to `TODO.md`, default `NEW`; transitions from `TODO_ARCHIVE.md` without `--reopen` or `reopen` are rejected)
  - Close (prepends to `TODO_ARCHIVE.md`): `{cmd:todo_md} done <ID> [-m "<note>"] [-c|--commit]`
    (prints `Unblocked: ...` when closing `<ID>` completes all prerequisites for
    open tasks in the current repo or workspace orchestrator),
    `{cmd:todo_md} cancel <ID> [-m "<reason>"] [-c|--commit]`
  - Validation & commits: mutating commands automatically validate and reorder
    `TODO.md` without git-committing by default (run `{cmd:todo_md} check` to
    validate manually; rejects stale completion date notes `— *YYYY-MM-DD...*`
    on active tasks in `TODO.md` so they are moved back to `TODO_ARCHIVE.md`
    or cleared):
    - `role=work`: do not pass `-c` / `--commit`; stage `TODO.md` and
      `TODO_ARCHIVE.md` into the final code commit so `done` is atomic with
      implementation. Record out-of-scope findings via `{cmd:todo_md} add` as
      problem/impact descriptions in default `NEW` status without `--depends`;
      they are staged into the final code commit, or committed immediately
      with `-c` / `--commit` when recorded after the code commit is already
      pushed or when no code commit follows.
    - `role=plan`, `role=design`, and `role=review`: batch `{cmd:todo_md}`
      mutations without `-c` and commit `TODO*.md` in a single commit once
      backlog updates are finished (via `-c` / `--commit` on the final
      `{cmd:todo_md}` command or `git add TODO*.md && git commit`) before
      starting `role=work`.
