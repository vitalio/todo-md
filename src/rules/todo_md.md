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
    automatically when starting `role=execute task=<ID>`, and `done` is run
    before the final commit in `role=execute` so backlog updates are committed
    atomically with code changes.
  - Inspect: `{cmd:todo_md} [--full] [-w]` (overview or cross-project workspace
    overview: full `WIP`/`NEXT`/`QUESTION`, or first `NEW`/`HOLD` task when none
    exist, + compact backlog; supports `<project>:<ID>` and `<project>` addressing),
    `{cmd:todo_md} projects` (list workspace projects and open counts), `{cmd:todo_md} <ID>` /
    `{cmd:todo_md} show <ID|last> [<STATUS|archive>]` (prints `Task:`, optional `Role:`,
    and `Workdir:` headers before `# TODO*.md:<line>`),
    `{cmd:todo_md} last [<STATUS|archive>]` (default: `NEW`),
    `{cmd:todo_md} last-id [<STATUS|archive>]` (default: `NEW`),
    `{cmd:todo_md} list [active|archive|all|<STATUS>] [--limit N] [--full]`,
    `{cmd:todo_md} archive`, `{cmd:todo_md} ids`,
    `{cmd:todo_md} next-id` (`--top`, top `WIP`/`NEXT` ID),
    `{cmd:todo_md} files [<ID>]` (existing backtick-referenced repo files)
  - Create: `{cmd:todo_md} add [<PROJECT>] [<PREFIX>] "<title>" [-p <PREFIX>] [--next] [--status WIP|NEXT|NEW|HOLD|QUESTION] [-m "<note>"] [-b "<body_md>"|-] [--role <role>] [--depends <ref>[,<ref>...]] [-c|--commit]`
    (auto-assigns `<ID>`, default prefix `F`; pass body via `-b`, `-b -` for `stdin`, or piped `stdin`;
    `{cmd:todo_md} init "<idea>"` bootstraps a new `TODO.md`)
  - Update: `{cmd:todo_md} edit <ID> [-t "<title>"] [-m "<note>"] [-b "<body_md>"|-] [--role <role>] [--depends <ref>[,<ref>...]] [-c|--commit]`,
    `{cmd:todo_md} append <ID> [-b "<text>"|-] [-c|--commit]`
  - Transition: `{cmd:todo_md} status <ID> <WIP|NEXT|NEW|HOLD|QUESTION> [-m "<note>"] [--reopen] [-c|--commit]`,
    `{cmd:todo_md} next <ID> [-m "<note>"] [--reopen] [-c|--commit]` (promote to `🎯 [NEXT]`),
    `{cmd:todo_md} reopen <ID> [--status <STATUS>] [-m "<note>"] [-c|--commit]` (reopen archived task to `TODO.md`, default `NEW`; transitions from `TODO_ARCHIVE.md` without `--reopen` or `reopen` are rejected)
  - Close (prepends to `TODO_ARCHIVE.md`): `{cmd:todo_md} done <ID> [-m "<note>"] [-c|--commit]`,
    `{cmd:todo_md} cancel <ID> [-m "<reason>"] [-c|--commit]`
  - Validation & commits: mutating commands automatically validate and reorder
    `TODO.md` without git-committing by default (run `{cmd:todo_md} check` to
    validate manually):
    - `role=execute`: do not pass `-c` / `--commit`; stage `TODO.md` and
      `TODO_ARCHIVE.md` into the final code commit so `done` is atomic with
      implementation.
    - `role=plan`, `role=design`, and `role=audit`: batch `{cmd:todo_md}`
      mutations without `-c` and commit `TODO*.md` in a single commit once
      backlog updates are finished (via `-c` / `--commit` on the final
      `{cmd:todo_md}` command or `git add TODO*.md && git commit`) before
      starting `role=execute`.
