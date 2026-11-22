#!/usr/bin/env python3
# todo_md-repo: vitalio/todo_md
"""todo_md CLI. Help text is rendered by usage_text() from the help tables below."""
from __future__ import annotations

if __doc__ is None:
    raise SystemExit("missing usage documentation")

import contextlib
import heapq
import io
import json
import os
import re
import secrets
import shlex
import shutil
import stat
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
EMBEDDED_RULE_TODO_MD = "__EMBEDDED_RULE_TODO_MD__"
EMBEDDED_RULE_TODO_MD_WORK = "__EMBEDDED_RULE_TODO_MD_WORK__"
RULE_SOURCE_PATH = Path(__file__).resolve().parent.parent / "agents" / "todo_md.md"
RULE_WORK_SOURCE_PATH = Path(__file__).resolve().parent.parent / "agents" / "todo_md_work.md"

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
LINE_SLICE_RE = re.compile(
    r"^(?P<path>.+?)(?::(?P<a>\d+)(?:-(?P<b>\d+))?(?::\d+)?|#L(?P<c>\d+)(?:-L?(?P<d>\d+))?)$"
)
FILE_SPEC_RE = re.compile(r"^(?P<path>.+):(?P<start>\d+)-(?P<end>\d+)$")
PROJECT_TASK_RE = re.compile(r"^(.+?):([A-Za-z]\d+)$")
TARGET_FILES_LINE_RE = re.compile(r"^\s*[-*]\s*Target files:", re.IGNORECASE)
BULLET_LINE_RE = re.compile(r"^\s*[-*]\s")
SYMBOL_SPEC_RE = re.compile(
    r"^(?P<path>[^:\s]+):(?P<first>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)"
    r"(?:\.\.(?P<last>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*))?\Z"
)
DEPENDS_LINE_RE = re.compile(r"^\s*[-*]\s*Depends on:\s*(.+?)\s*$", re.IGNORECASE)
ROLE_LINE_RE = re.compile(r"^\s*[-*]\s*Role:\s*(.*?)\s*$", re.IGNORECASE)
ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
RETIRED_ROLES: dict[str, str] = {
    "execute": "work",
    "audit": "review",
}
DEFAULT_TASK_PREFIX = "F"
PREFIX_INFO: dict[str, tuple[str, str | None]] = {
    "F": ("feature", None),
    "B": ("bugfix", None),
    "D": ("design", "design"),
}
PREFIX_DEFAULT_ROLES: dict[str, str] = {
    prefix: role for prefix, (_, role) in PREFIX_INFO.items() if role
}
STATUS_ROLES: dict[str, str] = {
    "WIP": "work",
    "NEXT": "work",
    "NEW": "plan",
    "QUESTION": "plan",
    "HOLD": "plan",
}

def prefix_legend_lines() -> list[str]:
    prefixes = ", ".join(
        f"{p}={name}" + (" (default)" if p == DEFAULT_TASK_PREFIX else "")
        for p, (name, _) in PREFIX_INFO.items()
    )
    design = ", ".join(f"{p}*={role}" for p, role in PREFIX_DEFAULT_ROLES.items())
    work = "/".join(s for s, r in STATUS_ROLES.items() if r == "work")
    plan = "/".join(s for s, r in STATUS_ROLES.items() if r == "plan")
    return [
        f"Prefixes: {prefixes}, other A-Z=custom domain",
        f"Roles: {design}; others: {work}=work, {plan}=plan",
    ]
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


def _rule_text(embedded: str, name: str, path: Path) -> str:
    if embedded != "__EMBEDDED_RULE_" + name + "__":
        raw = embedded
    else:
        raw = path.read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if not line.startswith("# Description:")]
    return "\n".join(lines).strip("\n") + "\n"

def get_embedded_todo_rule(role: str | None = None) -> str:
    if (role or "").strip().lower() == "work":
        return _rule_text(EMBEDDED_RULE_TODO_MD_WORK, "TODO_MD_WORK", RULE_WORK_SOURCE_PATH)
    return _rule_text(EMBEDDED_RULE_TODO_MD, "TODO_MD", RULE_SOURCE_PATH)

def prog_name() -> str:
    raw = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "todo_md"
    for suf in (".py", ".cmd", ".bat", ".exe"):
        if raw.lower().endswith(suf) and len(raw) > len(suf):
            raw = raw[:-len(suf)]
            break
    return raw or "todo_md"


