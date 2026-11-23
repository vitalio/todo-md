def _inbound_blocker_items(
    base_dir: Path,
    task: dict[str, object],
    own_clauses: list[list[list[str]]],
    explicit_dir: str | None = None,
) -> list[str]:
    dag = _task_dag(base_dir, task, explicit_dir=explicit_dir)
    if dag is None:
        return []
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    root_key: tuple[Path, str] = dag["root"]  # type: ignore[assignment]

    def _norm(ref: str) -> str:
        return ref.strip().upper().lstrip("~/")

    own = {_norm(ref) for clause in own_clauses for stage in clause for ref in stage}
    items: list[str] = []
    for p in prereqs.get(root_key, []):
        nd = nodes[p]
        st = str(nd["status"])
        if st == "DONE" or _norm(str(nd["ref"])) in own:
            continue
        emoji = str(nd.get("emoji", ""))
        label = f"{emoji} [{st}]".strip() if emoji else f"[{st}]"
        items.append(f"{nd['ref']} {label}")
    return items

def format_dependency_summary(
    base_dir: Path,
    section_text: str,
    explicit_dir: str | None = None,
    task: dict[str, object] | None = None,
) -> str | None:
    clauses, syntax_errors = parse_dependency_clauses(section_text)
    inbound_items = (
        _inbound_blocker_items(base_dir, task, clauses, explicit_dir=explicit_dir)
        if task is not None and not syntax_errors
        else []
    )
    if not clauses and not syntax_errors and not inbound_items:
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
    if inbound_items:
        blocked = True
        clause_strs.append(", ".join(inbound_items))
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
    sys.stdout.write(f"Open in TODO.md: {len(active_tasks)} task(s) | Archived in TODO_ARCHIVE.md: {len(arch_tasks)} task(s)\n")
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
    top = highest_ids_in_use(base_dir)
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
            f"{headers}\n\n# {t['file']}:{t['line']}\n{section}{dep_block}\n\n---\nIDs in use: {format_ids_summary(top)}\n"
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
    if ch == "\u23f8" or ord(ch) >= 0x1F300 or unicodedata.east_asian_width(ch) in ("W", "F"):
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
            badge = f"{emoji} [{st_str}]"
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
    top = highest_ids_in_use(base_dir)
    sys.stdout.write(f"\nIDs in use: {format_ids_summary(top)}\n")
    return 0

def cmd_projects(base_dir: Path, explicit_dir: str | None = None) -> int:
    ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    projects = discover_projects(ws_root)
    if not projects:
        sys.stdout.write(f"No todo_md projects found under {ws_root}\n")
        return 0
    sys.stdout.write(f"Workspace: {ws_root} ({len(projects)} project(s))\n")
    term_width = _get_terminal_columns()
    for name, proj_dir in projects:
        active = parse_tasks_in_text(read_if_exists(proj_dir / "TODO.md"), "TODO.md")
        counts: dict[str, int] = {}
        for t in active:
            st = str(t["status"])
            counts[st] = counts.get(st, 0) + 1
        highlights = [f"{st}: {counts[st]}" for st in ("WIP", "NEXT", "QUESTION") if counts.get(st)]
        base_prefix = f"  {_pad_display(name, 26)}  {len(active):>3} open"
        if highlights:
            sys.stdout.write(
                _wrap_table_row(f"{base_prefix} ", f"({', '.join(highlights)})", term_width) + "\n"
            )
        else:
            sys.stdout.write(f"{base_prefix}\n")
    return 0

@_discovery_scoped
def cmd_workspace_summary(workspace_root: Path, full: bool = False) -> int:
    projects = discover_projects(workspace_root)
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
    sys.stdout.write(f"Workspace: {workspace_root} | Projects: {len(projects)} | Open tasks: {total_open}\n")
    if empty_projects:
        sys.stdout.write(f"No open tasks: {', '.join(empty_projects)}\n")
    return 0

@_discovery_scoped
def cmd_workspace_list(
    workspace_root: Path,
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
    projects = discover_projects(workspace_root)
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
        focus_set, focus_unscoped = _normalize_target_refs(workspace_root, focus)
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
    target_set, unscoped_ids = _normalize_target_refs(workspace_root, active_targets)
    for name, proj_dir, t in items:
        is_blocked, dep_suffix = _ws_dep_info(proj_dir, t)
        st_str = str(t["status"])
        tid_up = str(t["id"]).upper()
        ref = f"{name}:{t['id']}"
        emoji = "⏳" if (st_str in ("WIP", "NEXT") and is_blocked) else str(t["emoji"])
        badge = f"{emoji} [{st_str}]"
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

def cmd_workspace_check(workspace_root: Path) -> int:
    projects = discover_projects(workspace_root)
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

@_discovery_scoped
def resolve_top_task_id(
    base_dir: Path,
    prefix: str | None = None,
    status: str | None = None,
    explicit_dir: str | None = None,
) -> str | None:
    todo_path = base_dir / "TODO.md"
    if not todo_path.is_file():
        return None
    active_tasks = parse_tasks_in_text(read_if_exists(todo_path), "TODO.md")
    wanted_prefix = prefix.strip().upper() if prefix is not None else None
    if status is not None:
        st_up = status.strip().upper()
        wanted_statuses: tuple[str, ...] = (
            tuple(ACTIVE_STATUS_ORDER) if st_up in ("ACTIVE", "ALL") else (st_up,)
        )
    else:
        wanted_statuses = ("WIP", "NEXT")
    for wanted in wanted_statuses:
        for t in active_tasks:
            if str(t["status"]) != wanted:
                continue
            if wanted_prefix is not None and not _task_matches_prefix(t, wanted_prefix):
                continue
            if _is_task_blocked(base_dir, t, explicit_dir=explicit_dir):
                continue
            return str(t["id"]).upper()
    return None

@_discovery_scoped
def cmd_next_id(
    base_dir: Path,
    target_dir: Path | None = None,
    task_id: str | None = None,
    explicit_dir: str | None = None,
    prefix: str | None = None,
    status: str | None = None,
) -> int:
    notes: list[str] = []
    if prefix is not None:
        notes.append(f"prefix={prefix.strip().upper()}")
    if status is not None:
        notes.append(f"status={status.strip().upper()}")
    filter_note = f" ({', '.join(notes)})" if notes else ""
    if task_id is None:
        tid = resolve_top_task_id(base_dir, prefix=prefix, status=status, explicit_dir=explicit_dir)
        if not tid:
            st_label = status.strip().upper() if status is not None else "WIP or NEXT"
            sys.stderr.write(
                f"{prog_name()}: no active {st_label} task{filter_note} found in TODO.md under {base_dir}\n"
            )
            return 1
        sys.stdout.write(f"{tid}\n")
        return 0

    tdir = target_dir or base_dir
    dag = build_dependency_dag(
        base_dir,
        tdir,
        task_id,
        explicit_dir=explicit_dir,
        stop_at_done=True,
    )
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
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
    next_act = _first_actionable_in_dag(dag, prefix=prefix, status=wanted_st_set)
    if not next_act:
        sys.stderr.write(
            f"{prog_name()}: no unblocked actionable task{filter_note} found for {root_node['ref']}\n"
        )
        return 1
    sys.stdout.write(f"{next_act}\n")
    return 0
