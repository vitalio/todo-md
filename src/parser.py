EMPTY_DEPENDS_LINE_RE = re.compile(r"^\s*[-*]\s*Depends on:\s*$", re.IGNORECASE)

def normalize_dep_ref_token(tok: str) -> tuple[str | None, str | None]:
    raw = tok.strip()
    if not raw:
        return None, "empty dependency reference"
    pm = PROJECT_TASK_RE.match(raw)
    if pm:
        proj_part = pm.group(1).strip().replace("\\", "/").strip("/")
        if not proj_part or ".." in proj_part.split("/"):
            return None, f"invalid dependency reference {raw!r}"
        return f"{proj_part}:{pm.group(2).upper()}", None
    if re.fullmatch(r"[A-Za-z]\d+", raw):
        return raw.upper(), None
    return None, f"invalid dependency reference {raw!r}"

def parse_depends_clause(raw_clause: str) -> tuple[list[list[str]], str | None]:
    if not raw_clause.strip():
        return [], "empty Depends on: clause"
    stages: list[list[str]] = []
    seen_prior_stages: set[str] = set()
    for raw_stage in raw_clause.split("->"):
        if not raw_stage.strip():
            return [], f"empty stage in dependency clause {raw_clause.strip()!r}"
        stage_refs: list[str] = []
        seen_stage: set[str] = set()
        for raw_item in raw_stage.split(","):
            tok = raw_item.strip()
            if not tok:
                return [], f"empty item in dependency stage {raw_stage.strip()!r}"
            norm, err = normalize_dep_ref_token(tok)
            if err or norm is None:
                return [], err or f"invalid dependency reference {tok!r}"
            if norm in seen_prior_stages:
                return [], (
                    f"duplicate task {norm} across '->' stages in {raw_clause.strip()!r} "
                    "(',' groups parallel items within a stage and binds tighter than '->'; "
                    "use ';' or repeat --depends to separate independent chains)"
                )
            if norm not in seen_stage:
                seen_stage.add(norm)
                stage_refs.append(norm)
        seen_prior_stages.update(seen_stage)
        stages.append(stage_refs)
    return stages, None

def parse_dependency_clauses(section_text: str) -> tuple[list[list[list[str]]], list[str]]:
    clauses: list[list[list[str]]] = []
    errors: list[str] = []
    in_fence = False
    for line in section_text.splitlines():
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if EMPTY_DEPENDS_LINE_RE.match(line):
            errors.append("empty Depends on: line")
            continue
        m = DEPENDS_LINE_RE.match(line)
        if not m:
            continue
        for sub_clause in m.group(1).split(";"):
            stages, err = parse_depends_clause(sub_clause)
            if err:
                errors.append(err)
            elif stages:
                clauses.append(stages)
    return clauses, errors