HELP_MAX_WIDTH = 100
HELP_PROSE_WIDTH = 80
HELP_INDENT = 2
HELP_GAP = 2

HELP_USAGE = (
    "{prog} [-C DIR|PROJ] [dir|project] [opts] [-w]",
    "{prog} [-C DIR|PROJ] <command> [args] [opts]",
    "{prog} <ID>...",
)

HELP_INTRO = (
    "With no command, prints the default Quest-Log view: flat root-anchored chains in "
    "execution order. Bare <ID>... prints those tasks (same as show)."
)

HELP_COMMANDS: tuple[tuple[str, str], ...] = (
    ("{prog} overview [--full] [-w]",
     "Print the Markdown overview (full WIP/NEXT/QUESTION or first task, plus compact "
     "backlog); bare --full prints it expanded"),
    ("{prog} search <QUERY> [opts]",
     "Search task IDs, titles, and bodies (same as -s/--search QUERY)"),
    ("{prog} projects", "List discovered workspace projects and open task counts"),
    ("{prog} <ID>... | show <ID>...",
     "Show tasks <ID>... (space- or comma-separated, <project>:<ID> supported) with "
     "Task/Title/Role/Workdir headers, separated by blank lines"),
    ("{prog} last [<STATUS|archive>]",
     "Show full section for the last task in a status or the archive (default: NEW); "
     "also available as show last"),
    ("{prog} last-id [<STATUS|archive>]",
     "Print ID of the last task in a status or the archive (default: NEW)"),
    ("{prog} list [filter] [<ID>...] [opts]",
     "List tasks; filter is active | archive | all | <STATUS>; <ID>... are highlighted. "
     "Options: --role ROLE, -r/--ready, --limit N, --full"),
    ("{prog} archive [<ID>] [-m NOTE]", "Print TODO_ARCHIVE.md, or archive task <ID>"),
    ("{prog} add [<PROJ>] [<PREFIX>] <TITLE>",
     "Add a task with an auto-assigned ID; body comes from -b or stdin. Options: "
     "-p PREFIX (default: F), --next, --status STATUS, -m NOTE, -b BODY|-, --depends SPEC"),
    ("{prog} edit <ID> [opts]",
     "Update a task. Options: -t TITLE, -m NOTE, -b BODY|-, --depends SPEC"),
    ("{prog} append <ID> [-b TEXT|-]",
     "Append text to the body of task <ID> (from -b TEXT|- or stdin)"),
    ("{prog} status <ID> <STATUS> [opts]",
     "Set status (WIP|NEXT|NEW|HOLD|QUESTION|DONE|CANCELED). Options: -m NOTE, --reopen"),
    ("{prog} next <ID> [-m NOTE] [--reopen]",
     "Promote task <ID> to 🎯 [NEXT] at the top of TODO.md (strips - Role: plan; "
     "--reopen if archived)"),
    ("{prog} reopen <ID> [opts]",
     "Move archived task <ID> back to TODO.md. Options: -s/--status STATUS (default: NEW), "
     "-m NOTE"),
    ("{prog} done <ID> [-m SHA_OR_NOTE]",
     "Mark <ID> as DONE and move it to TODO_ARCHIVE.md"),
    ("{prog} cancel <ID> [-m REASON]",
     "Mark <ID> as CANCELED and move it to TODO_ARCHIVE.md"),
    ("{prog} ids", "Print highest task IDs in use and next available ID per prefix"),
    ("{prog} chain [<ID>...] [opts]",
     "Show the Quest-Log: top-ranked work finales, root-anchored chains, role queues, "
     "ready tasks (see Quest-Log options)"),
    ("{prog} next-id [<ID>] [--role ROLE] | --top",
     "Print the top ready WIP/NEXT ID, or the first ready ID in <ID>'s queue"),
    ("{prog} files [<ID>] | --files [<ID>]",
     "List files named on the '- Target files:' bullet of task <ID>: paths, glob patterns, "
     "symbol slices (path:SYMBOL, path:SYM1..SYM2; Python, sh/Bash and brace languages; "
     "a symbol not found falls back to the whole file with a warning) and line slices "
     "(path:START-END, path:LINE, "
     "path#LSTART-LEND), merged per file and printed as path or path:START-END. Options: "
     "--max-lines N, --max-total-lines N, --max-bytes N, --max-total-bytes N (budgets count "
     "only the sliced lines)"),
    ("{prog} check", "Validate layout, headings, status badges, and unique IDs"),
    ("{prog} init [TEXT] [--force]",
     "Create starter TODO.md (with optional project idea from TEXT/stdin) and "
     "TODO_ARCHIVE.md"),
    ("{prog} update [--force]",
     "Self-update {prog} from GitHub (vitalio/todo_md); makes a network call"),
    ("{prog} check-update",
     "Check if a newer version is available on GitHub; makes a network call"),
    ("{prog} -V | --version", "Print version and exit 0"),
    ("{prog} -h | --help", "Print this usage and exit 0"),
)

