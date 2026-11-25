# todo-md (`todo`)

**Structured Markdown task management (`TODO.md`, `TODO_ARCHIVE.md`) for humans and AI coding agents.**

`todo` (`vitalio/todo-md`) is a zero-dependency Python 3 CLI that turns your repository's
open tasks (`TODO.md`) and completed history (`TODO_ARCHIVE.md`) into an interactive
RPG-style Quest-Log. It tracks dependency chains, highlights what is actionable right now,
and shows what each completed task unlocks next.

## Quick Installation

### Linux & macOS

```bash
curl -fsSL https://raw.githubusercontent.com/vitalio/todo-md/main/install.sh | sh
```

## Quick Start

Initialize `TODO.md` and `TODO_ARCHIVE.md` in your repository and view the Quest-Log:

```bash
todo init
todo
```

Create, update, and close tasks (mutating commands automatically validate and status-order
`TODO.md`; pass `-c` / `--commit` to also git-commit `TODO*.md`):

```bash
todo add F "Implement feature X" --next -b "Goal and acceptance criteria."
todo status F1 WIP -m "started implementation"
todo append F1 -b "- [x] Unit tests added"
todo done F1 -m "a1b2c3d"
```

Wire task dependencies (`--depends`) and drill into the Quest-Log by ready tasks (`-r`),
milestone trees (`-t`), or focused chains (`-f`):

```bash
todo add F "Ship v1 release" --depends "F1 -> F2, F3"
todo -r
todo -t
todo -f F4
```

## Quest-Log Views

Running `todo` (or `todo <project>`, `todo -w`, `todo chain`) renders the Quest-Log:

- **Overall progress header**: `<pct>% · ✅ <done>/<total> · <open> open: 🟢 <ready> ready (<count> <emoji> <STATUS>, ...) · ⏳ <blocked> blocked · ⏸️ <held> held`.
- **Root-anchored chains**: `<pct>% · <done>/<total> · Chain <N> -> <root_ref>: <root_title>:` rendered as flat topological rows in execution order by default, or as nested `<pct>% · <done>/<total> · Sub-chain -> <milestone_ref>: <title>:` trees with 4-char connectors (`├── `, `└── `, `└─► `) under `-t` / `--tree`.
- **Quest Momentum ranking**: ready `WIP` / `NEXT` chain finales (`🟢 ready · 🏁 FINAL`) rank first as top `Chain 1..K` entries, followed by chains ordered by bugfix priority (`B*`), active quest momentum / started-chain status floor, status tier (`WIP` -> `NEXT` -> `QUESTION` -> `NEW` -> `HOLD`), velocity, whole-cone size, and root tie-breaker. Shared prerequisites annotate cross-chain membership with `🔗 also in: <other_root_ref>, ...`.
- **Ready queue (`-r` / `--ready`)**: ranks immediately actionable tasks by bugfix prefix, status tier, Quest Momentum continuation, best parent chain rank (tasks advancing `Chain 1` first), multi-chain count, completed prerequisite count, and immediate ready unlocks (`🏁 FINAL · ⚡ STAGE · 🔥 COMBO · ⛓️ chain: <N> · 🟢 ready: +<M> · 🔓 unblocks: <K>`, showing `⛓️ chain: <N>` when `N > 1` and `🟢 ready: +<M>` when `M > 0`).
- **Dependency syntax (`--depends` / `- Depends on:`)**: `,` separates parallel items within a stage, `->` separates sequential stages (`,` binds tighter than `->`, e.g. `A, B -> C`), and `;` separates independent AND branches (`A -> B; C -> D`). In orchestrator repositories with `.todo_projects` (or `.todo_projects.local`, supporting project paths and `<project_id>=<path>` aliases), cross-project `<project>:<ID>` blockers merge transitively into child-project views.

## CLI Reference

### Commands

