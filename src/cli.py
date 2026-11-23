def parse_version_from_source(source: str) -> str | None:
    m = re.search(r'^VERSION\s*=\s*["\x27]([^"\x27]+)["\x27]', source, flags=re.MULTILINE)
    return m.group(1) if m else None


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.split(r"[^0-9]+", v) if p)


def fetch_remote_script(url: str | None = None) -> str:
    import urllib.request

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
    "rename",
    "done",
    "cancel",
    "canceled",
    "status",
    "next",
    "reopen",
    "top",
    "queue",
    "chain",
    "next-id",
    "last-id",
    "last",
    "ids",
    "check",
    "init",
    "list",
    "show",
    "update",
    "check-update",
    "help",
    "version",
    "overview",
    "search",
)


def _validate_prefix_filter(raw_val: str) -> str:
    return _normalize_prefix_arg(raw_val)

def _validate_status_filter(prog: str, raw_val: str) -> str:
    kw = raw_val.strip().upper()
    if kw not in STATUS_FILTER_KEYWORDS:
        raise SystemExit(
            f"{prog}: invalid status {raw_val!r}; expected one of {', '.join(STATUS_FILTER_KEYWORDS)}"
        )
    return kw

STATUS_FILTER_KEYWORDS = (
    "WIP",
    "NEXT",
    "QUESTION",
    "NEW",
    "HOLD",
    "DONE",
    "CANCELED",
    "ARCHIVE",
    "ACTIVE",
    "ALL",
)
QUEST_LOG_USAGE = (
    "[--tree] [--numbered[=left|right]] [--prefix PREFIX] [--status STATUS] [--all] [-r|--ready] "
    "[-l N|--limit N] [--include-hold] [-f|--filter <ID>...] [-H|--highlight [<ID>...]] "
    "[-s|--search QUERY]"
)


def _is_status_keyword(tok: str) -> bool:
    return tok.upper() in STATUS_FILTER_KEYWORDS


def _collect_task_refs(args: list[str]) -> list[str] | None:
    refs: list[str] = []
    for a in args:
        parts = _split_task_ref_arg(a)
        if parts is None:
            return None
        refs.extend(parts)
    return refs


def _consume_task_refs(prog: str, flag: str, args: list[str], i: int) -> tuple[list[str], int]:
    refs: list[str] = []
    while i < len(args) and not args[i].startswith("-"):
        parts = _split_task_ref_arg(args[i])
        if parts is None:
            break
        refs.extend(parts)
        i += 1
    if not refs:
        raise SystemExit(f"{prog}: {flag} requires at least one task ID")
    return refs, i


def _parse_limit(prog: str, raw: str) -> int:
    if not raw.isdigit() or int(raw) < 1:
        raise SystemExit(f"{prog}: invalid limit {raw!r}; expected a positive integer")
    return int(raw)


