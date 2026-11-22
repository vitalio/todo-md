# Description: Structured Markdown task management (TODO.md and TODO_ARCHIVE.md) via todo_md
[if role=work]
- Task management (`todo_md`: `TODO.md`, `TODO_ARCHIVE.md`, `role=work`):
  - Always inspect and modify `TODO.md` and `TODO_ARCHIVE.md` via `todo_md`
    (never via `cat` or manual file edits). Repository scope only: record each
    task in the `TODO.md` of the repository it belongs to.
  - Close the active task via `todo_md done <ID>` inside the final guarded
    commit step (after the edit-and-diff step is verified clean, immediately
    before staging and `git commit`, never during the edit step). Do not pass
    `-c` / `--commit`; stage `TODO.md` and `TODO_ARCHIVE.md` into the final
    code commit so backlog updates are committed atomically with code changes.
  - Record out-of-scope findings via
    `todo_md add "<title>" -b "<problem_and_impact>"` in default `NEW` status
    without `--depends`; stage them into the final code commit (or pass `-c` /
    `--commit` when recorded after the code commit is already pushed or when no
    code commit follows). Run `todo_md -h` for full CLI flags and options.
[endif]
[if role!=work]
- Task management (`todo_md`: `TODO.md`, `TODO_ARCHIVE.md`): Always inspect and
  modify `TODO.md` and `TODO_ARCHIVE.md` via `todo_md` (never via `cat` or
  manual file edits). Repository scope only: record each task in the `TODO.md`
  of the repository it belongs to (run `todo_md -h` for full CLI option lists).
  - Status lifecycle & role derivation: `TODO.md` orders active tasks as
    `🔵 [WIP]` -> `🎯 [NEXT]` -> `❓ [QUESTION]` -> `⚪ [NEW]` -> `⏸️ [HOLD]`,
    and `TODO_ARCHIVE.md` keeps `✅ [DONE]` and `❌ [CANCELED]` newest-first.
    Task ID prefixes: `F` is a feature (default on `add`), `B` is a bugfix
    (ranked ahead in `chain`), `D` is a design task (`D*` -> `design` in any
    status), and other `A-Z` prefixes are custom domains; non-`D` tasks resolve
    to `work` in `WIP`/`NEXT` and `plan` in `NEW`/`QUESTION`/`HOLD`.
    `todo_md check` rejects `- Role:` lines in active `TODO.md` tasks,
    `todo_md next <ID>` strips an existing `- Role: plan` line, and
    `todo_md <ID>` in bundle mode (`todo_md <ID> | agents_bundle | run_block`)
    emits `Role: <role>`, auto-transitions `NEXT` `work` (and `NEW`/`NEXT` `D*`
    `design`) tasks to `WIP` (`--no-wip` opts out), and preloads target files
    (`--no-files` opts out).
  - Inspect & target selection: pass `-C <dir|project>` or `--project <name>`
    before subcommands (or `<project>:<ID>` on task refs). Core views:
    `todo_md [opts] [-w]`, `todo_md overview [--full] [-w]`, `todo_md projects`,
    `todo_md [show] <ID>...`, `todo_md last[-id] [<STATUS|archive>]`,
    `todo_md list [active|archive|all|<STATUS>] [<ID>...] [--role <role>] [-r|--ready] [--limit N] [--full]`,
    `todo_md archive`, `todo_md ids`, `todo_md queue <ID> [--all]` (alias for `todo_md chain <ID> [--all]`),
    `todo_md chain [<ID>...] [--all] [--by-role] [--role <role>] [--ready] [-l N|--limit N] [--include-hold] [--tree] [--numbered[=left|right]] [-f <ID>...] [-H] [-s <QUERY>]`,
    `todo_md next-id [<ID>] [--role <role>]`,
    `todo_md files [<ID>] [--max-lines N] [--max-total-lines N] [--max-bytes N] [--max-total-bytes N]`.
  - Mutate & validate: `todo_md add [<PROJECT>] [<PREFIX>] "<title>" [-p <P>]
    [--next] [--status <S>] [-m "<note>"] [-b "<body_md>"|-] [--depends <spec>]
    [-c]`, `todo_md edit <ID> [-t "<title>"] [-m "<note>"] [-b "<body_md>"|-]
    [--depends <spec>] [-c]`, `todo_md append <ID> [-b "<text>"|-] [-c]`,
    `todo_md next <ID> [-m "<note>"] [--reopen] [-c]`,
    `todo_md status <ID> <STATUS> [-m "<note>"] [--reopen] [-c]`,
    `todo_md reopen <ID> [--status <S>] [-m "<note>"] [-c]`,
    `todo_md done <ID> [-m "<note>"] [-c]`,
    `todo_md cancel <ID> [-m "<reason>"] [-c]`, `todo_md check`. In
    `role=plan`, `role=design`, and `role=review`, batch mutations without `-c`
    and commit `TODO*.md` once backlog updates are complete; in `role=work`,
    run `todo_md done <ID>` inside the final commit step without `-c`.
  - Dependencies & Chain integration (both directions): in `--depends` and
    `- Depends on:`, use `,` for parallel items (`A,B`) and `->` for sequential
    stages (`"A -> B -> C"`, `,` binds tighter than `->`; repeat for AND
    branches; do not introduce a separate `- Order:` field). Wire new or refined
    tasks both upstream (`--depends`) and downstream (`todo_md edit <ID>
    --depends ...` on existing open tasks or waves).
  - Target files contract: record touched files on one `- Target files:` bullet
    (backticked, excluding `TODO*.md` and `AGENTS.md`) when promoting a task to
    `NEXT`: plain paths for files <= 400 lines, and `path:symbol`,
    `path:sym1..sym2`, or `path:start-end` slices for larger files.
[endif]
