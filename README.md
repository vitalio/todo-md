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

### Windows (PowerShell 7+)

```powershell
irm https://raw.githubusercontent.com/vitalio/todo_md/main/install.ps1 | iex
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

Global options accepted before subcommands:

- `-C <dir|project>`, `--project <name>` — target a repository directory or discovered workspace project from any working directory (keeping `-p` in `add` for ID prefix, and `<project>:<ID>` strictly for task-level references like `show`, `edit`, `done`, and `Depends on:`). Target precedence: `-C`/`--project` > `TODO_MD_CWD` > `<project>:<ID>` > current directory.
- `-w`, `--workspace` — operate across all discovered workspace projects.
- `--full` — show full task sections without compacting `NEW` / `HOLD`.
- `-c`, `--commit` — git-commit `TODO*.md` after mutating commands.

| Command | Description |
| :--- | :--- |
| `todo_md [project] [--full] [-w]` | Print `TODO.md` or workspace (`-w`) overview (supports `<project>` and `<project>:<ID>`) |
| `todo_md projects` | List discovered workspace projects and their open task counts |
| `todo_md <ID>` / `todo_md show <ID\|last>` | Show `Task:`, `Title:`, `Role:`, and `Workdir:` headers plus full Markdown section for task `<ID>` (or `last [<STATUS\|archive>]`, ready for `todo_md <ID> \| agents_bundle \| run_block`) |
| `todo_md last [<STATUS\|archive>]` | Show full Markdown section for last task in status/archive (default: `NEW`) |
| `todo_md last-id [<STATUS\|archive>]` | Print ID of last task in status/archive (default: `NEW`) |
| `todo_md list [filter] [--role ROLE] [--ready] [--tree] [--limit N] [--full]` | List tasks (`active`, `archive`, `all`, or `<STATUS>`) in dependency order with display-width aligned status badges, terminal-width column wrapping, full `[blocked: ...]` unblock chains, optional `--role` / `--ready` filters, and `--tree` single-line truncated hierarchy |
| `todo_md archive [<ID>] [-m NOTE]` | Print `TODO_ARCHIVE.md`, or archive task `<ID>` to `TODO_ARCHIVE.md` |
| `todo_md add [<PROJ>] [<PREFIX>] <TITLE> [opts]` | Add a new task with auto-assigned ID (`-p PREFIX`, `--next`, `--status STATUS`, `-m NOTE`, `-b BODY\|-`, `--role ROLE`, `--depends SPEC`) |
| `todo_md edit <ID> [opts]` | Update task title, note, body, role, or dependencies (`-t TITLE`, `-m NOTE`, `-b BODY\|-`, `--role ROLE`, `--depends SPEC`) |
| `todo_md append <ID> [-b TEXT\|-]` | Append progress/notes to task `<ID>` body (`-b TEXT\|-` or `stdin`) |
| `todo_md status <ID> <STATUS> [-m N] [--reopen]` | Update task status (`WIP`, `NEXT`, `NEW`, `HOLD`, `QUESTION`, `DONE`, `CANCELED`; `--reopen` required if archived) |
| `todo_md next <ID> [-m NOTE] [--reopen]` | Promote task `<ID>` to `🎯 [NEXT]` priority at the top of `TODO.md` (strips `- Role: plan` so non-`D` tasks transition to `work`; `--reopen` required if archived) |
| `todo_md reopen <ID> [--status S] [-m NOTE]` | Reopen archived task `<ID>` back to `TODO.md` (default status `NEW`, clears prior closing note unless `-m` is given) |
| `todo_md done <ID> [-m NOTE]` | Mark task `<ID>` as `✅ [DONE]`, move it to `TODO_ARCHIVE.md`, and print any newly `Unblocked:` tasks |
| `todo_md cancel <ID> [-m REASON]` | Mark task `<ID>` as `❌ [CANCELED]` and move it to `TODO_ARCHIVE.md` |
| `todo_md ids` | Print highest task IDs in use and next free ID per letter prefix |
| `todo_md queue <ID> [--all]` | Show topologically sorted execution queue for `<ID>` (use `--all` to include `DONE`) |
| `todo_md chain [--by-role] [--role ROLE] [--ready] [--limit N] [--include-hold]` | Show ready `work` chain finales (`[ready \| after: ...]`), numbered RPG progress chains (`Chain <N> (<total> tasks, <pct>% \| <done> done, <open> open):`), and standalone tasks (or role-tiered queues with `--by-role`) across the repository or `.todo_projects` orchestrator DAG (merging orchestrator blockers into child-project views, formatting task refs relative to `cwd`, and dimming external-project tasks in project-scoped chains), ranked by bug priority (`B*`), role execution ease, status, role-weighted velocity (`work=1, plan=2, design=5`), and total chain value (`-w` for workspace; `--role` to filter by role; `--ready` for actionable tasks with next unblocked targets) |
| `todo_md next-id [<ID>] [--role ROLE]` / `--top` | Print the top ready `WIP`/`NEXT` task ID (filtered by optional `--role`), or first ready task ID in `<ID>`'s queue |
| `todo_md files [<ID>] [opts]` | List existing repo file paths referenced in backticks in task `<ID>` (`--max-lines N`, `--max-total-lines N`, `--max-bytes N`, `--max-total-bytes N`) |
| `todo_md check` | Validate task headings, status badges, unique IDs, active task roles (`^[a-z][a-z0-9_-]*$`, single `- Role:`, no retired `execute`/`audit`), dependencies, and reject stale completion date notes on active tasks across `TODO*.md` |
| `todo_md init [TEXT] [--force]` | Create starter `TODO.md` (with optional project idea from `TEXT` or `stdin`) and `TODO_ARCHIVE.md` |
| `todo_md update [--force]` | Self-update `todo_md` from GitHub (`vitalio/todo_md`) |
| `todo_md check-update` | Check GitHub for a newer version |
| `todo_md -V`, `--version` | Print version and exit `0` |
| `todo_md -h`, `--help` | Print usage help and exit `0` |

## License

MIT © 2026 vitalio