def _parse_quest_log_args(prog: str, argv: list[str], cmd: str, positional_focus: bool) -> dict[str, object]:
    o: dict[str, object] = {
        "limit": None,
        "include_hold": False,
        "include_done": False,
        "ready": False,
        "tree": False,
        "numbered": None,
        "prefix": None,
        "status": None,
        "archive": None,
        "filter": [],
        "highlight": False,
        "search": None,
    }

    def set_status(raw: str) -> None:
        kw = raw.strip().upper()
        if kw not in STATUS_FILTER_KEYWORDS:
            raise SystemExit(
                f"{prog}: invalid status {raw!r}; expected one of {', '.join(STATUS_FILTER_KEYWORDS)}"
            )
        if kw == "ALL":
            o["include_done"] = True
        elif kw == "ACTIVE":
            pass
        elif kw in ("DONE", "CANCELED", "ARCHIVE"):
            o["archive"] = kw
        else:
            o["status"] = frozenset({kw})
            if kw == "HOLD":
                o["include_hold"] = True

    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--limit", "-n", "-l"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires an integer argument")
            o["limit"] = _parse_limit(prog, argv[i + 1])
            i += 2
        elif a.startswith("--limit="):
            o["limit"] = _parse_limit(prog, a.split("=", 1)[1])
            i += 1
        elif a == "--prefix":
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires a prefix argument")
            o["prefix"] = _validate_prefix_filter(argv[i + 1])
            i += 2
        elif a.startswith("--prefix="):
            o["prefix"] = _validate_prefix_filter(a.split("=", 1)[1])
            i += 1
        elif a == "--status":
            if i + 1 >= len(argv):
                raise SystemExit(f"{prog}: {a} requires a status argument")
            set_status(argv[i + 1])
            i += 2
        elif a.startswith("--status="):
            set_status(a.split("=", 1)[1])
            i += 1
        elif a in ("--filter", "-f", "--focus"):
            refs, i = _consume_task_refs(prog, a, argv, i + 1)
            o["filter"].extend(refs)  # type: ignore[attr-defined]
        elif a.startswith("--filter=") or a.startswith("--focus="):
            flag_name, raw_val = a.split("=", 1)
            parts = _split_task_ref_arg(raw_val)
            if not parts:
                raise SystemExit(f"{prog}: {flag_name} requires at least one task ID")
            o["filter"].extend(parts)  # type: ignore[attr-defined]
            i += 1
        elif a in ("--highlight", "-H"):
            o["highlight"] = True
            j = i + 1
            hl_refs: list[str] = []
            while j < len(argv) and not argv[j].startswith("-"):
                if _is_status_keyword(argv[j]):
                    break
                parts = _split_task_ref_arg(argv[j])
                if parts is None:
                    break
                hl_refs.extend(parts)
                j += 1
            o["filter"].extend(hl_refs)  # type: ignore[attr-defined]
            i = j
        elif a in ("--search", "-s"):
            if i + 1 >= len(argv) or not argv[i + 1].strip():
                raise SystemExit(f"{prog}: {a} requires a non-empty query argument")
            o["search"] = argv[i + 1]
            i += 2
        elif a.startswith("--search="):
            if not a.split("=", 1)[1].strip():
                raise SystemExit(f"{prog}: --search requires a non-empty query argument")
            o["search"] = a.split("=", 1)[1]
            i += 1
        elif a in ("--tree", "-t"):
            o["tree"] = True
            i += 1
        elif a == "--numbered" or a.startswith("--numbered="):
            side = a.split("=", 1)[1] if "=" in a else "left"
            if side not in ("left", "right"):
                raise SystemExit(f"{prog}: invalid --numbered value {side!r}; expected left or right")
            o["numbered"] = side
            i += 1
        elif a == "--include-hold":
            o["include_hold"] = True
            i += 1
        elif a == "--all":
            o["include_done"] = True
            i += 1
        elif a in ("--ready", "-r"):
            o["ready"] = True
            i += 1
        elif a.startswith("-"):
            raise SystemExit(f"{prog}: unknown option for {cmd}: {a}")
        elif _is_status_keyword(a):
            set_status(a)
            i += 1
        else:
            parts = _split_task_ref_arg(a)
            if parts is None:
                raise SystemExit(f"{prog}: usage: {prog} {cmd} [<ID>...] {QUEST_LOG_USAGE}")
            if not positional_focus:
                raise SystemExit(
                    f"{prog}: unexpected task ID {a!r} for the default view "
                    f"(use -f/--filter, -H/--highlight, or '{prog} chain <ID>')"
                )
            o["filter"].extend(parts)  # type: ignore[attr-defined]
            i += 1
    return o


