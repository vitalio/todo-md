# todo-md (`todo`)

**Structured Markdown task management (`TODO.md`, `TODO_ARCHIVE.md`) for humans and AI coding agents.**

`todo` (`vitalio/todo-md`) is a zero-dependency Python 3 CLI that keeps your repository's open tasks
(`TODO.md`) and completed/canceled history (`TODO_ARCHIVE.md`) clean, validated, and easy
to manage from the terminal.

## Quick Installation

### Linux & macOS

```bash
curl -fsSL https://raw.githubusercontent.com/vitalio/todo-md/main/install.sh | sh
```

## Quick Start

Initialize `TODO.md` and `TODO_ARCHIVE.md` in your repository:

```bash
todo init
todo
```

Create, update, and transition tasks via the CLI (mutating commands automatically validate and status-order `TODO.md`; pass `-c` / `--commit` to also git-commit `TODO*.md`):

```bash
todo add F "Implement feature X" --next -b "Goal and acceptance criteria."
todo status F1 WIP -m "started implementation"
todo append F1 -b "- [x] Unit tests added"
todo done F1 -m "a1b2c3d"
todo check
```

## CLI Reference

Mutating commands (`init`, `add`, `edit`, `append`, `rename`, `status`, `next`, `reopen`,
`done`, `cancel`, `archive <ID>...`) first run `git pull --ff-only --no-rebase --quiet` when the repository has a
configured git upstream, so task IDs are never assigned from a stale `HEAD`. The sync is
skipped outside a git repository, without an upstream, when `TODO_MD_NO_GIT_PULL=1` is
set, or when any tracked file (including `TODO*.md` modified earlier in an uncommitted
batch) has uncommitted changes. If the pull fails (for example the branch has diverged),
the command aborts with an error before touching `TODO*.md`.

Global options accepted before subcommands:

- `-C <dir>` — target a filesystem directory path relative to current `PWD` (matching `git -C <dir>`).
- `-p <project>`, `--project <name>` — target a discovered workspace or `.todo_projects` project name/alias before subcommands (keeping `-p <P>` inside `todo add` for task ID prefix, and `<project>:<ID>` for task-level references like `show`, `edit`, `done`, and `Depends on:`). Target precedence: `-C`/`-p`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory.
- `-w`, `--workspace` — operate across all discovered workspace projects.
- `--full` — show full task sections without compacting `NEW` / `HOLD` (bare `todo --full` prints the expanded Markdown overview; with `--search` it prints full matching sections).
- `-c`, `--commit` — git-commit `TODO*.md` after mutating commands.
- `--bundle`, `--plain`, `role=<role>` — context bundle protocol controls (see Context Bundle Protocol below).