def parse_task_dependencies(section_text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    in_fence = False
    for line in section_text.splitlines():
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = DEPENDS_LINE_RE.match(line)
        if not m:
            continue
        for sub_clause in m.group(1).split(";"):
            for raw_stage in sub_clause.split("->"):
                for raw in raw_stage.split(","):
                    tok = raw.strip()
                    if not tok:
                        continue
                    norm, _ = normalize_dep_ref_token(tok)
                    val = norm if norm is not None else tok
                    if val not in seen:
                        seen.add(val)
                        refs.append(val)
    return refs


def read_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

def _read_stdin_if_piped() -> str | None:
    try:
        if not sys.stdin.isatty():
            data = sys.stdin.read()
            return data if data.strip() else None
    except Exception:
        pass
    return None

def parse_tasks_in_text(text: str, filename: str) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    in_fence = False
    current: dict[str, object] | None = None
    body_lines: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
        if not in_fence and line.startswith("# "):
            if current is not None:
                current["section"] = "\n".join(body_lines).rstrip()
                tasks.append(current)
                current = None
                body_lines = []
            m = HEADING_RE.match(line)
            if m:
                emoji, status, tid, title = m.groups()
                current = {
                    "id": tid,
                    "status": status,
                    "emoji": emoji,
                    "title": title,
                    "file": filename,
                    "line": lineno,
                    "heading": line,
                }
                body_lines = [line]
                continue
        if current is not None:
            body_lines.append(line)
    if current is not None:
        current["section"] = "\n".join(body_lines).rstrip()
        tasks.append(current)
    return tasks

def collect_all_tasks(base_dir: Path) -> list[dict[str, object]]:
    all_tasks: list[dict[str, object]] = []
    for fname in TASK_FILES:
        p = base_dir / fname
        if p.is_file():
            all_tasks.extend(parse_tasks_in_text(read_if_exists(p), fname))
    return all_tasks

def compile_search_pattern(query: str) -> re.Pattern[str]:
    try:
        return re.compile(query, re.IGNORECASE | re.MULTILINE)
    except re.error:
        return re.compile(re.escape(query), re.IGNORECASE)

def task_matches_pattern(
    t: dict[str, object],
    pat: re.Pattern[str],
    base_dir: Path,
    project_label: str | None = None,
) -> bool:
    tid = str(t["id"])
    b_name = base_dir.resolve().name
    id_tokens = [tid, f"{b_name}:{tid}"]
    if project_label and project_label != b_name:
        id_tokens.append(f"{project_label}:{tid}")
    haystack = "\n".join([*id_tokens, str(t["title"]), str(t.get("section", ""))])
    return bool(pat.search(haystack))

def search_tasks(
    base_dir: Path,
    query: str,
    include_archive: bool = False,
    project_label: str | None = None,
) -> list[dict[str, object]]:
    pat = compile_search_pattern(query)
    fnames = TASK_FILES if include_archive else TASK_FILES[:1]
    matches: list[dict[str, object]] = []
    for fname in fnames:
        path = base_dir / fname
        if not path.is_file():
            continue
        for t in parse_tasks_in_text(read_if_exists(path), fname):
            if task_matches_pattern(t, pat, base_dir, project_label=project_label):
                matches.append(t)
    return matches

def highest_ids_in_use(base_dir: Path) -> dict[str, int]:
    top: dict[str, int] = {}
    for fname in TASK_FILES:
        text = read_if_exists(base_dir / fname)
        if not text:
            continue
        in_fence = False
        for line in text.splitlines():
            if line.lstrip().startswith(FENCE):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = ANY_ID_RE.match(line)
            if m:
                ident = m.group(1)
                prefix, num = ident[0], int(ident[1:])
                top[prefix] = max(top.get(prefix, 0), num)
    return top

def next_free_id(base_dir: Path, prefix: str = "F") -> str:
    p = prefix.upper()
    if not re.fullmatch(r"[A-Za-z]", p):
        raise SystemExit(f"{prog_name()}: invalid ID prefix {prefix!r}; expected a single letter A-Z")
    top = highest_ids_in_use(base_dir)
    return f"{p}{top.get(p, 0) + 1}"

def resolve_last_task_id(base_dir: Path, filt: str | None = None) -> str | None:
    mode = (filt or "NEW").strip().upper()
    if mode != "ARCHIVE" and mode not in VALID_STATUSES:
        raise SystemExit(
            f"{prog_name()}: unknown status or filter {filt!r}; expected {', '.join(VALID_STATUSES)}, or archive"
        )
    if mode in ("ARCHIVE", "DONE", "CANCELED"):
        arch_path = base_dir / "TODO_ARCHIVE.md"
        if not arch_path.is_file():
            return None
        arch_tasks = parse_tasks_in_text(read_if_exists(arch_path), "TODO_ARCHIVE.md")
        if mode == "ARCHIVE":
            return str(arch_tasks[0]["id"]).upper() if arch_tasks else None
        for t in arch_tasks:
            if str(t["status"]) == mode:
                return str(t["id"]).upper()
        return None
    todo_path = base_dir / "TODO.md"
    if not todo_path.is_file():
        return None
    active_tasks = parse_tasks_in_text(read_if_exists(todo_path), "TODO.md")
    matching = [t for t in active_tasks if str(t["status"]) == mode]
    if not matching:
        return None
    if mode in ("WIP", "NEXT"):
        return str(matching[0]["id"]).upper()
    return str(matching[-1]["id"]).upper()

def _strip_heading_note(title: str) -> tuple[str, str | None]:
    m = re.match(r"^(.*?)\s+—\s+\*(.*)\*\s*$", title.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title.strip(), None

def _task_prefix(task_id: str) -> str:
    return task_id.strip().upper().split(":")[-1][:1]

def _task_matches_prefix(task: dict[str, object], wanted_prefix: str) -> bool:
    raw_id = str(task.get("id") or task.get("ref") or "")
    return bool(raw_id) and _task_prefix(raw_id) == wanted_prefix.strip().upper()

SHELL_QUOTE_HINT = (
    "quote Markdown args with single quotes (-b '...') or a quoted heredoc (-b - <<'EOF') "
    "so the shell does not expand inline `...` or $VAR"
)
_BULLET_PREFIX_RE = re.compile(r"^(\s*(?:(?:[-*+]|\d+[.)])\s+(?:\[[ xX~]\]\s+)?)?)(.*)$")
_EMPTY_PARENS_BRACKETS_RE = re.compile(r"(?:^|\s)(\(\)|\[\])(?=\s|$|[.,;:!?)\]])")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\S\s+[.,;:](?=\s|$)")


def _mask_section_inline_code(
    non_fence_lines: list[tuple[int, int, str]]
) -> tuple[dict[int, str], list[tuple[int, str]]]:
    masked_by_offset: dict[int, list[str]] = {off: [] for off, _, _ in non_fence_lines}
    errors: list[tuple[int, str]] = []
    open_tick_len = 0
    open_lineno = 1
    open_offset = 0
    span_chars = 0

    for offset, lineno, text in non_fence_lines:
        # Heading line (offset 0) cannot leave an unclosed inline span into body lines
        out = masked_by_offset[offset]
        i = 0
        n = len(text)
        is_new_item = bool(re.match(r"^\s*(?:[-*+]|\d+[.)]|#+)\s+", text))
        if open_tick_len > 0 and (not text.strip() or is_new_item):
            if open_tick_len == 2 and span_chars <= 1:
                errors.append(
                    (open_lineno, f"empty inline code span ({chr(96) * 2}) (possible swallowed shell expansion)")
                )
            else:
                errors.append((open_lineno, "unpaired inline backtick (`) (possible swallowed shell expansion)"))
            open_tick_len = 0
            span_chars = 0
        while i < n:
            ch = text[i]
            if open_tick_len == 0:
                if ch == "\\" and i + 1 < n and text[i + 1] == "`":
                    out.append("``")
                    i += 2
                    continue
                if ch != "`":
                    out.append(ch)
                    i += 1
                    continue
                run_start = i
                while i < n and text[i] == "`":
                    i += 1
                tick_len = i - run_start
                if tick_len == 2 and (i >= n or not text[i].isalnum()):
                    # Check if a matching `` closes on the remaining line
                    rem = text[i:]
                    if not re.search(r"(?<!`)``(?!`)", rem):
                        errors.append(
                            (
                                lineno,
                                f"empty inline code span ({chr(96) * 2}) (possible swallowed shell expansion)",
                            )
                        )
                        continue
                open_tick_len = tick_len
                open_lineno = lineno
                open_offset = offset
                span_chars = 0
                out.append("`CODE`")
            else:
                if ch == "`":
                    c_start = i
                    while i < n and text[i] == "`":
                        i += 1
                    c_len = i - c_start
                    if c_len == open_tick_len:
                        if span_chars == 0 and offset == open_offset:
                            errors.append(
                                (
                                    open_lineno,
                                    f"empty inline code span ({chr(96) * 2}) (possible swallowed shell expansion)",
                                )
                            )
                        open_tick_len = 0
                        span_chars = 0
                    else:
                        span_chars += c_len
                else:
                    span_chars += 1
                    i += 1
        if open_tick_len > 0 and offset == 0:
            if open_tick_len == 2 and span_chars == 0:
                errors.append(
                    (open_lineno, f"empty inline code span ({chr(96) * 2}) (possible swallowed shell expansion)")
                )
            else:
                errors.append((open_lineno, "unpaired inline backtick (`) (possible swallowed shell expansion)"))
            open_tick_len = 0
            span_chars = 0
        elif open_tick_len > 0:
            span_chars += 1

    if open_tick_len > 0:
        if open_tick_len == 2 and span_chars <= 1:
            errors.append(
                (open_lineno, f"empty inline code span ({chr(96) * 2}) (possible swallowed shell expansion)")
            )
        else:
            errors.append((open_lineno, "unpaired inline backtick (`) (possible swallowed shell expansion)"))

    return {off: "".join(chars) for off, chars in masked_by_offset.items()}, errors


def validate_task_section_markdown(
    sec_lines: list[str],
    tid: str,
    fname: str = "TODO.md",
    start_lineno: int = 1,
) -> list[str]:
    errors: list[str] = []
    in_fence = False
    fence_open_lineno = start_lineno
    non_fence_lines: list[tuple[int, int, str]] = []

    for offset, line in enumerate(sec_lines):
        lineno = start_lineno + offset
        stripped = line.lstrip()
        if stripped.startswith(FENCE):
            if not in_fence:
                in_fence = True
                fence_open_lineno = lineno
            else:
                in_fence = False
            continue
        if in_fence:
            continue
        if offset == 0 and line.startswith("# "):
            m = HEADING_RE.match(line)
            if m:
                raw_title = m.group(4)
                base_title, note_text = _strip_heading_note(raw_title)
                check_text = base_title if note_text is None else f"{base_title} — {note_text}"
            else:
                check_text = line
        else:
            check_text = line
        non_fence_lines.append((offset, lineno, check_text))

    if in_fence:
        errors.append(
            f"{fname}:{fence_open_lineno}: task {tid} has an unclosed fenced code block ({FENCE}); "
            f"{SHELL_QUOTE_HINT}"
        )

    masked_map, code_errors = _mask_section_inline_code(non_fence_lines)
    err_lines: set[int] = set()
    for err_lineno, code_err in code_errors:
        errors.append(f"{fname}:{err_lineno}: task {tid} has {code_err}; {SHELL_QUOTE_HINT}")
        err_lines.add(err_lineno)

    for offset, lineno, orig_text in non_fence_lines:
        if lineno in err_lines:
            continue
        loc = f"{fname}:{lineno}"
        stripped = orig_text.lstrip()
        if stripped.startswith("|"):
            continue
        masked = masked_map.get(offset, "")
        pm = _EMPTY_PARENS_BRACKETS_RE.search(masked)
        if pm:
            tok = pm.group(1)
            errors.append(
                f"{loc}: task {tid} has empty '{tok}' outside inline code "
                f"(possible swallowed shell expansion); {SHELL_QUOTE_HINT}"
            )
            continue

        if offset == 0:
            prose = masked
        else:
            bm = _BULLET_PREFIX_RE.match(masked)
            prose = bm.group(2) if bm else masked

        prose_core = prose.strip()
        if not prose_core:
            continue

        if "  " in prose_core:
            errors.append(
                f"{loc}: task {tid} has consecutive spaces in prose outside inline code "
                f"(possible swallowed shell expansion); {SHELL_QUOTE_HINT}"
            )
            continue

        if _SPACE_BEFORE_PUNCT_RE.search(prose_core):
            errors.append(
                f"{loc}: task {tid} has space before punctuation outside inline code "
                f"(possible swallowed shell expansion); {SHELL_QUOTE_HINT}"
            )
            continue

    return errors


@_discovery_scoped
def validate_all(base_dir: Path) -> tuple[list[str], int]:
    errors: list[str] = []
    seen_ids: dict[str, str] = {}
    has_archive = (base_dir / "TODO_ARCHIVE.md").is_file()
    if (base_dir / "TODO_PLAN.md").is_file():
        errors.append("TODO_PLAN.md: deprecated file exists (merge deferred tasks into TODO.md)")
    for fname in TASK_FILES:
        p = base_dir / fname
        if not p.is_file():
            continue
        text = read_if_exists(p)
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith(FENCE):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if line.startswith("# "):
                m = HEADING_RE.match(line)
                if not m:
                    errors.append(f"{fname}:{lineno}: invalid task heading format: {line}")
                    continue
                emoji, status, tid, title = m.groups()
                norm_emoji = "⏸️" if emoji.startswith("⏸") else emoji
                if VALID_STATUSES.get(status) != norm_emoji:
                    errors.append(f"{fname}:{lineno}: mismatched emoji {emoji} for status [{status}]")
                if title.endswith(",") or title.count("(") != title.count(")"):
                    errors.append(f"{fname}:{lineno}: truncated/malformed task heading title: {title!r}")
                loc = f"{fname}:{lineno}"
                if tid in seen_ids:
                    errors.append(f"{loc}: duplicate task ID {tid} (first seen at {seen_ids[tid]})")
                else:
                    seen_ids[tid] = loc
                if fname == "TODO.md" and has_archive and status in ("DONE", "CANCELED"):
                    errors.append(f"{loc}: {status} task {tid} should be moved to TODO_ARCHIVE.md")
                if fname == "TODO.md" and status not in ("DONE", "CANCELED"):
                    _, heading_note = _strip_heading_note(title)
                    if heading_note and STALE_COMPLETION_NOTE_RE.match(heading_note):
                        errors.append(
                            f"{loc}: active task {tid} [{status}] retains completion date note "
                            f"'— *{heading_note}*' (move it back to TODO_ARCHIVE.md or clear the stale note)"
                        )
                if fname == "TODO_ARCHIVE.md" and status not in ("DONE", "CANCELED"):
                    errors.append(f"{loc}: non-archived status [{status}] on task {tid} in TODO_ARCHIVE.md")

    for fname in TASK_FILES:
        fpath = base_dir / fname
        if not fpath.is_file():
            continue
        for t in parse_tasks_in_text(read_if_exists(fpath), fname):
            tid = str(t["id"]).upper()
            lineno = int(t["line"])
            sec = str(t["section"])
            in_body_fence = False
            for offset, sline in enumerate(sec.splitlines()):
                if sline.lstrip().startswith(FENCE):
                    in_body_fence = not in_body_fence
                    continue
                if in_body_fence:
                    continue
                if ROLE_LINE_RE.match(sline):
                    errors.append(
                        f"{fname}:{lineno + offset}: task {tid} has an in-body 'Role:' line "
                        "(remove it; task prefixes and statuses are managed via headings)"
                    )
                elif TARGET_FILES_LINE_RE.match(sline):
                    errors.append(
                        f"{fname}:{lineno + offset}: task {tid} has an in-body 'Target files:' line "
                        "(remove it)"
                    )
            errors.extend(
                validate_task_section_markdown(
                    sec.splitlines(),
                    tid=tid,
                    fname=fname,
                    start_lineno=lineno,
                )
            )

    ws_root = _workspace_root_cached(base_dir)
    is_orchestrator = has_local_todo_projects_config(base_dir)
    local_ids = set(seen_ids.keys())
    shared = _ACTIVE_DISCOVERY
    task_cache: dict[Path, dict[str, dict[str, object]]] = (
        shared.task_maps if shared is not None else {}
    )

    def _proj_task_ids(proj_dir: Path) -> dict[str, dict[str, object]]:
        p_res = proj_dir.resolve()
        if p_res not in task_cache:
            mapping: dict[str, dict[str, object]] = {}
            if is_todo_project(p_res):
                for pt in collect_all_tasks(p_res):
                    mapping[str(pt["id"]).upper()] = pt
            task_cache[p_res] = mapping
        return task_cache[p_res]
    todo_path = base_dir / "TODO.md"
    if todo_path.is_file():
        for t in parse_tasks_in_text(read_if_exists(todo_path), "TODO.md"):
            tid = str(t["id"]).upper()
            lineno = int(t["line"])
            sec = str(t["section"])
            clauses, syntax_errs = parse_dependency_clauses(sec)
            for serr in syntax_errs:
                errors.append(f"TODO.md:{lineno}: task {tid} has dependency syntax error: {serr}")
            checked_refs: set[str] = set()
            for clause in clauses:
                for stage in clause:
                    for ref in stage:
                        if ref in checked_refs:
                            continue
                        checked_refs.add(ref)
                        pm = PROJECT_TASK_RE.match(ref)
                        if pm:
                            proj_name = pm.group(1).strip().replace("\\", "/").strip("/")
                            target_tid = pm.group(2).upper()
                            if not proj_name or ".." in proj_name.split("/"):
                                errors.append(f"TODO.md:{lineno}: task {tid} has invalid dependency reference {ref!r}")
                                continue
                            if not is_orchestrator:
                                errors.append(
                                    f"TODO.md:{lineno}: task {tid} has cross-project dependency {ref!r} in a "
                                    "non-orchestrator repository (keep cross-project dependencies in the "
                                    "workspace orchestrator repository with .todo_projects)"
                                )
                                continue
                            ext_dir = lookup_external_alias(base_dir, ws_root, proj_name)
                            if ext_dir is not None and is_todo_project(ext_dir):
                                target_dir = ext_dir
                            else:
                                target_dir = (ws_root / proj_name).resolve()
                            if not is_todo_project(target_dir):
                                errors.append(f"TODO.md:{lineno}: task {tid} depends on unknown project in {ref!r}")
                                continue
                            if target_tid not in _proj_task_ids(target_dir):
                                errors.append(f"TODO.md:{lineno}: task {tid} depends on missing task {ref!r}")
                            elif target_dir == base_dir.resolve() and target_tid == tid:
                                errors.append(f"TODO.md:{lineno}: task {tid} cannot depend on itself")
                        elif re.fullmatch(r"[A-Za-z]\d+", ref):
                            target_tid = ref.upper()
                            if target_tid == tid:
                                errors.append(f"TODO.md:{lineno}: task {tid} cannot depend on itself")
                            elif target_tid not in local_ids:
                                errors.append(f"TODO.md:{lineno}: task {tid} depends on missing task {ref!r}")
                        else:
                            errors.append(f"TODO.md:{lineno}: task {tid} has invalid dependency reference {ref!r}")
            if clauses:
                dag = build_dependency_dag(base_dir, base_dir, tid, stop_at_done=False)
                if dag["cycle"]:
                    errors.append(
                        f"TODO.md:{lineno}: task {tid} has dependency cycle: {' -> '.join(dag['cycle'])}"
                    )

    return errors, len(seen_ids)