| Command | Description |
| :--- | :--- |
| `todo [dir\|project] [opts] [-w]` | Print the default Quest-Log view of the repository, `<project>`, or workspace (`-w`): flat root-anchored chains in execution order |
| `todo overview [--full] [-w]` | Print the Markdown `TODO.md` or workspace overview (full `WIP`/`NEXT`/`QUESTION` or first task, plus compact backlog; bare `todo --full` prints it expanded) |
| `todo search <QUERY> [opts]` | Search task IDs (`<ID>` and `<project>:<ID>`), titles, and bodies across all projects in view and focus the Quest-Log on matches (same as `todo -s <QUERY>`) |
| `todo projects` | List workspace or `.todo_projects` orchestrator projects, open task counts, and resolved physical directory paths |
| `todo <ID>...` / `todo show <ID>...\|last` | Show `Task:`, `Prefix:`, `Status:`, `Title:`, and `Workdir:` headers plus full Markdown sections (space- or comma-separated, `<project>:<ID>` supported, separated by blank lines), ready for `todo <ID> \| context \| run` |
| `todo last [<STATUS\|archive>]` | Show full Markdown section for the last task in a status or archive (default: `NEW`; also available as `todo show last`) |
| `todo last-id [<STATUS\|archive>]` | Print ID of the last task in a status or archive (default: `NEW`) |
| `todo list [filter] [<ID>...] [opts]` | List tasks (`active`, `archive`, `all`, or `<STATUS>`) in dependency order with aligned status badges, `[blocked: ...]` chains, and target `<ID>...` highlighting (`--prefix P`, `--status S`, `-r`/`--ready`, `-s`/`--search Q`, `-H`/`--highlight`, `-l N`/`--limit N`, `--full`) |
| `todo archive [<ID>...] [-m NOTE] [--canceled]` | Print `TODO_ARCHIVE.md`, or archive task(s) `<ID>...` to `TODO_ARCHIVE.md` (as `DONE`, or `CANCELED` with `--canceled`) |
| `todo add [<PROJ>] [<PREFIX>] <TITLE> [opts]` | Add a task with an auto-assigned ID; body comes from `-b` (repeatable, joined with `\n`) or `stdin` (`-p PREFIX` default `F`, `-q`/`--quiet`/`--id-only`, `--next`, `--status STATUS`, `-m NOTE`, `-b BODY\|-`, `--depends SPEC`) |
| `todo edit <ID>... [opts]` | Update status, title, note, body, or dependencies (`--next`, `--status STATUS`, `-t TITLE`, `-m NOTE`, `-b BODY\|-` repeatable, `--depends SPEC`; a new body keeps existing `- Depends on:` lines it omits, and `--depends ""` clears dependencies) |
| `todo append <ID>... [-b TEXT\|-]` | Append text to the body of task(s) `<ID>...` (from repeatable `-b TEXT\|-` or `stdin`) |
| `todo rename <OLD> <NEW\|P> \| <OLD>=<NEW\|P>...` | Atomically rename task ID(s) across `TODO*.md` (explicit `<NEW_ID>`, allowing swaps/cycles, or single-letter prefix `A-Z` for next free ID) and rewrite `- Depends on:` references |
| `todo status <ID>... <STATUS> [-m NOTE] [--reopen]` | Set task status (`WIP`, `NEXT`, `NEW`, `HOLD`, `QUESTION`, `DONE`, `CANCELED`; `--reopen` if archived) |
| `todo next <ID>... [-m NOTE] [--reopen]` | Promote task(s) `<ID>...` to `🎯 [NEXT]` at the top of `TODO.md` (`--reopen` if archived) |
| `todo reopen <ID>... [-s\|--status S] [-m NOTE]` | Move archived task(s) `<ID>...` back to `TODO.md` (default status: `NEW`, clearing prior closing note unless `-m` is given) |
| `todo done <ID>... [-m SHA_OR_NOTE]` | Mark `<ID>...` as `✅ [DONE]`, move to `TODO_ARCHIVE.md`, and print any newly `Unblocked:` tasks |
| `todo cancel <ID>... [-m REASON]` | Mark `<ID>...` as `❌ [CANCELED]` and move to `TODO_ARCHIVE.md` |
| `todo ids` | Print highest task IDs in use and next available ID per prefix, followed by the prefix legend |
| `todo chain [<ID>...] [opts]` | Show the Quest-Log: overall progress header, top-ranked finales, root-anchored chains, and ready tasks (see Global & Quest-Log Options) |
| `todo queue <ID>... [--all]` | Alias for `todo chain <ID>... [--all]`: focused Quest-Log of the chain(s) containing `<ID>...` with `Next actionable: <ref>` for a single ID |
| `todo next-id [<ID>] [--prefix P] [--status S]` / `--top` | Print the top ready `WIP`/`NEXT` task ID (or matching `--status`), or the first ready ID in `<ID>`'s queue |
| `todo check` | Validate layout, task headings, status badges, unique IDs, dependency syntax/cycles, cross-project refs, forbidden `- Role:` / `- Target files:` lines, and stale completion notes |
| `todo init [TEXT] [--force]` | Create starter `TODO.md` (with optional project idea from `TEXT` or `stdin`) and `TODO_ARCHIVE.md` |
| `todo update [--force]` | Self-update `todo` from GitHub (`vitalio/todo-md`); makes a network call |
| `todo check-update` | Check if a newer version is available on GitHub; makes a network call |
| `todo uninstall` / `--uninstall` | Remove the installed `todo` binary |
| `todo -V` / `--version` | Print version and exit `0` |
| `todo -h` / `--help` | Print structured usage (`Usage:`, `Commands:`, option and environment tables) and exit `0` |

