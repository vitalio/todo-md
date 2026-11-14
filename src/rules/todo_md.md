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
  - Inspect: `{cmd:todo_md} [--full]` (overview: full `WIP`/`NEXT`/`QUESTION` +
    compact `NEW`/`HOLD` backlog), `{cmd:todo_md} <ID>`,
    `{cmd:todo_md} list [active|archive|all|<STATUS>]`,
    `{cmd:todo_md} archive`, `{cmd:todo_md} ids`
  - Create: `{cmd:todo_md} add [<PREFIX>] "<title>" [-p <PREFIX>] [--next] [--status WIP|NEXT|NEW|HOLD|QUESTION] [-m "<note>"] [-b "<body_md>"] [-c|--commit]`
    (auto-assigns `<ID>`, default prefix `F`; pass body via `-b` or `stdin`;
    `{cmd:todo_md} init "<idea>"` bootstraps a new `TODO.md`)
  - Update: `{cmd:todo_md} edit <ID> [-t "<title>"] [-m "<note>"] [-b "<body_md>"] [-c|--commit]`,
    `{cmd:todo_md} append <ID> [-b "<text>"] [-c|--commit]`
  - Transition: `{cmd:todo_md} status <ID> <WIP|NEXT|NEW|HOLD|QUESTION> [-m "<note>"] [-c|--commit]`,
    `{cmd:todo_md} next <ID> [-m "<note>"] [-c|--commit]` (promote to `🎯 [NEXT]`)
  - Close (prepends to `TODO_ARCHIVE.md`): `{cmd:todo_md} done <ID> [-m "<note>"] [-c|--commit]`,
    `{cmd:todo_md} cancel <ID> [-m "<reason>"] [-c|--commit]`
  - Validation & commits: mutating commands automatically validate and reorder
    `TODO.md` without git-committing by default (pass `-c` / `--commit` for a
    standalone `TODO*.md` commit, or stage `TODO*.md` into the final commit;
    run `{cmd:todo_md} check` to validate manually)