HELP_GLOBAL_OPTIONS: tuple[tuple[str, str], ...] = (
    ("-C DIR|PROJ, --project NAME",
     "Target repository directory or workspace project (precedence: -C/--project > "
     "TODO_MD_CWD > <project>:<ID> > cwd; keep -p in 'add' for ID prefix and "
     "<project>:<ID> for task refs)"),
    ("-w, --workspace", "Operate across all discovered workspace projects"),
    ("--full", "Show full task sections without compacting NEW/HOLD"),
    ("-c, --commit",
     "Git-commit TODO*.md after mutating commands (opt-in; creates a git commit)"),
    ("--no-commit", "Accepted as a no-op alias (commits are disabled by default)"),
    ("--bundle",
     "Emit a context-bundle-protocol v1 stream for <ID> (show), last, the default view and "
     "overview; auto-enabled when stdout is a pipe other than the run_block step output. "
     "The stream is read-only: it never changes task status"),
    ("--plain", "Disable bundle auto-detection (--bundle takes precedence)"),
    ("--no-files", "Bundle mode: do not preload the '- Target files:' of the task"),
    ("role=ROLE, --role ROLE",
     "Bundle mode session role for <ID>, show, last, overview, and the default view (--role "
     "ROLE only for <ID>, show, last, overview): sets the Role: header and selects the "
     "matching embedded rule (work -> compact rule, others -> full rule)"),
)

HELP_QUEST_OPTIONS: tuple[tuple[str, str], ...] = (
    ("-t, --tree",
     "Render nested Sub-chain milestone trees with 4-char connectors (default: flat rows "
     "in execution order)"),
    ("--numbered[=left|right]",
     "Add period-free row numbers padded to the widest number (default: no numbers; "
     "side default: left)"),
    ("-l N, --limit N, -n N", "Limit displayed rows to N (-n is a backward-compatible alias)"),
    ("--all",
     "Include archived DONE/CANCELED tasks from TODO_ARCHIVE.md (same as the ALL status "
     "keyword)"),
    ("-r, --ready",
     "Show only ready tasks ranked by role ease, Quest Momentum, best chain rank, chain "
     "count, done count, and ready unlocks (rows show [FINAL | STAGE | COMBO | chain: N, "
     "ready: +M, "
     "unblocks: K], with chain only when N > 1 and ready only when M > 0); also accepted "
     "by list"),
    ("--by-role", "Partition active tasks into role queues"),
    ("--role ROLE", "Show only tasks matching ROLE"),
    ("--include-hold", "Include HOLD tasks and branches blocked by HOLD"),
    ("--status STATUS",
     "Status filter WIP|NEXT|QUESTION|NEW|HOLD|ACTIVE|ALL (also accepted as a bare "
     "keyword); DONE|CANCELED|ARCHIVE render the list view instead"),
    ("-f, --filter <ID>...",
     "Filter by task IDs (bare <ID> matches across all projects in view, <project>:<ID> "
     "matches one project); focuses and highlights by default, and prints Next actionable "
     "for one ID; positional <ID>... under chain do the same"),
    ("-H, --highlight [<ID>...]",
     "Disable focus to render the full Quest-Log with matched -f/-s tasks highlighted "
     "(or pass -H <ID>... as shorthand for -f <ID>... -H)"),
    ("-s, --search QUERY",
     "Search task IDs (<ID> and <project>:<ID>), titles, and bodies across all projects "
     "in view (case-insensitive regex, substring if invalid; TODO.md only unless --all or "
     "an archive status is set); focuses and highlights matches, or prints full sections "
     "with --full"),
)