### Global & Quest-Log Options

| Option | Description |
| :--- | :--- |
| `-C DIR` | Run as if `todo` was started in filesystem directory `DIR` relative to current `PWD` (matching `git -C DIR`) |
| `-p PROJ`, `--project PROJ` | Target workspace or `.todo_projects` project name/alias before subcommands (precedence: `-C`/`-p`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > `cwd`; inside `add`, `-p PREFIX` sets the task ID prefix) |
| `-w`, `--workspace` | Operate across all discovered workspace projects |
| `--full` | Show full task sections without compacting `NEW`/`HOLD` (bare `todo --full` prints the expanded Markdown overview; with `-s`/`--search` prints full matching sections) |
| `-c`, `--commit` | Git-commit `TODO*.md` after mutating commands (opt-in; creates a git commit) |
| `--no-commit` | Accepted as a no-op alias (commits are disabled by default) |
| `--bundle` | Emit a `context-bundle-protocol` v1 stream for `<ID>` (`show`), `last`, the default view, and `overview` (read-only: never changes task status) |
| `--plain` | Disable bundle auto-detection (`--bundle` takes precedence) |
| `role=ROLE` | Bundle mode explicit role override for `<ID>`, `show`, `last`, `overview`, and the default view: emits `Role: ROLE` in the bundle preamble |
| `-t`, `--tree` | Render nested `Sub-chain` milestone trees with 4-char connectors (`├── `, `└── `, `└─► `; default: flat rows in execution order) |
| `--numbered[=left\|right]` | Add period-free row numbers padded to the widest number (default: no numbers; side default: `left`) |
| `-l N`, `--limit N`, `-n N` | Limit displayed rows to `N` (`-n` is a backward-compatible alias) |
| `--all` | Include archived `DONE`/`CANCELED` tasks from `TODO_ARCHIVE.md` (same as the `ALL` status keyword) |
| `-r`, `--ready` | Show only ready tasks ranked by bugfix prefix, status tier, Quest Momentum, best chain rank, chain count, done count, and ready unlocks (also accepted by `list`) |
| `--prefix PREFIX` | Show only tasks matching single-letter ID prefix `PREFIX` (`A-Z`) |
| `--include-hold` | Include `HOLD` tasks and branches blocked by `HOLD` |
| `--status STATUS` | Status filter `WIP\|NEXT\|QUESTION\|NEW\|HOLD\|ACTIVE\|ALL` (also accepted as a bare keyword); `DONE\|CANCELED\|ARCHIVE` render the `list` view instead |
| `-f`, `--filter <ID>...` | Filter by task IDs (bare `<ID>` matches across all projects in view, `<project>:<ID>` matches one project); focuses and highlights by default, and prints `Next actionable: <ref>` for one ID (positional `<ID>...` under `chain` do the same) |
| `-H`, `--highlight [<ID>...]` | Disable focus to render the full Quest-Log with matched `-f`/`-s` tasks highlighted (or pass `-H <ID>...` as shorthand for `-f <ID>... -H`) |
| `-s`, `--search QUERY` | Search task IDs (`<ID>` and `<project>:<ID>`), titles, and bodies across all projects in view (case-insensitive regex, falling back to substring; `TODO.md` only unless `--all` or an archive status is set) |

