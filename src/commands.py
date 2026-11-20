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
    stripped_plan_role = False
    if final_status == "NEXT":
        sec_lines, stripped_plan_role = _strip_plan_role_from_section_lines(sec_lines)

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
        start_idx: int | None = None
        end_idx: int | None = None
        for idx, line in enumerate(orig_lines):
            if line.lstrip().startswith(FENCE):
                in_fence = not in_fence
            if not in_fence and line.startswith("# "):
                if start_idx is not None:
                    end_idx = idx
                    break
                m = HEADING_RE.match(line)
                if m and m.group(3).upper() == target:
                    start_idx = idx
                    if not stripped_plan_role:
                        orig_lines[idx] = sec_lines[0]
                        break
        if stripped_plan_role and start_idx is not None:
            if end_idx is None:
                end_idx = len(orig_lines)
            orig_lines = orig_lines[:start_idx] + [*sec_lines, ""] + orig_lines[end_idx:]
            new_src_text = re.sub(r"\n{3,}", "\n\n", "\n".join(orig_lines).rstrip()) + "\n"
            src_path.write_text(new_src_text, encoding="utf-8")
        else:
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


def _strip_plan_role_from_section_lines(sec_lines: list[str]) -> tuple[list[str], bool]:
    if not sec_lines:
        return sec_lines, False
    heading = sec_lines[0]
    body_lines: list[str] = []
    in_fence = False
    removed = False
    for line in sec_lines[1:]:
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
        if not in_fence:
            m = ROLE_LINE_RE.match(line)
            if m and m.group(1).strip().lower() == "plan":
                removed = True
                continue
        body_lines.append(line)
    if not removed:
        return sec_lines, False
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    if not body_lines:
        return [heading], True
    return [heading, "", *body_lines], True


def _normalize_role_arg(raw_role: str, allow_empty: bool = False) -> str:
    if "\n" in raw_role or "\r" in raw_role:
        raise SystemExit(f"{prog_name()}: --role value must be a single line")
    stripped = raw_role.strip()
    if not stripped:
        if allow_empty:
            return ""
        raise SystemExit(f"{prog_name()}: --role requires a non-empty role name")
    role = stripped.lower()
    if role in RETIRED_ROLES:
        replacement = RETIRED_ROLES[role]
        raise SystemExit(
            f"{prog_name()}: retired --role value {stripped!r}; use {replacement!r} instead"
        )
    if not ROLE_NAME_RE.match(role):
        raise SystemExit(
            f"{prog_name()}: invalid --role value {stripped!r}; "
            "expected lowercase role identifier matching ^[a-z][a-z0-9_-]*$"
        )
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
        elif a.startswith("--role="):
            role = _normalize_role_arg(a.split("=", 1)[1])
            i += 1
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
            role = _normalize_role_arg(argv[i + 1], allow_empty=True)
            i += 2
        elif a.startswith("--role="):
            role = _normalize_role_arg(a.split("=", 1)[1], allow_empty=True)
            i += 1
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


def resolve_top_task_id(
    base_dir: Path,
    role: str | None = None,
    explicit_dir: str | None = None,
) -> str | None:
    todo_path = base_dir / "TODO.md"
    if not todo_path.is_file():
        return None
    active_tasks = parse_tasks_in_text(read_if_exists(todo_path), "TODO.md")
    wanted_role = role.strip().lower() if role is not None else None
    for wanted in ("WIP", "NEXT"):
        for t in active_tasks:
            if str(t["status"]) != wanted:
                continue
            if wanted_role is not None and not _task_matches_role(t, wanted_role):
                continue
            if _is_task_blocked(base_dir, t, explicit_dir=explicit_dir):
                continue
            return str(t["id"]).upper()
    return None


