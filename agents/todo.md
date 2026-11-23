# Description: Structured Markdown task management (TODO.md and TODO_ARCHIVE.md) via todo
- Task management (`{cmd:todo}`: `TODO.md`, `TODO_ARCHIVE.md`): Always inspect and
  modify `TODO.md` and `TODO_ARCHIVE.md` via `{cmd:todo}` (never via `cat` or
  manual file edits). Repository scope only: record each task in the `TODO.md`
  of the repository it belongs to (run `{cmd:todo} -h` for full CLI option lists).
  - Status lifecycle & task ID prefixes: `TODO.md` orders active tasks as
    `🔵 [WIP]` -> `🎯 [NEXT]` -> `❓ [QUESTION]` -> `⚪ [NEW]` -> `⏸️ [HOLD]`,
    and `TODO_ARCHIVE.md` keeps `✅ [DONE]` and `❌ [CANCELED]` newest-first.
    Task ID prefixes (`A-Z`): `F` is a feature (default on `add`), `B` is a
    bugfix (ranked ahead in `chain`), `D` is a design task, `L` is a
    legislative rule task (`agents/`, `AGENTS.md`), and other `A-Z` prefixes
    are custom domains. `{cmd:todo} check` rejects `- Role:` and `- Target files:`
    lines across `TODO*.md`, and `{cmd:todo} <ID> [role=<role>]` is read-only;
    start a task with `{cmd:todo} status <ID> WIP` or `{cmd:todo} next <ID>`.
  - Inspect & target selection: pass `-C <dir>` (filesystem directory relative
    to current `PWD`, matching `git -C <dir>`) or `-p <project>` / `--project
    <name>` (workspace / `.todo_projects` project name or alias) before
    subcommands (keeping `-p <P>` inside `{cmd:todo} add` for ID prefix, or
    `<project>:<ID>` on task refs). Core views:
    `{cmd:todo} [opts] [-w]`, `{cmd:todo} overview [--full] [-w]`, `{cmd:todo} projects`,
    `{cmd:todo} [show] <ID>...`, `{cmd:todo} last[-id] [<STATUS|archive>]`,
    `{cmd:todo} list [active|archive|all|<STATUS>] [<ID>...] [--prefix <P>] [--status <S>] [-r|--ready] [-s <QUERY>] [-H] [-l N|--limit N] [--full]`,
    `{cmd:todo} archive [<ID>...] [-m "<note>"] [--canceled] [-c]`, `{cmd:todo} ids`,
    `{cmd:todo} queue <ID>... [--all]` (alias for `{cmd:todo} chain <ID>... [--all]`),
    `{cmd:todo} chain [<ID>...] [--all] [--prefix <P>] [--status <S>] [--ready] [-l N|--limit N] [--tree] [-f <ID>...] [-H] [-s <QUERY>]`,
    `{cmd:todo} next-id [<ID>] [--prefix <P>] [--status <S>]`. Do not re-run broad
    workspace views (`{cmd:todo}`, `overview`, `chain`) when the Quest-Log is
    already present in `===== Prompt =====`, and do not run `{cmd:todo} chain --all
    --tree` across the entire backlog without a target `<ID>` or `-l N`.
  - Mutate & validate: `{cmd:todo} add [<PROJECT>] [<PREFIX>] "<title>" [-p <P>]
    [--next] [--status <S>] [-m "<note>"] [-b "<body_md>"|-] [--depends <spec>]
    [-c]`, `{cmd:todo} edit <ID>... [--next] [--status <S>] [-t "<title>"]
    [-m "<note>"] [-b "<body_md>"|-] [--depends <spec>] [-c]`, `{cmd:todo} append <ID>... [-b "<text>"|-] [-c]`,
    `{cmd:todo} rename <OLD> <NEW|PREFIX> | <OLD>=<NEW|PREFIX>... [-c]`,
    `{cmd:todo} next <ID>... [-m "<note>"] [--reopen] [-c]`,
    `{cmd:todo} status <ID>... <STATUS> [-m "<note>"] [--reopen] [-c]`,
    `{cmd:todo} reopen <ID>... [--status <S>] [-m "<note>"] [-c]`,
    `{cmd:todo} done <ID>... [-m "<note>"] [-c]`,
    `{cmd:todo} cancel <ID>... [-m "<reason>"] [-c]`, `{cmd:todo} check`.
  - Dependencies & Chain integration (both directions): in `--depends` and
    `- Depends on:`, use `,` for parallel items (`A,B`), `->` for sequential
    stages (`"A -> B -> C"`, `,` binds tighter than `->`), and `;` (or repeated
    `--depends` / `- Depends on:` lines) for independent AND branches (`"A -> B;
    C -> D"`; do not introduce a separate `- Order:` field). Wire new or refined
    tasks both upstream (`--depends`) and downstream (`{cmd:todo} edit <ID>
    --depends ...` on existing open tasks or waves).