| Command | Description |
| :--- | :--- |
| `todo [project] [opts] [-w]` | Print the default Quest-Log view of the repository, `<project>`, or workspace (`-w`): flat root-anchored chains in execution order (accepts the `chain` options below) |
| `todo overview [--full] [-w]` | Print the Markdown `TODO.md` or workspace overview (bare `todo --full` prints the expanded overview) |
| `todo projects` | List discovered workspace projects and their open task counts |
| `todo <ID>...` / `todo show <ID>...\|last` | Show `Task:`, `Prefix:`, `Status:`, `Title:`, and `Workdir:` headers plus the full Markdown section for one or more tasks (space- or comma-separated, including `<project>:<ID>`, separated by a blank line), or `last [<STATUS\|archive>]`, ready for `todo <ID> \| agents_bundle \| run_block` |
| `todo last [<STATUS\|archive>]` | Show full Markdown section for last task in status/archive (default: `NEW`) |
| `todo last-id [<STATUS\|archive>]` | Print ID of last task in status/archive (default: `NEW`) |
| `todo list [filter] [<ID>...] [--prefix P] [--status S] [-r\|--ready] [-s\|--search Q] [-H\|--highlight] [-l N\|--limit N] [--full]` | List tasks (`active`, `archive`, `all`, or `<STATUS>`) in dependency order with display-width aligned status badges, terminal-width column wrapping, full `[blocked: ...]` unblock chains, composable TTY target `<ID>...` highlighting and `DONE` dimming, and optional `--prefix` / `--status` / `-r` / `--ready` / `-s` / `--search` (`-H` / `--highlight` to highlight matches in full list) / `-l N` / `--limit N` filters |
| `todo archive [<ID>...] [-m NOTE] [--canceled]` | Print `TODO_ARCHIVE.md`, or archive task(s) `<ID>...` to `TODO_ARCHIVE.md` (as `DONE`, or `CANCELED` with `--canceled`) |
| `todo add [<PROJ>] [<PREFIX>] <TITLE> [opts]` | Add a new task with auto-assigned ID (`-p PREFIX`, `--next`, `--status STATUS`, `-m NOTE`, `-b BODY\|-`, `--depends SPEC`) |
| `todo edit <ID>... [opts]` | Update status, title, note, body, or dependencies for task(s) `<ID>...` (`--next`, `--status STATUS`, `-t TITLE`, `-m NOTE`, `-b BODY\|-`, `--depends SPEC`); a new body keeps existing `- Depends on:` lines that it omits, and `--depends ""` clears dependencies |
| `todo append <ID>... [-b TEXT\|-]` | Append progress/notes to task(s) `<ID>...` body (`-b TEXT\|-` or `stdin`) |
| `todo rename <OLD> <NEW\|P> \| <OLD>=<NEW\|P>...` | Atomically rename task ID(s) across `TODO.md` and `TODO_ARCHIVE.md` (target can be an explicit `<NEW_ID>`, allowing swaps/cycles, or a single-letter prefix `A-Z` for the next free ID) and rewrite `- Depends on:` references (including `<project>:<OLD>` in workspace orchestrators) |
| `todo status <ID>... <STATUS> [-m N] [--reopen]` | Update status for one or more tasks (`WIP`, `NEXT`, `NEW`, `HOLD`, `QUESTION`, `DONE`, `CANCELED`; `--reopen` required if archived) |
| `todo next <ID>... [-m NOTE] [--reopen]` | Promote task(s) `<ID>...` to `🎯 [NEXT]` priority at the top of `TODO.md` (`--reopen` required if archived) |
| `todo reopen <ID>... [--status S] [-m NOTE]` | Reopen archived task(s) `<ID>...` back to `TODO.md` (default status `NEW`, clears prior closing note unless `-m` is given) |
| `todo done <ID>... [-m NOTE]` | Mark task(s) `<ID>...` as `✅ [DONE]`, move to `TODO_ARCHIVE.md`, and print any newly `Unblocked:` tasks |
| `todo cancel <ID>... [-m REASON]` | Mark task(s) `<ID>...` as `❌ [CANCELED]` and move to `TODO_ARCHIVE.md` |
| `todo ids` | Print highest task IDs in use and next free ID per letter prefix, followed by a compact prefix legend (`F` feature, `B` bugfix, `D` design, `L` legislative rule, custom `A-Z`) |
| `todo queue <ID>... [--all]` | Alias for `todo chain <ID>... [--all]`: focused Quest-Log of the chain(s) containing `<ID>...` with `Next actionable: <ref>` for a single ID (use `--all` to include `DONE`) |
| `todo chain [<ID>...] [opts]` | Show the Quest-Log: root-anchored RPG progress chains (`<pct>% \| <done>/<total> \| Chain <N> -> <root_ref>: <root_title>:`, with ready `WIP`/`NEXT` chain finales `[ready \| FINAL]` ranked first as top `Chain 1..K` entries) rendered as flat priority-topological rows by default (`--tree` / `-t` renders nested `<pct>% \| <done>/<total> \| Sub-chain -> <milestone_ref>: <title>:` milestone trees with 4-char connectors `├── `, `└── `, `└─► `), `[also in: <other_root_ref>, ...]` on shared prerequisites, and standalone tasks across the repository or `.todo_projects` orchestrator DAG (merging orchestrator blockers (including nested `.todo_projects` hierarchies expanded transitively and external project path aliases such as `~/chrome/canary` -> `chrome/canary:<ID>`) into child-project views, formatting task refs relative to `cwd`, and applying composable TTY styling for external-project tasks, `DONE` tasks, and highlighted targets), ranked with monotonic Quest Momentum by ready finale priority, bug priority (`B*`), active quest momentum / started-chain status floor, status tier (`WIP` -> `NEXT` -> `QUESTION` -> `NEW` -> `HOLD`), velocity, whole-cone size, and root tie-breaker. Options: `--all` (include archived `DONE`/`CANCELED` tasks from `TODO_ARCHIVE.md`), `-r` / `--ready` (ready tasks ranked by status tier, finale priority, bug priority, Quest Momentum continuation, best parent chain rank (tasks advancing `Chain 1` first), multi-chain count, completed prerequisite count, and immediate ready unlocks, shown as `[FINAL \| STAGE \| COMBO \| chain: <N>, ready: +<M>, unblocks: <K>]`, with `chain: <N>` shown only when `N > 1` and `ready: +<M>` only when `M > 0`), `--prefix PREFIX`, `-l N` / `--limit N` (`-n N` alias), `--include-hold`, `--numbered[=left\|right]` (period-free row numbers, default side `left`), `--status STATUS` or a bare `WIP\|NEXT\|QUESTION\|NEW\|HOLD\|ACTIVE\|ALL` keyword (`DONE\|CANCELED\|archive` render the list view), `-f` / `--filter <ID>...` (and positional `<ID>...`: bare `<ID>` matches across all projects in view, `<project>:<ID>` matches one project; focuses and highlights by default, and prints `Next actionable: <ref>` for a single ID), `-H` / `--highlight [<ID>...]` (boolean toggle disabling focus to render the full view with matched `-f`/`-s` tasks highlighted; `-H <ID>...` is shorthand for `-f <ID>... -H`), `-s` / `--search <QUERY>` (`-w` for workspace) |
| `todo search <QUERY> [opts]` | Search task IDs (`<ID>` and `<project>:<ID>`), titles, and bodies across all projects in the active view (including `.todo_projects` child projects; case-insensitive regex, falling back to substring; `TODO.md` only unless `--all` or an archive status is set) and focus the Quest-Log on matches (or highlight in full view with `-H`, or print full sections with `--full`; same as `todo -s <QUERY>`) |
| `todo next-id [<ID>] [--prefix P] [--status S]` / `--top` | Print the top ready `WIP`/`NEXT` task ID (filtered by optional `--prefix` and `--status`), or first ready task ID in `<ID>`'s queue |
| `todo check` | Validate task headings, status badges, unique IDs, dependencies (rejecting cross-project `<project>:<ID>` references in non-orchestrator repositories without `.todo_projects` / `.todo_projects.local`), in-body `- Role:` and `- Target files:` lines, and reject stale completion date notes on active tasks across `TODO*.md` |
| `todo init [TEXT] [--force]` | Create starter `TODO.md` (with optional project idea from `TEXT` or `stdin`) and `TODO_ARCHIVE.md` |
| `todo update [--force]` | Self-update `todo` from GitHub (`vitalio/todo-md`) |
| `todo check-update` | Check GitHub for a newer version |
| `todo uninstall`, `--uninstall` | Remove the installed `todo` binary |
| `todo -V`, `--version` | Print version and exit `0` |
| `todo -h`, `--help` | Print structured help (`Usage:`, `Commands:`, option sections; lines at most 100 columns, aligned description columns) and exit `0` |