def _quest_log(
    prog: str,
    base_dir: Path,
    explicit_dir: str | None,
    workspace: bool,
    full: bool,
    argv: list[str],
    cmd: str = "todo_md",
    positional_focus: bool = False,
) -> int:
    o = _parse_quest_log_args(prog, argv, cmd, positional_focus)
    filter_refs = [
        resolve_filter_task_ref(base_dir, r, explicit_dir=explicit_dir)
        for r in o["filter"]  # type: ignore[attr-defined]
    ]
    highlight_toggle = bool(o["highlight"])
    use_ws = workspace
    ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    if not use_ws and not is_todo_project(base_dir) and not (base_dir / "TODO.md").is_file():
        if discover_projects(ws_root):
            use_ws = True
    matched_refs: list[tuple[Path, str]] = list(filter_refs)
    search = o["search"]
    if search is not None:
        include_archive = bool(o["include_done"]) or o["archive"] is not None
        b_res = base_dir.resolve()
        is_orch = (not use_ws) and is_orchestrator_project(b_res, ws_root, explicit_dir=explicit_dir)
        if use_ws or is_orch:
            search_projects = resolve_workspace_chain_projects(base_dir, ws_root)
        else:
            search_projects = [(b_res.name, base_dir)]
        search_matches: list[tuple[Path, str]] = []
        for plabel, sdir in search_projects:
            for st in search_tasks(sdir, str(search), include_archive=include_archive, project_label=plabel):
                search_matches.append((sdir, str(st["id"]).upper()))
        if not search_matches:
            sys.stderr.write(f"{prog}: no tasks match {search!r}\n")
            return 1
        if full:
            show_rc = 0
            for n, (sdir, stid) in enumerate(search_matches):
                if n > 0:
                    sys.stdout.write("\n")
                show_rc = max(show_rc, cmd_show(sdir, stid))
            return show_rc
        matched_refs.extend((sdir, f".:{stid}") for sdir, stid in search_matches)
    focus_refs = None if highlight_toggle else (matched_refs or None)
    archive = o["archive"]
    if archive is not None:
        filt = "archive" if archive == "ARCHIVE" else str(archive)
        if use_ws:
            return cmd_workspace_list(
                ws_root,
                filt,
                limit=o["limit"],
                full=full,
                prefix=o["prefix"],
                ready=False,
                targets=matched_refs,
                focus=focus_refs,
            )
        return cmd_list(
            base_dir,
            filt,
            limit=o["limit"],
            full=full,
            prefix=o["prefix"],
            ready=False,
            targets=matched_refs,
            focus=focus_refs,
        )
    return cmd_chain(
        base_dir,
        limit=o["limit"],
        include_hold=o["include_hold"],
        include_done=o["include_done"],
        ready=o["ready"],
        prefix=o["prefix"],
        workspace=use_ws,
        explicit_dir=explicit_dir,
        targets=matched_refs,
        tree=o["tree"],
        numbered=o["numbered"],
        focus=focus_refs,
        status=o["status"],
    )


def _overview(
    base_dir: Path, explicit_dir: str | None, workspace: bool, full: bool, bundle: BundleOptions
) -> int:
    def render() -> int:
        return _render_overview(base_dir, explicit_dir, workspace, full)

    if bundle.enabled:
        return emit_context_bundle(bundle, base_dir, render)
    return render()


def _render_overview(base_dir: Path, explicit_dir: str | None, workspace: bool, full: bool) -> int:
    if workspace:
        return cmd_workspace_summary(resolve_workspace_root(base_dir, explicit_dir=explicit_dir), full=full)
    if not is_todo_project(base_dir) and not (base_dir / "TODO.md").is_file():
        ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
        if discover_projects(ws_root):
            return cmd_workspace_summary(ws_root, full=full)
    return cmd_summary(base_dir, full=full)


@_discovery_scoped
def _show_tasks(base_dir: Path, refs: list[str], explicit_dir: str | None, bundle: BundleOptions) -> int:
    if bundle.enabled and len(refs) == 1:
        tdir, tid = resolve_project_task_ref(base_dir, refs[0], explicit_dir=explicit_dir)
        return emit_task_bundle(bundle, tdir, tid, lambda: cmd_show(tdir, tid))
    rc = 0
    for n, ref in enumerate(refs):
        tdir, tid = resolve_project_task_ref(base_dir, ref, explicit_dir=explicit_dir)
        if n > 0:
            sys.stdout.write("\n")
        rc = max(rc, cmd_show(tdir, tid))
    return rc


def _last(base_dir: Path, filt: str | None, bundle: BundleOptions) -> int:
    if bundle.enabled:
        return emit_task_bundle(bundle, base_dir, None, lambda: cmd_last(base_dir, filt))
    return cmd_last(base_dir, filt)


CONTEXT_COMMANDS = ("show", "--show", "last", "--last", "overview", "--overview")


