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
            if norm not in seen_stage:
                seen_stage.add(norm)
                stage_refs.append(norm)
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
        stages, err = parse_depends_clause(m.group(1))
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
        for raw_stage in m.group(1).split("->"):
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

def search_tasks(
    base_dir: Path,
    query: str,
    include_archive: bool = False,
    project_label: str | None = None,
) -> list[dict[str, object]]:
    pat = compile_search_pattern(query)
    fnames = TASK_FILES if include_archive else TASK_FILES[:1]
    b_name = base_dir.resolve().name
    matches: list[dict[str, object]] = []
    for fname in fnames:
        path = base_dir / fname
        if not path.is_file():
            continue
        for t in parse_tasks_in_text(read_if_exists(path), fname):
            tid = str(t["id"])
            id_tokens = [tid, f"{b_name}:{tid}"]
            if project_label and project_label != b_name:
                id_tokens.append(f"{project_label}:{tid}")
            haystack = "\n".join([*id_tokens, str(t["title"]), str(t.get("section", ""))])
            if pat.search(haystack):
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

    ws_root = resolve_workspace_root(base_dir)
    local_ids = set(seen_ids.keys())
    proj_task_cache: dict[Path, set[str]] = {}
    todo_path = base_dir / "TODO.md"
    if todo_path.is_file():
        for t in parse_tasks_in_text(read_if_exists(todo_path), "TODO.md"):
            tid = str(t["id"]).upper()
            lineno = int(t["line"])
            sec = str(t["section"])
            in_role_fence = False
            for offset, sline in enumerate(sec.splitlines()):
                if sline.lstrip().startswith(FENCE):
                    in_role_fence = not in_role_fence
                    continue
                if in_role_fence:
                    continue
                if ROLE_LINE_RE.match(sline):
                    errors.append(
                        f"TODO.md:{lineno + offset}: task {tid} has an in-body 'Role:' line "
                        "(remove it; task prefixes and statuses are managed via headings)"
                    )
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
                            target_dir = (ws_root / proj_name).resolve()
                            if not is_todo_project(target_dir):
                                ext_dir = lookup_external_alias(base_dir, ws_root, proj_name)
                                if ext_dir is not None:
                                    target_dir = ext_dir
                            if not is_todo_project(target_dir):
                                errors.append(f"TODO.md:{lineno}: task {tid} depends on unknown project in {ref!r}")
                                continue
                            if target_dir not in proj_task_cache:
                                proj_task_cache[target_dir] = {
                                    str(pt["id"]).upper() for pt in collect_all_tasks(target_dir)
                                }
                            if target_tid not in proj_task_cache[target_dir]:
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

def split_line_slice(token: str) -> tuple[str, tuple[int, int] | None]:
    m = LINE_SLICE_RE.match(token)
    if not m:
        return token, None
    start = int(m.group("a") or m.group("c"))
    end_raw = m.group("b") or m.group("d")
    return m.group("path"), (start, int(end_raw) if end_raw else start)

def split_file_spec(spec: str) -> tuple[str, tuple[int, int] | None]:
    m = FILE_SPEC_RE.match(spec)
    if not m:
        return spec, None
    return m.group("path"), (int(m.group("start")), int(m.group("end")))

def _resolve_repo_file(repo_root: Path, token: str) -> str | None:
    p_tok = Path(token)
    target = p_tok.resolve() if p_tok.is_absolute() else (repo_root / token).resolve()
    try:
        rel_posix = target.relative_to(repo_root).as_posix()
    except ValueError:
        return None
    if rel_posix == "." or not target.is_file():
        return None
    return rel_posix

def _expand_task_glob(repo_root: Path, pattern: str) -> list[str]:
    if pattern.startswith("/") or ("/" not in pattern and "." not in pattern):
        return []
    if ".." in pattern.split("/"):
        return []
    try:
        matches = sorted(repo_root.glob(pattern))
    except (NotImplementedError, ValueError, OSError):
        return []
    out: list[str] = []
    for m in matches:
        try:
            rel = m.resolve().relative_to(repo_root)
        except (ValueError, OSError):
            continue
        if not m.is_file() or {".git", "__pycache__"} & set(rel.parts):
            continue
        out.append(rel.as_posix())
    return out

def _target_file_tokens(section_text: str) -> list[str]:
    tokens: list[str] = []
    in_fence = False
    in_target = False
    for line in section_text.splitlines():
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            in_target = False
            continue
        if in_fence:
            continue
        if TARGET_FILES_LINE_RE.match(line):
            in_target = True
        elif not (in_target and line[:1].isspace() and line.strip() and not BULLET_LINE_RE.match(line)):
            in_target = False
        if in_target:
            tokens.extend(BACKTICK_TOKEN_RE.findall(line))
    return tokens

def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip())

def _symbol_span_end(lines: list[str], start: int, indent: int) -> int:
    end = start
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if not line.strip():
            continue
        line_indent = _line_indent(line)
        if line_indent == indent and line.lstrip().startswith("}"):
            end = idx
            break
        if line_indent <= indent and not line.lstrip().startswith((")", "]", "}")):
            break
        end = idx
    return end

def _find_symbol_span(lines: list[str], name: str, lo: int, hi: int) -> tuple[int, int] | None:
    esc = re.escape(name)
    patterns = (
        re.compile(
            rf"^(\s*)(?:async\s+def|def|class|function|fn|func|struct|enum|interface|type)\s+{esc}\b"
        ),
        re.compile(rf"^(\s*)(?:function\s+)?{esc}\s*\(\s*\)\s*\{{?"),
        re.compile(rf"^(\s*){esc}\s*(?::[^=\n]+)?=(?!=)"),
    )
    for pat in patterns:
        best: tuple[int, int] | None = None
        for idx in range(lo, hi + 1):
            m = pat.match(lines[idx])
            if m and (best is None or len(m.group(1)) < best[0]):
                best = (len(m.group(1)), idx)
        if best is None:
            continue
        indent, idx = best
        start = idx
        while (
            start > lo
            and lines[start - 1].lstrip().startswith("@")
            and _line_indent(lines[start - 1]) == indent
        ):
            start -= 1
        return start, min(_symbol_span_end(lines, idx, indent), hi)
    return None

