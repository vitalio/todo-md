def format_dependency_summary(
    base_dir: Path,
    section_text: str,
    explicit_dir: str | None = None,
    task: dict[str, object] | None = None,
) -> str | None:
    clauses, syntax_errors = parse_dependency_clauses(section_text)
    if not clauses and not syntax_errors:
        return None
    flat_refs: list[str] = []
    seen_refs: set[str] = set()
    for clause in clauses:
        for stage in clause:
            for ref in stage:
                if ref not in seen_refs:
                    seen_refs.add(ref)
                    flat_refs.append(ref)
    resolved_list = resolve_dependency_statuses(base_dir, flat_refs, explicit_dir=explicit_dir)
    status_map = {ref: (st, emoji) for ref, st, emoji in resolved_list}
    blocked = bool(syntax_errors)
    clause_strs: list[str] = []
    for clause in clauses:
        stage_strs: list[str] = []
        for stage in clause:
            item_strs: list[str] = []
            for ref in stage:
                st, emoji = status_map.get(ref, ("MISSING", ""))
                if st == "DONE":
                    item_strs.append(f"{ref} {emoji} [DONE]".replace("  ", " "))
                elif st == "MISSING":
                    blocked = True
                    item_strs.append(f"{ref} [MISSING]")
                else:
                    blocked = True
                    label = f"{emoji} [{st}]".strip() if emoji else f"[{st}]"
                    item_strs.append(f"{ref} {label}")
            stage_strs.append(", ".join(item_strs))
        clause_strs.append(" -> ".join(stage_strs))
    if syntax_errors and not clause_strs:
        return f"Dependencies (blocked): [syntax error: {'; '.join(syntax_errors)}]"
    state = "blocked" if blocked else "ready"
    suffix = f" [syntax error: {'; '.join(syntax_errors)}]" if syntax_errors else ""
    return f"Dependencies ({state}): " + "; ".join(clause_strs) + suffix

def format_ids_summary(top: dict[str, int]) -> str:
    if not top:
        return "[none]"
    used = " ".join(f"{k}:{v}" for k, v in sorted(top.items()))
    nxt = ", ".join(f"{k}{v + 1}" for k, v in sorted(top.items()))
    return f"{used}  (next free: {nxt})"

def _format_task_for_summary(
    task: dict[str, object],
    full: bool = False,
    base_dir: Path | None = None,
    proj_prefix: str | None = None,
) -> str:
    sec = str(task["section"]).rstrip()
    if proj_prefix:
        lines = sec.splitlines()
        tid = str(task["id"])
        lines[0] = lines[0].replace(f"] {tid}:", f"] {proj_prefix}:{tid}:", 1)
        sec = "\n".join(lines)
    dep_line = (
        format_dependency_summary(base_dir, str(task["section"]), task=task)
        if base_dir
        else None
    )
    status = str(task["status"])
    if full or status in ("WIP", "NEXT", "QUESTION"):
        return f"{sec}\n{dep_line}" if dep_line else sec
    lines = sec.splitlines()
    heading = lines[0]
    body_non_empty = [l for l in lines[1:] if l.strip()]
    if not body_non_empty:
        return heading
    if len(body_non_empty) == 1:
        out = f"{heading}\n\n{body_non_empty[0]}"
        return f"{out}\n{dep_line}" if dep_line else out
    tid = str(task["id"])
    ref_cmd = f"{proj_prefix}:{tid}" if proj_prefix else tid
    extra = len(body_non_empty) - 1
    out = f"{heading}\n\n{body_non_empty[0]}\n*(+{extra} more line{'s' if extra != 1 else ''} — run `{prog_name()} {ref_cmd}` to view full task)*"
    return f"{out}\n{dep_line}" if dep_line else out

@_discovery_scoped
def cmd_summary(base_dir: Path, full: bool = False) -> int:
    todo_path = base_dir / "TODO.md"
    if not todo_path.is_file():
        sys.stderr.write(f"{prog_name()}: no TODO.md found in {base_dir} (run '{prog_name()} init' to create one)\n")
        return 1
    todo_text = read_if_exists(todo_path).rstrip()
    active_tasks = parse_tasks_in_text(todo_text, "TODO.md")
    arch_tasks = parse_tasks_in_text(read_if_exists(base_dir / "TODO_ARCHIVE.md"), "TODO_ARCHIVE.md")
    top = highest_ids_in_use(base_dir)

    if active_tasks:
        if full:
            sys.stdout.write(todo_text + "\n\n")
        else:
            ordered = sorted(
                enumerate(active_tasks),
                key=lambda iv: (ACTIVE_STATUS_ORDER.get(str(iv[1]["status"]), 99), iv[0]),
            )
            has_expanded = any(
                str(t["status"]) in ("WIP", "NEXT", "QUESTION")
                for _, t in ordered
            )
            rendered = [
                _format_task_for_summary(t, full=(not has_expanded and idx == 0), base_dir=base_dir)
                for idx, (_, t) in enumerate(ordered)
            ]
            sys.stdout.write("\n\n".join(rendered) + "\n\n")

    if not active_tasks:
        sys.stdout.write("*(No open tasks in TODO.md)*\n\n")
    sys.stdout.write("---\n")
    sys.stdout.write(f"IDs in use: {format_ids_summary(top)}\n")
    sys.stdout.write(f"Open in TODO.md: {len(active_tasks)} task(s) · Archived in TODO_ARCHIVE.md: {len(arch_tasks)} task(s)\n")
    return 0

def cmd_ids(base_dir: Path) -> int:
    top = highest_ids_in_use(base_dir)
    sys.stdout.write(f"IDs in use: {format_ids_summary(top)}\n")
    for legend_line in prefix_legend_lines():
        sys.stdout.write(legend_line + "\n")
    return 0

