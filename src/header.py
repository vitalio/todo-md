#!/usr/bin/env python3
# todo_md-repo: vitalio/todo_md
"""Usage:
  {prog} [-C DIR|PROJ] [command] [opts]    Run any command against a target directory or workspace project
  {prog} [dir|project] [opts] [-w]           Print the default Quest-Log view: flat chains in execution order (see Quest-Log options)
  {prog} overview [--full] [-w]              Print the Markdown overview (full WIP/NEXT/QUESTION or first task + compact); bare --full prints it expanded
  {prog} search <QUERY> [opts]               Search task IDs, titles, and bodies (same as -s/--search QUERY)
  {prog} projects                            List discovered workspace projects and open task counts
  {prog} <ID>... | show <ID>... | show last  Show tasks <ID>... (space- or comma-separated, supports <project>:<ID>, blank-line separated)
                                             with Task/Title/Role/Workdir headers; last [<STATUS|archive>] shows the last task in a status
  {prog} last [<STATUS|archive>]           Show full section for last task in status/archive (default: NEW)
  {prog} last-id [<STATUS|archive>]        Print ID of last task in status/archive (default: NEW)
  {prog} list [filter] [<ID>...] [opts]      List tasks (active | archive | all | <STATUS>; highlight <ID>...; opts: --role ROLE, --ready, --limit N, --full)
  {prog} archive [<ID>] [-m NOTE]            Print TODO_ARCHIVE.md, or archive task <ID>
  {prog} add [<PROJ>] [<PREFIX>] <TITLE>     Add a new task with auto-assigned ID (reads body from -b TEXT|- or stdin)
                                             Opts: -p PREFIX (default: F), --next, --status STATUS, -m NOTE, -b BODY|-, --role ROLE, --depends SPEC
  {prog} edit <ID> [opts]                    Update task title, note, body, role, or deps (-t TITLE, -m NOTE, -b BODY|-, --role ROLE, --depends SPEC)
  {prog} append <ID> [-b TEXT|-]             Append text to task <ID> body (from -b TEXT|- or stdin)
  {prog} status <ID> <STATUS> [opts]         Update status of <ID> (WIP|NEXT|NEW|HOLD|QUESTION|DONE|CANCELED; opts: -m NOTE, --reopen)
  {prog} next <ID> [-m NOTE] [--reopen]      Promote task <ID> to 🎯 [NEXT] priority at the top of TODO.md (strips - Role: plan; --reopen if archived)
  {prog} reopen <ID> [opts]                  Move archived task <ID> back to TODO.md (opts: -s/--status STATUS [default: NEW], -m NOTE)
  {prog} done <ID> [-m SHA_OR_NOTE]          Mark task <ID> as DONE and move it to TODO_ARCHIVE.md
  {prog} cancel <ID> [-m REASON]             Mark task <ID> as CANCELED and move it to TODO_ARCHIVE.md
  {prog} ids                                 Print highest task IDs in use and next available ID per prefix
  {prog} queue <ID> [--all]                  Alias for chain <ID> [--all]: focused Quest-Log with Next actionable (--all includes DONE)
  {prog} chain [<ID>...] [opts]              Show the Quest-Log: chain finales, root-anchored chains, role queues, ready tasks (see Quest-Log options)
  {prog} next-id [<ID>] [--role ROLE] | --top  Print top ready WIP/NEXT ID, or first ready ID in <ID>'s queue
  {prog} files [<ID>] | --files [<ID>]       List existing repository file paths referenced in backticks in task <ID>
                                             Opts: --max-lines N, --max-total-lines N, --max-bytes N, --max-total-bytes N
  {prog} check                               Validate layout, headings, status badges, and unique IDs
  {prog} init [TEXT] [--force]               Create starter TODO.md (with optional project idea from TEXT/stdin) and TODO_ARCHIVE.md
  {prog} update [--force]                    Self-update {prog} from GitHub (vitalio/todo_md)
  {prog} check-update                        Check if a newer version is available on GitHub
  {prog} -V | --version                      Print version and exit 0
  {prog} -h | --help                         Print this usage and exit 0

Global options (accepted before subcommands):
  -C DIR|PROJ, --project NAME   Target repository directory or workspace project
                                (precedence: -C/--project > TODO_MD_CWD > <project>:<ID> > cwd;
                                keep -p in 'add' for ID prefix and <project>:<ID> for task refs)
  -w, --workspace               Operate across all discovered workspace projects
  --full                        Show full task sections without compacting NEW/HOLD
  -c, --commit                  Git-commit TODO*.md after mutating commands (opt-in)
  --no-commit                   Accepted as a no-op alias (commits are disabled by default)

Quest-Log options ({prog} [opts], {prog} chain [<ID>...] [opts], {prog} queue <ID>, {prog} search <QUERY>):
  -t, --tree                    Render nested Sub-chain milestone trees with 4-char connectors (default: flat rows in execution order)
  --numbered[=left|right]       Add period-free row numbers padded to the widest number (default: no numbers; side default: left)
  -l N, --limit N, -n N         Limit displayed rows to N (-n is a backward-compatible alias)
  --all                         Include resolved DONE prerequisites (same as the ALL status keyword)
  --ready                       Show only ready tasks with their next unblocked targets
  --by-role                     Partition active tasks into role queues
  --role ROLE                   Show only tasks matching ROLE
  --include-hold                Include HOLD tasks and branches blocked by HOLD
  --status STATUS               Status filter WIP|NEXT|QUESTION|NEW|HOLD|ACTIVE|ALL (also accepted as a bare keyword);
                                DONE|CANCELED|ARCHIVE render the list view instead
  -f, --focus <ID>...           Scope output to chains containing <ID>... (highlighted; prints Next actionable for one ID);
                                positional <ID>... under chain/queue do the same
  -H, --highlight <ID>...       Render the full Quest-Log and highlight <ID>...
  -s, --search QUERY            Search IDs, titles, and bodies (case-insensitive regex, substring if invalid); searches TODO.md only
                                unless --all or an archive status is set; scopes the Quest-Log, or prints sections with --full

Tabular views (list, chain, queue, projects) align status badges by display width and wrap long
descriptions into aligned columns based on terminal width (falling back to a 4-space indent on
narrow terminals). Mutating commands automatically validate and
status-order TODO.md (pass -c / --commit to also git-commit TODO*.md when inside a Git repository;
--no-commit is accepted as a no-op alias).

Manages structured Markdown task files in a repository:
  - TODO.md          All open tasks ordered by status (🔵 [WIP], 🎯 [NEXT], ❓ [QUESTION], ⚪ [NEW], ⏸️ [HOLD])
  - TODO_ARCHIVE.md  Completed (✅ [DONE]) and dropped (❌ [CANCELED]) tasks (newest at top)

Environment variables:
  TODO_MD_CWD          Override target directory (default: current directory)
  TODO_MD_WORKSPACE    Override workspace root directory for project discovery and <project>:<ID>
  TODO_MD_PROJECTS     Override or specify configured .todo_projects file/list for orchestrator chain DAGs
  TODO_MD_COMMIT       Set to 1 to git-commit TODO*.md automatically on mutating commands
  TODO_MD_NO_COMMIT    Set to 1 to suppress git commits even when --commit / TODO_MD_COMMIT is set
  TODO_MD_UPDATE_URL   Override raw script URL for update / check-update
"""
from __future__ import annotations

