# todo_md

**Structured Markdown task management (`TODO.md`, `TODO_ARCHIVE.md`) for humans and AI coding agents.**

`todo_md` is a zero-dependency Python 3 CLI that keeps your repository's open tasks
(`TODO.md`) and completed/canceled history (`TODO_ARCHIVE.md`) clean, validated, and easy
to manage from the terminal.

## Quick Installation

### Linux & macOS

```bash
curl -fsSL https://raw.githubusercontent.com/vitalio/todo_md/main/install.sh | sh
```

## Quick Start

Initialize `TODO.md` and `TODO_ARCHIVE.md` in your repository:

```bash
todo_md init
todo_md
```

Create, update, and transition tasks via the CLI (mutating commands automatically validate and status-order `TODO.md`; pass `-c` / `--commit` to also git-commit `TODO*.md`):

```bash
todo_md add F "Implement feature X" --next -b "Goal and acceptance criteria."
todo_md status F1 WIP -m "started implementation"
todo_md append F1 -b "- [x] Unit tests added"
todo_md done F1 -m "a1b2c3d"
todo_md check
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

- `-C <dir|project>`, `--project <name>` — target a repository directory or discovered workspace project from any working directory (keeping `-p` in `add` for ID prefix, and `<project>:<ID>` strictly for task-level references like `show`, `edit`, `done`, and `Depends on:`). Target precedence: `-C`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory.
- `-w`, `--workspace` — operate across all discovered workspace projects.
- `--full` — show full task sections without compacting `NEW` / `HOLD` (bare `todo_md --full` prints the expanded Markdown overview; with `--search` it prints full matching sections).
- `-c`, `--commit` — git-commit `TODO*.md` after mutating commands.
- `--bundle`, `--plain`, `role=<role>` — context bundle protocol controls (see Context Bundle Protocol below).

| Command | Description |
| :--- | :--- |
| `todo_md [project] [opts] [-w]` | Print the default Quest-Log view of the repository, `<project>`, or workspace (`-w`): flat root-anchored chains in execution order (accepts the `chain` options below) |
| `todo_md overview [--full] [-w]` | Print the Markdown `TODO.md` or workspace overview (bare `todo_md --full` prints the expanded overview) |
| `todo_md projects` | List discovered workspace projects and their open task counts |
| `todo_md <ID>...` / `todo_md show <ID>...\|last` | Show `Task:`, `Prefix:`, `Status:`, `Title:`, and `Workdir:` headers plus the full Markdown section for one or more tasks (space- or comma-separated, including `<project>:<ID>`, separated by a blank line), or `last [<STATUS\|archive>]`, ready for `todo_md <ID> \| agents_bundle \| run_block` |
| `todo_md last [<STATUS\|archive>]` | Show full Markdown section for last task in status/archive (default: `NEW`) |
| `todo_md last-id [<STATUS\|archive>]` | Print ID of last task in status/archive (default: `NEW`) |
| `todo_md list [filter] [<ID>...] [--prefix P] [--status S] [-r\|--ready] [--limit N] [--full]` | List tasks (`active`, `archive`, `all`, or `<STATUS>`) in dependency order with display-width aligned status badges, terminal-width column wrapping, full `[blocked: ...]` unblock chains, composable TTY target `<ID>...` highlighting and `DONE` dimming, and optional `--prefix` / `--status` / `-r` / `--ready` filters |
| `todo_md archive [<ID>...] [-m NOTE] [--canceled]` | Print `TODO_ARCHIVE.md`, or archive task(s) `<ID>...` to `TODO_ARCHIVE.md` (as `DONE`, or `CANCELED` with `--canceled`) |
| `todo_md add [<PROJ>] [<PREFIX>] <TITLE> [opts]` | Add a new task with auto-assigned ID (`-p PREFIX`, `--next`, `--status STATUS`, `-m NOTE`, `-b BODY\|-`, `--depends SPEC`) |
| `todo_md edit <ID>... [opts]` | Update title, note, body, or dependencies for task(s) `<ID>...` (`-t TITLE`, `-m NOTE`, `-b BODY\|-`, `--depends SPEC`); a new body keeps existing `- Depends on:` lines that it omits, and `--depends ""` clears dependencies |
| `todo_md append <ID>... [-b TEXT\|-]` | Append progress/notes to task(s) `<ID>...` body (`-b TEXT\|-` or `stdin`) |
| `todo_md rename <OLD> <NEW\|P> \| <OLD>=<NEW\|P>...` | Atomically rename task ID(s) across `TODO.md` and `TODO_ARCHIVE.md` (target can be an explicit `<NEW_ID>`, allowing swaps/cycles, or a single-letter prefix `A-Z` for the next free ID) and rewrite `- Depends on:` references (including `<project>:<OLD>` in workspace orchestrators) |
| `todo_md status <ID>... <STATUS> [-m N] [--reopen]` | Update status for one or more tasks (`WIP`, `NEXT`, `NEW`, `HOLD`, `QUESTION`, `DONE`, `CANCELED`; `--reopen` required if archived) |
| `todo_md next <ID>... [-m NOTE] [--reopen]` | Promote task(s) `<ID>...` to `🎯 [NEXT]` priority at the top of `TODO.md` (`--reopen` required if archived) |
| `todo_md reopen <ID>... [--status S] [-m NOTE]` | Reopen archived task(s) `<ID>...` back to `TODO.md` (default status `NEW`, clears prior closing note unless `-m` is given) |
| `todo_md done <ID>... [-m NOTE]` | Mark task(s) `<ID>...` as `✅ [DONE]`, move to `TODO_ARCHIVE.md`, and print any newly `Unblocked:` tasks |
| `todo_md cancel <ID>... [-m REASON]` | Mark task(s) `<ID>...` as `❌ [CANCELED]` and move to `TODO_ARCHIVE.md` |
| `todo_md ids` | Print highest task IDs in use and next free ID per letter prefix, followed by a compact prefix legend (`F` feature, `B` bugfix, `D` design, `L` legislative rule, custom `A-Z`) |
| `todo_md queue <ID>... [--all]` | Alias for `todo_md chain <ID>... [--all]`: focused Quest-Log of the chain(s) containing `<ID>...` with `Next actionable: <ref>` for a single ID (use `--all` to include `DONE`) |
| `todo_md chain [<ID>...] [opts]` | Show the Quest-Log: root-anchored RPG progress chains (`[<pct>% \| <done>/<total>] Chain <N> -> <root_ref>: <root_title>:`, with ready `WIP`/`NEXT` chain finales `[ready \| FINAL]` ranked first as top `Chain 1..K` entries) rendered as flat priority-topological rows by default (`--tree` / `-t` renders nested `[<pct>% \| <done>/<total>] Sub-chain -> <milestone_ref>: <title>:` milestone trees with 4-char connectors `├── `, `└── `, `└─► `), `[also in: <other_root_ref>, ...]` on shared prerequisites, and standalone tasks across the repository or `.todo_projects` orchestrator DAG (merging orchestrator blockers (including nested `.todo_projects` hierarchies expanded transitively and external project path aliases such as `~/chrome/canary` -> `chrome/canary:<ID>`) into child-project views, formatting task refs relative to `cwd`, and applying composable TTY styling for external-project tasks, `DONE` tasks, and highlighted targets), ranked with monotonic Quest Momentum by ready finale priority, bug priority (`B*`), active quest momentum / started-chain status floor, status tier (`WIP` -> `NEXT` -> `QUESTION` -> `NEW` -> `HOLD`), velocity, whole-cone size, and root tie-breaker. Options: `--all` (include archived `DONE`/`CANCELED` tasks from `TODO_ARCHIVE.md`), `-r` / `--ready` (ready tasks ranked by status tier, finale priority, bug priority, Quest Momentum continuation, best parent chain rank (tasks advancing `Chain 1` first), multi-chain count, completed prerequisite count, and immediate ready unlocks, shown as `[FINAL \| STAGE \| COMBO \| chain: <N>, ready: +<M>, unblocks: <K>]`, with `chain: <N>` shown only when `N > 1` and `ready: +<M>` only when `M > 0`), `--prefix PREFIX`, `-l N` / `--limit N` (`-n N` alias), `--include-hold`, `--numbered[=left\|right]` (period-free row numbers, default side `left`), `--status STATUS` or a bare `WIP\|NEXT\|QUESTION\|NEW\|HOLD\|ACTIVE\|ALL` keyword (`DONE\|CANCELED\|archive` render the list view), `-f` / `--filter <ID>...` (and positional `<ID>...`: bare `<ID>` matches across all projects in view, `<project>:<ID>` matches one project; focuses and highlights by default, and prints `Next actionable: <ref>` for a single ID), `-H` / `--highlight [<ID>...]` (boolean toggle disabling focus to render the full view with matched `-f`/`-s` tasks highlighted; `-H <ID>...` is shorthand for `-f <ID>... -H`), `-s` / `--search <QUERY>` (`-w` for workspace) |
| `todo_md search <QUERY> [opts]` | Search task IDs (`<ID>` and `<project>:<ID>`), titles, and bodies across all projects in the active view (including `.todo_projects` child projects; case-insensitive regex, falling back to substring; `TODO.md` only unless `--all` or an archive status is set) and focus the Quest-Log on matches (or highlight in full view with `-H`, or print full sections with `--full`; same as `todo_md -s <QUERY>`) |
| `todo_md next-id [<ID>] [--prefix P] [--status S]` / `--top` | Print the top ready `WIP`/`NEXT` task ID (filtered by optional `--prefix` and `--status`), or first ready task ID in `<ID>`'s queue |
| `todo_md check` | Validate task headings, status badges, unique IDs, dependencies, in-body `- Role:` and `- Target files:` lines, and reject stale completion date notes on active tasks across `TODO*.md` |
| `todo_md init [TEXT] [--force]` | Create starter `TODO.md` (with optional project idea from `TEXT` or `stdin`) and `TODO_ARCHIVE.md` |
| `todo_md update [--force]` | Self-update `todo_md` from GitHub (`vitalio/todo_md`) |
| `todo_md check-update` | Check GitHub for a newer version |
| `todo_md -V`, `--version` | Print version and exit `0` |
| `todo_md -h`, `--help` | Print structured help (`Usage:`, `Commands:`, option sections; lines at most 100 columns, aligned description columns) and exit `0` |

## Task ID Prefixes

Task IDs are a single uppercase letter plus a number (`F1`, `B3`, `D2`, `L1`):

- `F` - feature (default prefix for `todo_md add`).
- `B` - bugfix (ranked ahead of other tasks in the Quest-Log).
- `D` - design task.
- `L` - legislative rule task (`agents/`, `AGENTS.md`).
- Any other `A-Z` letter is a custom domain prefix.

`todo_md` manages only tasks, prefixes (`A-Z`), statuses (`WIP`, `NEXT`,
`QUESTION`, `NEW`, `HOLD`, `DONE`, `CANCELED`), and dependency graphs.
`todo_md check` rejects `- Role:` and `- Target files:` lines across `TODO*.md`;
filter views natively with `--prefix` and `--status`.

## Context Bundle Protocol

`todo_md` is a self-contained producer of `context-bundle-protocol` v1 for
agent sessions (`todo_md <ID> | agents_bundle | run_block`). In bundle mode it
prints `Bundle-*` transport headers (`Bundle-Protocol: 1`,
`Bundle-Name: todo_md`, `Bundle-Command`, `Bundle-Boundary`), native task
preamble headers (`Task: <ID>`, `Prefix: <P>`, `Status: <S>`, `Title: <title>`,
`Workdir: <dir>`, plus `Role: <role>` only when an explicit `role=<role>` CLI
override is passed), the embedded `agents/todo_md.md` rule fragment
(`kind: "rule"`, `id: "todo_md:todo_md"`), and the task section (or the
Quest-Log / overview for `todo_md [-w]` and `todo_md overview`) as a prompt
fragment (`kind: "prompt"`).

- Bundle mode is on with `--bundle` (`TODO_MD_BUNDLE=1`), or automatically when
  stdout is a pipe that is not the `run_block` step output (inside a
  `run_block` step without `RUN_BLOCK_STEP_STDOUT_INO`, plain output is used).
  `--plain` (`TODO_MD_PLAIN=1`) disables auto-detection.
- Read-only: `todo_md <ID>`, plain or in bundle mode, never changes `TODO.md`.
- Role override: `role=<role>` on `<ID>`, `show`, `last`, `overview`, and the
  default view emits `Role: <role>` in the bundle preamble
  (`todo_md <ID> role=plan | agents_bundle | run_block`).

## License

MIT © 2026 vitalio