def cmd_last_id(base_dir: Path, filt: str | None = None) -> int:
    tid = resolve_last_task_id(base_dir, filt)
    if not tid:
        label = (filt or "NEW").strip()
        sys.stderr.write(f"{prog_name()}: no matching task found for {label!r} under {base_dir}\n")
        return 1
    sys.stdout.write(f"{tid}\n")
    return 0

def cmd_last(base_dir: Path, filt: str | None = None) -> int:
    tid = resolve_last_task_id(base_dir, filt)
    if not tid:
        label = (filt or "NEW").strip()
        sys.stderr.write(f"{prog_name()}: no matching task found for {label!r} under {base_dir}\n")
        return 1
    return cmd_show(base_dir, tid)

@_discovery_scoped
def cmd_show(base_dir: Path, task_id: str) -> int:
    target = task_id.strip().upper()
    p_res = base_dir.resolve()
    workdir = str(p_res)
    shared = _ACTIVE_DISCOVERY
    task_cache: dict[Path, dict[str, dict[str, object]]] = (
        shared.task_maps if shared is not None else {}
    )
    if p_res not in task_cache:
        task_cache[p_res] = {
            str(t["id"]).upper(): t for t in collect_all_tasks(p_res)
        }
    t = task_cache[p_res].get(target)
    if t is not None:
        tid = str(t["id"]).upper()
        prefix = _task_prefix(tid)
        status = str(t.get("status", "")).upper()
        base_title, _ = _strip_heading_note(str(t["title"]))
        section = str(t["section"])
        header_lines = [
            f"Task: {tid}",
            f"Prefix: {prefix}",
            f"Status: {status}",
            f"Title: {base_title}",
            f"Workdir: {workdir}",
        ]
        headers = "\n".join(header_lines)
        dep_line = format_dependency_summary(base_dir, section, task=t)
        dep_block = f"\n{dep_line}" if dep_line else ""
        sys.stdout.write(
            f"{headers}\n\n# {t['file']}:{t['line']}\n{section}{dep_block}\n"
        )
        return 0
    sys.stderr.write(f"{prog_name()}: task {target!r} not found in TODO*.md under {base_dir}\n")
    return 1


DEFAULT_TERMINAL_WIDTH = 100

MIN_TABLE_DESC_COLS = 20

COMPACT_CONTINUATION_INDENT = 4

def _get_terminal_columns(fallback: int = DEFAULT_TERMINAL_WIDTH) -> int:
    cols = shutil.get_terminal_size(fallback=(fallback, 24)).columns
    return cols if cols > 0 else fallback

def _char_display_width(ch: str) -> int:
    if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    if ch in ("\u23f8", "\u26a0", "\u26d3") or ord(ch) >= 0x1F300 or unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

ANSI_DIM_ON = "\033[2m"

ANSI_EXTERNAL_ON = "\033[2;3m"

ANSI_DONE_ON = "\033[2;90m"

ANSI_EXTERNAL_DONE_ON = "\033[2;3;90m"

ANSI_HIGHLIGHT_ON = "\033[1;93m"

ANSI_EXTERNAL_HIGHLIGHT_ON = "\033[1;3;93m"

ANSI_RESET = "\033[0m"

def _strip_ansi(text: str) -> str:
    if "\x1b" not in text:
        return text
    return ANSI_ESCAPE_RE.sub("", text)

def _use_ansi_color() -> bool:
    force = os.environ.get("FORCE_COLOR", "").strip()
    if force and force != "0":
        return True
    if os.environ.get("NO_COLOR", "").strip():
        return False
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False

def _style_ansi_lines(text: str, sgr_open: str) -> str:
    if not sgr_open:
        return text
    has_nl = text.endswith("\n")
    raw = text[:-1] if has_nl else text
    styled = "\n".join(f"{sgr_open}{line}{ANSI_RESET}" if line else line for line in raw.split("\n"))
    return f"{styled}\n" if has_nl else styled

ANSI_SEP_SGR = "2;90"
ANSI_PCT_SGR = "1;36"
ANSI_PCT_DONE_SGR = "1;32"
ANSI_STAT_FRAC_SGR = "32"
ANSI_STAT_ZERO_SGR = "2;90"
ANSI_OPEN_LABEL_SGR = "1"
ANSI_READY_SGR = "32"
ANSI_BLOCKED_SGR = "33"
ANSI_HELD_SGR = "90"
ANSI_PERK_FINAL_SGR = "1;35"
ANSI_PERK_STAGE_SGR = "1;36"
ANSI_PERK_COMBO_SGR = "1;91"
ANSI_CHAIN_STAT_SGR = "36"
ANSI_UNBLOCKS_SGR = "36"
ANSI_ALSO_IN_SGR = "2"

STATUS_BADGE_SGR: dict[str, str] = {
    "WIP": "1;34",
    "NEXT": "36",
    "QUESTION": "35",
    "NEW": "37",
    "HOLD": "90",
}

_CHAIN_HEADER_STAT_RE = re.compile(r"^(\s*(?:(?:│   |    )*[├└]── )?)(\d+%)( · )(\d+/\d+)( · )(.*)$")
_OVERALL_STATUS_ITEM_RE = re.compile(r"(\d+\s+\S+\s+)(WIP|NEXT|QUESTION|NEW|HOLD)\b")
_ROW_TAG_TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"🏁 FINAL\b"), ANSI_PERK_FINAL_SGR),
    (re.compile(r"⚡ STAGE\b"), ANSI_PERK_STAGE_SGR),
    (re.compile(r"🔥 COMBO\b"), ANSI_PERK_COMBO_SGR),
    (re.compile(r"🟢 ready: \+\d+"), ANSI_READY_SGR),
    (re.compile(r"🟢 ready\b"), ANSI_READY_SGR),
    (re.compile(r"⛓️ chain: \d+"), ANSI_CHAIN_STAT_SGR),
    (re.compile(r"🔓 unblocks: \d+"), ANSI_UNBLOCKS_SGR),
    (re.compile(r"🔒 blocked(?: by: [^\n·]+)?"), ANSI_BLOCKED_SGR),
    (re.compile(r"🔗 also in: [^\n·]+"), ANSI_ALSO_IN_SGR),
    (re.compile(r"(?<!\S)·(?!\S)"), ANSI_SEP_SGR),
)