if __doc__ is None:
    raise SystemExit("missing usage documentation")

import heapq
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

VERSION = "__VERSION__"
REPO_MARKER = "todo_md-repo: vitalio/todo_md"
DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/vitalio/todo_md/main/todo_md"
FENCE = chr(96) * 3

VALID_STATUSES: dict[str, str] = {
    "WIP": "🔵",
    "NEXT": "🎯",
    "QUESTION": "❓",
    "NEW": "⚪",
    "HOLD": "⏸️",
    "DONE": "✅",
    "CANCELED": "❌",
}

ACTIVE_STATUS_ORDER: dict[str, int] = {
    "WIP": 0,
    "NEXT": 1,
    "QUESTION": 2,
    "NEW": 3,
    "HOLD": 4,
}

TASK_FILES = ("TODO.md", "TODO_ARCHIVE.md")

HEADING_RE = re.compile(
    r"^#\s+(🔵|🎯|⚪|⏸️?|❓|✅|❌)\s+`?\[(WIP|NEXT|NEW|HOLD|QUESTION|DONE|CANCELED)\]`?\s+([A-Z]\d+)\s*:\s*(.+?)\s*$"
)
STALE_COMPLETION_NOTE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:\b|$)")
STATUS_TOKEN_PAT = r"(?:(?:🔵|🎯|⚪|⏸️?|❓|✅|❌)\s+)?`?\[(?:WIP|NEXT|NEW|HOLD|QUESTION|DONE|CANCELED)\]`?"
ANY_ID_RE = re.compile(
    rf"^(?:#\s+(?:{STATUS_TOKEN_PAT}\s+|[-*o?+c]\s+)?|(?:- \[[ xX~]\]\s+(?:{STATUS_TOKEN_PAT}\s+)?|- |[*o?+c] ))([A-Z]\d+)\b"
)
BACKTICK_TOKEN_RE = re.compile(r"`([^`\n]+)`")
PROJECT_TASK_RE = re.compile(r"^(.+?):([A-Za-z]\d+)$")
DEPENDS_LINE_RE = re.compile(r"^\s*[-*]\s*Depends on:\s*(.+?)\s*$", re.IGNORECASE)
ROLE_LINE_RE = re.compile(r"^\s*[-*]\s*Role:\s*(.*?)\s*$", re.IGNORECASE)
ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
RETIRED_ROLES: dict[str, str] = {
    "execute": "work",
    "audit": "review",
}
PREFIX_DEFAULT_ROLES: dict[str, str] = {
    "D": "design",
}
ROLE_EASE_ORDER: dict[str, int] = {
    "work": 0,
    "plan": 1,
    "design": 2,
}
ROLE_EFFORT_WEIGHTS: dict[str, int] = {
    "work": 1,
    "plan": 2,
    "design": 5,
}
WORKSPACE_SKIP_DIRS = frozenset({
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "__pycache__",
    "venv",
    "env",
    "Pods",
    "DerivedData",
})
WORKSPACE_MAX_DEPTH = 3


def prog_name() -> str:
    raw = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "todo_md"
    for suf in (".py", ".cmd", ".bat", ".exe"):
        if raw.lower().endswith(suf) and len(raw) > len(suf):
            raw = raw[:-len(suf)]
            break
    return raw or "todo_md"


def usage_text() -> str:
    return (__doc__ or "").format(prog=prog_name())
