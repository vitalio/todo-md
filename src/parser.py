def is_todo_project(directory: Path) -> bool:
    return (directory / "TODO.md").is_file() and (directory / "TODO_ARCHIVE.md").is_file()


def resolve_target_dir(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            raise SystemExit(f"{prog_name()}: directory not found: {explicit}")
        return p
    env_cwd = os.environ.get("TODO_MD_CWD", "").strip()
    if env_cwd:
        return Path(env_cwd).expanduser().resolve()
    return Path.cwd().resolve()


def resolve_workspace_root(base_dir: Path, explicit_dir: str | None = None) -> Path:
    if explicit_dir:
        return base_dir
    env_ws = os.environ.get("TODO_MD_WORKSPACE", "").strip()
    if env_ws:
        p = Path(env_ws).expanduser().resolve()
        if not p.is_dir():
            raise SystemExit(f"{prog_name()}: workspace directory not found: {env_ws}")
        return p
    if is_todo_project(base_dir):
        cur = base_dir
        while cur.parent != cur and is_todo_project(cur.parent):
            cur = cur.parent
        return cur.parent
    return base_dir


def discover_projects(
    workspace_root: Path,
    max_depth: int = WORKSPACE_MAX_DEPTH,
) -> list[tuple[str, Path]]:
    root = workspace_root.resolve()
    if not root.is_dir():
        return []
    found: list[tuple[str, Path]] = []

    def _walk(cur: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(cur.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir() or entry.is_symlink():
                continue
            name = entry.name
            if name.startswith(".") or name in WORKSPACE_SKIP_DIRS:
                continue
            if is_todo_project(entry):
                rel = entry.relative_to(root).as_posix()
                found.append((rel, entry))
            if depth < max_depth:
                _walk(entry, depth + 1)

    _walk(root, 1)
    found.sort(key=lambda item: item[0])
    return found


def resolve_project_dir(
    base_dir: Path,
    project_name: str,
    explicit_dir: str | None = None,
) -> Path:
    norm = project_name.strip().replace("\\", "/").strip("/")
    ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    if not norm or ".." in norm.split("/"):
        raise SystemExit(f"{prog_name()}: invalid project reference {project_name!r}")
    candidate = (ws_root / norm).resolve()
    try:
        candidate.relative_to(ws_root.resolve())
    except ValueError:
        raise SystemExit(f"{prog_name()}: project {project_name!r} escapes workspace {ws_root}")
    if not is_todo_project(candidate):
        raise SystemExit(f"{prog_name()}: project {norm!r} not found under workspace {ws_root}")
    return candidate


def resolve_project_task_ref(
    base_dir: Path,
    ref: str,
    explicit_dir: str | None = None,
) -> tuple[Path, str]:
    m = PROJECT_TASK_RE.match(ref.strip())
    if m:
        proj_name, tid = m.group(1), m.group(2).upper()
        return resolve_project_dir(base_dir, proj_name, explicit_dir=explicit_dir), tid
    return base_dir, ref.strip()


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
        for raw in m.group(1).split(","):
            tok = raw.strip()
            if not tok:
                continue
            pm = PROJECT_TASK_RE.match(tok)
            if pm:
                proj_part = pm.group(1).strip().replace("\\", "/").strip("/")
                norm = f"{proj_part}:{pm.group(2).upper()}"
            elif re.fullmatch(r"[A-Za-z]\d+", tok):
                norm = tok.upper()
            else:
                norm = tok
            if norm not in seen:
                seen.add(norm)
                refs.append(norm)
    return refs


def resolve_dependency_statuses(
    base_dir: Path,
    deps: list[str],
    explicit_dir: str | None = None,
) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    cache: dict[Path, dict[str, str]] = {}

    def _task_statuses(proj_dir: Path) -> dict[str, str]:
        if proj_dir not in cache:
            mapping: dict[str, str] = {}
            for t in collect_all_tasks(proj_dir):
                mapping[str(t["id"]).upper()] = str(t["status"])
            cache[proj_dir] = mapping
        return cache[proj_dir]

    for ref in deps:
        pm = PROJECT_TASK_RE.match(ref)
        if pm:
            proj_name, tid = pm.group(1).strip().replace("\\", "/").strip("/"), pm.group(2).upper()
            target_dir = (ws_root / proj_name).resolve()
            if not is_todo_project(target_dir):
                results.append((ref, "MISSING", "project not found"))
                continue
        else:
            target_dir = base_dir
            tid = ref.upper()
        statuses = _task_statuses(target_dir)
        st = statuses.get(tid)
        if st is None:
            results.append((ref, "MISSING", "task not found"))
        else:
            results.append((ref, st, VALID_STATUSES.get(st, "")))
    return results


def format_dependency_summary(
    base_dir: Path,
    section_text: str,
    explicit_dir: str | None = None,
) -> str | None:
    deps = parse_task_dependencies(section_text)
    if not deps:
        return None
    resolved = resolve_dependency_statuses(base_dir, deps, explicit_dir=explicit_dir)
    parts: list[str] = []
    blocked = False
    for ref, st, emoji in resolved:
        if st == "DONE":
            parts.append(f"{ref} {emoji} [DONE]".replace("  ", " "))
        else:
            blocked = True
            label = f"{emoji} [{st}]".strip() if emoji else f"[{st}]"
            parts.append(f"{ref} {label}")
    state = "blocked" if blocked else "ready"
    return f"Dependencies ({state}): " + ", ".join(parts)


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
    dep_line = format_dependency_summary(base_dir, str(task["section"])) if base_dir else None
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
    return 0


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


def cmd_show(base_dir: Path, task_id: str) -> int:
    target = task_id.strip().upper()
    top = highest_ids_in_use(base_dir)
    for t in collect_all_tasks(base_dir):
        if str(t["id"]).upper() == target:
            dep_line = format_dependency_summary(base_dir, str(t["section"]))
            dep_block = f"\n{dep_line}" if dep_line else ""
            sys.stdout.write(f"# {t['file']}:{t['line']}\n{t['section']}{dep_block}\n\n---\nIDs in use: {format_ids_summary(top)}\n")
            return 0
    sys.stderr.write(f"{prog_name()}: task {target!r} not found in TODO*.md under {base_dir}\n")
    return 1


def _order_active_tasks_for_list(active_tasks: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for t in active_tasks:
        grouped.setdefault(str(t["status"]), []).append(t)
    ordered: list[dict[str, object]] = []
    seen_statuses: set[str] = set()
    for st in sorted(ACTIVE_STATUS_ORDER, key=lambda s: ACTIVE_STATUS_ORDER[s]):
        seen_statuses.add(st)
        bucket = grouped.get(st, [])
        if st in ("QUESTION", "NEW", "HOLD"):
            ordered.extend(reversed(bucket))
        else:
            ordered.extend(bucket)
    for st, bucket in grouped.items():
        if st not in seen_statuses:
            ordered.extend(bucket)
    return ordered


def cmd_list(
    base_dir: Path,
    filt: str | None = None,
    limit: int | None = None,
    full: bool = False,
) -> int:
    mode = (filt or "active").strip().lower()
    tasks = collect_all_tasks(base_dir)
    active_tasks = _order_active_tasks_for_list([t for t in tasks if t["file"] == "TODO.md"])
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

    if limit is not None:
        shown = shown[:limit]

    if not shown:
        sys.stdout.write(f"No matching tasks ({mode}) in {base_dir}\n")
    elif full:
        sections = [str(t["section"]).rstrip() for t in shown]
        sys.stdout.write("\n\n".join(sections) + "\n")
    else:
        for t in shown:
            badge = f"{t['emoji']} [{t['status']}]"
            loc = str(t["file"])
            deps = parse_task_dependencies(str(t["section"]))
            dep_suffix = ""
            if deps:
                resolved = resolve_dependency_statuses(base_dir, deps)
                blocked = [f"{r} ({st})" for r, st, _ in resolved if st != "DONE"]
                dep_suffix = f" [blocked: {', '.join(blocked)}]" if blocked else " [deps: DONE]"
            sys.stdout.write(f"  {str(t['id']):<6}  {badge:<14}  {loc:<16}  {t['title']}{dep_suffix}\n")
    top = highest_ids_in_use(base_dir)
    sys.stdout.write(f"\nIDs in use: {format_ids_summary(top)}\n")
    return 0


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
            for ref in parse_task_dependencies(str(t["section"])):
                pm = PROJECT_TASK_RE.match(ref)
                if pm:
                    proj_name = pm.group(1).strip().replace("\\", "/").strip("/")
                    target_tid = pm.group(2).upper()
                    if not proj_name or ".." in proj_name.split("/"):
                        errors.append(f"TODO.md:{lineno}: task {tid} has invalid dependency reference {ref!r}")
                        continue
                    target_dir = (ws_root / proj_name).resolve()
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

    return errors, len(seen_ids)


def cmd_projects(base_dir: Path, explicit_dir: str | None = None) -> int:
    ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    projects = discover_projects(ws_root)
    if not projects:
        sys.stdout.write(f"No todo_md projects found under {ws_root}\n")
        return 0
    sys.stdout.write(f"Workspace: {ws_root} ({len(projects)} project(s))\n")
    for name, proj_dir in projects:
        active = parse_tasks_in_text(read_if_exists(proj_dir / "TODO.md"), "TODO.md")
        counts: dict[str, int] = {}
        for t in active:
            st = str(t["status"])
            counts[st] = counts.get(st, 0) + 1
        highlights = [f"{st}: {counts[st]}" for st in ("WIP", "NEXT", "QUESTION") if counts.get(st)]
        detail = f" ({', '.join(highlights)})" if highlights else ""
        sys.stdout.write(f"  {name:<26}  {len(active):>3} open{detail}\n")
    return 0


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


def cmd_workspace_list(
    workspace_root: Path,
    filt: str | None = None,
    limit: int | None = None,
    full: bool = False,
) -> int:
    projects = discover_projects(workspace_root)
    if not projects:
        sys.stdout.write(f"No todo_md projects found under {workspace_root}\n")
        return 0
    mode = (filt or "active").strip().lower()
    if mode not in ("active", "open", "archive", "all") and mode.upper() not in VALID_STATUSES:
        raise SystemExit(f"{prog_name()}: unknown list filter {filt!r}; expected active, archive, all, or a status name")
    items: list[tuple[str, Path, dict[str, object]]] = []
    for name, proj_dir in projects:
        tasks = collect_all_tasks(proj_dir)
        active = _order_active_tasks_for_list([t for t in tasks if t["file"] == "TODO.md"])
        arch = [t for t in tasks if t["file"] == "TODO_ARCHIVE.md"]
        if mode in ("active", "open"):
            matched = active
        elif mode == "archive":
            matched = arch
        elif mode == "all":
            matched = active + arch
        else:
            st_up = mode.upper()
            matched = [t for t in (arch if st_up in ("DONE", "CANCELED") else active) if t["status"] == st_up]
        for t in matched:
            items.append((name, proj_dir, t))
    if limit is not None:
        items = items[:limit]
    if not items:
        sys.stdout.write(f"No matching tasks ({mode}) across workspace {workspace_root}\n")
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
    for name, proj_dir, t in items:
        ref = f"{name}:{t['id']}"
        badge = f"{t['emoji']} [{t['status']}]"
        sys.stdout.write(f"  {ref:<28}  {badge:<14}  {t['title']}\n")
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
