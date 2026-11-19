# Description: Structured Markdown task management (TODO.md and TODO_ARCHIVE.md) via todo_md
- Task management (`{cmd:todo_md}`: `TODO.md`, `TODO_ARCHIVE.md`): Always
  inspect and modify `TODO.md` and `TODO_ARCHIVE.md` via `{cmd:todo_md}` (never
  via `cat` or manual file edits). Repository scope only: record each task in
  the `TODO.md` of the repository it belongs to, never in an unrelated
  repository's backlog.
  - Status lifecycle & auto-ordering: `TODO.md` keeps active tasks ordered by
    status (`🔵 [WIP]` -> `🎯 [NEXT]` -> `❓ [QUESTION]` -> `⚪ [NEW]` ->
    `⏸️ [HOLD]`), and `TODO_ARCHIVE.md` keeps closed tasks (`✅ [DONE]`,
    `❌ [CANCELED]`) newest-first. `NEW` is the default backlog status
    (rendered in compact view by `{cmd:todo_md}`), `NEXT` is promoted in
    `role=plan` for prioritized ready tasks (expanded view), `WIP` is set
    automatically when starting `role=work task=<ID>`, and `done` is run
    before the final commit in `role=work` so backlog updates are committed
    atomically with code changes.
  - Target selection: pass `-C <dir|project>` or `--project <name>` before
    any `{cmd:todo_md}` subcommand (`ids`, `list`, `archive`, `last`, `last-id`,
    `next-id`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`,
    `done`, `cancel`, `show`) to target a repository directory or discovered
    workspace project from any working directory (keep `-p` in `add` for ID
    prefix and `<project>:<ID>` strictly for task-level references; precedence:
    `-C`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory).
  - Inspect: `{cmd:todo_md} [--full] [-w]` (overview or cross-project workspace
    overview: full `WIP`/`NEXT`/`QUESTION`, or first `NEW`/`HOLD` task when none
    exist, + compact backlog; supports `<project>:<ID>` and `<project>` addressing),
    `{cmd:todo_md} projects` (list workspace projects and open counts), `{cmd:todo_md} <ID>` /
    `{cmd:todo_md} show <ID|last> [<STATUS|archive>]` (prints `Task:`, `Title:`, optional `Role:`,
    and `Workdir:` headers before `# TODO*.md:<line>`),
    `{cmd:todo_md} last [<STATUS|archive>]` (default: `NEW`),
    `{cmd:todo_md} last-id [<STATUS|archive>]` (default: `NEW`),
    `{cmd:todo_md} list [active|archive|all|<STATUS>] [--role <role>] [--ready] [--tree] [--limit N] [--full]`
    (orders each status bucket with ready tasks first and prerequisites before dependents;
    renders blocked `WIP`/`NEXT` items as `⏳ [WIP]` / `⏳ [NEXT]` and multi-step chains as full
    ordered paths `[blocked: A (<STATUS>) -> B (<STATUS>)]`;
    `--ready` filters active tasks to those with no unresolved dependencies;
    `--tree` renders active dependency chains as an indented hierarchy `├─` / `└─` with
    prerequisites above blocked dependents across status buckets, truncating titles with `...`
    to terminal width or falling back to compact ID-only tree lines on narrow terminals),
    `{cmd:todo_md} archive`, `{cmd:todo_md} ids`,
    `{cmd:todo_md} queue <ID> [--all]` (topologically sorted execution queue;
    hides `DONE` unless `--all` is passed; prints `[ready]` / `[blocked by: ...]`
    and `Next actionable: <ref>`),
    `{cmd:todo_md} chain [--by-role] [--role <role>] [--ready] [--limit N] [--include-hold]`
    (local or `-w` workspace dependency chains `A -> B -> C` separated from
    standalone tasks, showing padded `[role]` badges and ranked by critical-path
    unblock impact `[unblocks N]`; `--by-role` partitions active tasks into
    topologically sorted role queues: `Queue 1 (work)` with only `work`
    transitive deps, `Queue 2 (plan)` with `work`/`plan` transitive deps,
    `Queue 3 (design)`, and `Queue 4 (deferred work)` for `work` blocked by
    `plan`/`design` [omitted with `--ready`]; `--role <role>` filters displayed
    tasks while preserving DAG validation and unblock context; `--ready` filters
    to highest-leverage ready tasks; excludes `HOLD` and tasks transitively
    blocked by `HOLD` into `Held branches:` unless `--include-hold` is passed;
    reports diagnostics on cycles, syntax errors, or `MISSING` / `CANCELED`
    blockers),
    `{cmd:todo_md} next-id [<ID>]` (`--top`, top `WIP`/`NEXT` ID, or with
    `<ID>`/`<project>:<ID>` prints the first unblocked actionable ID in `<ID>`'s
    queue, exiting non-zero on cycles, missing/canceled blockers, or closed targets),
    `{cmd:todo_md} files [<ID>] [--max-lines N] [--max-total-lines N] [--max-bytes N] [--max-total-bytes N]`
    (existing backtick-referenced repo files within optional size budgets;
    reference target file paths and key symbol names in backticks in task
    bodies rather than brittle line ranges)
  - Create: `{cmd:todo_md} add [<PROJECT>] [<PREFIX>] "<title>" [-p <PREFIX>] [--next] [--status WIP|NEXT|NEW|HOLD|QUESTION] [-m "<note>"] [-b "<body_md>"|-] [--role <role>] [--depends <spec>] [-c|--commit]`
    (auto-assigns `<ID>`, default prefix `F`; pass body via `-b`, `-b -` for `stdin`, or piped `stdin`;
    `{cmd:todo_md} init "<idea>"` bootstraps a new `TODO.md`)
  - Update: `{cmd:todo_md} edit <ID> [-t "<title>"] [-m "<note>"] [-b "<body_md>"|-] [--role <role>] [--depends <spec>] [-c|--commit]`,
    `{cmd:todo_md} append <ID> [-b "<text>"|-] [-c|--commit]`
  - Dependencies (`--depends` and `- Depends on:`): use `,` for parallel items
    within a stage (`A,B`) and `->` for sequential stages (`"A -> B -> C"`,
    with `,` binding tighter than `->` as in `"A, B -> C"`); repeat
    `--depends` or add multiple `- Depends on:` lines for independent branches
    combined with AND; do not introduce a separate `- Order:` field;
    cross-project orchestrator dependencies (`<project>:<ID>`) preserve one-way
    repo boundaries without modifying child repos
  - Transition: `{cmd:todo_md} status <ID> <WIP|NEXT|NEW|HOLD|QUESTION> [-m "<note>"] [--reopen] [-c|--commit]`,
    `{cmd:todo_md} next <ID> [-m "<note>"] [--reopen] [-c|--commit]` (promote to `🎯 [NEXT]`),
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
      implementation.
    - `role=plan`, `role=design`, and `role=review`: batch `{cmd:todo_md}`
      mutations without `-c` and commit `TODO*.md` in a single commit once
      backlog updates are finished (via `-c` / `--commit` on the final
      `{cmd:todo_md}` command or `git add TODO*.md && git commit`) before
      starting `role=work`.