def _sgr_wrap(token: str, sgr: str, base_sgr: str = "") -> str:
    combined = f"{base_sgr};{sgr}" if base_sgr else sgr
    restore = f"{ANSI_RESET}\033[{base_sgr}m" if base_sgr else ANSI_RESET
    return f"\033[{combined}m{token}{restore}"

def _style_overall_progress_header(
    line: str,
    use_color: bool | None = None,
) -> str:
    active_color = _use_ansi_color() if use_color is None else use_color
    if not active_color:
        return line
    styled = line
    styled = re.sub(
        r"^(\d+%)",
        lambda m: _sgr_wrap(m.group(1), ANSI_PCT_DONE_SGR if m.group(1) == "100%" else ANSI_PCT_SGR),
        styled,
        count=1,
    )
    styled = re.sub(
        r"✅ (\d+)/(\d+)",
        lambda m: _sgr_wrap(
            m.group(0),
            ANSI_STAT_FRAC_SGR if int(m.group(1)) > 0 else ANSI_STAT_ZERO_SGR,
        ),
        styled,
        count=1,
    )
    styled = re.sub(
        r"\b(\d+ open:)",
        lambda m: _sgr_wrap(m.group(1), ANSI_OPEN_LABEL_SGR),
        styled,
        count=1,
    )
    styled = re.sub(
        r"🟢 \d+ ready",
        lambda m: _sgr_wrap(m.group(0), ANSI_READY_SGR),
        styled,
        count=1,
    )
    styled = _OVERALL_STATUS_ITEM_RE.sub(
        lambda m: _sgr_wrap(m.group(0), STATUS_BADGE_SGR.get(m.group(2), "1")),
        styled,
    )
    styled = re.sub(
        r"⏳ \d+ blocked",
        lambda m: _sgr_wrap(m.group(0), ANSI_BLOCKED_SGR),
        styled,
        count=1,
    )
    styled = re.sub(
        r"⏸️ \d+ held",
        lambda m: _sgr_wrap(m.group(0), ANSI_HELD_SGR),
        styled,
        count=1,
    )
    styled = re.sub(
        r"(?<!\S)·(?!\S)",
        lambda m: _sgr_wrap(m.group(0), ANSI_SEP_SGR),
        styled,
    )
    return styled

def _style_chain_header_line(
    text: str,
    is_external: bool = False,
    is_done: bool = False,
    is_highlighted: bool = False,
    use_color: bool | None = None,
) -> str:
    active_color = _use_ansi_color() if use_color is None else use_color
    if not active_color:
        return text
    if is_highlighted or is_done:
        return _style_task_row(
            text,
            is_external=is_external,
            is_done=is_done,
            is_highlighted=is_highlighted,
            use_color=active_color,
        )
    base_sgr = "2;3" if is_external else ""
    has_nl = text.endswith("\n")
    raw = text[:-1] if has_nl else text
    lines = raw.split("\n")
    m = _CHAIN_HEADER_STAT_RE.match(lines[0]) if lines else None
    if m is not None:
        lead, pct_str, sep1, frac_str, sep2, rest = m.groups()
        done_num = int(frac_str.split("/", 1)[0])
        pct_sgr = ANSI_PCT_DONE_SGR if pct_str == "100%" else ANSI_PCT_SGR
        frac_sgr = ANSI_STAT_FRAC_SGR if done_num > 0 else ANSI_STAT_ZERO_SGR
        lines[0] = (
            f"{lead}"
            f"{_sgr_wrap(pct_str, pct_sgr, base_sgr)}"
            f" {_sgr_wrap('·', ANSI_SEP_SGR, base_sgr)} "
            f"{_sgr_wrap(frac_str, frac_sgr, base_sgr)}"
            f" {_sgr_wrap('·', ANSI_SEP_SGR, base_sgr)} "
            f"{rest}"
        )
    joined = "\n".join(lines)
    if base_sgr:
        joined = _style_ansi_lines(joined, f"\033[{base_sgr}m")
    return f"{joined}\n" if has_nl else joined

def _style_tag_suffix_line(line: str, base_sgr: str = "") -> str:
    out = line
    for pat, sgr in _ROW_TAG_TOKEN_PATTERNS:
        out = pat.sub(lambda m, _sgr=sgr: _sgr_wrap(m.group(0), _sgr, base_sgr), out)
    return out

def _style_chain_task_row(
    rendered: str,
    row_prefix: str,
    title: str,
    has_tags: bool,
    is_external: bool = False,
    is_done: bool = False,
    is_highlighted: bool = False,
    use_color: bool | None = None,
) -> str:
    active_color = _use_ansi_color() if use_color is None else use_color
    if not active_color:
        return rendered
    if is_highlighted or is_done or not has_tags:
        return _style_task_row(
            rendered,
            is_external=is_external,
            is_done=is_done,
            is_highlighted=is_highlighted,
            use_color=active_color,
        )
    base_sgr = "2;3" if is_external else ""
    pos = len(row_prefix)
    for word in title.split():
        found = rendered.find(word, pos)
        if found == -1:
            break
        pos = found + len(word)
    head_part = rendered[:pos]
    tail_part = rendered[pos:]
    tail_lines = tail_part.split("\n")
    styled_tail_lines = [_style_tag_suffix_line(tl, base_sgr=base_sgr) for tl in tail_lines]
    combined = head_part + "\n".join(styled_tail_lines)
    if base_sgr:
        return _style_ansi_lines(combined, f"\033[{base_sgr}m")
    return combined