HELP_PREFIXES: tuple[tuple[str, str], ...] = (
    ("F", "Feature (default prefix for add)"),
    ("B", "Bugfix (ranked ahead of other tasks in chain)"),
    ("D", "Design (role: design in any status)"),
    ("A-Z", "Any other letter is a custom domain prefix"),
    ("Status roles", "WIP/NEXT -> work; NEW/QUESTION/HOLD -> plan (non-D prefixes)"),
    ("Note", "{prog} check rejects '- Role:' lines in TODO.md; --role only filters views"),
)

HELP_NOTES = (
    "Tabular views (list, chain, projects) align status badges by display width and wrap "
    "long descriptions into aligned columns based on terminal width (falling back to a "
    "4-space indent on narrow terminals).",
    "Mutating commands first run git pull --ff-only when an upstream is configured, then "
    "automatically validate and status-order TODO.md; pass -c / --commit to also "
    "git-commit TODO*.md when inside a Git repository.",
)

HELP_FILES: tuple[tuple[str, str], ...] = (
    ("TODO.md",
     "All open tasks ordered by status (🔵 [WIP], 🎯 [NEXT], ❓ [QUESTION], ⚪ [NEW], "
     "⏸️ [HOLD])"),
    ("TODO_ARCHIVE.md",
     "Completed (✅ [DONE]) and dropped (❌ [CANCELED]) tasks (newest at top)"),
)

HELP_ENV: tuple[tuple[str, str], ...] = (
    ("TODO_MD_CWD", "Override target directory (default: current directory)"),
    ("TODO_MD_WORKSPACE",
     "Override workspace root directory for project discovery and <project>:<ID>"),
    ("TODO_MD_PROJECTS",
     "Override or specify configured .todo_projects file/list for orchestrator chain DAGs"),
    ("TODO_MD_COMMIT", "Set to 1 to git-commit TODO*.md automatically on mutating commands"),
    ("TODO_MD_NO_COMMIT",
     "Set to 1 to suppress git commits even when --commit / TODO_MD_COMMIT is set"),
    ("TODO_MD_NO_GIT_PULL",
     "Set to 1 to skip git pull --ff-only upstream sync before mutating commands"),
    ("TODO_MD_BUNDLE", "Set to 1 to emit bundle streams (same as --bundle)"),
    ("TODO_MD_PLAIN", "Set to 1 to disable bundle auto-detection (same as --plain)"),
    ("TODO_MD_UPDATE_URL", "Override raw script URL for update / check-update"),
)

def help_display_width(text: str) -> int:
    width = 0
    for ch in text:
        if ch == "\ufe0f":
            width += 1
        elif unicodedata.combining(ch):
            continue
        else:
            width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width

def _help_wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        cand = f"{cur} {word}" if cur else word
        if cur and help_display_width(cand) > width:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines

def _help_fill(text: str, prog: str) -> str:
    return text.replace("{prog}", prog)

def _help_table(rows: tuple[tuple[str, str], ...], prog: str) -> list[str]:
    lefts = [_help_fill(left, prog) for left, _ in rows]
    col = HELP_INDENT + max(len(left) for left in lefts) + HELP_GAP
    out: list[str] = []
    for left, (_, desc) in zip(lefts, rows):
        parts = _help_wrap(_help_fill(desc, prog), HELP_MAX_WIDTH - col) or [""]
        out.append((" " * HELP_INDENT + left).ljust(col) + parts[0])
        out.extend(" " * col + part for part in parts[1:])
    return [line.rstrip() for line in out]

def _help_prose(text: str, prog: str) -> list[str]:
    return _help_wrap(_help_fill(text, prog), HELP_PROSE_WIDTH)

def usage_text() -> str:
    prog = prog_name()
    lines = ["Usage:"]
    lines += [" " * HELP_INDENT + _help_fill(item, prog) for item in HELP_USAGE]
    lines += ["", *_help_prose(HELP_INTRO, prog), ""]
    sections = (
        ("Commands:", HELP_COMMANDS),
        ("Global options:", HELP_GLOBAL_OPTIONS),
        ("Quest-Log options (default view, chain, search):", HELP_QUEST_OPTIONS),
        ("Task ID prefixes and roles (derived from the ID prefix and status, never from the "
         "task body):", HELP_PREFIXES),
    )
    for title, rows in sections:
        lines += [title, *_help_table(rows, prog), ""]
    for note in HELP_NOTES:
        lines += [*_help_prose(note, prog), ""]
    lines += ["Files:", *_help_table(HELP_FILES, prog), ""]
    lines += ["Environment variables:", *_help_table(HELP_ENV, prog)]
    return "\n".join(lines) + "\n"