Mutating commands (`init`, `add`, `edit`, `append`, `rename`, `status`, `next`, `reopen`,
`done`, `cancel`, `archive <ID>...`) first run `git pull --ff-only --no-rebase --quiet` when
the repository has a configured git upstream (skipped outside a git repository, without an
upstream, when `TODO_MD_NO_GIT_PULL=1` is set, or when tracked files have uncommitted
changes), then automatically validate and status-order `TODO.md`.

### Environment

| Variable | Description |
| :--- | :--- |
| `TODO_MD_CWD` | Override target directory (default: current directory) |
| `TODO_MD_WORKSPACE` | Override workspace root directory for project discovery and `<project>:<ID>` |
| `TODO_MD_PROJECTS` | Override or specify configured `.todo_projects` file/list for orchestrator chain DAGs |
| `TODO_MD_COMMIT` | Set to `1` to git-commit `TODO*.md` automatically on mutating commands |
| `TODO_MD_NO_COMMIT` | Set to `1` to suppress git commits even when `--commit` / `TODO_MD_COMMIT` is set |
| `TODO_MD_NO_GIT_PULL` | Set to `1` to skip `git pull --ff-only` upstream sync before mutating commands |
| `TODO_MD_BUNDLE` | Set to `1` to emit bundle streams (same as `--bundle`) |
| `TODO_MD_PLAIN` | Set to `1` to disable bundle auto-detection (same as `--plain`) |
| `TODO_MD_UPDATE_URL` | Override raw script URL for `update` / `check-update` |

## Task ID Prefixes

Task IDs are a single uppercase letter plus a number (`F1`, `B3`, `D2`, `L1`):

- `F` — feature (default prefix for `todo add`).
- `B` — bugfix (ranked ahead of other tasks in the Quest-Log).
- `D` — design task.
- `L` — legislative rule task (`agents/`, `AGENTS.md`).
- Any other `A-Z` letter is a custom domain prefix.

`todo` manages only tasks, prefixes (`A-Z`), statuses (`WIP`, `NEXT`, `QUESTION`, `NEW`,
`HOLD`, `DONE`, `CANCELED`), and dependency graphs. `todo check` rejects `- Role:` and
`- Target files:` lines across `TODO*.md`; filter views natively with `--prefix` and
`--status`.

## Context Bundle Protocol

`todo` is a self-contained producer of `context-bundle-protocol` v1 for agent sessions
(`todo <ID> | context | run`). In bundle mode it prints `Bundle-*` transport headers
(`Bundle-Protocol: 1`, `Bundle-Name: vitalio/todo-md`, `Bundle-Command`, `Bundle-Boundary`),
native task preamble headers (`Task: <ID>`, `Prefix: <P>`, `Status: <S>`, `Title: <title>`,
`Workdir: <dir>`, plus `Role: <role>` only when an explicit `role=<role>` CLI override is
passed), the embedded `agents/todo.md` rule fragment (`kind: "rule"`,
`id: "vitalio/todo-md:todo"`), and the task section (or the Quest-Log / overview for
`todo [-w]` and `todo overview`) as a prompt fragment (`kind: "prompt"`).

- Bundle mode is on with `--bundle` (`TODO_MD_BUNDLE=1`), or automatically when stdout is
  piped into `context` (`agents_bundle`) or `run` (`run_block`) outside a `run_block` step
  output pipe (piping to standard shell filters like `grep`, `less`, `head`, `tail`, `wc`,
  `awk`, `sed`, `sort`, `cut`, or `tr` keeps plain output). `--plain` (`TODO_MD_PLAIN=1`)
  disables auto-detection.
- Read-only: `todo <ID>`, plain or in bundle mode, never changes `TODO.md`.
- Role override: `role=<role>` on `<ID>`, `show`, `last`, `overview`, and the default view
  emits `Role: <role>` in the bundle preamble (`todo <ID> role=plan | context | run`).

## License

[MIT](LICENSE)