def cmd_next_id(
    base_dir: Path,
    target_dir: Path | None = None,
    task_id: str | None = None,
    explicit_dir: str | None = None,
    role: str | None = None,
) -> int:
    if task_id is None:
        tid = resolve_top_task_id(base_dir, role=role, explicit_dir=explicit_dir)
        if not tid:
            role_note = f" (role={role.strip()})" if role is not None else ""
            sys.stderr.write(
                f"{prog_name()}: no active WIP or NEXT task{role_note} found in TODO.md under {base_dir}\n"
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
    next_act = _first_actionable_in_dag(dag, role=role)
    if not next_act:
        role_note = f" (role={role.strip()})" if role is not None else ""
        sys.stderr.write(
            f"{prog_name()}: no unblocked actionable task{role_note} found for {root_node['ref']}\n"
        )
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
    include_done: bool = False,
    ready: bool = False,
    role: str | None = None,
    by_role: bool = False,
    workspace: bool = False,
    explicit_dir: str | None = None,
    targets: list[tuple[Path, str]] | None = None,
    tree: bool = False,
    numbered: str | None = None,
    focus: list[tuple[Path, str]] | None = None,
    status: frozenset[str] | None = None,
) -> int:
    b_res = base_dir.resolve()
    row_scoped = status is not None or bool(focus)
    ws_root = resolve_workspace_root(b_res, explicit_dir=explicit_dir)
    is_orch = (not workspace) and is_orchestrator_project(b_res, ws_root, explicit_dir=explicit_dir)
    if workspace:
        if not resolve_workspace_chain_projects(b_res, ws_root):
            sys.stdout.write(f"No todo_md projects found under {ws_root}\n")
            return 0
    elif is_orch:
        if not read_configured_todo_projects(b_res, ws_root, include_env=True) and not (b_res / "TODO.md").is_file():
            sys.stdout.write(f"No todo_md projects found under {ws_root}\n")
            return 0
    elif not (b_res / "TODO.md").is_file():
        sys.stderr.write(f"{prog_name()}: no TODO.md found in {base_dir} (run '{prog_name()} init' to create one)\n")
        return 1

    dag = build_execution_chain_dag(
        base_dir,
        workspace=workspace,
        explicit_dir=explicit_dir,
        include_done=include_done,
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
    done_nodes: dict[tuple[Path, str], set[tuple[Path, str]]] = dag.get("done_nodes", {})  # type: ignore[assignment]
    direct_done_deps: dict[tuple[Path, str], list[tuple[Path, str]]] = dag.get("direct_done_deps", {})  # type: ignore[assignment]
    done_graph_prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag.get("done_graph_prereqs", {})  # type: ignore[assignment]
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["dependents"]  # type: ignore[assignment]
    topo_order: list[tuple[Path, str]] = dag["topo_order"]  # type: ignore[assignment]
    target_project: Path | None = dag.get("target_project")  # type: ignore[assignment]

    archived_tasks: list[tuple[Path, str]] = dag.get("archived_tasks", [])  # type: ignore[assignment]

    def _is_target_node(u: tuple[Path, str]) -> bool:
        return target_project is None or u[0] == target_project

    has_open_in_scope = bool(topo_order) and (
        target_project is None or any(u[0] == target_project for u in topo_order)
    )
    has_arch_in_scope = include_done and bool(archived_tasks) and (
        target_project is None or any(u[0] == target_project for u in archived_tasks)
    )
    if not has_open_in_scope and not has_arch_in_scope:
        scope_msg = "across workspace projects" if (workspace or is_orch) else "in TODO.md"
        sys.stdout.write(f"No open tasks {scope_msg}\n")
        return 0

    if by_role:
        plan = plan_execution_chains_by_role(
            dag,
            include_hold=include_hold,
            ready_only=ready,
            limit=(None if (target_project is not None or row_scoped) else limit),
            role=role,
        )
    else:
        plan = plan_execution_chains(
            dag,
            include_hold=include_hold,
            ready_only=ready,
            limit=(None if (role is not None or row_scoped or target_project is not None) else limit),
            include_done=include_done,
        )
    active_nodes: list[tuple[Path, str]] = plan["active_nodes"]  # type: ignore[assignment]
    active_unblocks: dict[tuple[Path, str], int] = plan["active_unblocks"]  # type: ignore[assignment]
    excluded_hold: set[tuple[Path, str]] = plan["excluded_hold"]  # type: ignore[assignment]
    finale_set: set[tuple[Path, str]] = plan.get("finale_set", set())  # type: ignore[assignment]
    chain_counts: dict[tuple[Path, str], int] = plan.get("chain_counts", {})  # type: ignore[assignment]
    immediate_ready_targets: dict[tuple[Path, str], list[tuple[Path, str]]] = plan.get("immediate_ready_targets", {})  # type: ignore[assignment]

    active_set = set(active_nodes)
    relevant_active_set: set[tuple[Path, str]] = set(active_set)
    if target_project is not None:
        undir: dict[tuple[Path, str], set[tuple[Path, str]]] = {u: set() for u in active_nodes}
        for u in active_nodes:
            for p in prereqs.get(u, []):
                if p in active_set:
                    undir[u].add(p)
                    undir[p].add(u)
        rel_vis: set[tuple[Path, str]] = set()
        for u in active_nodes:
            if u[0] == target_project and u not in rel_vis:
                stk = [u]
                rel_vis.add(u)
                while stk:
                    cur = stk.pop()
                    for nb in undir[cur]:
                        if nb not in rel_vis:
                            rel_vis.add(nb)
                            stk.append(nb)
        relevant_active_set = rel_vis

    had_blocker_error = False
    for u in active_nodes:
        if u not in relevant_active_set:
            continue
        st = str(nodes[u]["status"])
        if st in ("MISSING", "CANCELED"):
            had_blocker_error = True
            blocked_refs = [str(nodes[v]["ref"]) for v in dependents.get(u, []) if v in relevant_active_set]
            if blocked_refs:
                sys.stderr.write(
                    f"ERROR: unresolved blocker {nodes[u]['ref']} ({st}) blocks {', '.join(blocked_refs)}\n"
                )
            else:
                sys.stderr.write(f"ERROR: unresolved blocker {nodes[u]['ref']} ({st})\n")

    term_width = _get_terminal_columns()
    use_color = _use_ansi_color()
    target_set, unscoped_target_ids = _normalize_target_refs(base_dir, targets, explicit_dir=explicit_dir)
    wanted_role = role.strip().lower() if role is not None else None
    rank_pos = {node: idx for idx, node in enumerate(active_nodes)}

    def _is_highlighted_node(u: tuple[Path, str]) -> bool:
        return (u[0].resolve(), u[1].upper()) in target_set or u[1].upper() in unscoped_target_ids

    def _matches_role(u: tuple[Path, str]) -> bool:
        if wanted_role is None:
            return True
        nd = nodes[u]
        return bool(nd.get("exists")) and _task_matches_role(nd, wanted_role)

    focus_set, focus_unscoped = _normalize_target_refs(base_dir, focus, explicit_dir=explicit_dir)
    focus_active = bool(focus_set or focus_unscoped)

    def _is_focus_node(u: tuple[Path, str]) -> bool:
        return (u[0].resolve(), u[1].upper()) in focus_set or u[1].upper() in focus_unscoped

    def _status_ok(u: tuple[Path, str]) -> bool:
        return status is None or str(nodes[u]["status"]) in status

    def _row_ok(u: tuple[Path, str]) -> bool:
        return _status_ok(u) and (not focus_active or _is_focus_node(u))

    num_w_box = [1]

    def _lead_cell(prefix: str, idx: int, ref: str) -> str:
        if numbered is None:
            return f"{prefix}{ref}"
        width = num_w_box[0]
        if numbered == "right":
            return f"{prefix}{idx:>{width}} {ref}"
        return f"{prefix}{idx:<{width}} {ref}"

    def _format_row(
        idx: int,
        u: tuple[Path, str],
        show_downstream: bool = False,
        also_in_refs: list[str] | None = None,
        tree_prefix: str = "",
        cont_prefix: str | None = None,
        lead_col_width: int = 24,
    ) -> str:
        nd = nodes[u]
        st = str(nd["status"])
        ref = str(nd["ref"])
        title = str(nd["title"])
        blockers = [str(nodes[p]["ref"]) for p in prereqs.get(u, []) if str(nodes[p]["status"]) != "DONE"]
        role_badge = _task_role_badge(nd) if nd.get("exists") else ""
        impact = active_unblocks.get(u, 0)
        if st == "MISSING":
            badge = "[MISSING]"
            status_tag = "[blocked]" + (f" [unblocks {impact}]" if impact > 0 else "")
        elif st == "CANCELED":
            badge = f"{nd['emoji']} [CANCELED]"
            if u in active_set:
                status_tag = "[blocked]" + (f" [unblocks {impact}]" if impact > 0 else "")
            else:
                status_tag = ""
        elif st == "DONE":
            badge = f"{nd['emoji']} [DONE]"
            status_tag = ""
        else:
            emoji = "⏳" if (st in ("WIP", "NEXT") and blockers) else str(nd["emoji"])
            badge = f"{emoji} [{st}]"
            if blockers:
                status_tag = f"[blocked by: {', '.join(blockers)}]" + (
                    f" [unblocks {impact}]" if impact > 0 else ""
                )
            elif u in finale_set or (impact == 0 and bool(done_prereqs.get(u))):
                done_refs = done_prereqs.get(u, [])
                shown_done = list(done_refs[:3])
                if len(done_refs) > 3:
                    shown_done.append("...")
                status_tag = f"[ready | after: {', '.join(shown_done)}]"
            elif show_downstream and impact > 0:
                imm_targets = set(immediate_ready_targets.get(u, []))
                next_nodes = sorted(
                    [v for v in dependents.get(u, []) if v in active_set],
                    key=lambda v: (0 if v in imm_targets else 1, rank_pos.get(v, len(active_nodes))),
                )
                n_chains = chain_counts.get(u, 0)
                stats = f"{n_chains} chain{'' if n_chains == 1 else 's'} | +{len(imm_targets)} ready | unblocks {impact}"
                if next_nodes:
                    shown_refs = [str(nodes[v]["ref"]) for v in next_nodes[:3]]
                    if len(next_nodes) > 3:
                        shown_refs.append("...")
                    status_tag = f"[ready | {stats} -> {', '.join(shown_refs)}]"
                else:
                    status_tag = f"[ready | {stats}]"
            else:
                status_tag = "[ready]" + (f" [unblocks {impact}]" if impact > 0 else "")
        if also_in_refs:
            also_tag = f"[also in: {', '.join(also_in_refs)}]"
            status_tag = f"{status_tag} {also_tag}" if status_tag else also_tag
        lead_cell = _lead_cell(tree_prefix, idx, ref)
        prefix = (
            f"  {_pad_display(lead_cell, lead_col_width)}  "
            f"{_pad_display(badge, 14)}  "
            f"{_pad_display(role_badge, 10)}  "
        )
        desc = f"{title}  {status_tag}" if status_tag else title
        rendered = _wrap_table_row(prefix, desc, term_width, cont_prefix=cont_prefix) + "\n"
        return _style_task_row(
            rendered,
            is_external=not _is_target_node(u),
            is_done=(st == "DONE"),
            is_highlighted=_is_highlighted_node(u),
            use_color=use_color,
        )

    held_paths: list[list[tuple[Path, str]]] = []
    if excluded_hold:
        held_in_deg = {u: sum(1 for p in prereqs[u] if p in excluded_hold) for u in excluded_hold}
        held_deps = {u: [v for v in dependents.get(u, []) if v in excluded_hold] for u in excluded_hold}
        branch_roots = [u for u in topo_order if u in excluded_hold and held_in_deg[u] == 0]

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

        if target_project is not None:
            held_paths = [path for path in held_paths if any(_is_target_node(k) for k in path)]
        if wanted_role is not None:
            held_paths = [path for path in held_paths if any(_matches_role(k) for k in path)]
        if focus_active:
            held_paths = [path for path in held_paths if any(_is_focus_node(k) for k in path)]
        if status is not None:
            held_paths = [path for path in held_paths if any(_status_ok(k) for k in path)]

    scoped_excluded_hold = {
        u
        for u in excluded_hold
        if _is_target_node(u) or any(u in path for path in held_paths)
    }

    if by_role:
        queues: list[tuple[str, str, list[tuple[Path, str]]]] = plan["queues"]  # type: ignore[assignment]
        if target_project is not None or row_scoped:
            queues = [
                (q_key, q_label, [u for u in q_items if _is_target_node(u) and _row_ok(u)])
                for q_key, q_label, q_items in queues
            ]
            if limit is not None:
                rem = limit
                limited_queues: list[tuple[str, str, list[tuple[Path, str]]]] = []
                for q_key, q_label, q_items in queues:
                    if rem <= 0:
                        limited_queues.append((q_key, q_label, []))
                        continue
                    take = q_items[:rem]
                    limited_queues.append((q_key, q_label, take))
                    rem -= len(take)
                queues = limited_queues
        non_empty_queues = [(q_label, q_items) for _, q_label, q_items in queues if q_items]
        num_w_box[0] = len(str(max(1, sum(len(q_items) for _, q_items in non_empty_queues))))
        matching_held = [u for u in scoped_excluded_hold if _matches_role(u) and _is_target_node(u) and _row_ok(u)]
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
        if target_project is not None:
            ready_tasks = [u for u in ready_tasks if _is_target_node(u)]
        if wanted_role is not None:
            ready_tasks = [u for u in ready_tasks if _matches_role(u)]
        if row_scoped:
            ready_tasks = [u for u in ready_tasks if _row_ok(u)]
        if (target_project is not None or wanted_role is not None or row_scoped) and limit is not None:
            ready_tasks = ready_tasks[:limit]
        matching_held = [u for u in scoped_excluded_hold if _matches_role(u) and _is_target_node(u) and _row_ok(u)]
        num_w_box[0] = len(str(max(1, len(ready_tasks))))
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
        raw_chain_stats: list[dict[str, object]] = plan.get("chain_stats", [])  # type: ignore[assignment]
        if len(raw_chain_stats) == len(chains):
            chains_with_stats: list[tuple[list[tuple[Path, str]], dict[str, object]]] = list(
                zip(chains, raw_chain_stats)
            )
        else:
            chains_with_stats = [
                (
                    comp,
                    {
                        "open_count": len(comp),
                        "done_count": 0,
                        "total_tasks": len(comp),
                        "progress_pct": 0,
                    },
                )
                for comp in chains
            ]
        standalone: list[tuple[Path, str]] = plan["standalone"]  # type: ignore[assignment]

        def _chain_has_target_node(
            comp_nodes: list[tuple[Path, str]],
            st_info: dict[str, object],
        ) -> bool:
            open_list = st_info.get("open_nodes")
            if isinstance(open_list, list) and open_list:
                return any(_is_target_node(u) for u in open_list)
            non_done = [u for u in comp_nodes if str(nodes[u]["status"]) != "DONE"]
            check_list = non_done if non_done else comp_nodes
            return any(_is_target_node(u) for u in check_list)

        if target_project is not None:
            finales = [u for u in finales if _is_target_node(u)]
            chains_with_stats = [
                (comp, st_info)
                for comp, st_info in chains_with_stats
                if _chain_has_target_node(comp, st_info)
            ]
            standalone = [u for u in standalone if _is_target_node(u)]
        if wanted_role is not None:
            finales = [u for u in finales if _matches_role(u)]
            filtered_chains_with_stats: list[tuple[list[tuple[Path, str]], dict[str, object]]] = []
            for comp, st_info in chains_with_stats:
                f_comp = [u for u in comp if _matches_role(u)]
                if f_comp and (target_project is None or any(_is_target_node(u) for u in f_comp)):
                    filtered_chains_with_stats.append((f_comp, st_info))
            chains_with_stats = filtered_chains_with_stats
            standalone = [u for u in standalone if _matches_role(u)]
        if row_scoped:
            finales = [u for u in finales if _row_ok(u)]
            scoped_chains: list[tuple[list[tuple[Path, str]], dict[str, object]]] = []
            for comp, st_info in chains_with_stats:
                c_nodes = (
                    set(comp)
                    | set(st_info.get("nodes", []))  # type: ignore[arg-type]
                    | set(st_info.get("open_nodes", []))  # type: ignore[arg-type]
                    | set(st_info.get("done_nodes", set()))  # type: ignore[arg-type]
                )
                if focus_active and not any(_is_focus_node(u) for u in c_nodes):
                    continue
                f_comp = [u for u in comp if _status_ok(u)]
                if f_comp:
                    scoped_chains.append((f_comp, st_info))
            chains_with_stats = scoped_chains
            standalone = [u for u in standalone if _row_ok(u)]
        if (target_project is not None or wanted_role is not None or row_scoped) and limit is not None:
            rem = limit
            finales = finales[:rem] if rem > 0 else []
            rem -= len(finales)
            limited_chains_with_stats: list[tuple[list[tuple[Path, str]], dict[str, object]]] = []
            for comp, st_info in chains_with_stats:
                if rem <= 0:
                    break
                take = comp[:rem]
                limited_chains_with_stats.append((take, st_info))
                rem -= len(take)
            standalone = standalone[:rem] if rem > 0 else []
            chains_with_stats = limited_chains_with_stats
        matching_held = [u for u in scoped_excluded_hold if _matches_role(u) and _is_target_node(u) and _row_ok(u)]
        if finales or chains_with_stats or standalone:
            row_idx = 1
            wrote_section = False

            def _build_chain_tree(
                comp_nodes: list[tuple[Path, str]],
                st_info: dict[str, object],
            ) -> dict[str, object]:
                r_key = st_info.get("root")
                t_root: tuple[Path, str] = (
                    r_key
                    if isinstance(r_key, tuple) and r_key in nodes
                    else (comp_nodes[-1] if comp_nodes else (b_res, ""))
                )
                return build_chain_milestone_tree(
                    root=t_root,
                    display_nodes=comp_nodes,
                    nodes=nodes,
                    prereqs=prereqs,
                    done_nodes=done_nodes,
                    direct_done_deps=direct_done_deps,
                    done_graph_prereqs=done_graph_prereqs,
                    include_done=include_done,
                )

            def _flat_tree_nodes(t_node: dict[str, object]) -> list[tuple[Path, str]]:
                flat: list[tuple[Path, str]] = []
                for ch_item in t_node.get("children", []):  # type: ignore[attr-defined]
                    if ch_item.get("kind") == "subchain":
                        flat.extend(_flat_tree_nodes(ch_item))
                    else:
                        flat.append(ch_item["node"])
                return flat

            chain_trees = [_build_chain_tree(c_nodes, c_info) for c_nodes, c_info in chains_with_stats]
            total_rows = len(finales) + len(standalone) + sum(len(_flat_tree_nodes(ct)) for ct in chain_trees)
            num_w_box[0] = len(str(max(1, total_rows)))
            if finales:
                sys.stdout.write("Chain finales:\n")
                for u in finales:
                    sys.stdout.write(_format_row(row_idx, u))
                    row_idx += 1
                wrote_section = True
            for chain_idx, (comp, st_info) in enumerate(chains_with_stats, start=1):
                if wrote_section:
                    sys.stdout.write("\n")
                total_t = int(st_info.get("total_tasks", len(comp)))
                pct = int(st_info.get("progress_pct", 0))
                done_c = int(st_info.get("done_count", 0))
                open_c = int(st_info.get("open_count", len(comp)))
                root_key = st_info.get("root")
                if isinstance(root_key, tuple) and root_key in nodes:
                    root_ref = str(st_info.get("root_ref") or nodes[root_key]["ref"])
                    root_title = str(st_info.get("root_title") or nodes[root_key]["title"])
                else:
                    fallback_root = comp[-1] if comp else None
                    root_ref = str(
                        st_info.get("root_ref")
                        or (
                            nodes[fallback_root]["ref"]
                            if fallback_root is not None and fallback_root in nodes
                            else ""
                        )
                    )
                    root_title = str(
                        st_info.get("root_title")
                        or (
                            nodes[fallback_root]["title"]
                            if fallback_root is not None and fallback_root in nodes
                            else ""
                        )
                    )
                also_in_map: dict[tuple[Path, str], list[str]] = st_info.get("also_in", {})  # type: ignore[assignment]
                chain_nodes = (
                    set(comp)
                    | set(st_info.get("nodes", []))  # type: ignore[arg-type]
                    | set(st_info.get("open_nodes", []))  # type: ignore[arg-type]
                    | set(st_info.get("done_nodes", set()))  # type: ignore[arg-type]
                )
                chain_highlighted = any(_is_highlighted_node(u) for u in chain_nodes)
                header_line = (
                    f"Chain {chain_idx} -> {root_ref}: {root_title} "
                    f"({total_t} tasks, {pct}% | {done_c} done, {open_c} open):\n"
                )
                sys.stdout.write(
                    _style_task_row(
                        header_line,
                        is_highlighted=chain_highlighted,
                        use_color=use_color,
                    )
                )
                chain_tree = chain_trees[chain_idx - 1]

                def _max_lead_width(
                    t_node: dict[str, object],
                    active_bars: list[bool],
                    sim_idx: int,
                ) -> tuple[int, int]:
                    max_w = 24
                    ch_list: list[dict[str, object]] = t_node.get("children", [])  # type: ignore[assignment]
                    for c_i, ch_item in enumerate(ch_list):
                        is_last_c = c_i == len(ch_list) - 1
                        if ch_item.get("kind") == "subchain":
                            sub_w, sim_idx = _max_lead_width(
                                ch_item,
                                [*active_bars, not is_last_c],
                                sim_idx,
                            )
                            if sub_w > max_w:
                                max_w = sub_w
                        else:
                            u_node: tuple[Path, str] = ch_item["node"]  # type: ignore[assignment]
                            bars = "".join("│   " if b else "    " for b in active_bars)
                            is_closing = bool(ch_item.get("is_closing")) and is_last_c
                            conn = "└─► " if is_closing else ("└── " if is_last_c else "├── ")
                            cell = _lead_cell(f"{bars}{conn}", sim_idx, str(nodes[u_node]["ref"]))
                            cw = _display_width(cell)
                            if cw > max_w:
                                max_w = cw
                            sim_idx += 1
                    return max_w, sim_idx

                chain_lead_w, _ = _max_lead_width(chain_tree, [], row_idx)

                def _render_chain_tree_children(
                    t_node: dict[str, object],
                    active_bars: list[bool],
                    cur_idx: int,
                ) -> int:
                    ch_list: list[dict[str, object]] = t_node.get("children", [])  # type: ignore[assignment]
                    for c_i, ch_item in enumerate(ch_list):
                        is_last_c = c_i == len(ch_list) - 1
                        bars = "".join("│   " if b else "    " for b in active_bars)
                        if ch_item.get("kind") == "subchain":
                            m_node: tuple[Path, str] = ch_item["milestone"]  # type: ignore[assignment]
                            m_ref = str(ch_item.get("milestone_ref") or nodes[m_node]["ref"])
                            m_title = str(ch_item.get("milestone_title") or nodes[m_node]["title"])
                            m_pct = int(ch_item.get("progress_pct", 0))
                            m_done = int(ch_item.get("done_count", 0))
                            m_open = int(ch_item.get("open_count", 0))
                            sub_nodes: set[tuple[Path, str]] = ch_item.get("subtree_nodes", {m_node})  # type: ignore[assignment]
                            sub_hl = any(_is_highlighted_node(su) for su in sub_nodes)
                            sub_conn = "└── " if is_last_c else "├── "
                            sub_prefix = f"  {bars}{sub_conn}"
                            sub_cont_bars = "".join(
                                "│   " if b else "    " for b in [*active_bars, not is_last_c]
                            )
                            sub_cont_prefix = f"  {sub_cont_bars}" if sub_cont_bars.strip() else "    "
                            sub_desc = (
                                f"Sub-chain -> {m_ref}: {m_title} "
                                f"({m_pct}% | {m_done} done, {m_open} open):"
                            )
                            sub_hdr = (
                                _wrap_table_row(
                                    sub_prefix,
                                    sub_desc,
                                    term_width,
                                    cont_prefix=sub_cont_prefix,
                                )
                                + "\n"
                            )
                            sys.stdout.write(
                                _style_task_row(
                                    sub_hdr,
                                    is_external=not _is_target_node(m_node),
                                    is_done=(str(nodes[m_node]["status"]) == "DONE"),
                                    is_highlighted=sub_hl,
                                    use_color=use_color,
                                )
                            )
                            cur_idx = _render_chain_tree_children(
                                ch_item,
                                [*active_bars, not is_last_c],
                                cur_idx,
                            )
                        else:
                            u_node: tuple[Path, str] = ch_item["node"]  # type: ignore[assignment]
                            is_closing = bool(ch_item.get("is_closing")) and is_last_c
                            conn = "└─► " if is_closing else ("└── " if is_last_c else "├── ")
                            t_pref = f"{bars}{conn}"
                            row_bars = [*active_bars, not is_last_c]
                            cont_bars_str = "".join("│   " if b else "    " for b in row_bars)
                            c_pref = f"  {cont_bars_str}" if any(row_bars) else None
                            sys.stdout.write(
                                _format_row(
                                    cur_idx,
                                    u_node,
                                    also_in_refs=also_in_map.get(u_node),
                                    tree_prefix=t_pref,
                                    cont_prefix=c_pref,
                                    lead_col_width=chain_lead_w,
                                )
                            )
                            cur_idx += 1
                    return cur_idx

                if tree:
                    row_idx = _render_chain_tree_children(chain_tree, [], row_idx)
                else:
                    flat_nodes = _flat_tree_nodes(chain_tree)
                    flat_w = max(
                        [
                            24,
                            *(
                                _display_width(_lead_cell("", row_idx + k, str(nodes[fu]["ref"])))
                                for k, fu in enumerate(flat_nodes)
                            ),
                        ]
                    )
                    for fu in flat_nodes:
                        sys.stdout.write(
                            _format_row(
                                row_idx,
                                fu,
                                also_in_refs=also_in_map.get(fu),
                                lead_col_width=flat_w,
                            )
                        )
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

    if held_paths:
        sys.stdout.write("\nHeld branches:\n")
        for path in held_paths:
            parts: list[str] = []
            for k in path:
                token = _style_task_row(
                    f"{nodes[k]['ref']} ({nodes[k]['status']})",
                    is_external=not _is_target_node(k),
                    is_done=(str(nodes[k]["status"]) == "DONE"),
                    is_highlighted=_is_highlighted_node(k),
                    use_color=use_color,
                )
                parts.append(token)
            rendered = " -> ".join(parts)
            sys.stdout.write(f"  {rendered}\n")

    if focus is not None and len(focus) == 1:
        f_dir, raw_f_tid = focus[0]
        f_tid = raw_f_tid[2:].strip().upper() if raw_f_tid.startswith(".:") else raw_f_tid.split(":")[-1].strip().upper()
        cand_key = (f_dir.resolve(), f_tid)
        if cand_key not in nodes or not nodes[cand_key].get("exists"):
            matched_nodes = [u for u in nodes if _is_focus_node(u) and nodes[u].get("exists")]
            if len(matched_nodes) == 1:
                f_dir, f_tid = matched_nodes[0]
        f_dag = build_dependency_dag(base_dir, f_dir, f_tid, explicit_dir=explicit_dir, stop_at_done=True)
        f_nodes: dict[tuple[Path, str], dict[str, object]] = f_dag["nodes"]  # type: ignore[assignment]
        f_root: tuple[Path, str] = f_dag["root"]  # type: ignore[assignment]
        if f_nodes[f_root]["exists"] and not f_dag["syntax_errors"] and not f_dag["cycle"]:
            f_next = _first_actionable_in_dag(f_dag)
            sys.stdout.write(f"\nNext actionable: {f_next or 'none'}\n")

    return 1 if had_blocker_error else 0