## Task ID Prefixes

Task IDs are a single uppercase letter plus a number (`F1`, `B3`, `D2`, `L1`):

- `F` - feature (default prefix for `todo add`).
- `B` - bugfix (ranked ahead of other tasks in the Quest-Log).
- `D` - design task.
- `L` - legislative rule task (`agents/`, `AGENTS.md`).
- Any other `A-Z` letter is a custom domain prefix.

`todo` manages only tasks, prefixes (`A-Z`), statuses (`WIP`, `NEXT`,
`QUESTION`, `NEW`, `HOLD`, `DONE`, `CANCELED`), and dependency graphs.
`todo check` rejects `- Role:` and `- Target files:` lines across `TODO*.md`;
filter views natively with `--prefix` and `--status`.

## Context Bundle Protocol

`todo` is a self-contained producer of `context-bundle-protocol` v1 for
agent sessions (`todo <ID> | context | run`). In bundle mode it
prints `Bundle-*` transport headers (`Bundle-Protocol: 1`,
`Bundle-Name: vitalio/todo-md`, `Bundle-Command`, `Bundle-Boundary`), native task
preamble headers (`Task: <ID>`, `Prefix: <P>`, `Status: <S>`, `Title: <title>`,
`Workdir: <dir>`, plus `Role: <role>` only when an explicit `role=<role>` CLI
override is passed), the embedded `agents/todo.md` rule fragment
(`kind: "rule"`, `id: "vitalio/todo-md:todo"`), and the task section (or the
Quest-Log / overview for `todo [-w]` and `todo overview`) as a prompt
fragment (`kind: "prompt"`).

- Bundle mode is on with `--bundle` (`TODO_MD_BUNDLE=1`), or automatically when
  stdout is a pipe that is not the `run_block` step output (inside a
  `run_block` step without `RUN_BLOCK_STEP_STDOUT_INO`, plain output is used).
  `--plain` (`TODO_MD_PLAIN=1`) disables auto-detection.
- Read-only: `todo <ID>`, plain or in bundle mode, never changes `TODO.md`.
- Role override: `role=<role>` on `<ID>`, `show`, `last`, `overview`, and the
  default view emits `Role: <role>` in the bundle preamble
  (`todo <ID> role=plan | context | run`).

## License

MIT © 2026 vitalio