def _style_task_row(
    text: str,
    is_external: bool = False,
    is_done: bool = False,
    is_highlighted: bool = False,
    use_color: bool | None = None,
) -> str:
    active_color = _use_ansi_color() if use_color is None else use_color
    if not active_color:
        return text
    if is_highlighted:
        sgr = ANSI_EXTERNAL_HIGHLIGHT_ON if is_external else ANSI_HIGHLIGHT_ON
    elif is_external and is_done:
        sgr = ANSI_EXTERNAL_DONE_ON
    elif is_external:
        sgr = ANSI_EXTERNAL_ON
    elif is_done:
        sgr = ANSI_DONE_ON
    else:
        return text
    return _style_ansi_lines(text, sgr)

def _display_width(text: str) -> int:
    return sum(_char_display_width(ch) for ch in _strip_ansi(text))

def _pad_display(text: str, width: int) -> str:
    cur = _display_width(text)
    if cur >= width:
        return text
    return text + (" " * (width - cur))

def _split_word_by_display_width(word: str, max_cols: int) -> list[str]:
    if max_cols <= 0 or _display_width(word) <= max_cols:
        return [word]
    chunks: list[str] = []
    cur: list[str] = []
    cur_w = 0
    for ch in word:
        cw = _char_display_width(ch)
        if cur and cur_w + cw > max_cols:
            chunks.append("".join(cur))
            cur = [ch]
            cur_w = cw
        else:
            cur.append(ch)
            cur_w += cw
    if cur:
        chunks.append("".join(cur))
    return chunks

def _wrap_display_lines(text: str, first_width: int, next_width: int) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    cur_parts: list[str] = []
    cur_w = 0
    pending_ws = ""
    budget = max(1, first_width)
    next_budget = max(1, next_width)

    for tok in re.findall(r"\S+|\s+", text):
        if tok.isspace():
            if cur_parts:
                pending_ws += tok
            continue
        ws_w = _display_width(pending_ws)
        tok_w = _display_width(tok)
        if cur_parts and cur_w + ws_w + tok_w <= budget:
            cur_parts.append(pending_ws)
            cur_parts.append(tok)
            cur_w += ws_w + tok_w
            pending_ws = ""
            continue
        if cur_parts:
            lines.append("".join(cur_parts))
            cur_parts = []
            cur_w = 0
            pending_ws = ""
            budget = next_budget
        if not lines and budget < next_budget and tok_w > budget:
            lines.append("")
            budget = next_budget
        if tok_w <= budget:
            cur_parts.append(tok)
            cur_w = tok_w
        else:
            chunks = _split_word_by_display_width(tok, budget)
            first_chunk = chunks[0]
            rest_text = tok[len(first_chunk):]
            if not rest_text:
                cur_parts.append(first_chunk)
                cur_w = _display_width(first_chunk)
            else:
                lines.append(first_chunk)
                budget = next_budget
                rem_chunks = _split_word_by_display_width(rest_text, budget)
                for ch_piece in rem_chunks[:-1]:
                    lines.append(ch_piece)
                cur_parts = [rem_chunks[-1]]
                cur_w = _display_width(rem_chunks[-1])

    if cur_parts:
        lines.append("".join(cur_parts))
    return lines

def _wrap_table_row(
    prefix: str,
    description: str,
    term_width: int | None = None,
    cont_prefix: str | None = None,
) -> str:
    if not description:
        return prefix
    width = _get_terminal_columns() if term_width is None else term_width
    prefix_w = _display_width(prefix)
    avail_first = width - prefix_w
    base_cont = cont_prefix if cont_prefix is not None else ""
    base_cont_w = _display_width(base_cont)
    if avail_first >= MIN_TABLE_DESC_COLS:
        cont_indent = base_cont + (" " * max(0, prefix_w - base_cont_w))
        avail_cont = max(1, width - _display_width(cont_indent))
        wrapped = _wrap_display_lines(description, avail_first, avail_cont)
    else:
        target_cont_w = max(COMPACT_CONTINUATION_INDENT, base_cont_w)
        cont_indent = base_cont + (" " * max(0, target_cont_w - base_cont_w))
        avail_cont = max(1, width - _display_width(cont_indent))
        if avail_first <= 0:
            wrapped = _wrap_display_lines(description, avail_cont, avail_cont)
            return "\n".join([prefix.rstrip(), *(f"{cont_indent}{line}" for line in wrapped)])
        wrapped = _wrap_display_lines(description, avail_first, avail_cont)
    if not wrapped:
        return prefix.rstrip()
    out_lines: list[str] = []
    if wrapped[0]:
        out_lines.append(f"{prefix}{wrapped[0]}")
    else:
        out_lines.append(prefix.rstrip())
    for cont in wrapped[1:]:
        out_lines.append(f"{cont_indent}{cont}")
    return "\n".join(out_lines)