def _extract_session_role(prog: str, args: list[str]) -> tuple[str | None, list[str]]:
    plain = [a for a in args if not a.startswith("role=")]
    if len(plain) == len(args):
        return None, args
    if plain:
        is_context = plain[0] in CONTEXT_COMMANDS or _collect_task_refs(plain) is not None
    else:
        is_context = True
    if not is_context:
        return None, args
    role: str | None = None
    rest: list[str] = []
    for a in args:
        if a.startswith("role="):
            role = _normalize_role_override(a.split("=", 1)[1])
        else:
            rest.append(a)
    return role, rest


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    orig_args = list(args)
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
    commit = False
    no_commit = False
    workspace = False
    bundle_flags: set[str] = set()
    project_selector: str | None = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-C", "--project"):
            if i + 1 >= len(args) or not args[i + 1].strip():
                raise SystemExit(f"{prog}: {a} requires a directory or project argument")
            project_selector = args[i + 1]
            i += 2
        elif a.startswith("--project="):
            val = a.split("=", 1)[1]
            if not val.strip():
                raise SystemExit(f"{prog}: --project requires a non-empty directory or project argument")
            project_selector = val
            i += 1
        elif a == "--full":
            full = True
            i += 1
        elif a in ("--commit", "-c"):
            commit = True
            i += 1
        elif a == "--no-commit":
            no_commit = True
            i += 1
        elif a in ("--workspace", "-w"):
            workspace = True
            i += 1
        elif a in BUNDLE_FLAGS:
            bundle_flags.add(a)
            i += 1
        else:
            break
    args = args[i:]

    if "--full" in args:
        full = True
        args = [a for a in args if a != "--full"]
    if "--commit" in args or "-c" in args:
        commit = True
        args = [a for a in args if a not in ("--commit", "-c")]
    if "--no-commit" in args:
        no_commit = True
        args = [a for a in args if a != "--no-commit"]
    if "--workspace" in args or "-w" in args:
        workspace = True
        args = [a for a in args if a not in ("--workspace", "-w")]
    bundle_flags.update(a for a in args if a in BUNDLE_FLAGS)
    args = [a for a in args if a not in BUNDLE_FLAGS]
    bundle = BundleOptions(
        bundle_mode_enabled("--bundle" in bundle_flags, "--plain" in bundle_flags),
        argv=orig_args,
    )

    explicit_dir: str | None = resolve_project_or_dir(project_selector) if project_selector is not None else None
    if explicit_dir is None and args and args[0] not in KNOWN_SUBCOMMANDS and not args[0].startswith("-"):
        if Path(args[0]).is_dir():
            explicit_dir = args.pop(0)
        elif not re.fullmatch(r"[A-Za-z]\d+", args[0]) and not PROJECT_TASK_RE.match(args[0]):
            ws_probe = resolve_workspace_root(resolve_target_dir(None))
            cand = (ws_probe / args[0].replace("\\", "/").strip("/")).resolve()
            if is_todo_project(cand):
                explicit_dir = str(cand)
                args.pop(0)
    base_dir = resolve_target_dir(explicit_dir)
    bundle.role, args = _extract_session_role(prog, args)
    if args and args[0] in ("projects", "--projects"):
        return cmd_projects(base_dir, explicit_dir=explicit_dir)
    if args and args[0] in ("search", "--search-cmd"):
        if len(args) < 2 or args[1].startswith("-") or not args[1].strip():
            raise SystemExit(f"{prog}: usage: {prog} search <QUERY> [opts]")
        return _quest_log(prog, base_dir, explicit_dir, workspace, full, ["--search", args[1], *args[2:]], cmd="search")
    if args and args[0] in ("overview", "--overview"):
        if len(args) > 1:
            raise SystemExit(f"{prog}: usage: {prog} overview [--full] [-w]")
        return _overview(base_dir, explicit_dir, workspace, full, bundle)
    if not args:
        if full:
            return _overview(base_dir, explicit_dir, workspace, True, bundle)
        if bundle.enabled:
            return emit_context_bundle(
                bundle, base_dir,
                lambda: _quest_log(prog, base_dir, explicit_dir, workspace, full, []),
            )
        return _quest_log(prog, base_dir, explicit_dir, workspace, full, [])
    if args[0] in ("archive", "--archive", "-a"):
        pos, note = _parse_note_arg(args[1:])
        canceled = "--canceled" in pos or "--cancel" in pos
        pos = [p for p in pos if p not in ("--canceled", "--cancel", "--done")]
        bad_flags = [p for p in pos if p.startswith("-")]
        if bad_flags:
            raise SystemExit(f"{prog}: unknown option for archive: {bad_flags[0]}")
        if not pos:
            return cmd_archive_view(base_dir)
        raw_ids = _expand_task_id_args(pos)
        if not raw_ids:
            raise SystemExit(f"{prog}: usage: {prog} archive [<ID>...] [-m NOTE] [--canceled]")
        targets = [resolve_project_task_ref(base_dir, ref, explicit_dir=explicit_dir) for ref in raw_ids]
        return cmd_transition_batch(
            targets,
            new_status=("CANCELED" if canceled else "DONE"),
            dest_file="TODO_ARCHIVE.md",
            note=note,
            commit=commit,
            no_commit=no_commit,
        )
    if args[0] in ("add", "--add"):
        return cmd_add(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("edit", "--edit"):
        return cmd_edit(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("append", "--append"):
        return cmd_append(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("rename", "--rename"):
        return cmd_rename(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("done", "--done"):
        pos, note = _parse_note_arg(args[1:])
        bad_flags = [p for p in pos if p.startswith("-")]
        if bad_flags:
            raise SystemExit(f"{prog}: unknown option for done: {bad_flags[0]}")
        raw_ids = _expand_task_id_args(pos)
        if not raw_ids:
            raise SystemExit(f"{prog}: usage: {prog} done <ID>... [-m NOTE]")
        targets = [resolve_project_task_ref(base_dir, ref, explicit_dir=explicit_dir) for ref in raw_ids]
        return cmd_transition_batch(targets, new_status="DONE", dest_file="TODO_ARCHIVE.md", note=note, commit=commit, no_commit=no_commit)
    if args[0] in ("cancel", "canceled", "--cancel"):
        pos, note = _parse_note_arg(args[1:])
        bad_flags = [p for p in pos if p.startswith("-")]
        if bad_flags:
            raise SystemExit(f"{prog}: unknown option for cancel: {bad_flags[0]}")
        raw_ids = _expand_task_id_args(pos)
        if not raw_ids:
            raise SystemExit(f"{prog}: usage: {prog} cancel <ID>... [-m REASON]")
        targets = [resolve_project_task_ref(base_dir, ref, explicit_dir=explicit_dir) for ref in raw_ids]
        return cmd_transition_batch(targets, new_status="CANCELED", dest_file="TODO_ARCHIVE.md", note=note, commit=commit, no_commit=no_commit)
    if args[0] == "status" or (
        args[0] == "--status" and len(args) > 1 and _collect_task_refs([args[1]]) is not None
    ):
        pos, note = _parse_note_arg(args[1:])
        reopen = "--reopen" in pos
        pos = [p for p in pos if p != "--reopen"]
        bad_flags = [p for p in pos if p.startswith("-")]
        if bad_flags:
            raise SystemExit(f"{prog}: unknown option for status: {bad_flags[0]}")
        if len(pos) < 2:
            raise SystemExit(f"{prog}: usage: {prog} status <ID>... <STATUS> [-m NOTE] [--reopen]")
        raw_ids = _expand_task_id_args(pos[:-1])
        if not raw_ids:
            raise SystemExit(f"{prog}: usage: {prog} status <ID>... <STATUS> [-m NOTE] [--reopen]")
        targets = [resolve_project_task_ref(base_dir, ref, explicit_dir=explicit_dir) for ref in raw_ids]
        st_up = pos[-1].upper()
        return cmd_transition_batch(targets, new_status=st_up, dest_file=None, note=note, promote_top=(st_up in ("WIP", "NEXT")), reopen=reopen, commit=commit, no_commit=no_commit)
    if args[0] in ("reopen", "--reopen"):
        return cmd_reopen(base_dir, args[1:], commit=commit, no_commit=no_commit, explicit_dir=explicit_dir)
    if args[0] in ("queue", "--queue"):
        bad_q = [a for a in args[1:] if a.startswith("-") and a != "--all"]
        if bad_q:
            raise SystemExit(f"{prog}: unknown option for queue: {bad_q[0]}")
        q_pos = [a for a in args[1:] if a != "--all"]
        q_refs = _collect_task_refs(q_pos)
        if not q_refs:
            raise SystemExit(f"{prog}: usage: {prog} queue <ID>... [--all]")
        return _quest_log(
            prog, base_dir, explicit_dir, workspace, full, args[1:], cmd="queue", positional_focus=True
        )
    if args[0] in ("chain", "--chain"):
        return _quest_log(
            prog, base_dir, explicit_dir, workspace, full, args[1:], cmd="chain", positional_focus=True
        )
    if args[0] in ("next-id", "--next-id"):
        prefix_filter: str | None = None
        status_filter: str | None = None
        pos: list[str] = []
        i = 1
        while i < len(args):
            a = args[i]
            if a == "--prefix":
                if i + 1 >= len(args):
                    raise SystemExit(f"{prog}: {a} requires a prefix argument")
                prefix_filter = _validate_prefix_filter(args[i + 1])
                i += 2
            elif a.startswith("--prefix="):
                prefix_filter = _validate_prefix_filter(a.split("=", 1)[1])
                i += 1
            elif a == "--status":
                if i + 1 >= len(args):
                    raise SystemExit(f"{prog}: {a} requires a status argument")
                st_val = _validate_status_filter(prog, args[i + 1])
                if st_val not in ACTIVE_STATUS_ORDER and st_val not in ("ACTIVE", "ALL"):
                    raise SystemExit(
                        f"{prog}: next-id --status must be an active status ({', '.join(ACTIVE_STATUS_ORDER)}), got {args[i + 1]!r}"
                    )
                status_filter = st_val
                i += 2
            elif a.startswith("--status="):
                raw_st = a.split("=", 1)[1]
                st_val = _validate_status_filter(prog, raw_st)
                if st_val not in ACTIVE_STATUS_ORDER and st_val not in ("ACTIVE", "ALL"):
                    raise SystemExit(
                        f"{prog}: next-id --status must be an active status ({', '.join(ACTIVE_STATUS_ORDER)}), got {raw_st!r}"
                    )
                status_filter = st_val
                i += 1
            elif a.startswith("-"):
                raise SystemExit(f"{prog}: unknown option for next-id: {a}")
            else:
                pos.append(a)
                i += 1
        if len(pos) > 1:
            raise SystemExit(f"{prog}: usage: {prog} next-id [<ID>] [--prefix PREFIX] [--status STATUS]")
        if len(pos) == 1:
            tdir, tid = resolve_project_task_ref(base_dir, pos[0], explicit_dir=explicit_dir)
            return cmd_next_id(
                base_dir,
                target_dir=tdir,
                task_id=tid,
                explicit_dir=explicit_dir,
                prefix=prefix_filter,
                status=status_filter,
            )
        return cmd_next_id(base_dir, explicit_dir=explicit_dir, prefix=prefix_filter, status=status_filter)
    if args[0] in ("last-id", "--last-id"):
        if len(args) > 2:
            raise SystemExit(f"{prog}: usage: {prog} last-id [<STATUS|archive>]")
        return cmd_last_id(base_dir, args[1] if len(args) == 2 else None)
    if args[0] in ("last", "--last"):
        if len(args) > 2:
            raise SystemExit(f"{prog}: usage: {prog} last [<STATUS|archive>]")
        return _last(base_dir, args[1] if len(args) == 2 else None, bundle)
    if args[0] in ("next", "top", "--next", "--top"):
        pos, note = _parse_note_arg(args[1:])
        if args[0] == "--top" and not pos and note is None:
            return cmd_next_id(base_dir, explicit_dir=explicit_dir)
        reopen = "--reopen" in pos
        pos = [p for p in pos if p != "--reopen"]
        bad_flags = [p for p in pos if p.startswith("-")]
        if bad_flags:
            raise SystemExit(f"{prog}: unknown option for next: {bad_flags[0]}")
        raw_ids = _expand_task_id_args(pos)
        if not raw_ids:
            raise SystemExit(f"{prog}: usage: {prog} next <ID>... [-m NOTE] [--reopen]")
        targets = [resolve_project_task_ref(base_dir, ref, explicit_dir=explicit_dir) for ref in raw_ids]
        return cmd_transition_batch(targets, new_status="NEXT", dest_file="TODO.md", note=note, promote_top=True, reopen=reopen, commit=commit, no_commit=no_commit)
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
    if args[0] in ("list", "--list") or (args[0] == "-l" and not (len(args) > 1 and args[1].isdigit())):
        filt: str | None = None
        limit: int | None = None
        prefix_filter: str | None = None
        status_filter: str | None = None
        ready = False
        highlight_only = False
        search_query: str | None = None
        raw_target_refs: list[str] = []
        i = 1
        while i < len(args):
            a = args[i]
            if a in ("--limit", "-n", "-l"):
                if i + 1 >= len(args):
                    raise SystemExit(f"{prog}: {a} requires an integer argument")
                limit = _parse_limit(prog, args[i + 1])
                i += 2
            elif a.startswith("--limit="):
                limit = _parse_limit(prog, a.split("=", 1)[1])
                i += 1
            elif a == "--prefix":
                if i + 1 >= len(args):
                    raise SystemExit(f"{prog}: {a} requires a prefix argument")
                prefix_filter = _validate_prefix_filter(args[i + 1])
                i += 2
            elif a.startswith("--prefix="):
                prefix_filter = _validate_prefix_filter(a.split("=", 1)[1])
                i += 1
            elif a == "--status":
                if i + 1 >= len(args):
                    raise SystemExit(f"{prog}: {a} requires a status argument")
                status_filter = _validate_status_filter(prog, args[i + 1])
                i += 2
            elif a.startswith("--status="):
                status_filter = _validate_status_filter(prog, a.split("=", 1)[1])
                i += 1
            elif a in ("--search", "-s"):
                if i + 1 >= len(args) or not args[i + 1].strip():
                    raise SystemExit(f"{prog}: {a} requires a non-empty query argument")
                search_query = args[i + 1]
                i += 2
            elif a.startswith("--search="):
                raw_sq = a.split("=", 1)[1]
                if not raw_sq.strip():
                    raise SystemExit(f"{prog}: --search requires a non-empty query argument")
                search_query = raw_sq
                i += 1
            elif a in ("--highlight", "-H"):
                highlight_only = True
                i += 1
            elif a in ("--ready", "-r"):
                ready = True
                i += 1
            elif a == "--all":
                filt = "all"
                i += 1
            elif a.startswith("-"):
                raise SystemExit(f"{prog}: unknown option for list: {a}")
            else:
                ref_parts = _split_task_ref_arg(a)
                if ref_parts is not None:
                    raw_target_refs.extend(ref_parts)
                    i += 1
                elif filt is None and not raw_target_refs:
                    filt = a
                    i += 1
                else:
                    raise SystemExit(
                        f"{prog}: usage: {prog} list [filter] [<ID>...] [--prefix PREFIX] [--status STATUS] "
                        "[-r|--ready] [-s|--search QUERY] [-H|--highlight] [-l N|--limit N] [--full]"
                    )
        target_refs: list[tuple[Path, str]] = [
            resolve_filter_task_ref(base_dir, ref, explicit_dir=explicit_dir)
            for ref in raw_target_refs
        ]
        if workspace or (not is_todo_project(base_dir) and not (base_dir / "TODO.md").is_file()):
            ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
            if workspace or discover_projects(ws_root):
                return cmd_workspace_list(
                    ws_root,
                    filt,
                    limit=limit,
                    full=full,
                    prefix=prefix_filter,
                    status=status_filter,
                    ready=ready,
                    targets=target_refs,
                    search=search_query,
                    highlight_only=highlight_only,
                )
        return cmd_list(
            base_dir,
            filt,
            limit=limit,
            full=full,
            prefix=prefix_filter,
            status=status_filter,
            ready=ready,
            targets=target_refs,
            search=search_query,
            highlight_only=highlight_only,
        )
    show_usage = f"{prog}: usage: {prog} show <ID>[,<ID>...] [<ID>...] | show last [<STATUS|archive>]"
    if args[0] in ("show", "--show"):
        if len(args) < 2:
            raise SystemExit(show_usage)
        if args[1].lower() == "last":
            if len(args) > 3:
                raise SystemExit(show_usage)
            return _last(base_dir, args[2] if len(args) == 3 else None, bundle)
        show_refs = _collect_task_refs(args[1:])
        if show_refs is None:
            raise SystemExit(show_usage)
        return _show_tasks(base_dir, show_refs, explicit_dir, bundle)
    bare_refs = _collect_task_refs(args)
    if bare_refs is not None:
        return _show_tasks(base_dir, bare_refs, explicit_dir, bundle)
    if len(args) == 1 and Path(args[0]).is_dir():
        return cmd_summary(resolve_target_dir(args[0]), full=full)
    if args[0].startswith("-") or _is_status_keyword(args[0]):
        return _quest_log(prog, base_dir, explicit_dir, workspace, full, args)
    raise SystemExit(f"{prog}: unknown arguments: {' '.join(args)} (see {prog} --help)")


if __name__ == "__main__":
    raise SystemExit(main())