def _resolve_symbol(lines: list[str], dotted: str) -> tuple[int, int] | None:
    lo, hi = 0, len(lines) - 1
    span: tuple[int, int] | None = None
    for part in dotted.split("."):
        if lo > hi:
            return None
        span = _find_symbol_span(lines, part, lo, hi)
        if span is None:
            return None
        lo, hi = span
    return span

def _resolve_symbol_range(lines: list[str], first: str, last: str | None) -> tuple[int, int] | None:
    a = _resolve_symbol(lines, first)
    if a is None:
        return None
    if last is None:
        return a[0] + 1, a[1] + 1
    b = _resolve_symbol(lines, last)
    if b is None or b[1] < a[0]:
        return None
    return a[0] + 1, b[1] + 1

def _normalize_file_entries(entries: list[tuple[str, tuple[int, int] | None]]) -> list[str]:
    order: list[str] = []
    whole: set[str] = set()
    spans: dict[str, list[tuple[int, int]]] = {}
    for rel, span in entries:
        if rel not in spans:
            order.append(rel)
            spans[rel] = []
        if span is None:
            whole.add(rel)
        else:
            spans[rel].append(span)
    out: list[str] = []
    for rel in order:
        if rel in whole:
            out.append(rel)
            continue
        merged: list[tuple[int, int]] = []
        for s, e in sorted(spans[rel]):
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        out.extend(f"{rel}:{s}-{e}" for s, e in merged)
    return out

def extract_task_files(base_dir: Path, section_text: str) -> list[str]:
    repo_root = base_dir.resolve()
    entries: list[tuple[str, tuple[int, int] | None]] = []
    cache: dict[str, list[str]] = {}

    def file_lines(rel: str) -> list[str]:
        if rel not in cache:
            data = (repo_root / rel).read_bytes()
            cache[rel] = [ln.decode("utf-8", "replace") for ln in data.splitlines()]
        return cache[rel]

    for raw in _target_file_tokens(section_text):
        cand = raw.strip()
        if not cand or any(ch.isspace() for ch in cand) or "://" in cand:
            continue
        if cand.startswith("-") or any(ch in cand for ch in "<>{}"):
            continue
        path_part, span = split_line_slice(cand)
        if PROJECT_TASK_RE.match(cand):
            continue
        sym = SYMBOL_SPEC_RE.match(cand) if span is None else None
        if sym is not None:
            rel_sym = _resolve_repo_file(repo_root, sym.group("path"))
            if rel_sym is None:
                continue
            sym_span = _resolve_symbol_range(file_lines(rel_sym), sym.group("first"), sym.group("last"))
            if sym_span is None:
                sys.stderr.write(
                    f"{prog_name()}: warning: symbol slice {cand!r} not found in {rel_sym}; using whole file\n"
                )
                entries.append((rel_sym, None))
                continue
            entries.append((rel_sym, sym_span))
            continue
        if span is not None and (span[0] < 1 or span[1] < span[0]):
            continue
        if any(ch in path_part for ch in "*?["):
            if span is None:
                entries.extend((g, None) for g in _expand_task_glob(repo_root, path_part))
            continue
        rel = _resolve_repo_file(repo_root, path_part)
        if rel is None:
            continue
        if span is None:
            entries.append((rel, None))
            continue
        n_total = len(file_lines(rel))
        if span[0] > n_total:
            continue
        entries.append((rel, (span[0], min(span[1], n_total))))
    return _normalize_file_entries(entries)

def select_task_files(
    base_dir: Path,
    task_id: str | None = None,
    max_lines: int | None = None,
    max_total_lines: int | None = None,
    max_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> list[str] | None:
    target = task_id.strip().upper() if task_id else resolve_top_task_id(base_dir)
    if not target:
        sys.stderr.write(f"{prog_name()}: no active WIP or NEXT task found in TODO.md under {base_dir}\n")
        return None
    has_budget = any(
        cap is not None for cap in (max_lines, max_total_lines, max_bytes, max_total_bytes)
    )
    repo_root = base_dir.resolve()
    total_lines = 0
    total_bytes = 0
    for t in collect_all_tasks(base_dir):
        if str(t["id"]).upper() != target:
            continue
        selected: list[str] = []
        for spec in extract_task_files(base_dir, str(t["section"])):
            if has_budget:
                rel_path, span = split_file_spec(spec)
                chunks = (repo_root / rel_path).read_bytes().splitlines(keepends=True)
                if span is not None:
                    chunks = chunks[span[0] - 1 : span[1]]
                n_bytes = sum(len(c) for c in chunks)
                n_lines = len(chunks)
                if max_bytes is not None and n_bytes > max_bytes:
                    continue
                if max_total_bytes is not None and total_bytes + n_bytes > max_total_bytes:
                    continue
                if max_lines is not None and n_lines > max_lines:
                    continue
                if max_total_lines is not None and total_lines + n_lines > max_total_lines:
                    continue
                total_bytes += n_bytes
                total_lines += n_lines
            selected.append(spec)
        return selected
    sys.stderr.write(f"{prog_name()}: task {target!r} not found in TODO*.md under {base_dir}\n")
    return None