@_discovery_scoped
def cmd_list(
    base_dir: Path,
    filt: str | None = None,
    limit: int | None = None,
    full: bool = False,
    prefix: str | None = None,
    status: str | None = None,
    ready: bool = False,
    targets: list[tuple[Path, str]] | None = None,
    focus: list[tuple[Path, str]] | None = None,
    search: str | None = None,
    highlight_only: bool = False,
) -> int:
    mode = (filt or "active").strip().lower()
    tasks = collect_all_tasks(base_dir)
    if _ACTIVE_DISCOVERY is not None:
        _ACTIVE_DISCOVERY.task_maps.setdefault(
            base_dir.resolve(),
            {str(t["id"]).upper(): t for t in tasks},
        )
    active_tasks = _order_active_tasks_for_list(
        [t for t in tasks if t["file"] == "TODO.md"],
        base_dir=base_dir,
    )
    arch_tasks = [t for t in tasks if t["file"] == "TODO_ARCHIVE.md"]
    if mode in ("active", "open"):
        shown = active_tasks
    elif mode == "archive":
        shown = arch_tasks
    elif mode == "all":
        shown = active_tasks + arch_tasks
    elif mode.upper() in VALID_STATUSES:
        st_up = mode.upper()
        if st_up in ("DONE", "CANCELED"):
            shown = [t for t in arch_tasks if t["status"] == st_up]
        else:
            shown = [t for t in active_tasks if t["status"] == st_up]
    else:
        raise SystemExit(f"{prog_name()}: unknown list filter {filt!r}; expected active, archive, all, or a status name")

    if status is not None:
        st_w = status.strip().upper()
        if st_w == "ALL":
            if filt is None:
                shown = active_tasks + arch_tasks
        elif st_w in ("ACTIVE", "OPEN"):
            shown = [t for t in shown if t["file"] == "TODO.md"]
        elif st_w == "ARCHIVE":
            if filt is None:
                shown = arch_tasks
            else:
                shown = [t for t in shown if t["file"] == "TODO_ARCHIVE.md"]
        else:
            if filt is None and st_w in ("DONE", "CANCELED"):
                shown = [t for t in arch_tasks if str(t["status"]) == st_w]
            else:
                shown = [t for t in shown if str(t["status"]) == st_w]

    if prefix is not None:
        wanted_prefix = prefix.strip().upper()
        shown = [t for t in shown if _task_matches_prefix(t, wanted_prefix)]

    dep_cache: dict[tuple[str, str], tuple[bool, str]] = {}

    def _dep_info(t: dict[str, object]) -> tuple[bool, str]:
        key = (str(t["file"]), str(t["id"]).upper())
        if key not in dep_cache:
            dep_cache[key] = _task_dependency_info(base_dir, t)
        return dep_cache[key]

    if ready:
        shown = [
            t
            for t in shown
            if str(t["status"]) in ACTIVE_STATUS_ORDER and not _dep_info(t)[0]
        ]

    if focus:
        b_res_f = base_dir.resolve()
        focus_set, focus_unscoped = _normalize_target_refs(base_dir, focus)
        if focus_set or focus_unscoped:
            shown = [
                t
                for t in shown
                if (b_res_f, str(t["id"]).upper()) in focus_set or str(t["id"]).upper() in focus_unscoped
            ]

    active_targets = list(targets or [])
    if search is not None:
        pat = compile_search_pattern(search)
        b_res_s = base_dir.resolve()
        matched_shown = [t for t in shown if task_matches_pattern(t, pat, base_dir)]
        active_targets.extend((b_res_s, f".:{str(t['id']).upper()}") for t in matched_shown)
        if not highlight_only:
            shown = matched_shown

    if limit is not None:
        shown = shown[:limit]

    if not shown:
        notes: list[str] = []
        if prefix is not None:
            notes.append(f"prefix={prefix.strip().upper()}")
        if status is not None:
            notes.append(f"status={status.strip().upper()}")
        if ready:
            notes.append("ready")
        if search is not None:
            notes.append(f"search={search!r}")
        extra = f", {', '.join(notes)}" if notes else ""
        sys.stdout.write(f"No matching tasks ({mode}{extra}) in {base_dir}\n")
    elif full:
        sections = [str(t["section"]).rstrip() for t in shown]
        sys.stdout.write("\n\n".join(sections) + "\n")
    else:
        term_width = _get_terminal_columns()
        use_color = _use_ansi_color()
        b_res = base_dir.resolve()
        target_set, unscoped_ids = _normalize_target_refs(base_dir, active_targets)
        for t in shown:
            is_blocked, dep_suffix = _dep_info(t)
            st_str = str(t["status"])
            tid_up = str(t["id"]).upper()
            emoji = "⏳" if (st_str in ("WIP", "NEXT") and is_blocked) else str(t["emoji"])
            badge = f"{emoji} {st_str}"
            loc = str(t["file"])
            row_prefix = (
                f"  {_pad_display(str(t['id']), 6)}  "
                f"{_pad_display(badge, 14)}  "
                f"{_pad_display(loc, 16)}  "
            )
            desc = f"{t['title']}{dep_suffix}"
            rendered = _wrap_table_row(row_prefix, desc, term_width) + "\n"
            is_highlighted = (b_res, tid_up) in target_set or tid_up in unscoped_ids
            sys.stdout.write(
                _style_task_row(
                    rendered,
                    is_done=(st_str == "DONE"),
                    is_highlighted=is_highlighted,
                    use_color=use_color,
                )
            )
    return 0

@_discovery_scoped
def cmd_projects(base_dir: Path, explicit_dir: str | None = None) -> int:
    b_res = base_dir.resolve()
    if has_todo_projects_config(b_res, include_env=(explicit_dir is None)):
        ws_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
        ws_res = ws_root.resolve()
        projects = resolve_workspace_chain_projects(b_res, ws_res)
        header_root = ws_root
    else:
        projects = [(b_res.name, b_res)] if is_todo_project(b_res) else []
        header_root = b_res
    if not projects:
        sys.stdout.write(f"No todo_md projects found under {header_root}\n")
        return 0
    sys.stdout.write(f"Workspace: {header_root} ({len(projects)} project(s))\n")
    term_width = _get_terminal_columns()
    for name, proj_dir in projects:
        p_res = proj_dir.resolve()
        active = parse_tasks_in_text(read_if_exists(p_res / "TODO.md"), "TODO.md")
        counts: dict[str, int] = {}
        for t in active:
            st = str(t["status"])
            counts[st] = counts.get(st, 0) + 1
        highlights = [f"{st}: {counts[st]}" for st in ("WIP", "NEXT", "QUESTION") if counts.get(st)]
        base_prefix = f"  {_pad_display(name, 26)}  {len(active):>3} open"
        details = f"({', '.join(highlights)})  {p_res}" if highlights else str(p_res)
        sys.stdout.write(
            _wrap_table_row(f"{base_prefix} ", details, term_width) + "\n"
        )
    return 0

