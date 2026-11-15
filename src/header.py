#!/usr/bin/env python3
# todo_md-repo: vitalio/todo_md
"""Usage:
  {prog} [dir] [--full]                      Print TODO.md overview (full WIP/NEXT tasks + compact backlog + IDs)
  {prog} <ID> | show <ID|last>               Show full section for task <ID> (or last [<STATUS|archive>]) across TODO*.md
  {prog} last [<STATUS|archive>]           Show full section for last task in status/archive (default: NEW)
  {prog} last-id [<STATUS|archive>]        Print ID of last task in status/archive (default: NEW)
  {prog} list [filter] [--limit N] [--full]  List tasks (active | archive | all | <STATUS>)
  {prog} archive [<ID>] [-m NOTE]            Print TODO_ARCHIVE.md, or archive task <ID>
  {prog} add [<PREFIX>] <TITLE> [opts]       Add a new task with auto-assigned ID (reads body from -b TEXT or stdin)
                                             Opts: -p PREFIX (default: F), --next, --status STATUS, -m NOTE, -b BODY
  {prog} edit <ID> [opts]                    Update task title, note, or body (-t TITLE, -m NOTE, -b BODY or stdin)
  {prog} append <ID> [-b TEXT]               Append text to task <ID> body (from -b TEXT or stdin)
  {prog} status <ID> <STATUS> [-m NOTE]      Update status of <ID> (WIP|NEXT|NEW|HOLD|QUESTION|DONE|CANCELED)
  {prog} next <ID> [-m NOTE]                 Promote task <ID> to 🎯 [NEXT] priority at the top of TODO.md
  {prog} done <ID> [-m SHA_OR_NOTE]          Mark task <ID> as DONE and move it to TODO_ARCHIVE.md
  {prog} cancel <ID> [-m REASON]             Mark task <ID> as CANCELED and move it to TODO_ARCHIVE.md
  {prog} ids                                 Print highest task IDs in use and next available ID per prefix
  {prog} next-id | --next-id | --top         Print the top WIP or NEXT task ID in TODO.md
  {prog} files [<ID>] | --files [<ID>]       List existing repository file paths referenced in backticks in task <ID>
  {prog} check                               Validate layout, headings, status badges, and unique IDs
  {prog} init [TEXT] [--force]               Create starter TODO.md (with optional project idea from TEXT/stdin) and TODO_ARCHIVE.md
  {prog} update [--force]                    Self-update {prog} from GitHub (vitalio/todo_md)
  {prog} check-update                        Check if a newer version is available on GitHub
  {prog} -V | --version                      Print version and exit 0
  {prog} -h | --help                         Print this usage and exit 0

Mutating commands automatically validate and status-order TODO.md (pass -c / --commit to also
git-commit TODO*.md when inside a Git repository; --no-commit is accepted as a no-op alias).

Manages structured Markdown task files in a repository:
  - TODO.md          All open tasks ordered by status (🔵 [WIP], 🎯 [NEXT], ❓ [QUESTION], ⚪ [NEW], ⏸️ [HOLD])
  - TODO_ARCHIVE.md  Completed (✅ [DONE]) and dropped (❌ [CANCELED]) tasks (newest at top)

Environment variables:
  TODO_MD_CWD          Override target directory (default: current directory or Git root)
  TODO_MD_COMMIT       Set to 1 to git-commit TODO*.md automatically on mutating commands
  TODO_MD_NO_COMMIT    Set to 1 to suppress git commits even when --commit / TODO_MD_COMMIT is set
  TODO_MD_UPDATE_URL   Override raw script URL for update / check-update
"""
from __future__ import annotations

if __doc__ is None:
    raise SystemExit("missing usage documentation")

import os
import re
import subprocess
import sys
import tempfile
import urllib.request
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
STATUS_TOKEN_PAT = r"(?:(?:🔵|🎯|⚪|⏸️?|❓|✅|❌)\s+)?`?\[(?:WIP|NEXT|NEW|HOLD|QUESTION|DONE|CANCELED)\]`?"
ANY_ID_RE = re.compile(
    rf"^(?:#\s+(?:{STATUS_TOKEN_PAT}\s+|[-*o?+c]\s+)?|(?:- \[[ xX~]\]\s+(?:{STATUS_TOKEN_PAT}\s+)?|- |[*o?+c] ))([A-Z]\d+)\b"
)
BACKTICK_TOKEN_RE = re.compile(r"`([^`\n]+)`")


def prog_name() -> str:
    raw = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "todo_md"
    for suf in (".py", ".cmd", ".bat", ".exe"):
        if raw.lower().endswith(suf) and len(raw) > len(suf):
            raw = raw[:-len(suf)]
            break
    return raw or "todo_md"


def usage_text() -> str:
    return (__doc__ or "").format(prog=prog_name())
