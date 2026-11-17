def parse_version_from_source(source: str) -> str | None:
    m = re.search(r'^VERSION\s*=\s*["\x27]([^"\x27]+)["\x27]', source, flags=re.MULTILINE)
    return m.group(1) if m else None


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.split(r"[^0-9]+", v) if p)


def fetch_remote_script(url: str | None = None) -> str:
    target_url = url or os.environ.get("TODO_MD_UPDATE_URL") or DEFAULT_UPDATE_URL
    req = urllib.request.Request(target_url, headers={"User-Agent": f"todo_md/{VERSION}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read().decode("utf-8")
    if REPO_MARKER not in data:
        raise ValueError(f"remote file at {target_url} is not a valid vitalio/todo_md script")
    return data


def cmd_check_update(url: str | None = None) -> int:
    prog = prog_name()
    try:
        remote_src = fetch_remote_script(url)
    except Exception as exc:
        sys.stderr.write(f"{prog}: failed to check for updates: {exc}\n")
        return 1
    remote_ver = parse_version_from_source(remote_src) or "unknown"
    if version_tuple(remote_ver) > version_tuple(VERSION):
        sys.stdout.write(f"{prog}: update available: {VERSION} -> {remote_ver} (run '{prog} update')\n")
    else:
        sys.stdout.write(f"{prog} {VERSION} is up to date (remote: {remote_ver}).\n")
    return 0


def cmd_update(force: bool = False, url: str | None = None, target_path: Path | None = None) -> int:
    prog = prog_name()
    dest = target_path or Path(__file__).resolve()
    try:
        remote_src = fetch_remote_script(url)
    except Exception as exc:
        sys.stderr.write(f"{prog}: update failed: {exc}\n")
        return 1
    remote_ver = parse_version_from_source(remote_src) or "unknown"
    if not force and version_tuple(remote_ver) <= version_tuple(VERSION):
        sys.stdout.write(f"{prog} {VERSION} is already up to date.\n")
        return 0
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", dir=str(dest.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(remote_src)
            os.chmod(tmp_name, 0o755)
            os.replace(tmp_name, dest)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
    except Exception as exc:
        sys.stderr.write(f"{prog}: could not write updated binary to {dest}: {exc}\n")
        return 1
    sys.stdout.write(f"{prog}: updated {VERSION} -> {remote_ver} ({dest})\n")
    return 0


KNOWN_SUBCOMMANDS = (
    "projects",
    "archive",
    "add",
    "edit",
    "append",
    "done",
    "cancel",
    "canceled",
    "status",
    "next",
    "reopen",
    "top",
    "queue",
    "next-id",
    "last-id",
    "last",
    "files",
    "ids",
    "check",
    "init",
    "list",
    "show",
    "update",
    "check-update",
    "help",
    "version",
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    prog = prog_name()
    if "-h" in args or "--help" in args or (args and args[0] == "help"):
        sys.stdout.write(usage_text())
        return 0
    if "-V" in args or "--version" in args or (args and args[0] == "version"):
        sys.stdout.write(f"{prog} {VERSION}\n")
        return 0
    if args and args[0] in ("check-update", "--check-update"):
        return cmd_check_update()
    if args and args[0] in ("update", "--update", "--self-update"):
        force = "--force" in args[1:]
        return cmd_update(force=force)

    full = False
    if "--full" in args:
        full = True
        args = [a for a in args if a != "--full"]
    commit = False
    if "--commit" in args or "-c" in args:
        commit = True
        args = [a for a in args if a not in ("--commit", "-c")]
    no_commit = False
    if "--no-commit" in args:
        no_commit = True
        args = [a for a in args if a != "--no-commit"]
    workspace = False
    if "--workspace" in args or "-w" in args:
        workspace = True
        args = [a for a in args if a not in ("--workspace", "-w")]

    explicit_dir: str | None = None
    if args and args[0] not in KNOWN_SUBCOMMANDS and not args[0].startswith("-"):
        if Path(args[0]).is_dir():
            explicit_dir = args.pop(0)
        elif not re.fullmatch(r"[A-Za-z]\d+", args[0]) and not PROJECT_TASK_RE.match(args[0]):
            ws_probe = resolve_workspace_root(resolve_target_dir(None))
            cand = (ws_probe / args[0].replace("\\", "/").strip("/")).resolve()
            if is_todo_project(cand):
                explicit_dir = str(cand)
                args.pop(0)
    base_dir = resolve_target_dir(explicit_dir)
    if args and args[0] in ("projects", "--projects"):
        return cmd_projects(base_dir, explicit_dir=explicit_dir)
    if not args:
        if workspace:
            return cmd_workspace_summary(resolve_workspace_root(base_dir, explicit_dir=explicit_dir), full=full)
        if not is_todo_project(base_dir) and not (base_dir / "TODO.md").is_file():
            ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
            if discover_projects(ws_root):
                return cmd_workspace_summary(ws_root, full=full)
        return cmd_summary(base_dir, full=full)
    if args[0] in ("archive", "--archive", "-a"):
        pos, note = _parse_note_arg(args[1:])
        canceled = "--canceled" in pos or "--cancel" in pos
        pos = [p for p in pos if p not in ("--canceled", "--cancel", "--done")]
        if not pos:
            return cmd_archive_view(base_dir)
        tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
        return cmd_transition(tdir, tid, new_status=("CANCELED" if canceled else "DONE"), dest_file="TODO_ARCHIVE.md", note=note, commit=commit, no_commit=no_commit)
    if args[0] in ("add", "--add"):
        return cmd_add(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("edit", "--edit"):
        return cmd_edit(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("append", "--append"):
        if len(args) >= 2 and not args[1].startswith("-"):
            tdir, tid = resolve_project_task_ref(base_dir, args[1], explicit_dir=explicit_dir)
            return cmd_append(tdir, [tid, *args[2:]], commit=commit, no_commit=no_commit)
        return cmd_append(base_dir, args[1:], commit=commit, no_commit=no_commit)
    if args[0] in ("done", "--done"):
        pos, note = _parse_note_arg(args[1:])
        if len(pos) != 1:
            raise SystemExit(f"{prog}: usage: {prog} done <ID> [-m NOTE]")
        tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
        return cmd_transition(tdir, tid, new_status="DONE", dest_file="TODO_ARCHIVE.md", note=note, commit=commit, no_commit=no_commit)
    if args[0] in ("cancel", "canceled", "--cancel"):
        pos, note = _parse_note_arg(args[1:])
        if len(pos) != 1:
            raise SystemExit(f"{prog}: usage: {prog} cancel <ID> [-m REASON]")
        tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
        return cmd_transition(tdir, tid, new_status="CANCELED", dest_file="TODO_ARCHIVE.md", note=note, commit=commit, no_commit=no_commit)
    if args[0] in ("status", "--status"):
        pos, note = _parse_note_arg(args[1:])
        reopen = "--reopen" in pos
        pos = [p for p in pos if p != "--reopen"]
        bad_flags = [p for p in pos if p.startswith("-")]
        if bad_flags:
            raise SystemExit(f"{prog}: unknown option for status: {bad_flags[0]}")
        if len(pos) != 2:
            raise SystemExit(f"{prog}: usage: {prog} status <ID> <STATUS> [-m NOTE] [--reopen]")
        tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
        st_up = pos[1].upper()
        return cmd_transition(tdir, tid, new_status=st_up, dest_file=None, note=note, promote_top=(st_up in ("WIP", "NEXT")), reopen=reopen, commit=commit, no_commit=no_commit)
    if args[0] in ("reopen", "--reopen"):
        return cmd_reopen(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("queue", "--queue"):
        show_all = False
        pos: list[str] = []
        for a in args[1:]:
            if a == "--all":
                show_all = True
            elif a.startswith("-"):
                raise SystemExit(f"{prog}: unknown option for queue: {a}")
            else:
                pos.append(a)
        if len(pos) != 1:
            raise SystemExit(f"{prog}: usage: {prog} queue <ID> [--all]")
        tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
        return cmd_queue(base_dir, tdir, tid, show_all=show_all, explicit_dir=explicit_dir)
    if args[0] in ("next-id", "--next-id"):
        if len(args) > 2:
            raise SystemExit(f"{prog}: usage: {prog} next-id [<ID>]")
        if len(args) == 2:
            if args[1].startswith("-"):
                raise SystemExit(f"{prog}: unknown option for next-id: {args[1]}")
            tdir, tid = resolve_project_task_ref(base_dir, args[1], explicit_dir=explicit_dir)
            return cmd_next_id(base_dir, target_dir=tdir, task_id=tid, explicit_dir=explicit_dir)
        return cmd_next_id(base_dir)
    if args[0] in ("last-id", "--last-id"):
        if len(args) > 2:
            raise SystemExit(f"{prog}: usage: {prog} last-id [<STATUS|archive>]")
        return cmd_last_id(base_dir, args[1] if len(args) == 2 else None)
    if args[0] in ("last", "--last"):
        if len(args) > 2:
            raise SystemExit(f"{prog}: usage: {prog} last [<STATUS|archive>]")
        return cmd_last(base_dir, args[1] if len(args) == 2 else None)
    if args[0] in ("files", "--files"):
        budgets: dict[str, int | None] = {
            "--max-lines": None,
            "--max-total-lines": None,
            "--max-bytes": None,
            "--max-total-bytes": None,
        }
        pos: list[str] = []
        i = 1
        while i < len(args):
            a = args[i]
            matched_flag = None
            raw_val: str | None = None
            for flag in budgets:
                if a == flag:
                    if i + 1 >= len(args):
                        raise SystemExit(f"{prog}: {flag} requires a positive integer argument")
                    matched_flag = flag
                    raw_val = args[i + 1]
                    i += 2
                    break
                if a.startswith(f"{flag}="):
                    matched_flag = flag
                    raw_val = a.split("=", 1)[1]
                    i += 1
                    break
            if matched_flag is not None:
                assert raw_val is not None
                if not raw_val.isdigit() or int(raw_val) < 1:
                    raise SystemExit(f"{prog}: invalid {matched_flag} value {raw_val!r}; expected a positive integer")
                budgets[matched_flag] = int(raw_val)
            elif a.startswith("-"):
                raise SystemExit(f"{prog}: unknown option for files: {a}")
            else:
                pos.append(a)
                i += 1
        if len(pos) > 1:
            raise SystemExit(
                f"{prog}: usage: {prog} files [<ID>] [--max-lines N] [--max-total-lines N] [--max-bytes N] [--max-total-bytes N]"
            )
        if len(pos) == 1:
            tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
        else:
            tdir, tid = base_dir, None
        return cmd_files(
            tdir,
            tid,
            max_lines=budgets["--max-lines"],
            max_total_lines=budgets["--max-total-lines"],
            max_bytes=budgets["--max-bytes"],
            max_total_bytes=budgets["--max-total-bytes"],
        )
    if args[0] in ("next", "top", "--next", "--top"):
        pos, note = _parse_note_arg(args[1:])
        if args[0] == "--top" and not pos and note is None:
            return cmd_next_id(base_dir)
        reopen = "--reopen" in pos
        pos = [p for p in pos if p != "--reopen"]
        bad_flags = [p for p in pos if p.startswith("-")]
        if bad_flags:
            raise SystemExit(f"{prog}: unknown option for next: {bad_flags[0]}")
        if len(pos) != 1:
            raise SystemExit(f"{prog}: usage: {prog} next <ID> [-m NOTE] [--reopen]")
        tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
        return cmd_transition(tdir, tid, new_status="NEXT", dest_file="TODO.md", note=note, promote_top=True, reopen=reopen, commit=commit, no_commit=no_commit)
    if args[0] in ("ids", "--ids"):
        return cmd_ids(base_dir)
    if args[0] in ("check", "--check"):
        if workspace or (not is_todo_project(base_dir) and not (base_dir / "TODO.md").is_file()):
            ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
            if workspace or discover_projects(ws_root):
                return cmd_workspace_check(ws_root)
        return cmd_check(base_dir)
    if args[0] in ("init", "--init"):
        return cmd_init(base_dir, argv=args[1:], commit=commit, no_commit=no_commit)
    if args[0] in ("list", "--list", "-l"):
        filt: str | None = None
        limit: int | None = None
        role_filter: str | None = None
        ready = False
        i = 1
        while i < len(args):
            a = args[i]
            if a in ("--limit", "-n"):
                if i + 1 >= len(args):
                    raise SystemExit(f"{prog}: {a} requires an integer argument")
                raw_lim = args[i + 1]
                if not raw_lim.isdigit() or int(raw_lim) < 1:
                    raise SystemExit(f"{prog}: invalid limit {raw_lim!r}; expected a positive integer")
                limit = int(raw_lim)
                i += 2
            elif a.startswith("--limit="):
                raw_lim = a.split("=", 1)[1]
                if not raw_lim.isdigit() or int(raw_lim) < 1:
                    raise SystemExit(f"{prog}: invalid limit {raw_lim!r}; expected a positive integer")
                limit = int(raw_lim)
                i += 1
            elif a == "--role":
                if i + 1 >= len(args):
                    raise SystemExit(f"{prog}: {a} requires a role argument")
                raw_role = args[i + 1].strip()
                if not raw_role or "\n" in raw_role or "\r" in raw_role:
                    raise SystemExit(f"{prog}: invalid --role value {args[i + 1]!r}; expected a non-empty single-line role")
                role_filter = raw_role
                i += 2
            elif a.startswith("--role="):
                raw_val = a.split("=", 1)[1]
                raw_role = raw_val.strip()
                if not raw_role or "\n" in raw_role or "\r" in raw_role:
                    raise SystemExit(f"{prog}: invalid --role value {raw_val!r}; expected a non-empty single-line role")
                role_filter = raw_role
                i += 1
            elif a == "--ready":
                ready = True
                i += 1
            elif a.startswith("-"):
                raise SystemExit(f"{prog}: unknown option for list: {a}")
            elif filt is None:
                filt = a
                i += 1
            else:
                raise SystemExit(f"{prog}: usage: {prog} list [filter] [--role ROLE] [--ready] [--limit N] [--full]")
        if workspace or (not is_todo_project(base_dir) and not (base_dir / "TODO.md").is_file()):
            ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
            if workspace or discover_projects(ws_root):
                return cmd_workspace_list(ws_root, filt, limit=limit, full=full, role=role_filter, ready=ready)
        return cmd_list(base_dir, filt, limit=limit, full=full, role=role_filter, ready=ready)
    if args[0] in ("show", "--show"):
        if len(args) < 2 or len(args) > 3:
            raise SystemExit(f"{prog}: usage: {prog} show <ID|last> [<STATUS|archive>]")
        if args[1].lower() == "last":
            return cmd_last(base_dir, args[2] if len(args) == 3 else None)
        if len(args) != 2:
            raise SystemExit(f"{prog}: usage: {prog} show <ID>")
        tdir, tid = resolve_project_task_ref(base_dir, args[1], explicit_dir=explicit_dir)
        return cmd_show(tdir, tid)
    if len(args) == 1 and (re.fullmatch(r"[A-Za-z]\d+", args[0]) or PROJECT_TASK_RE.match(args[0])):
        tdir, tid = resolve_project_task_ref(base_dir, args[0], explicit_dir=explicit_dir)
        return cmd_show(tdir, tid)
    if len(args) == 1 and Path(args[0]).is_dir():
        return cmd_summary(resolve_target_dir(args[0]), full=full)
    raise SystemExit(f"{prog}: unknown arguments: {' '.join(args)} (see {prog} --help)")


if __name__ == "__main__":
    raise SystemExit(main())