@_discovery_scoped
def cmd_workspace_summary(
    base_dir: Path,
    full: bool = False,
    explicit_dir: str | None = None,
) -> int:
    b_res = base_dir.resolve()
    require_todo_projects_config(b_res, "workspace mode (-w/--workspace)")
    workspace_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
    projects = resolve_workspace_chain_projects(b_res, workspace_root)
    if not projects:
        sys.stdout.write(f"No todo_md projects found under {workspace_root}\n")
        return 0
    total_open = 0
    empty_projects: list[str] = []
    blocks: list[str] = []
    for name, proj_dir in projects:
        active = parse_tasks_in_text(read_if_exists(proj_dir / "TODO.md"), "TODO.md")
        if not active:
            empty_projects.append(name)
            continue
        total_open += len(active)
        ordered = sorted(
            enumerate(active),
            key=lambda iv: (ACTIVE_STATUS_ORDER.get(str(iv[1]["status"]), 99), iv[0]),
        )
        has_expanded = any(str(t["status"]) in ("WIP", "NEXT", "QUESTION") for _, t in ordered)
        rendered = [
            _format_task_for_summary(
                t,
                full=(full or (not has_expanded and idx == 0)),
                base_dir=proj_dir,
                proj_prefix=name,
            )
            for idx, (_, t) in enumerate(ordered)
        ]
        blocks.append(f"## {name} ({len(active)} open)\n\n" + "\n\n".join(rendered))

    if blocks:
        sys.stdout.write("\n\n".join(blocks) + "\n\n")
    else:
        sys.stdout.write("*(No open tasks across workspace projects)*\n\n")
    sys.stdout.write("---\n")
    sys.stdout.write(f"Workspace: {workspace_root} · Projects: {len(projects)} · Open tasks: {total_open}\n")
    if empty_projects:
        sys.stdout.write(f"No open tasks: {', '.join(empty_projects)}\n")
    return 0

@_discovery_scoped
def cmd_workspace_list(
    base_dir: Path,
    filt: str | None = None,
    limit: int | None = None,
    full: bool = False,
    prefix: str | None = None,
    status: str | None = None,
    ready: bool = False,
    targets: list[tuple[Path, str]] | None = None,
    focus: list[tuple[Path, str]] | None = None,
    search: str | None = None,
    highlight_only: bool = False,
    explicit_dir: str | None = None,
) -> int:
    b_res = base_dir.resolve()
    require_todo_projects_config(b_res, "workspace mode (-w/--workspace)")
    workspace_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
    projects = resolve_workspace_chain_projects(b_res, workspace_root)
    if not projects:
        sys.stdout.write(f"No todo_md projects found under {workspace_root}\n")
        return 0
    mode = (filt or "active").strip().lower()
    if mode not in ("active", "open", "archive", "all") and mode.upper() not in VALID_STATUSES:
        raise SystemExit(f"{prog_name()}: unknown list filter {filt!r}; expected active, archive, all, or a status name")
    effective_mode = mode
    if filt is None and status is not None:
        st_m = status.strip().upper()
        if st_m == "ALL":
            effective_mode = "all"
        elif st_m in ("ARCHIVE", "DONE", "CANCELED"):
            effective_mode = st_m.lower()
    items: list[tuple[str, Path, dict[str, object]]] = []
    for name, proj_dir in projects:
        tasks = collect_all_tasks(proj_dir)
        active = _order_active_tasks_for_list(
            [t for t in tasks if t["file"] == "TODO.md"],
            base_dir=proj_dir,
        )
        arch = [t for t in tasks if t["file"] == "TODO_ARCHIVE.md"]
        if effective_mode in ("active", "open"):
            matched = active
        elif effective_mode == "archive":
            matched = arch
        elif effective_mode == "all":
            matched = active + arch
        else:
            st_up = effective_mode.upper()
            matched = [t for t in (arch if st_up in ("DONE", "CANCELED") else active) if t["status"] == st_up]
        for t in matched:
            items.append((name, proj_dir, t))
    if status is not None:
        st_w = status.strip().upper()
        if st_w in ("ACTIVE", "OPEN"):
            items = [(name, proj_dir, t) for name, proj_dir, t in items if t["file"] == "TODO.md"]
        elif st_w == "ARCHIVE":
            items = [(name, proj_dir, t) for name, proj_dir, t in items if t["file"] == "TODO_ARCHIVE.md"]
        elif st_w != "ALL":
            items = [(name, proj_dir, t) for name, proj_dir, t in items if str(t["status"]) == st_w]
    if prefix is not None:
        wanted_prefix = prefix.strip().upper()
        items = [(name, proj_dir, t) for name, proj_dir, t in items if _task_matches_prefix(t, wanted_prefix)]

    dep_cache: dict[tuple[Path, str, str], tuple[bool, str]] = {}

    def _ws_dep_info(proj_dir: Path, t: dict[str, object]) -> tuple[bool, str]:
        key = (proj_dir, str(t["file"]), str(t["id"]).upper())
        if key not in dep_cache:
            dep_cache[key] = _task_dependency_info(proj_dir, t)
        return dep_cache[key]

    if ready:
        items = [
            (name, proj_dir, t)
            for name, proj_dir, t in items
            if str(t["status"]) in ACTIVE_STATUS_ORDER and not _ws_dep_info(proj_dir, t)[0]
        ]

    if focus:
        focus_set, focus_unscoped = _normalize_target_refs(b_res, focus, explicit_dir=explicit_dir)
        if focus_set or focus_unscoped:
            items = [
                (name, proj_dir, t)
                for name, proj_dir, t in items
                if (proj_dir.resolve(), str(t["id"]).upper()) in focus_set or str(t["id"]).upper() in focus_unscoped
            ]

    active_targets = list(targets or [])
    if search is not None:
        pat = compile_search_pattern(search)
        matched_items = [
            (name, proj_dir, t)
            for name, proj_dir, t in items
            if task_matches_pattern(t, pat, proj_dir, project_label=name)
        ]
        active_targets.extend(
            (proj_dir.resolve(), f".:{str(t['id']).upper()}")
            for _, proj_dir, t in matched_items
        )
        if not highlight_only:
            items = matched_items

    if limit is not None:
        items = items[:limit]
    if not items:
        notes: list[str] = []
        if prefix is not None:
            notes.append(f"prefix={prefix.strip().upper()}")
        if status is not None:
            notes.append(f"status={status.strip().upper()}")
        if ready:
            notes.append("ready")
        if search is not None:
            notes.append(f"search={search!r}")
        extra = f", {', '.join(notes)}" if notes else ""
        sys.stdout.write(f"No matching tasks ({mode}{extra}) across workspace {workspace_root}\n")
        return 0
    if full:
        sections: list[str] = []
        for name, proj_dir, t in items:
            lines = str(t["section"]).rstrip().splitlines()
            tid = str(t["id"])
            lines[0] = lines[0].replace(f"] {tid}:", f"] {name}:{tid}:", 1)
            sections.append("\n".join(lines))
        sys.stdout.write("\n\n".join(sections) + "\n")
        return 0
    term_width = _get_terminal_columns()
    use_color = _use_ansi_color()
    target_set, unscoped_ids = _normalize_target_refs(b_res, active_targets, explicit_dir=explicit_dir)
    for name, proj_dir, t in items:
        is_blocked, dep_suffix = _ws_dep_info(proj_dir, t)
        st_str = str(t["status"])
        tid_up = str(t["id"]).upper()
        ref = f"{name}:{t['id']}"
        emoji = "⏳" if (st_str in ("WIP", "NEXT") and is_blocked) else str(t["emoji"])
        badge = f"{emoji} {st_str}"
        row_prefix = (
            f"  {_pad_display(ref, 28)}  "
            f"{_pad_display(badge, 14)}  "
        )
        desc = f"{t['title']}{dep_suffix}"
        rendered = _wrap_table_row(row_prefix, desc, term_width) + "\n"
        is_highlighted = (proj_dir.resolve(), tid_up) in target_set or tid_up in unscoped_ids
        sys.stdout.write(
            _style_task_row(
                rendered,
                is_done=(st_str == "DONE"),
                is_highlighted=is_highlighted,
                use_color=use_color,
            )
        )
    return 0

