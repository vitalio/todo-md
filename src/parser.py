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
_SENTENCE_DOUBLE_SPACE_RE = re.compile(r"([.!?])  +(?=[A-Z0-9\"'`(\[])")
_NEW_BLOCK_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|#+)\s+")


def _find_closing_backtick_run(text: str, start: int, tick_len: int) -> int | None:
    i = start
    n = len(text)
    while i < n:
        if text[i] != "`":
            i += 1
            continue
        c_start = i
        while i < n and text[i] == "`":
            i += 1
        if i - c_start == tick_len:
            return c_start
    return None


def _try_parse_escaped_single_tick_span(text: str, start: int) -> tuple[str, int] | None:
    n = len(text)
    j = start
    inner_parts: list[str] = []
    escaped_count = 0
    while j < n:
        ch = text[j]
        if ch == "\\":
            bs_start = j
            while j < n and text[j] == "\\":
                j += 1
            bs_count = j - bs_start
            if j < n and text[j] == "`":
                if bs_count % 2 == 1:
                    if bs_count > 1:
                        inner_parts.append("\\" * (bs_count - 1))
                    inner_parts.append("`")
                    escaped_count += 1
                    j += 1
                    continue
                inner_parts.append("\\" * bs_count)
                continue
            inner_parts.append("\\" * bs_count)
            continue
        if ch == "`":
            c_start = j
            while j < n and text[j] == "`":
                j += 1
            c_len = j - c_start
            if c_len == 1:
                if escaped_count >= 2 and escaped_count % 2 == 0:
                    inner = "".join(inner_parts)
                    if inner.startswith("`"):
                        inner = " " + inner
                    if inner.endswith("`"):
                        inner = inner + " "
                    return f"``{inner}``", j
                return None
            return None
        inner_parts.append(ch)
        j += 1
    return None


def _normalize_escaped_nested_backticks(text: str) -> str:
    if "\\`" not in text:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            bs_start = i
            while i < n and text[i] == "\\":
                i += 1
            bs_count = i - bs_start
            if i < n and text[i] == "`" and bs_count % 2 == 1:
                out.append(text[bs_start : i + 1])
                i += 1
                continue
            out.append(text[bs_start:i])
            continue
        if ch != "`":
            out.append(ch)
            i += 1
            continue
        run_start = i
        while i < n and text[i] == "`":
            i += 1
        tick_len = i - run_start
        if tick_len >= 2:
            close_idx = _find_closing_backtick_run(text, i, tick_len)
            if close_idx is not None:
                out.append(text[run_start : close_idx + tick_len])
                i = close_idx + tick_len
            else:
                out.append(text[run_start:i])
            continue
        parsed = _try_parse_escaped_single_tick_span(text, i)
        if parsed is not None:
            normalized_span, next_i = parsed
            out.append(normalized_span)
            i = next_i
            continue
        close_idx = _find_closing_backtick_run(text, i, 1)
        if close_idx is not None:
            out.append(text[run_start : close_idx + 1])
            i = close_idx + 1
        else:
            out.append("`")
    return "".join(out)


def _collapse_sentence_double_spaces_outside_code(text: str) -> str:
    if "  " not in text:
        return text
    spans: list[str] = []
    masked_parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] == "`":
            masked_parts.append(text[i : i + 2])
            i += 2
            continue
        if ch != "`":
            masked_parts.append(ch)
            i += 1
            continue
        run_start = i
        while i < n and text[i] == "`":
            i += 1
        tick_len = i - run_start
        close_idx = _find_closing_backtick_run(text, i, tick_len)
        if close_idx is not None and close_idx > i:
            span_idx = len(spans)
            spans.append(text[run_start : close_idx + tick_len])
            masked_parts.append(f"`\x00{span_idx}\x00`")
            i = close_idx + tick_len
        else:
            masked_parts.append(text[run_start:i])
    masked = "".join(masked_parts)
    collapsed = _SENTENCE_DOUBLE_SPACE_RE.sub(r"\1 ", masked)
    for idx, orig_span in enumerate(spans):
        collapsed = collapsed.replace(f"`\x00{idx}\x00`", orig_span, 1)
    return collapsed


