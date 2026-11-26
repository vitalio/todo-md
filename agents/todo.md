# Description: Structured Markdown task management (TODO.md and TODO_ARCHIVE.md) via todo
- Task management (`{cmd:todo}`: `TODO.md`, `TODO_ARCHIVE.md`): Always inspect and
  modify `TODO.md` and `TODO_ARCHIVE.md` via `{cmd:todo}` (never via `cat` or
  manual file edits). Repository scope only: record each task in the `TODO.md`
  of the repository it belongs to (run `{cmd:todo} -h` for full CLI option lists).
  - Status lifecycle & task ID prefixes: `TODO.md` orders active tasks as
    `🔵 [WIP]` -> `🎯 [NEXT]` -> `❓ [QUESTION]` -> `⚪ [NEW]` -> `⏸️ [HOLD]`,
    and `TODO_ARCHIVE.md` keeps `✅ [DONE]` and `❌ [CANCELED]` newest-first.
    Status readiness contract: `NEW` for unscoped tasks needing planning,
    `NEXT` for scoped tasks ready for execution, `WIP` for active work,
    `QUESTION` for tasks blocked on clarification, `HOLD` for deferred items.
    Task ID prefixes (`A-Z`): `F` is a feature (default on `add`), `B` is a
    bugfix (ranked ahead in `chain`), `D` is a design task, `L` is a
    legislative rule task (`agents/`, `AGENTS.md`), and other `A-Z` prefixes
    are custom domains. `{cmd:todo} check` rejects `- Role:` and `- Target files:`
    lines across `TODO*.md`, and `{cmd:todo} [-B|--bundle] <ID> [role=<role>]`
    is read-only (`-B` / `--bundle` emits a `context-bundle-protocol` v1
    stream); start a task with `{cmd:todo} status <ID> WIP` or
    `{cmd:todo} next <ID>`.
  - Inspect & target selection: pass `-C <dir>` (filesystem directory relative
    to current `PWD`, matching `git -C <dir>`) or `-p <project>` / `--project
    <name>` (workspace / `.todo_projects` project name or alias) before
    subcommands (keeping `-p <P>` inside `{cmd:todo} add` for ID prefix, or
    `<project>:<ID>` on task refs). `{cmd:todo} projects` resolves workspace
    project names and aliases (including `<project_id>=<path>` in
    `.todo_projects` and `.todo_projects.local`) to physical directory paths.
    Core views: `{cmd:todo} [opts] [-w]`, `{cmd:todo} overview [--full] [-w]`,
    `{cmd:todo} projects`, `{cmd:todo} [show] <ID>...`,
    `{cmd:todo} list [active|archive|all|<STATUS>] [<ID>...] [--prefix <P>] [--status <S>] [--ready] [-s <QUERY>] [-l N] [--full]`,
    `{cmd:todo} chain [<ID>...] [--all] [--prefix <P>] [--status <S>] [--ready] [-l N] [--tree] [-f <ID>...] [-s <QUERY>]`.
    Do not re-run broad workspace views (`{cmd:todo}`, `overview`, `chain`)
    when the Quest-Log is already present in `===== Prompt =====`, and
    do not run `{cmd:todo} chain --all --tree` across the entire backlog
    without a target `<ID>` or `-l N`.
  - Mutate & validate: `{cmd:todo} add [<PROJECT>] [<PREFIX>] "<title>" [-p <P>]
    [-q|--quiet] [--next] [--status <S>] [-m "<note>"] [-b '<body_md>'|-]... [--depends <spec>]`
    auto-assigns and prints the new `<ID>` (`-q` / `--quiet` prints only `<ID>`;
    always capture auto-assigned IDs via `id=$({cmd:todo} add -q ...)` rather
    than guessing future IDs beforehand when wiring `--depends`),
    `{cmd:todo} edit <ID>... [--next] [--status <S>] [-t "<title>"]
    [-m "<note>"] [-b '<body_md>'|-]... [--depends <spec>]`,
    `{cmd:todo} append <ID>... [-b '<text>'|-]...` (repeated `-b` / `--body`
    flags are joined with `\n`; Markdown bodies containing backticks or `$`
    must use single quotes `-b '...'` or a quoted heredoc `-b - <<'EOF'` so
    `bash` does not execute inline code as command substitution),
    `{cmd:todo} rename <OLD> <NEW|PREFIX> | <OLD>=<NEW|PREFIX>...`,
    `{cmd:todo} next <ID>... [-m "<note>"]`,
    `{cmd:todo} status <ID>... <STATUS> [-m "<note>"]`,
    `{cmd:todo} reopen <ID>... [--status <S>] [-m "<note>"]`,
    `{cmd:todo} done <ID>... [-m "<note>"]`,
    `{cmd:todo} cancel <ID>... [-m "<reason>"]`,
    `{cmd:todo} archive [<ID>...] [-m "<note>"] [--canceled]`, `{cmd:todo} check`.
  - Dependencies & Chain integration (both directions): in `--depends` and
    `- Depends on:`, use `,` for parallel items (`A,B`), `->` for sequential
    stages (`"A -> B -> C"`), and `;` (or repeated `--depends` / `- Depends on:`
    lines) for independent AND branches (`"A -> B; C -> D"`;
    do not introduce a separate `- Order:` field). Because `,` binds tighter
    than `->`, `"X, A -> B, Y"` parses as `"(X, A) -> (B, Y)"`, so a sequential
    chain alongside parallel items must be separated with `;`
    (`"X, Y; A -> B"`). Cross-project `<project>:<ID>` dependencies are allowed
    only in orchestrator repositories with `.todo_projects` (or
    `.todo_projects.local`); `{cmd:todo} check` rejects them in
    non-orchestrator repositories. Wire new or refined tasks both upstream
    (`--depends`) and downstream (`{cmd:todo} edit <ID> --depends ...` on
    existing open tasks or waves).