@_discovery_scoped
def cmd_workspace_check(base_dir: Path, explicit_dir: str | None = None) -> int:
    b_res = base_dir.resolve()
    require_todo_projects_config(b_res, "workspace mode (-w/--workspace)")
    workspace_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
    projects = resolve_workspace_chain_projects(b_res, workspace_root)
    if not projects:
        sys.stdout.write(f"No todo_md projects found under {workspace_root}\n")
        return 0
    total_tasks = 0
    had_error = False
    for name, proj_dir in projects:
        errors, count = validate_all(proj_dir)
        total_tasks += count
        if errors:
            had_error = True
            for e in errors:
                sys.stderr.write(f"ERROR [{name}]: {e}\n")
    if had_error:
        return 1
    sys.stdout.write(f"{prog_name()}: OK ({total_tasks} task(s) verified across {len(projects)} project(s))\n")
    return 0

def cmd_archive_view(base_dir: Path) -> int:
    arch_path = base_dir / "TODO_ARCHIVE.md"
    if not arch_path.is_file():
        sys.stderr.write(f"{prog_name()}: no TODO_ARCHIVE.md found in {base_dir}\n")
        return 1
    sys.stdout.write(read_if_exists(arch_path).rstrip() + "\n")
    return 0

def _format_next_id_ref(
    node_key: tuple[Path, str],
    base_dir: Path,
    ws_root: Path,
    workspace: bool = False,
) -> str:
    b_res = base_dir.resolve()
    ndir, ntid = node_key
    if not workspace and is_todo_project(b_res) and ndir == b_res:
        return ntid
    return f"{project_display_name(ndir, ws_root.resolve(), b_res)}:{ntid}"

@_discovery_scoped
def resolve_top_task_id(
    base_dir: Path,
    prefix: str | None = None,
    status: str | None = None,
    explicit_dir: str | None = None,
    workspace: bool = False,
) -> str | None:
    b_res = base_dir.resolve()
    ws_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
    ws_res = ws_root.resolve()
    is_orch = (not workspace) and is_orchestrator_project(b_res, ws_res, explicit_dir=explicit_dir)
    if workspace:
        if not resolve_workspace_chain_projects(b_res, ws_res):
            return None
    elif is_orch:
        if not read_configured_todo_projects(b_res, ws_res, include_env=True) and not (b_res / "TODO.md").is_file():
            return None
    elif not (b_res / "TODO.md").is_file():
        return None

    dag = build_execution_chain_dag(
        base_dir,
        workspace=workspace,
        explicit_dir=explicit_dir,
        include_done=False,
    )
    if dag["syntax_errors"] or dag["cycle"]:
        return None
    wanted_prefix = prefix.strip().upper() if prefix is not None else None
    if status is not None:
        st_up = status.strip().upper()
        wanted_statuses: frozenset[str] = (
            frozenset(ACTIVE_STATUS_ORDER) if st_up in ("ACTIVE", "ALL") else frozenset({st_up})
        )
        include_hold = st_up == "HOLD"
    else:
        wanted_statuses = frozenset({"WIP", "NEXT"})
        include_hold = False

    plan = plan_execution_chains(
        dag,
        include_hold=include_hold,
        ready_only=True,
    )
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    target_project: Path | None = dag.get("target_project")  # type: ignore[assignment]
    ready_tasks: list[tuple[Path, str]] = plan["ready_tasks"]  # type: ignore[assignment]
    for u in ready_tasks:
        if target_project is not None and u[0] != target_project:
            continue
        nd = nodes[u]
        if not nd.get("exists"):
            continue
        if str(nd["status"]) not in wanted_statuses:
            continue
        if wanted_prefix is not None and not _task_matches_prefix(nd, wanted_prefix):
            continue
        return _format_next_id_ref(u, b_res, ws_res, workspace=workspace)
    return None

