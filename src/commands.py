def cmd_check(base_dir: Path) -> int:
    if not (base_dir / "TODO.md").is_file():
        sys.stderr.write(f"{prog_name()}: no TODO.md found in {base_dir} (run '{prog_name()} init' to create one)\n")
        return 1
    errors, count = validate_all(base_dir)
    if errors:
        for e in errors:
            sys.stderr.write(f"ERROR: {e}\n")
        return 1
    sys.stdout.write(f"{prog_name()}: OK ({count} task(s) verified across TODO*.md)\n")
    return 0


def _default_todo_header(base_dir: Path) -> str:
    return ""


def _default_archive_header(base_dir: Path) -> str:
    return ""


def _git_commit_todo(base_dir: Path, commit_msg: str) -> None:
    try:
        r_wt = subprocess.run(
            ["git", "-C", str(base_dir), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return
    if r_wt.returncode != 0 or r_wt.stdout.strip() != "true":
        return
    existing = [f for f in TASK_FILES if (base_dir / f).is_file()]
    if not existing:
        return
    r_add = subprocess.run(
        ["git", "-C", str(base_dir), "add", "--", *existing],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if r_add.returncode != 0:
        return
    r_st = subprocess.run(
        ["git", "-C", str(base_dir), "status", "--porcelain", "--", *existing],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if r_st.returncode != 0 or not r_st.stdout.strip():
        return
    st_lines = r_st.stdout.splitlines()
    changed = [f for f in existing if any(line.endswith(f) for line in st_lines)] or existing
    r_cm = subprocess.run(
        ["git", "-C", str(base_dir), "commit", "--only", "-m", commit_msg, "--", *existing],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if r_cm.returncode != 0:
        return
    r_sha = subprocess.run(
        ["git", "-C", str(base_dir), "rev-parse", "--short", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    sha = f" ({r_sha.stdout.strip()})" if r_sha.returncode == 0 and r_sha.stdout.strip() else ""
    sys.stdout.write(f"{prog_name()}: committed {', '.join(changed)}{sha}: {commit_msg}\n")


def _sort_todo_file(todo_path: Path, promote_id: str | None = None) -> None:
    if not todo_path.is_file():
        return
    raw = todo_path.read_text(encoding="utf-8")
    if not raw.strip():
        return
    tasks = parse_tasks_in_text(raw, "TODO.md")
    if not tasks:
        return
    ordered = _order_active_tasks(
        tasks,
        base_dir=todo_path.parent,
        promote_id=promote_id,
        ready_statuses=frozenset({"WIP", "NEXT"}),
    )
    sections = [str(t["section"]).rstrip() for t in ordered]
    new_text = "\n\n".join(sections) + "\n"
    if new_text != raw:
        todo_path.write_text(new_text, encoding="utf-8")


def _finalize_mutation(
    base_dir: Path,
    commit_msg: str,
    commit: bool = False,
    no_commit: bool = False,
    promote_id: str | None = None,
) -> int:
    _sort_todo_file(base_dir / "TODO.md", promote_id=promote_id)
    errors, _ = validate_all(base_dir)
    if errors:
        for e in errors:
            sys.stderr.write(f"ERROR: {e}\n")
        return 1
    env_commit = os.environ.get("TODO_MD_COMMIT", "").strip().lower() in ("1", "true", "yes")
    env_no_commit = os.environ.get("TODO_MD_NO_COMMIT", "").strip().lower() in ("1", "true", "yes")
    if (commit or env_commit) and not no_commit and not env_no_commit:
        _git_commit_todo(base_dir, commit_msg)
    return 0


def cmd_init(
    base_dir: Path,
    argv: list[str] | None = None,
    force: bool = False,
    commit: bool = False,
    no_commit: bool = False,
) -> int:
    prog = prog_name()
    pos: list[str] = []
    for a in argv or []:
        if a == "--force":
            force = True
        elif a in ("--commit", "-c"):
            commit = True
        elif a == "--no-commit":
            no_commit = True
        elif a.startswith("-"):
            raise SystemExit(f"{prog}: unknown option for init: {a}")
        else:
            pos.append(a)
    idea_text = " ".join(pos).strip() if pos else (_read_stdin_if_piped() or "").strip()
    todo_content = ""
    if idea_text:
        todo_content = f"# 🎯 [NEXT] F1: Project concept and initial design\n\n{idea_text}\n"
    templates = {
        "TODO.md": todo_content,
        "TODO_ARCHIVE.md": "",
    }
    created: list[str] = []
    for fname, content in templates.items():
        p = base_dir / fname
        if p.exists() and not force:
            continue
        p.write_text(content, encoding="utf-8")
        created.append(fname)
    if not created:
        sys.stdout.write(f"{prog}: TODO*.md files already exist in {base_dir} (use --force to overwrite)\n")
        return 0
    sys.stdout.write(f"{prog}: initialized {', '.join(created)} in {base_dir}\n")
    return _finalize_mutation(base_dir, f"Initialize {' and '.join(created)}", commit=commit, no_commit=no_commit)


def _extract_and_remove_task(text: str, target_id: str) -> tuple[dict[str, object] | None, str]:
    lines = text.splitlines()
    in_fence = False
    start_idx: int | None = None
    end_idx: int | None = None
    found_info: dict[str, object] | None = None
    for idx, line in enumerate(lines):
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
        if not in_fence and line.startswith("# "):
            if start_idx is not None:
                end_idx = idx
                break
            m = HEADING_RE.match(line)
            if m and m.group(3).upper() == target_id:
                emoji, status, tid, title = m.groups()
                start_idx = idx
                found_info = {"id": tid, "status": status, "emoji": emoji, "title": title}
    if start_idx is None or found_info is None:
        return None, text
    if end_idx is None:
        end_idx = len(lines)
    section_lines = lines[start_idx:end_idx]
    while section_lines and not section_lines[-1].strip():
        section_lines.pop()
    found_info["lines"] = section_lines
    remaining = lines[:start_idx] + lines[end_idx:]
    new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(remaining).rstrip()) + "\n"
    return found_info, new_text


def _format_heading(status: str, tid: str, title: str, note: str | None = None) -> str:
    emoji = VALID_STATUSES[status]
    base_title, existing_note = _strip_heading_note(title)
    final_note = note.strip() if note is not None else existing_note
    if final_note:
        return f"# {emoji} [{status}] {tid}: {base_title} — *{final_note}*"
    return f"# {emoji} [{status}] {tid}: {base_title}"


def _insert_task_section(file_path: Path, section_lines: list[str], default_header: str = "", prepend: bool = False) -> None:
    if not file_path.is_file() or not file_path.read_text(encoding="utf-8").strip():
        file_path.write_text("\n".join(section_lines) + "\n", encoding="utf-8")
        return
    existing = file_path.read_text(encoding="utf-8")
    if not prepend:
        file_path.write_text(existing.rstrip() + "\n\n" + "\n".join(section_lines) + "\n", encoding="utf-8")
        return
    if file_path.name == "TODO_ARCHIVE.md":
        updated = section_lines + [""] + existing.splitlines()
        new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(updated).rstrip()) + "\n"
        file_path.write_text(new_text, encoding="utf-8")
        return
    lines = existing.splitlines()
    in_fence = False
    insert_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
        if not in_fence and line.startswith("# "):
            m = HEADING_RE.match(line)
            if m and m.group(2) == "WIP":
                continue
            insert_idx = idx
            break
    if insert_idx is None:
        file_path.write_text(existing.rstrip() + "\n\n" + "\n".join(section_lines) + "\n", encoding="utf-8")
        return
    updated = lines[:insert_idx] + section_lines + [""] + lines[insert_idx:]
    new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(updated).rstrip()) + "\n"
    file_path.write_text(new_text, encoding="utf-8")


def _parse_note_arg(rest: list[str]) -> tuple[list[str], str | None]:
    pos: list[str] = []
    note: str | None = None
    i = 0
    while i < len(rest):
        if rest[i] in ("-m", "--note", "--reason"):
            if i + 1 >= len(rest):
                raise SystemExit(f"{prog_name()}: {rest[i]} requires an argument")
            note = rest[i + 1]
            i += 2
        else:
            pos.append(rest[i])
            i += 1
    return pos, note


def cmd_archive_view(base_dir: Path) -> int:
    arch_path = base_dir / "TODO_ARCHIVE.md"
    if not arch_path.is_file():
        sys.stderr.write(f"{prog_name()}: no TODO_ARCHIVE.md found in {base_dir}\n")
        return 1
    sys.stdout.write(read_if_exists(arch_path).rstrip() + "\n")
    return 0


def cmd_transition(
    base_dir: Path,
    task_id: str,
    new_status: str | None = None,
    dest_file: str | None = None,
    note: str | None = None,
    promote_top: bool = False,
    reopen: bool = False,
    require_archived: bool = False,
    commit: bool = False,
    no_commit: bool = False,
) -> int:
    target = task_id.strip().upper()
    if new_status and new_status not in VALID_STATUSES:
        raise SystemExit(f"{prog_name()}: invalid status {new_status!r}; expected one of {', '.join(VALID_STATUSES)}")
    source_file: str | None = None
    found: dict[str, object] | None = None
    updated_source_text = ""
    for fname in TASK_FILES:
        p = base_dir / fname
        if not p.is_file():
            continue
        info, rem = _extract_and_remove_task(read_if_exists(p), target)
        if info is not None:
            source_file = fname
            found = info
            updated_source_text = rem
            break
    if found is None or source_file is None:
        sys.stderr.write(f"{prog_name()}: task {target!r} not found in TODO*.md under {base_dir}\n")
        return 1

    cur_status = str(found["status"])
    is_archived = source_file == "TODO_ARCHIVE.md" or cur_status in ("DONE", "CANCELED")
    final_status = new_status or cur_status
    base_title, existing_note = _strip_heading_note(str(found["title"]))

    if require_archived and not is_archived:
        sys.stderr.write(
            f"{prog_name()}: task {found['id']} is already active ([{cur_status}] in {source_file})\n"
        )
        return 1

    if is_archived:
        note_detail = f" (closing note: {existing_note})" if existing_note else ""
        if final_status in ("DONE", "CANCELED"):
            sys.stderr.write(
                f"{prog_name()}: task {found['id']} is already archived as [{cur_status}]{note_detail}; "
                f"use '{prog_name()} reopen {found['id']}' or pass --reopen with status/next to reopen it\n"
            )
            return 1
        if not reopen:
            sys.stderr.write(
                f"{prog_name()}: task {found['id']} is archived as [{cur_status}]{note_detail}; "
                f"pass --reopen or run '{prog_name()} reopen {found['id']}' to move it back to TODO.md\n"
            )
            return 1

    if dest_file is None:
        if final_status in ("DONE", "CANCELED"):
            dest_file = "TODO_ARCHIVE.md"
        else:
            dest_file = "TODO.md"

    today_iso = date.today().isoformat()
    effective_note = note
    if is_archived and reopen:
        if effective_note is None:
            effective_note = ""
    elif final_status == "DONE":
        if effective_note and today_iso not in effective_note:
            effective_note = f"{today_iso}, {effective_note}"
        elif effective_note is None:
            if not existing_note:
                effective_note = today_iso

    tid = str(found["id"])
    sec_lines = list(found["lines"])  # type: ignore[arg-type]
    sec_lines[0] = _format_heading(final_status, tid, str(found["title"]), note=effective_note)

    if require_archived or (is_archived and reopen):
        commit_msg = f"Reopen task {tid} as {final_status}: {base_title}"
    elif final_status == "DONE":
        commit_msg = f"Complete task {tid}: {base_title}"
    elif final_status == "CANCELED":
        commit_msg = f"Cancel task {tid}: {base_title}"
    elif promote_top and final_status == "NEXT":
        commit_msg = f"Promote task {tid} to NEXT: {base_title}"
    else:
        commit_msg = f"Mark task {tid} as {final_status}: {base_title}"

    if dest_file == source_file and not promote_top:
        src_path = base_dir / source_file
        orig_lines = read_if_exists(src_path).splitlines()
        in_fence = False
        for idx, line in enumerate(orig_lines):
            if line.lstrip().startswith(FENCE):
                in_fence = not in_fence
            if not in_fence and line.startswith("# "):
                m = HEADING_RE.match(line)
                if m and m.group(3).upper() == target:
                    orig_lines[idx] = sec_lines[0]
                    break
        src_path.write_text("\n".join(orig_lines) + "\n", encoding="utf-8")
        sys.stdout.write(f"{prog_name()}: updated {target} -> [{final_status}] in {source_file}\n")
        return _finalize_mutation(base_dir, commit_msg, commit=commit, no_commit=no_commit)

    (base_dir / source_file).write_text(updated_source_text, encoding="utf-8")
    default_hdrs = {
        "TODO.md": _default_todo_header(base_dir),
        "TODO_ARCHIVE.md": _default_archive_header(base_dir),
    }
    _insert_task_section(
        base_dir / dest_file,
        sec_lines,
        default_hdrs[dest_file],
        prepend=(dest_file == "TODO_ARCHIVE.md" or (promote_top and dest_file == "TODO.md")),
    )
    if dest_file == source_file:
        sys.stdout.write(f"{prog_name()}: promoted {target} ([{final_status}]) to top of {dest_file}\n")
    else:
        sys.stdout.write(f"{prog_name()}: moved {target} ([{final_status}]) from {source_file} -> {dest_file}\n")
    rc = _finalize_mutation(
        base_dir,
        commit_msg,
        commit=commit,
        no_commit=no_commit,
        promote_id=(target if promote_top and dest_file == "TODO.md" else None),
    )
    if rc == 0 and final_status == "DONE":
        unblocked = find_newly_unblocked_tasks(base_dir, tid)
        if unblocked:
            sys.stdout.write(f"Unblocked: {', '.join(unblocked)}\n")
    return rc


def cmd_reopen(
    base_dir: Path,
    argv: list[str],
    commit: bool = False,
    no_commit: bool = False,
    explicit_dir: str | None = None,
) -> int:
    prog = prog_name()
    target_status = "NEW"
    note: str | None = None
    pos: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--commit", "-c"):
            commit = True
            i += 1
        elif a == "--no-commit":
            no_commit = True
            i += 1
        elif a in ("--status", "-s"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            target_status = argv[i + 1].upper()
            i += 2
        elif a.startswith("--status="):
            target_status = a.split("=", 1)[1].upper()
            i += 1
        elif a in ("-m", "--note", "--reason"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            note = argv[i + 1]
            i += 2
        elif a.startswith("-"):
            raise SystemExit(f"{prog}: unknown option for reopen: {a}")
        else:
            pos.append(a)
            i += 1

    if len(pos) != 1:
        raise SystemExit(f"{prog}: usage: {prog} reopen <ID> [--status STATUS] [-m NOTE]")
    if target_status not in ACTIVE_STATUS_ORDER:
        raise SystemExit(
            f"{prog}: reopen --status must be an active status ({', '.join(ACTIVE_STATUS_ORDER)}), got {target_status!r}"
        )
    tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
    return cmd_transition(
        tdir,
        tid,
        new_status=target_status,
        dest_file="TODO.md",
        note=note,
        promote_top=(target_status in ("WIP", "NEXT")),
        reopen=True,
        require_archived=True,
        commit=commit,
        no_commit=no_commit,
    )


def _resolve_body_arg(body: str | None) -> str | None:
    if body == "-":
        if sys.stdin.isatty():
            raise SystemExit(f"{prog_name()}: -b - / --body - requires non-TTY stdin")
        return sys.stdin.read()
    if body is None:
        return _read_stdin_if_piped()
    return body


def _normalize_depends_clauses(raw_items: list[str]) -> list[str]:
    clauses: list[str] = []
    for item in raw_items:
        if not item.strip():
            continue
        stages, err = parse_depends_clause(item)
        if err:
            raise SystemExit(
                f"{prog_name()}: invalid --depends value {item!r}: {err}; expected <ID> or <project>:<ID> separated by ',' and '->'"
            )
        clauses.append(" -> ".join(", ".join(stage) for stage in stages))
    return clauses


def _normalize_role_arg(raw_role: str) -> str:
    role = raw_role.strip()
    if "\n" in role or "\r" in role:
        raise SystemExit(f"{prog_name()}: --role value must be a single line")
    return role


def _apply_role_to_body_lines(lines: list[str], role: str | None) -> list[str]:
    if role is None:
        return lines
    filtered: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
        if not in_fence and ROLE_LINE_RE.match(line):
            continue
        filtered.append(line)
    while filtered and not filtered[0].strip():
        filtered.pop(0)
    while filtered and not filtered[-1].strip():
        filtered.pop()
    if not role:
        return filtered
    role_line = f"- Role: {role}"
    return [role_line, *filtered] if filtered else [role_line]


def _apply_depends_to_body_lines(lines: list[str], depends_clauses: list[str] | None) -> list[str]:
    if depends_clauses is None:
        return lines
    filtered: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
        if not in_fence and (DEPENDS_LINE_RE.match(line) or EMPTY_DEPENDS_LINE_RE.match(line)):
            continue
        filtered.append(line)
    while filtered and not filtered[0].strip():
        filtered.pop(0)
    while filtered and not filtered[-1].strip():
        filtered.pop()
    if not depends_clauses:
        return filtered
    dep_lines = [f"- Depends on: {clause}" for clause in depends_clauses]
    return [*dep_lines, *filtered] if filtered else dep_lines


def cmd_add(
    base_dir: Path,
    argv: list[str],
    commit: bool = False,
    no_commit: bool = False,
    explicit_dir: str | None = None,
) -> int:
    prog = prog_name()
    status = "NEW"
    prepend = False
    prefix: str | None = None
    note: str | None = None
    body: str | None = None
    role: str | None = None
    depends_raw: list[str] = []
    pos: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--commit", "-c"):
            commit = True
            i += 1
        elif a == "--no-commit":
            no_commit = True
            i += 1
        elif a in ("--next", "-n", "--top"):
            status = "NEXT"
            prepend = True
            i += 1
        elif a in ("-p", "--prefix"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            prefix = argv[i + 1].strip().upper()
            if not re.fullmatch(r"[A-Z]", prefix):
                raise SystemExit(f"{prog}: invalid ID prefix {argv[i + 1]!r}; expected a single letter A-Z")
            i += 2
        elif a in ("--status", "-s"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            status = argv[i + 1].upper()
            if status in ("WIP", "NEXT"):
                prepend = True
            i += 2
        elif a in ("-m", "--note", "--reason"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            note = argv[i + 1]
            i += 2
        elif a in ("-b", "--body"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            body = argv[i + 1]
            i += 2
        elif a == "--role":
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            role = _normalize_role_arg(argv[i + 1])
            i += 2
        elif a in ("--depends", "-d"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            depends_raw.append(argv[i + 1])
            i += 2
        elif a.startswith("-"):
            raise SystemExit(f"{prog}: unknown option for add: {a}")
        else:
            pos.append(a)
            i += 1

    if status not in ("WIP", "NEXT", "NEW", "HOLD", "QUESTION"):
        raise SystemExit(f"{prog}: add status must be WIP, NEXT, NEW, HOLD, or QUESTION (got {status!r})")

    if len(pos) >= 2 and not re.fullmatch(r"[A-Za-z](?:\d+)?", pos[0].strip()):
        cand_proj = pos[0].strip().replace("\\", "/").strip("/")
        ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
        cand_dir = (ws_root / cand_proj).resolve()
        if cand_proj and ".." not in cand_proj.split("/") and is_todo_project(cand_dir):
            base_dir = cand_dir
            pos = pos[1:]

    if len(pos) == 1:
        tid = next_free_id(base_dir, prefix or "F")
        title = pos[0].strip()
    elif len(pos) == 2 and prefix is None:
        first, second = pos[0].strip(), pos[1].strip()
        if re.fullmatch(r"[A-Za-z]", first):
            tid = next_free_id(base_dir, first.upper())
            title = second
        elif re.fullmatch(r"[A-Za-z]\d+", first):
            tid = next_free_id(base_dir, first[0].upper())
            title = second
            if first.upper() != tid:
                sys.stderr.write(
                    f"{prog}: note: ignoring explicit ID {first.upper()}; auto-assigned {tid}\n"
                )
        else:
            raise SystemExit(f"{prog}: invalid ID prefix {first!r}; expected a single letter A-Z (e.g. F, B, P)")
    else:
        raise SystemExit(
            f"{prog}: usage: {prog} add [<PREFIX>] <TITLE> [-p PREFIX] [--next] [--status STATUS] [-m NOTE] [-b BODY] [--role ROLE]"
        )

    if not title:
        raise SystemExit(f"{prog}: task title cannot be empty")

    body = _resolve_body_arg(body)
    depends_clauses = _normalize_depends_clauses(depends_raw) if depends_raw else None
    body_lines = body.strip().splitlines() if body and body.strip() else []
    body_lines = _apply_depends_to_body_lines(body_lines, depends_clauses)
    body_lines = _apply_role_to_body_lines(body_lines, role)

    heading = _format_heading(status, tid, title, note=note)
    sec_lines = [heading]
    if body_lines:
        sec_lines.extend(["", *body_lines])

    _insert_task_section(base_dir / "TODO.md", sec_lines, _default_todo_header(base_dir), prepend=prepend)
    sys.stdout.write(f"{prog}: added {tid} ([{status}]) to TODO.md\n")
    base_title, _ = _strip_heading_note(title)
    return _finalize_mutation(
        base_dir,
        f"Add task {tid}: {base_title}",
        commit=commit,
        no_commit=no_commit,
        promote_id=(tid if prepend else None),
    )


def cmd_edit(
    base_dir: Path,
    argv: list[str],
    commit: bool = False,
    no_commit: bool = False,
    explicit_dir: str | None = None,
) -> int:
    prog = prog_name()
    new_title: str | None = None
    note: str | None = None
    clear_note = False
    body: str | None = None
    role: str | None = None
    depends_raw: list[str] | None = None
    pos: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--commit", "-c"):
            commit = True
            i += 1
        elif a == "--no-commit":
            no_commit = True
            i += 1
        elif a in ("-t", "--title"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            new_title = argv[i + 1]
            i += 2
        elif a in ("-m", "--note", "--reason"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            note = argv[i + 1]
            if note == "":
                clear_note = True
            i += 2
        elif a in ("-b", "--body"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            body = argv[i + 1]
            i += 2
        elif a == "--role":
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            role = _normalize_role_arg(argv[i + 1])
            i += 2
        elif a in ("--depends", "-d"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            if depends_raw is None:
                depends_raw = []
            depends_raw.append(argv[i + 1])
            i += 2
        elif a.startswith("-"):
            raise SystemExit(f"{prog}: unknown option for edit: {a}")
        else:
            pos.append(a)
            i += 1

    if len(pos) != 1:
        raise SystemExit(f"{prog}: usage: {prog} edit <ID> [-t TITLE] [-m NOTE] [-b BODY] [--role ROLE] [--depends SPEC]")
    base_dir, resolved_id = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
    target = resolved_id.upper()
    body = _resolve_body_arg(body)
    depends_clauses = _normalize_depends_clauses(depends_raw) if depends_raw is not None else None

    if new_title is None and note is None and body is None and depends_clauses is None and role is None:
        raise SystemExit(f"{prog}: edit requires at least one of -t TITLE, -m NOTE, -b BODY, --role ROLE, --depends, or stdin")

    for fname in TASK_FILES:
        p = base_dir / fname
        if not p.is_file():
            continue
        lines = read_if_exists(p).splitlines()
        in_fence = False
        start_idx: int | None = None
        end_idx: int | None = None
        matched_groups: tuple[str, str, str, str] | None = None
        for idx, line in enumerate(lines):
            if line.lstrip().startswith(FENCE):
                in_fence = not in_fence
            if not in_fence and line.startswith("# "):
                if start_idx is not None:
                    end_idx = idx
                    break
                m = HEADING_RE.match(line)
                if m and m.group(3).upper() == target:
                    start_idx = idx
                    matched_groups = (m.group(1), m.group(2), m.group(3), m.group(4))
        if start_idx is None or matched_groups is None:
            continue
        if end_idx is None:
            end_idx = len(lines)
        _, status, tid, old_full_title = matched_groups
        base_title, old_note = _strip_heading_note(old_full_title)
        final_title = new_title.strip() if new_title is not None else base_title
        final_note = None if clear_note else (note if note is not None else old_note)
        heading = _format_heading(status, tid, final_title, note=final_note)

        if body is not None:
            body_lines = body.strip().splitlines() if body.strip() else []
            body_lines = _apply_depends_to_body_lines(body_lines, depends_clauses)
            body_lines = _apply_role_to_body_lines(body_lines, role)
            new_sec = [heading]
            if body_lines:
                new_sec.extend(["", *body_lines])
            new_sec.append("")
        else:
            old_sec = lines[start_idx:end_idx]
            if depends_clauses is not None or role is not None:
                body_lines = _apply_depends_to_body_lines(old_sec[1:], depends_clauses)
                body_lines = _apply_role_to_body_lines(body_lines, role)
                new_sec = [heading, *(["", *body_lines] if body_lines else []), ""]
            else:
                old_sec[0] = heading
                new_sec = old_sec

        updated_lines = lines[:start_idx] + new_sec + lines[end_idx:]
        new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(updated_lines).rstrip()) + "\n"
        p.write_text(new_text, encoding="utf-8")
        sys.stdout.write(f"{prog}: updated task {tid} in {fname}\n")
        return _finalize_mutation(base_dir, f"Update task {tid}: {final_title}", commit=commit, no_commit=no_commit)

    sys.stderr.write(f"{prog}: task {target!r} not found in TODO*.md under {base_dir}\n")
    return 1


def cmd_append(base_dir: Path, argv: list[str], commit: bool = False, no_commit: bool = False) -> int:
    prog = prog_name()
    body: str | None = None
    pos: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--commit", "-c"):
            commit = True
            i += 1
        elif a == "--no-commit":
            no_commit = True
            i += 1
        elif a in ("-b", "--body", "-m", "--note"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an argument")
            body = argv[i + 1]
            i += 2
        elif a.startswith("-"):
            raise SystemExit(f"{prog}: unknown option for append: {a}")
        else:
            pos.append(a)
            i += 1

    if len(pos) != 1:
        raise SystemExit(f"{prog}: usage: {prog} append <ID> [-b TEXT]")
    target = pos[0].strip().upper()
    body = _resolve_body_arg(body)
    if not body or not body.strip():
        raise SystemExit(f"{prog}: append requires non-empty text via -b TEXT or stdin")

    for fname in TASK_FILES:
        p = base_dir / fname
        if not p.is_file():
            continue
        lines = read_if_exists(p).splitlines()
        in_fence = False
        start_idx: int | None = None
        end_idx: int | None = None
        matched_title = ""
        for idx, line in enumerate(lines):
            if line.lstrip().startswith(FENCE):
                in_fence = not in_fence
            if not in_fence and line.startswith("# "):
                if start_idx is not None:
                    end_idx = idx
                    break
                m = HEADING_RE.match(line)
                if m and m.group(3).upper() == target:
                    start_idx = idx
                    matched_title = m.group(4)
        if start_idx is None:
            continue
        if end_idx is None:
            end_idx = len(lines)
        sec_lines = lines[start_idx:end_idx]
        while sec_lines and not sec_lines[-1].strip():
            sec_lines.pop()
        sec_lines.extend(["", body.strip(), ""])
        updated_lines = lines[:start_idx] + sec_lines + lines[end_idx:]
        new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(updated_lines).rstrip()) + "\n"
        p.write_text(new_text, encoding="utf-8")
        sys.stdout.write(f"{prog}: appended to {target} in {fname}\n")
        base_title, _ = _strip_heading_note(matched_title)
        return _finalize_mutation(base_dir, f"Append to task {target}: {base_title}", commit=commit, no_commit=no_commit)

    sys.stderr.write(f"{prog}: task {target!r} not found in TODO*.md under {base_dir}\n")
    return 1


def resolve_top_task_id(base_dir: Path) -> str | None:
    todo_path = base_dir / "TODO.md"
    if not todo_path.is_file():
        return None
    active_tasks = parse_tasks_in_text(read_if_exists(todo_path), "TODO.md")
    for wanted in ("WIP", "NEXT"):
        for t in active_tasks:
            if str(t["status"]) == wanted:
                return str(t["id"]).upper()
    return None


def cmd_queue(
    base_dir: Path,
    target_dir: Path,
    task_id: str,
    show_all: bool = False,
    explicit_dir: str | None = None,
) -> int:
    dag = build_dependency_dag(
        base_dir,
        target_dir,
        task_id,
        explicit_dir=explicit_dir,
        stop_at_done=True,
    )
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    topo_order: list[tuple[Path, str]] = dag["topo_order"]  # type: ignore[assignment]
    root_key: tuple[Path, str] = dag["root"]  # type: ignore[assignment]
    root_node = nodes[root_key]
    if not root_node["exists"]:
        sys.stderr.write(f"{prog_name()}: task {root_node['ref']!r} not found in TODO*.md under {target_dir}\n")
        return 1
    syntax_errors: list[str] = dag["syntax_errors"]  # type: ignore[assignment]
    if syntax_errors:
        for e in syntax_errors:
            sys.stderr.write(f"ERROR: {e}\n")
        return 1
    cycle: list[str] = dag["cycle"]  # type: ignore[assignment]
    if cycle:
        sys.stderr.write(f"ERROR: dependency cycle detected: {' -> '.join(cycle)}\n")
        return 1

    shown = topo_order if show_all else [u for u in topo_order if str(nodes[u]["status"]) != "DONE"]
    if not shown:
        sys.stdout.write(f"No pending tasks in queue for {root_node['ref']} (all tasks DONE)\n")
    else:
        term_width = _get_terminal_columns()
        for idx, u in enumerate(shown, start=1):
            nd = nodes[u]
            st = str(nd["status"])
            ref = str(nd["ref"])
            title = str(nd["title"])
            if st == "MISSING":
                badge = "[MISSING]"
                marker = "[blocked]"
            elif st == "CANCELED":
                badge = f"{nd['emoji']} [CANCELED]"
                marker = "[blocked]"
            elif st == "DONE":
                badge = f"{nd['emoji']} [DONE]"
                marker = ""
            else:
                badge = f"{nd['emoji']} [{st}]"
                blockers = [str(nodes[p]["ref"]) for p in prereqs[u] if str(nodes[p]["status"]) != "DONE"]
                marker = f"[blocked by: {', '.join(blockers)}]" if blockers else "[ready]"
            desc = f"{title}  {marker}" if marker else title
            prefix = f"  {idx:>2}. {_pad_display(ref, 20)}  {_pad_display(badge, 14)}  "
            sys.stdout.write(_wrap_table_row(prefix, desc, term_width) + "\n")

    next_act = _first_actionable_in_dag(dag)
    sys.stdout.write(f"Next actionable: {next_act or 'none'}\n")
    return 0


def cmd_next_id(
    base_dir: Path,
    target_dir: Path | None = None,
    task_id: str | None = None,
    explicit_dir: str | None = None,
) -> int:
    if task_id is None:
        tid = resolve_top_task_id(base_dir)
        if not tid:
            sys.stderr.write(f"{prog_name()}: no active WIP or NEXT task found in TODO.md under {base_dir}\n")
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
    next_act = _first_actionable_in_dag(dag)
    if not next_act:
        sys.stderr.write(f"{prog_name()}: no unblocked actionable task found for {root_node['ref']}\n")
        return 1
    sys.stdout.write(f"{next_act}\n")
    return 0


def extract_task_files(base_dir: Path, section_text: str) -> list[str]:
    repo_root = base_dir.resolve()
    found: list[str] = []
    seen: set[str] = set()
    in_fence = False
    for line in section_text.splitlines():
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for raw in BACKTICK_TOKEN_RE.findall(line):
            cand = raw.strip()
            if not cand or any(ch.isspace() for ch in cand) or "://" in cand:
                continue
            if cand.startswith("-") or any(ch in cand for ch in "<>*?{}"):
                continue
            cand = re.sub(r"(?::\d+(?::\d+)?|#L\d+(?:-L\d+)?)$", "", cand)
            if not cand:
                continue
            p_cand = Path(cand)
            target = p_cand.resolve() if p_cand.is_absolute() else (repo_root / cand).resolve()
            try:
                rel_posix = target.relative_to(repo_root).as_posix()
            except ValueError:
                continue
            if rel_posix == "." or not target.is_file():
                continue
            if rel_posix not in seen:
                seen.add(rel_posix)
                found.append(rel_posix)
    return found


def cmd_files(
    base_dir: Path,
    task_id: str | None = None,
    max_lines: int | None = None,
    max_total_lines: int | None = None,
    max_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> int:
    target = task_id.strip().upper() if task_id else resolve_top_task_id(base_dir)
    if not target:
        sys.stderr.write(f"{prog_name()}: no active WIP or NEXT task found in TODO.md under {base_dir}\n")
        return 1
    has_budget = any(
        cap is not None for cap in (max_lines, max_total_lines, max_bytes, max_total_bytes)
    )
    need_lines = max_lines is not None or max_total_lines is not None
    repo_root = base_dir.resolve()
    total_lines = 0
    total_bytes = 0
    for t in collect_all_tasks(base_dir):
        if str(t["id"]).upper() == target:
            for rel_path in extract_task_files(base_dir, str(t["section"])):
                if has_budget:
                    raw = (repo_root / rel_path).read_bytes()
                    n_bytes = len(raw)
                    if max_bytes is not None and n_bytes > max_bytes:
                        continue
                    if max_total_bytes is not None and total_bytes + n_bytes > max_total_bytes:
                        continue
                    n_lines = len(raw.splitlines()) if need_lines else 0
                    if max_lines is not None and n_lines > max_lines:
                        continue
                    if max_total_lines is not None and total_lines + n_lines > max_total_lines:
                        continue
                    total_bytes += n_bytes
                    total_lines += n_lines
                sys.stdout.write(f"{rel_path}\n")
            return 0
    sys.stderr.write(f"{prog_name()}: task {target!r} not found in TODO*.md under {base_dir}\n")
    return 1


def cmd_chain(
    base_dir: Path,
    limit: int | None = None,
    include_hold: bool = False,
    ready: bool = False,
    role: str | None = None,
    by_role: bool = False,
    workspace: bool = False,
    explicit_dir: str | None = None,
) -> int:
    if workspace:
        ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
        if not discover_projects(ws_root):
            sys.stdout.write(f"No todo_md projects found under {ws_root}\n")
            return 0
    elif not (base_dir / "TODO.md").is_file():
        sys.stderr.write(f"{prog_name()}: no TODO.md found in {base_dir} (run '{prog_name()} init' to create one)\n")
        return 1

    dag = build_execution_chain_dag(
        base_dir,
        workspace=workspace,
        explicit_dir=explicit_dir,
    )
    syntax_errors: list[str] = dag["syntax_errors"]  # type: ignore[assignment]
    if syntax_errors:
        for e in syntax_errors:
            sys.stderr.write(f"ERROR: {e}\n")
        return 1
    cycle: list[str] = dag["cycle"]  # type: ignore[assignment]
    if cycle:
        sys.stderr.write(f"ERROR: dependency cycle detected: {' -> '.join(cycle)}\n")
        return 1

    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    done_prereqs: dict[tuple[Path, str], list[str]] = dag.get("done_prereqs", {})  # type: ignore[assignment]
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["dependents"]  # type: ignore[assignment]
    topo_order: list[tuple[Path, str]] = dag["topo_order"]  # type: ignore[assignment]

    if not topo_order:
        scope_msg = "across workspace projects" if workspace else "in TODO.md"
        sys.stdout.write(f"No open tasks {scope_msg}\n")
        return 0

    if by_role:
        plan = plan_execution_chains_by_role(
            dag,
            include_hold=include_hold,
            ready_only=ready,
            limit=limit,
            role=role,
        )
    else:
        plan = plan_execution_chains(
            dag,
            include_hold=include_hold,
            ready_only=ready,
            limit=(None if role is not None else limit),
        )
    active_nodes: list[tuple[Path, str]] = plan["active_nodes"]  # type: ignore[assignment]
    active_unblocks: dict[tuple[Path, str], int] = plan["active_unblocks"]  # type: ignore[assignment]
    excluded_hold: set[tuple[Path, str]] = plan["excluded_hold"]  # type: ignore[assignment]
    finale_set: set[tuple[Path, str]] = plan.get("finale_set", set())  # type: ignore[assignment]

    active_set = set(active_nodes)
    had_blocker_error = False
    for u in active_nodes:
        st = str(nodes[u]["status"])
        if st in ("MISSING", "CANCELED"):
            had_blocker_error = True
            blocked_refs = [str(nodes[v]["ref"]) for v in dependents.get(u, []) if v in active_set]
            if blocked_refs:
                sys.stderr.write(
                    f"ERROR: unresolved blocker {nodes[u]['ref']} ({st}) blocks {', '.join(blocked_refs)}\n"
                )
            else:
                sys.stderr.write(f"ERROR: unresolved blocker {nodes[u]['ref']} ({st})\n")

    term_width = _get_terminal_columns()
    wanted_role = role.strip().lower() if role is not None else None
    rank_pos = {node: idx for idx, node in enumerate(active_nodes)}

    def _matches_role(u: tuple[Path, str]) -> bool:
        if wanted_role is None:
            return True
        nd = nodes[u]
        return bool(nd.get("exists")) and _task_matches_role(nd, wanted_role)

    def _format_row(idx: int, u: tuple[Path, str], show_downstream: bool = False) -> str:
        nd = nodes[u]
        st = str(nd["status"])
        ref = str(nd["ref"])
        title = str(nd["title"])
        blockers = [str(nodes[p]["ref"]) for p in prereqs[u] if str(nodes[p]["status"]) != "DONE"]
        role_badge = _task_role_badge(nd) if nd.get("exists") else ""
        impact = active_unblocks.get(u, 0)
        if st == "MISSING":
            badge = "[MISSING]"
            status_tag = "[blocked]" + (f" [unblocks {impact}]" if impact > 0 else "")
        elif st == "CANCELED":
            badge = f"{nd['emoji']} [CANCELED]"
            status_tag = "[blocked]" + (f" [unblocks {impact}]" if impact > 0 else "")
        else:
            emoji = "⏳" if (st in ("WIP", "NEXT") and blockers) else str(nd["emoji"])
            badge = f"{emoji} [{st}]"
            if blockers:
                status_tag = f"[blocked by: {', '.join(blockers)}]" + (
                    f" [unblocks {impact}]" if impact > 0 else ""
                )
            elif u in finale_set:
                done_refs = done_prereqs.get(u, [])
                shown_done = list(done_refs[:3])
                if len(done_refs) > 3:
                    shown_done.append("...")
                status_tag = f"[ready | after: {', '.join(shown_done)}]"
            elif show_downstream and impact > 0:
                next_nodes = sorted(
                    [v for v in dependents.get(u, []) if v in active_set],
                    key=lambda v: rank_pos.get(v, len(active_nodes)),
                )
                if next_nodes:
                    shown_refs = [str(nodes[v]["ref"]) for v in next_nodes[:3]]
                    if len(next_nodes) > 3:
                        shown_refs.append("...")
                    status_tag = f"[ready | unblocks {impact} -> {', '.join(shown_refs)}]"
                else:
                    status_tag = f"[ready | unblocks {impact}]"
            else:
                status_tag = "[ready]" + (f" [unblocks {impact}]" if impact > 0 else "")
        prefix = (
            f"  {idx:>2}. {_pad_display(ref, 20)}  "
            f"{_pad_display(badge, 14)}  "
            f"{_pad_display(role_badge, 10)}  "
        )
        desc = f"{title}  {status_tag}"
        return _wrap_table_row(prefix, desc, term_width) + "\n"

    if by_role:
        queues: list[tuple[str, str, list[tuple[Path, str]]]] = plan["queues"]  # type: ignore[assignment]
        non_empty_queues = [(q_label, q_items) for _, q_label, q_items in queues if q_items]
        matching_held = [u for u in excluded_hold if _matches_role(u)]
        if non_empty_queues:
            row_idx = 1
            for sec_idx, (q_label, q_items) in enumerate(non_empty_queues):
                if sec_idx > 0:
                    sys.stdout.write("\n")
                sys.stdout.write(f"{q_label}:\n")
                for u in q_items:
                    sys.stdout.write(_format_row(row_idx, u))
                    row_idx += 1
        elif matching_held:
            role_note = f" matching role={role.strip()}" if role is not None else ""
            sys.stdout.write(
                f"Queues: (none{role_note} — {len(matching_held)} held task(s); pass --include-hold to include)\n"
            )
        elif role is not None:
            sys.stdout.write(f"Queues: (none matching role={role.strip()})\n")
        else:
            sys.stdout.write("Queues: (none)\n")
    elif ready:
        ready_tasks: list[tuple[Path, str]] = plan["ready_tasks"]  # type: ignore[assignment]
        if wanted_role is not None:
            ready_tasks = [u for u in ready_tasks if _matches_role(u)]
            if limit is not None:
                ready_tasks = ready_tasks[:limit]
        matching_held = [u for u in excluded_hold if _matches_role(u)]
        if ready_tasks:
            sys.stdout.write("Ready tasks:\n")
            for idx, u in enumerate(ready_tasks, start=1):
                sys.stdout.write(_format_row(idx, u, show_downstream=True))
        elif matching_held:
            role_note = f" matching role={role.strip()}" if role is not None else ""
            sys.stdout.write(
                f"Ready tasks: (none{role_note} — {len(matching_held)} held task(s); pass --include-hold to include)\n"
            )
        elif role is not None:
            sys.stdout.write(f"Ready tasks: (none matching role={role.strip()})\n")
        else:
            sys.stdout.write("Ready tasks: (none)\n")
    else:
        finales: list[tuple[Path, str]] = plan.get("finales", [])  # type: ignore[assignment]
        chains: list[list[tuple[Path, str]]] = plan["chains"]  # type: ignore[assignment]
        standalone: list[tuple[Path, str]] = plan["standalone"]  # type: ignore[assignment]
        if wanted_role is not None:
            finales = [u for u in finales if _matches_role(u)]
            chains = [[u for u in comp if _matches_role(u)] for comp in chains]
            chains = [comp for comp in chains if comp]
            standalone = [u for u in standalone if _matches_role(u)]
            if limit is not None:
                rem = limit
                finales = finales[:rem] if rem > 0 else []
                rem -= len(finales)
                limited_chains: list[list[tuple[Path, str]]] = []
                for comp in chains:
                    if rem <= 0:
                        break
                    take = comp[:rem]
                    limited_chains.append(take)
                    rem -= len(take)
                standalone = standalone[:rem] if rem > 0 else []
                chains = limited_chains
        matching_held = [u for u in excluded_hold if _matches_role(u)]
        if finales or chains or standalone:
            row_idx = 1
            wrote_section = False
            if finales:
                sys.stdout.write("Chain finales:\n")
                for u in finales:
                    sys.stdout.write(_format_row(row_idx, u))
                    row_idx += 1
                wrote_section = True
            for comp in chains:
                if wrote_section:
                    sys.stdout.write("\n")
                chain_str = " -> ".join(str(nodes[u]["ref"]) for u in comp)
                sys.stdout.write(f"Chain: {chain_str}\n")
                for u in comp:
                    sys.stdout.write(_format_row(row_idx, u))
                    row_idx += 1
                wrote_section = True
            if standalone:
                if wrote_section:
                    sys.stdout.write("\n")
                sys.stdout.write("Standalone tasks:\n")
                for u in standalone:
                    sys.stdout.write(_format_row(row_idx, u))
                    row_idx += 1
        elif matching_held:
            role_note = f" matching role={role.strip()}" if role is not None else ""
            sys.stdout.write(
                f"Chain: (none{role_note} — {len(matching_held)} held task(s); pass --include-hold to include)\n"
            )
        elif role is not None:
            sys.stdout.write(f"Chain: (none matching role={role.strip()})\n")
        else:
            sys.stdout.write("Chain: (none)\n")

    if excluded_hold:
        held_in_deg = {u: sum(1 for p in prereqs[u] if p in excluded_hold) for u in excluded_hold}
        held_deps = {u: [v for v in dependents.get(u, []) if v in excluded_hold] for u in excluded_hold}
        branch_roots = [u for u in topo_order if u in excluded_hold and held_in_deg[u] == 0]
        held_paths: list[list[tuple[Path, str]]] = []

        def _collect_held_paths(u: tuple[Path, str], path: list[tuple[Path, str]]) -> None:
            if len(held_paths) >= 64:
                return
            nxts = held_deps[u]
            if not nxts:
                held_paths.append(path)
                return
            for v in nxts:
                _collect_held_paths(v, [*path, v])

        for r in branch_roots:
            _collect_held_paths(r, [r])

        if wanted_role is not None:
            held_paths = [path for path in held_paths if any(_matches_role(k) for k in path)]

        if held_paths:
            sys.stdout.write("\nHeld branches:\n")
            for path in held_paths:
                rendered = " -> ".join(f"{nodes[k]['ref']} ({nodes[k]['status']})" for k in path)
                sys.stdout.write(f"  {rendered}\n")

    return 1 if had_blocker_error else 0
