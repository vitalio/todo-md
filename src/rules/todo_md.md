# Description: Structured Markdown task management (TODO.md and TODO_ARCHIVE.md) via todo_md
- Task management (`{cmd:todo_md}`: `TODO.md`, `TODO_ARCHIVE.md`): Always
  inspect and modify `TODO.md` and `TODO_ARCHIVE.md` via `{cmd:todo_md}` (never
  via `cat` or manual file edits). Repository scope only: record only tasks
  belonging to the current repository.
  - Inspect: `{cmd:todo_md} [--full]` (overview: full `WIP`/`NEXT` + compact
    backlog), `{cmd:todo_md} <ID>`, `{cmd:todo_md} list [active|archive|all|<STATUS>]`,
    `{cmd:todo_md} archive`, `{cmd:todo_md} ids`
  - Create: `{cmd:todo_md} add [<PREFIX>] "<title>" [-p <PREFIX>] [--next] [--status WIP|NEXT|NEW|HOLD|QUESTION] [-m "<note>"] [-b "<body_md>"]`
    (auto-assigns `<ID>`, default prefix `F`; pass body via `-b` or `stdin`;
    `{cmd:todo_md} init "<idea>"` bootstraps a new `TODO.md`)
  - Update: `{cmd:todo_md} edit <ID> [-t "<title>"] [-m "<note>"] [-b "<body_md>"]`,
    `{cmd:todo_md} append <ID> [-b "<text>"]`
  - Transition: `{cmd:todo_md} status <ID> <WIP|NEXT|NEW|HOLD|QUESTION> [-m "<note>"]`,
    `{cmd:todo_md} next <ID> [-m "<note>"]` (promote to `🎯 [NEXT]`)
  - Close (moves to `TODO_ARCHIVE.md`): `{cmd:todo_md} done <ID> [-m "<note>"] [--no-commit]`,
    `{cmd:todo_md} cancel <ID> [-m "<reason>"] [--no-commit]`
  - Auto-commit & validate: mutating commands automatically validate and
    git-commit `TODO*.md` (pass `--no-commit` when batching multiple updates or
    staging task completion into a release commit; run `{cmd:todo_md} check` to
    validate manually)