@_discovery_scoped
def cmd_next_id(
    base_dir: Path,
    target_dir: Path | None = None,
    task_id: str | None = None,
    explicit_dir: str | None = None,
    prefix: str | None = None,
    status: str | None = None,
    workspace: bool = False,
) -> int:
    notes: list[str] = []
    if prefix is not None:
        notes.append(f"prefix={prefix.strip().upper()}")
    if status is not None:
        notes.append(f"status={status.strip().upper()}")
    filter_note = f" ({', '.join(notes)})" if notes else ""
    if task_id is None:
        tid = resolve_top_task_id(
            base_dir,
            prefix=prefix,
            status=status,
            explicit_dir=explicit_dir,
            workspace=workspace,
        )
        if not tid:
            st_label = status.strip().upper() if status is not None else "WIP or NEXT"
            sys.stderr.write(
                f"{prog_name()}: no active {st_label} task{filter_note} found in TODO.md under {base_dir}\n"
            )
            return 1
        sys.stdout.write(f"{tid}\n")
        return 0

    b_res = base_dir.resolve()
    ws_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
    ws_res = ws_root.resolve()
    is_orch = (not workspace) and is_orchestrator_project(b_res, ws_res, explicit_dir=explicit_dir)
    tdir = (target_dir or base_dir).resolve()
    tid_norm = task_id.strip().upper()
    include_hold = status is not None and status.strip().upper() == "HOLD"

    chain_dag = build_execution_chain_dag(
        base_dir,
        workspace=workspace,
        explicit_dir=explicit_dir,
        include_done=False,
    )
    ready_order: dict[tuple[Path, str], int] = {}
    if not chain_dag["syntax_errors"] and not chain_dag["cycle"]:
        c_plan = plan_execution_chains(
            chain_dag,
            include_hold=include_hold,
            ready_only=True,
        )
        c_ready: list[tuple[Path, str]] = c_plan["ready_tasks"]  # type: ignore[assignment]
        ready_order = {u: idx for idx, u in enumerate(c_ready)}
        if (workspace or is_orch) and (target_dir is None or tdir == b_res):
            c_nodes: dict[tuple[Path, str], dict[str, object]] = chain_dag["nodes"]  # type: ignore[assignment]
            if not c_nodes.get((tdir, tid_norm), {}).get("exists"):
                c_active: list[tuple[Path, str]] = c_plan["active_nodes"]  # type: ignore[assignment]
                matched = [u for u in c_active if u[1] == tid_norm and c_nodes.get(u, {}).get("exists")]
                if not matched:
                    matched = [u for u in c_nodes if u[1] == tid_norm and c_nodes[u].get("exists")]
                if matched:
                    tdir = matched[0][0]

    dag = build_dependency_dag(
        base_dir,
        tdir,
        tid_norm,
        explicit_dir=explicit_dir,
        stop_at_done=True,
    )
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    topo_order: list[tuple[Path, str]] = dag["topo_order"]  # type: ignore[assignment]
    root_key: tuple[Path, str] = dag["root"]  # type: ignore[assignment]
    root_node = nodes[root_key]
    if not root_node["exists"]:
        sys.stderr.write(f"{prog_name()}: task {root_node['ref']!r} not found in TODO*.md under {tdir}\n")
        return 1
    root_status = str(root_node["status"])
    if root_status in ("DONE", "CANCELED"):
        sys.stderr.write(f"{prog_name()}: task {root_node['ref']} is already closed ([{root_status}])\n")
        return 1
    syntax_errors: list[str] = dag["syntax_errors"]  # type: ignore[assignment]
    if syntax_errors:
        for e in syntax_errors:
            sys.stderr.write(f"ERROR: {e}\n")
        return 1
    cycle: list[str] = dag["cycle"]  # type: ignore[assignment]
    if cycle:
        sys.stderr.write(f"{prog_name()}: dependency cycle detected: {' -> '.join(cycle)}\n")
        return 1
    bad_blockers = [
        f"{nodes[u]['ref']} ({nodes[u]['status']})"
        for u in topo_order
        if str(nodes[u]["status"]) in ("MISSING", "CANCELED")
    ]
    if bad_blockers:
        sys.stderr.write(
            f"{prog_name()}: task {root_node['ref']} is blocked by {', '.join(bad_blockers)}\n"
        )
        return 1
    wanted_st_set: frozenset[str] | None = None
    if status is not None:
        st_u = status.strip().upper()
        if st_u not in ("ACTIVE", "ALL"):
            wanted_st_set = frozenset({st_u})
    wanted_prefix = prefix.strip().upper() if prefix is not None else None
    candidates: list[tuple[int, tuple[Path, str]]] = []
    for idx, u in enumerate(topo_order):
        nd = nodes[u]
        st = str(nd["status"])
        if st not in ACTIVE_STATUS_ORDER:
            continue
        if wanted_st_set is not None and st not in wanted_st_set:
            continue
        if wanted_prefix is not None and not _task_matches_prefix(nd, wanted_prefix):
            continue
        if any(str(nodes[p]["status"]) != "DONE" for p in prereqs[u]):
            continue
        candidates.append((idx, u))
    if not candidates:
        sys.stderr.write(
            f"{prog_name()}: no unblocked actionable task{filter_note} found for {root_node['ref']}\n"
        )
        return 1
    fallback_rank = len(ready_order)
    _, best_u = min(
        candidates,
        key=lambda item: (
            ready_order.get(item[1], fallback_rank),
            0 if _is_bug_task_node(nodes, item[1]) else 1,
            ACTIVE_STATUS_ORDER.get(str(nodes[item[1]]["status"]), 99),
            item[0],
        ),
    )
    next_act = _format_next_id_ref(best_u, b_res, ws_res, workspace=workspace)
    sys.stdout.write(f"{next_act}\n")
    return 0