def _normalize_prose_block(text: str, collapse_spaces: bool = True) -> str:
    res = _normalize_escaped_nested_backticks(text)
    if collapse_spaces:
        res = _collapse_sentence_double_spaces_outside_code(res)
    return res


def normalize_task_section_markdown(sec_lines: list[str]) -> list[str]:
    if not sec_lines:
        return []
    out: list[str] = [
        "" for _ in sec_lines
    ]
    in_fence = False
    para_indices: list[int] = []

    def _flush_para() -> None:
        if not para_indices:
            return
        joined = "\n".join(sec_lines[idx] for idx in para_indices)
        normalized = _normalize_prose_block(joined, collapse_spaces=True)
        for idx, nline in zip(para_indices, normalized.split("\n")):
            out[idx] = nline
        para_indices.clear()

    for idx, line in enumerate(sec_lines):
        stripped = line.lstrip()
        if stripped.startswith(FENCE):
            _flush_para()
            in_fence = not in_fence
            out[idx] = line
            continue
        if in_fence:
            out[idx] = line
            continue
        if idx == 0 and line.startswith("# "):
            _flush_para()
            m = HEADING_RE.match(line)
            if m:
                raw_title = m.group(4)
                base_title, note_text = _strip_heading_note(raw_title)
                norm_base = _normalize_prose_block(base_title, collapse_spaces=True)
                prefix = line[: m.start(4)]
                if note_text is not None:
                    norm_note = _normalize_prose_block(note_text, collapse_spaces=True)
                    out[idx] = f"{prefix}{norm_base} — *{norm_note}*"
                else:
                    out[idx] = f"{prefix}{norm_base}"
            else:
                out[idx] = _normalize_prose_block(line, collapse_spaces=True)
            continue
        if not stripped:
            _flush_para()
            out[idx] = line
            continue
        if stripped.startswith("|"):
            _flush_para()
            out[idx] = _normalize_prose_block(line, collapse_spaces=False)
            continue
        if _NEW_BLOCK_ITEM_RE.match(line):
            _flush_para()
        para_indices.append(idx)

    _flush_para()

    if in_fence:
        trailing_blanks: list[str] = []
        while out and not out[-1].strip():
            trailing_blanks.append(out.pop())
        out.append(FENCE)
        out.extend(reversed(trailing_blanks))

    return out


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
                    # Check if a matching `` closes on the remaining line or continuation lines
                    rem_parts = [text[i:]]
                    if offset > 0:
                        for next_off, _, next_text in non_fence_lines:
                            if next_off <= offset:
                                continue
                            if not next_text.strip() or _NEW_BLOCK_ITEM_RE.match(next_text) or next_text.lstrip().startswith("|"):
                                break
                            rem_parts.append(next_text)
                    rem = "\n".join(rem_parts)
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
def validate_all(
    base_dir: Path,
    explicit_dir: str | None = None,
) -> tuple[list[str], int]:
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

    ws_root = _workspace_root_cached(base_dir, explicit_dir=explicit_dir)
    is_orchestrator = has_todo_projects_config(base_dir, explicit_dir=explicit_dir)
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
                            if ext_dir is None or not is_todo_project(ext_dir):
                                errors.append(f"TODO.md:{lineno}: task {tid} depends on unknown project in {ref!r}")
                                continue
                            target_dir = ext_dir
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
                dag = build_dependency_dag(
                    base_dir,
                    base_dir,
                    tid,
                    explicit_dir=explicit_dir,
                    stop_at_done=False,
                )
                if dag["cycle"]:
                    errors.append(
                        f"TODO.md:{lineno}: task {tid} has dependency cycle: {' -> '.join(dag['cycle'])}"
                    )

    return errors, len(seen_ids)
