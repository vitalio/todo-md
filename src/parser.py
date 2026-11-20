def is_todo_project(directory: Path) -> bool:
    try:
        return (directory / "TODO.md").is_file() and (directory / "TODO_ARCHIVE.md").is_file()
    except OSError:
        return False


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
    env_ws = os.environ.get("TODO_MD_WORKSPACE", "").strip()
    if explicit_dir:
        if is_todo_project(base_dir):
            if env_ws:
                p = Path(env_ws).expanduser().resolve()
                if not p.is_dir():
                    raise SystemExit(f"{prog_name()}: workspace directory not found: {env_ws}")
                try:
                    base_dir.resolve().relative_to(p)
                    return p
                except ValueError:
                    pass
            cur = base_dir
            while cur.parent != cur and is_todo_project(cur.parent):
                cur = cur.parent
            return cur.parent
        return base_dir
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


def resolve_project_or_dir(selector: str) -> str:
    raw = selector.strip()
    if not raw:
        raise SystemExit(f"{prog_name()}: empty project or directory selector")
    p_cand = Path(raw).expanduser()
    if p_cand.is_dir():
        return str(p_cand.resolve())
    looks_like_path = (
        raw.startswith(("/", "~", "./", "../", ".\\", "..\\"))
        or p_cand.is_absolute()
    )
    if looks_like_path:
        raise SystemExit(f"{prog_name()}: directory not found: {selector}")

    norm = raw.replace("\\", "/").strip("/")
    if not norm or ".." in norm.split("/"):
        raise SystemExit(f"{prog_name()}: target directory or project not found: {selector}")

    cwd_res = Path.cwd().resolve()
    probe_bases: list[Path] = [cwd_res]
    for anc in cwd_res.parents:
        if is_todo_project(anc):
            if anc not in probe_bases:
                probe_bases.append(anc)
            break
    env_cwd = os.environ.get("TODO_MD_CWD", "").strip()
    if env_cwd:
        p_env_cwd = Path(env_cwd).expanduser().resolve()
        if p_env_cwd.is_dir() and p_env_cwd not in probe_bases:
            probe_bases.append(p_env_cwd)

    seen_ws: set[Path] = set()
    for base in probe_bases:
        ws_root = resolve_workspace_root(base).resolve()
        if ws_root in seen_ws:
            continue
        seen_ws.add(ws_root)
        cand = (ws_root / norm).resolve()
        try:
            cand.relative_to(ws_root)
            if is_todo_project(cand):
                return str(cand)
        except ValueError:
            pass
        projects = discover_projects(ws_root)
        exact = [p for rel, p in projects if rel == norm]
        if exact:
            return str(exact[0].resolve())
        if "/" not in norm:
            by_name = [(rel, p) for rel, p in projects if Path(rel).name == norm]
            if len(by_name) == 1:
                return str(by_name[0][1].resolve())
            if len(by_name) > 1:
                matches = ", ".join(rel for rel, _ in by_name)
                raise SystemExit(
                    f"{prog_name()}: ambiguous project name {selector!r}; matches: {matches}"
                )

    raise SystemExit(f"{prog_name()}: target directory or project not found: {selector}")


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
            if not is_todo_project(target_dir) and ws_root.name == ".todo_projects":
                alt_dir = (ws_root.parent / proj_name).resolve()
                if is_todo_project(alt_dir):
                    target_dir = alt_dir
            if not is_todo_project(target_dir):
                results.append((ref, "MISSING", ""))
                continue
        else:
            target_dir = base_dir
            tid = ref.upper()
        statuses = _task_statuses(target_dir)
        st = statuses.get(tid)
        if st is None:
            results.append((ref, "MISSING", ""))
        else:
            results.append((ref, st, VALID_STATUSES.get(st, "")))
    return results


def build_dependency_dag(
    base_dir: Path,
    target_dir: Path,
    task_id: str,
    explicit_dir: str | None = None,
    stop_at_done: bool = False,
) -> dict[str, object]:
    ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    ws_resolved = ws_root.resolve()
    disp_resolved = base_dir.resolve()
    disp_is_proj = is_todo_project(disp_resolved)
    task_cache: dict[Path, dict[str, dict[str, object]]] = {}

    def _task_map(proj_dir: Path) -> dict[str, dict[str, object]]:
        p_res = proj_dir.resolve()
        if p_res not in task_cache:
            mapping: dict[str, dict[str, object]] = {}
            if is_todo_project(p_res):
                for t in collect_all_tasks(p_res):
                    mapping[str(t["id"]).upper()] = t
            task_cache[p_res] = mapping
        return task_cache[p_res]

    def _resolve_ref(cur_dir: Path, ref: str) -> tuple[Path, str]:
        pm = PROJECT_TASK_RE.match(ref)
        if pm:
            proj_name = pm.group(1).strip().replace("\\", "/").strip("/")
            return (ws_resolved / proj_name).resolve(), pm.group(2).upper()
        return cur_dir.resolve(), ref.upper()

    def _format_ref(node_key: tuple[Path, str]) -> str:
        ndir, ntid = node_key
        if disp_is_proj and ndir == disp_resolved:
            return ntid
        try:
            rel = ndir.relative_to(ws_resolved).as_posix()
            if rel and rel != ".":
                return f"{rel}:{ntid}"
        except ValueError:
            pass
        return f"{ndir.name}:{ntid}"

    root = (target_dir.resolve(), task_id.strip().upper())
    nodes: dict[tuple[Path, str], dict[str, object]] = {}
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    prereq_sets: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    order_idx: dict[tuple[Path, str], int] = {}
    syntax_errors: list[str] = []

    def _ensure_node_slot(k: tuple[Path, str]) -> None:
        if k not in prereqs:
            prereqs[k] = []
            prereq_sets[k] = set()

    def _add_prereq(node: tuple[Path, str], dep: tuple[Path, str]) -> None:
        _ensure_node_slot(node)
        _ensure_node_slot(dep)
        if dep not in prereq_sets[node]:
            prereq_sets[node].add(dep)
            prereqs[node].append(dep)

    def _visit(node_key: tuple[Path, str]) -> None:
        if node_key in nodes:
            return
        ndir, ntid = node_key
        _ensure_node_slot(node_key)
        tdict = _task_map(ndir).get(ntid)
        if tdict is None:
            missing_title = "(missing task)" if is_todo_project(ndir) else "(unknown project)"
            nodes[node_key] = {
                "id": ntid,
                "status": "MISSING",
                "emoji": "",
                "title": missing_title,
                "exists": False,
                "ref": _format_ref(node_key),
            }
            order_idx[node_key] = len(order_idx)
            return

        st = str(tdict["status"])
        nodes[node_key] = {
            **tdict,
            "exists": True,
            "ref": _format_ref(node_key),
        }
        clauses, errs = parse_dependency_clauses(str(tdict["section"]))
        for err in errs:
            syntax_errors.append(f"{_format_ref(node_key)}: {err}")

        if stop_at_done and st == "DONE":
            done_refs_to_visit: list[tuple[Path, str]] = []
            for clause in clauses:
                resolved_stages = [[_resolve_ref(ndir, r) for r in stage] for stage in clause]
                for i, stage_keys in enumerate(resolved_stages):
                    for k in stage_keys:
                        kt = _task_map(k[0]).get(k[1])
                        if kt is not None and str(kt["status"]) == "DONE":
                            _add_prereq(node_key, k)
                            done_refs_to_visit.append(k)
                            if i > 0:
                                for prev_k in resolved_stages[i - 1]:
                                    pt = _task_map(prev_k[0]).get(prev_k[1])
                                    if pt is not None and str(pt["status"]) == "DONE":
                                        _add_prereq(k, prev_k)
            for k in done_refs_to_visit:
                _visit(k)
            order_idx[node_key] = len(order_idx)
            return

        to_visit: list[tuple[Path, str]] = []
        for clause in clauses:
            resolved_stages = [[_resolve_ref(ndir, r) for r in stage] for stage in clause]
            for i, stage_keys in enumerate(resolved_stages):
                for k in stage_keys:
                    _add_prereq(node_key, k)
                    to_visit.append(k)
                    if i > 0:
                        for prev_k in resolved_stages[i - 1]:
                            _add_prereq(k, prev_k)
        for k in to_visit:
            _visit(k)
        order_idx[node_key] = len(order_idx)

    _visit(root)

    in_degree: dict[tuple[Path, str], int] = {u: len(prereqs[u]) for u in nodes}
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = {u: [] for u in nodes}
    for u in nodes:
        for p in prereqs[u]:
            dependents[p].append(u)

    avail: list[tuple[int, str, tuple[Path, str]]] = [
        (order_idx.get(u, 0), str(nodes[u]["ref"]), u)
        for u in nodes
        if in_degree[u] == 0
    ]
    heapq.heapify(avail)
    topo_order: list[tuple[Path, str]] = []
    while avail:
        _, _, u = heapq.heappop(avail)
        topo_order.append(u)
        for v in dependents[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                heapq.heappush(avail, (order_idx.get(v, 0), str(nodes[v]["ref"]), v))

    cycle: list[str] = []
    if len(topo_order) < len(nodes):
        cyclic_nodes = {u for u, deg in in_degree.items() if deg > 0}
        state: dict[tuple[Path, str], int] = {}
        stack: list[tuple[Path, str]] = []

        def _find_cycle(u: tuple[Path, str]) -> list[tuple[Path, str]] | None:
            state[u] = 1
            stack.append(u)
            for nxt in prereqs[u]:
                if nxt not in cyclic_nodes:
                    continue
                st_nxt = state.get(nxt, 0)
                if st_nxt == 1:
                    idx_start = stack.index(nxt)
                    return list(reversed(stack[idx_start:] + [nxt]))
                if st_nxt == 0:
                    res = _find_cycle(nxt)
                    if res:
                        return res
            stack.pop()
            state[u] = 2
            return None

        ordered_cyclic = sorted(cyclic_nodes, key=lambda k: order_idx.get(k, 0))
        for start_node in ordered_cyclic:
            if state.get(start_node, 0) == 0:
                found_cyc = _find_cycle(start_node)
                if found_cyc:
                    cycle = [str(nodes[k]["ref"]) for k in found_cyc]
                    break

    return {
        "root": root,
        "nodes": nodes,
        "prereqs": prereqs,
        "topo_order": topo_order,
        "cycle": cycle,
        "syntax_errors": syntax_errors,
    }


def _first_actionable_in_dag(
    dag: dict[str, object],
    role: str | None = None,
) -> str | None:
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    topo_order: list[tuple[Path, str]] = dag["topo_order"]  # type: ignore[assignment]
    wanted_role = role.strip().lower() if role is not None else None
    for u in topo_order:
        nd = nodes[u]
        if str(nd["status"]) not in ACTIVE_STATUS_ORDER:
            continue
        if wanted_role is not None and not _task_matches_role(nd, wanted_role):
            continue
        blockers = [p for p in prereqs[u] if str(nodes[p]["status"]) != "DONE"]
        if not blockers:
            return str(nd["ref"])
    return None


def _task_dependency_info(
    base_dir: Path,
    task: dict[str, object],
    explicit_dir: str | None = None,
) -> tuple[bool, str]:
    sec = str(task["section"])
    _, syntax_errs = parse_dependency_clauses(sec)
    deps = parse_task_dependencies(sec)
    if not deps and not syntax_errs:
        return False, ""
    resolved = resolve_dependency_statuses(base_dir, deps, explicit_dir=explicit_dir) if deps else []
    blocked = [f"{r} ({st})" for r, st, _ in resolved if st != "DONE"]
    if syntax_errs and not blocked:
        return True, f" [blocked: syntax error: {'; '.join(syntax_errs)}]"
    if not blocked and not syntax_errs:
        return False, " [deps: DONE]"
    if not syntax_errs and str(task.get("status", "")) in ACTIVE_STATUS_ORDER:
        dag = build_dependency_dag(
            base_dir,
            base_dir,
            str(task["id"]),
            explicit_dir=explicit_dir,
            stop_at_done=True,
        )
        if not dag["syntax_errors"] and not dag["cycle"]:
            nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
            prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
            root_key: tuple[Path, str] = dag["root"]  # type: ignore[assignment]
            anc_cache: dict[tuple[Path, str], set[tuple[Path, str]]] = {}

            def _unres_ancestors(u: tuple[Path, str]) -> set[tuple[Path, str]]:
                if u not in anc_cache:
                    found: set[tuple[Path, str]] = set()
                    for p in prereqs.get(u, []):
                        if str(nodes[p]["status"]) != "DONE":
                            found.add(p)
                            found.update(_unres_ancestors(p))
                    anc_cache[u] = found
                return anc_cache[u]

            def _reduced_unres_prereqs(u: tuple[Path, str]) -> list[tuple[Path, str]]:
                raw = [p for p in prereqs.get(u, []) if str(nodes[p]["status"]) != "DONE"]
                return [
                    p
                    for p in raw
                    if not any(p in _unres_ancestors(other) for other in raw if other != p)
                ]

            def _paths_to(u: tuple[Path, str]) -> list[list[tuple[Path, str]]]:
                ups = _reduced_unres_prereqs(u)
                if not ups:
                    return [[u]]
                out: list[list[tuple[Path, str]]] = []
                for p in ups:
                    for sub in _paths_to(p):
                        out.append(sub + [u])
                return out

            chain_strs: list[str] = []
            seen_chains: set[str] = set()
            for direct_blocker in _reduced_unres_prereqs(root_key):
                for path_nodes in _paths_to(direct_blocker):
                    rendered = " -> ".join(
                        f"{nodes[k]['ref']} ({nodes[k]['status']})" for k in path_nodes
                    )
                    if rendered not in seen_chains:
                        seen_chains.add(rendered)
                        chain_strs.append(rendered)
            if chain_strs:
                return True, f" [blocked: {', '.join(chain_strs)}]"
    return True, f" [blocked: {', '.join(blocked)}]"


def _is_task_blocked(
    base_dir: Path,
    task: dict[str, object],
    explicit_dir: str | None = None,
) -> bool:
    sec = str(task["section"])
    _, syntax_errs = parse_dependency_clauses(sec)
    if syntax_errs:
        return True
    deps = parse_task_dependencies(sec)
    if not deps:
        return False
    resolved = resolve_dependency_statuses(base_dir, deps, explicit_dir=explicit_dir)
    return any(st != "DONE" for _, st, _ in resolved)


def parse_task_role(section_text: str) -> str | None:
    in_fence = False
    for line in section_text.splitlines():
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = ROLE_LINE_RE.match(line)
        if m:
            role = m.group(1).strip()
            if role:
                return role.lower()
    return None


def resolve_task_role(
    task_id: str,
    section_text: str,
    status: str | None = None,
) -> str:
    explicit = parse_task_role(section_text)
    if explicit:
        return explicit.lower()
    prefix = task_id.strip().upper().split(":")[-1][:1]
    if prefix in PREFIX_DEFAULT_ROLES:
        return PREFIX_DEFAULT_ROLES[prefix]
    norm_status = (status or "").strip().upper()
    if not norm_status and section_text:
        first_line = section_text.splitlines()[0].strip()
        m = HEADING_RE.match(first_line)
        if m:
            norm_status = m.group(2).upper()
    if norm_status in ("WIP", "NEXT"):
        return "work"
    if norm_status in ("NEW", "QUESTION", "HOLD"):
        return "plan"
    return "work" if norm_status in ("DONE", "CANCELED") else "plan"


def format_dependency_summary(
    base_dir: Path,
    section_text: str,
    explicit_dir: str | None = None,
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


def _strip_heading_note(title: str) -> tuple[str, str | None]:
    m = re.match(r"^(.*?)\s+—\s+\*(.*)\*\s*$", title.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title.strip(), None


def cmd_show(base_dir: Path, task_id: str) -> int:
    target = task_id.strip().upper()
    top = highest_ids_in_use(base_dir)
    workdir = str(base_dir.resolve())
    for t in collect_all_tasks(base_dir):
        if str(t["id"]).upper() == target:
            tid = str(t["id"]).upper()
            base_title, _ = _strip_heading_note(str(t["title"]))
            section = str(t["section"])
            role = resolve_task_role(tid, section, status=str(t.get("status", "")))
            header_lines = [
                f"Task: {tid}",
                f"Title: {base_title}",
                f"Role: {role}",
                f"Workdir: {workdir}",
            ]
            headers = "\n".join(header_lines)
            dep_line = format_dependency_summary(base_dir, section)
            dep_block = f"\n{dep_line}" if dep_line else ""
            sys.stdout.write(
                f"{headers}\n\n# {t['file']}:{t['line']}\n{section}{dep_block}\n\n---\nIDs in use: {format_ids_summary(top)}\n"
            )
            return 0
    sys.stderr.write(f"{prog_name()}: task {target!r} not found in TODO*.md under {base_dir}\n")
    return 1


def _order_active_tasks(
    active_tasks: list[dict[str, object]],
    base_dir: Path | None = None,
    promote_id: str | None = None,
    ready_statuses: frozenset[str] | None = None,
) -> list[dict[str, object]]:
    if not active_tasks:
        return []
    target = promote_id.strip().upper() if promote_id else None
    task_by_id: dict[str, int] = {}
    for idx, t in enumerate(active_tasks):
        tid = str(t["id"]).upper()
        if tid not in task_by_id:
            task_by_id[tid] = idx

    blocked_flags: list[bool] = []
    direct_local_prereqs: list[list[int]] = []
    for idx, t in enumerate(active_tasks):
        if base_dir is not None:
            blocked_flags.append(_is_task_blocked(base_dir, t))
        else:
            _, syntax_errs = parse_dependency_clauses(str(t["section"]))
            deps = parse_task_dependencies(str(t["section"]))
            blocked_flags.append(bool(syntax_errs) or any(r.upper() in task_by_id for r in deps))
        local_deps: list[int] = []
        for ref in parse_task_dependencies(str(t["section"])):
            if re.fullmatch(r"[A-Za-z]\d+", ref):
                p_idx = task_by_id.get(ref.upper())
                if p_idx is not None and p_idx != idx and p_idx not in local_deps:
                    local_deps.append(p_idx)
        direct_local_prereqs.append(local_deps)

    all_local_prereqs: list[set[int]] = []
    for start_idx in range(len(active_tasks)):
        reach: set[int] = set()
        stack = list(direct_local_prereqs[start_idx])
        while stack:
            cur = stack.pop()
            if cur == start_idx or cur in reach:
                continue
            reach.add(cur)
            for nxt in direct_local_prereqs[cur]:
                if nxt not in reach and nxt != start_idx:
                    stack.append(nxt)
        all_local_prereqs.append(reach)

    grouped: dict[str, list[int]] = {}
    for idx, t in enumerate(active_tasks):
        grouped.setdefault(str(t["status"]), []).append(idx)

    def _order_bucket(st: str, bucket_indices: list[int]) -> list[int]:
        if len(bucket_indices) <= 1:
            return bucket_indices
        bucket_set = set(bucket_indices)
        in_degree: dict[int, int] = {idx: 0 for idx in bucket_indices}
        dependents: dict[int, list[int]] = {idx: [] for idx in bucket_indices}
        for u_idx in bucket_indices:
            for p_idx in all_local_prereqs[u_idx]:
                if p_idx in bucket_set and p_idx != u_idx:
                    in_degree[u_idx] += 1
                    dependents[p_idx].append(u_idx)

        use_ready = ready_statuses is None or st in ready_statuses

        def _key(idx: int) -> tuple[int, int, int]:
            is_blk = 1 if (use_ready and blocked_flags[idx]) else 0
            prom = 0 if (target and str(active_tasks[idx]["id"]).upper() == target) else 1
            return (is_blk, prom, idx)

        avail = [_key(idx) for idx in bucket_indices if in_degree[idx] == 0]
        heapq.heapify(avail)
        result: list[int] = []
        while avail:
            _, _, u = heapq.heappop(avail)
            result.append(u)
            for v in dependents[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    heapq.heappush(avail, _key(v))
        if len(result) < len(bucket_indices):
            done_set = set(result)
            remaining = [idx for idx in bucket_indices if idx not in done_set]
            remaining.sort(key=_key)
            result.extend(remaining)
        return result

    ordered: list[dict[str, object]] = []
    seen_statuses: set[str] = set()
    for st in sorted(ACTIVE_STATUS_ORDER, key=lambda s: ACTIVE_STATUS_ORDER[s]):
        seen_statuses.add(st)
        for idx in _order_bucket(st, grouped.get(st, [])):
            ordered.append(active_tasks[idx])
    for st, bucket in grouped.items():
        if st not in seen_statuses:
            for idx in _order_bucket(st, bucket):
                ordered.append(active_tasks[idx])
    return ordered


def _order_active_tasks_for_list(
    active_tasks: list[dict[str, object]],
    base_dir: Path | None = None,
) -> list[dict[str, object]]:
    return _order_active_tasks(active_tasks, base_dir=base_dir)


def _task_role_badge(task: dict[str, object]) -> str:
    role = resolve_task_role(
        str(task["id"]),
        str(task["section"]),
        status=str(task.get("status", "")),
    )
    return f"[{role}]" if role else ""


def _task_matches_role(task: dict[str, object], wanted_role: str) -> bool:
    role = resolve_task_role(
        str(task["id"]),
        str(task["section"]),
        status=str(task.get("status", "")),
    )
    return bool(role) and role.lower() == wanted_role.strip().lower()


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
) -> str:
    if not description:
        return prefix
    width = _get_terminal_columns() if term_width is None else term_width
    prefix_w = _display_width(prefix)
    avail_first = width - prefix_w
    if avail_first >= MIN_TABLE_DESC_COLS:
        cont_indent = " " * prefix_w
        wrapped = _wrap_display_lines(description, avail_first, avail_first)
    else:
        cont_indent = " " * COMPACT_CONTINUATION_INDENT
        avail_cont = max(1, width - COMPACT_CONTINUATION_INDENT)
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


def cmd_list(
    base_dir: Path,
    filt: str | None = None,
    limit: int | None = None,
    full: bool = False,
    role: str | None = None,
    ready: bool = False,
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

    if role is not None:
        wanted_role = role.strip().lower()
        shown = [t for t in shown if _task_matches_role(t, wanted_role)]

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

    if limit is not None:
        shown = shown[:limit]

    if not shown:
        notes: list[str] = []
        if role is not None:
            notes.append(f"role={role.strip()}")
        if ready:
            notes.append("ready")
        extra = f", {', '.join(notes)}" if notes else ""
        sys.stdout.write(f"No matching tasks ({mode}{extra}) in {base_dir}\n")
    elif full:
        sections = [str(t["section"]).rstrip() for t in shown]
        sys.stdout.write("\n\n".join(sections) + "\n")
    else:
        term_width = _get_terminal_columns()
        for t in shown:
            is_blocked, dep_suffix = _dep_info(t)
            emoji = "⏳" if (str(t["status"]) in ("WIP", "NEXT") and is_blocked) else str(t["emoji"])
            badge = f"{emoji} [{t['status']}]"
            role_badge = _task_role_badge(t)
            loc = str(t["file"])
            prefix = (
                f"  {_pad_display(str(t['id']), 6)}  "
                f"{_pad_display(badge, 14)}  "
                f"{_pad_display(role_badge, 10)}  "
                f"{_pad_display(loc, 16)}  "
            )
            desc = f"{t['title']}{dep_suffix}"
            sys.stdout.write(_wrap_table_row(prefix, desc, term_width) + "\n")
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
            role_entries: list[tuple[int, str]] = []
            for offset, sline in enumerate(sec.splitlines()):
                if sline.lstrip().startswith(FENCE):
                    in_role_fence = not in_role_fence
                    continue
                if in_role_fence:
                    continue
                rm = ROLE_LINE_RE.match(sline)
                if rm:
                    role_entries.append((lineno + offset, rm.group(1).strip()))
            if len(role_entries) > 1:
                dup_lines = ", ".join(str(r_line) for r_line, _ in role_entries)
                errors.append(
                    f"TODO.md:{role_entries[1][0]}: task {tid} has multiple Role: lines (lines {dup_lines})"
                )
            for r_line, raw_role in role_entries:
                low_role = raw_role.lower()
                if low_role in RETIRED_ROLES:
                    replacement = RETIRED_ROLES[low_role]
                    errors.append(
                        f"TODO.md:{r_line}: task {tid} uses retired role {raw_role!r} "
                        f"(use {replacement!r} instead)"
                    )
                elif not ROLE_NAME_RE.match(raw_role):
                    errors.append(
                        f"TODO.md:{r_line}: task {tid} has invalid Role: value {raw_role!r} "
                        "(expected lowercase identifier matching ^[a-z][a-z0-9_-]*$)"
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
    role: str | None = None,
    ready: bool = False,
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
        active = _order_active_tasks_for_list(
            [t for t in tasks if t["file"] == "TODO.md"],
            base_dir=proj_dir,
        )
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
    if role is not None:
        wanted_role = role.strip().lower()
        items = [(name, proj_dir, t) for name, proj_dir, t in items if _task_matches_role(t, wanted_role)]

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

    if limit is not None:
        items = items[:limit]
    if not items:
        notes: list[str] = []
        if role is not None:
            notes.append(f"role={role.strip()}")
        if ready:
            notes.append("ready")
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
    for name, proj_dir, t in items:
        is_blocked, dep_suffix = _ws_dep_info(proj_dir, t)
        ref = f"{name}:{t['id']}"
        emoji = "⏳" if (str(t["status"]) in ("WIP", "NEXT") and is_blocked) else str(t["emoji"])
        badge = f"{emoji} [{t['status']}]"
        role_badge = _task_role_badge(t)
        prefix = (
            f"  {_pad_display(ref, 28)}  "
            f"{_pad_display(badge, 14)}  "
            f"{_pad_display(role_badge, 10)}  "
        )
        desc = f"{t['title']}{dep_suffix}"
        sys.stdout.write(_wrap_table_row(prefix, desc, term_width) + "\n")
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


TODO_PROJECTS_FILES = (".todo_projects", ".todo_projects.local")


def _parse_todo_projects_text(raw_text: str) -> list[str]:
    entries: list[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"\s+#.*$", "", line).strip()
        for part in line.split(","):
            tok = part.strip()
            if tok and tok not in entries:
                entries.append(tok)
    return entries


def _resolve_todo_project_entry(
    entry: str,
    config_dir: Path,
    ws_root: Path,
    discovered: list[tuple[str, Path]] | None = None,
) -> Path | None:
    raw = entry.strip()
    if not raw:
        return None
    cfg_res = config_dir.resolve()
    ws_res = ws_root.resolve()
    if raw in (".", "./"):
        return cfg_res if is_todo_project(cfg_res) else None
    p_cand = Path(raw).expanduser()
    candidates: list[Path] = []
    if p_cand.is_absolute():
        candidates.append(p_cand.resolve())
    else:
        candidates.append((cfg_res / p_cand).resolve())
        candidates.append((ws_res / p_cand).resolve())
        if cfg_res.parent != cfg_res:
            candidates.append((cfg_res.parent / p_cand).resolve())
    for cand in candidates:
        if is_todo_project(cand):
            return cand
    norm = raw.replace("\\", "/").strip("/")
    if not norm or ".." in norm.split("/"):
        return None
    projs = discovered if discovered is not None else discover_projects(ws_res)
    for rel, pdir in projs:
        if rel == norm:
            return pdir.resolve()
    if "/" not in norm:
        by_name = [pdir.resolve() for rel, pdir in projs if Path(rel).name == norm]
        if len(by_name) == 1:
            return by_name[0]
    return None


def read_configured_todo_projects(
    config_dir: Path,
    ws_root: Path | None = None,
    include_env: bool = True,
    discovered: list[tuple[str, Path]] | None = None,
) -> list[Path]:
    cfg_res = config_dir.resolve()
    ws_res = (ws_root or resolve_workspace_root(cfg_res)).resolve()
    raw_entries: list[tuple[Path, str]] = []
    has_config_source = False

    for fname in TODO_PROJECTS_FILES:
        fpath = cfg_res / fname
        if fpath.is_file():
            has_config_source = True
            for item in _parse_todo_projects_text(read_if_exists(fpath)):
                raw_entries.append((cfg_res, item))
        elif fname == ".todo_projects" and fpath.is_dir():
            has_config_source = True
            if is_todo_project(fpath):
                raw_entries.append((fpath.resolve(), "."))
            for _, sub_dir in discover_projects(fpath):
                raw_entries.append((fpath.resolve(), str(sub_dir.resolve())))

    if include_env:
        env_raw = os.environ.get("TODO_MD_PROJECTS", "").strip()
        if env_raw:
            has_config_source = True
            p_env = Path(env_raw).expanduser()
            if p_env.is_file():
                env_cfg_dir = p_env.resolve().parent
                for item in _parse_todo_projects_text(read_if_exists(p_env)):
                    raw_entries.append((env_cfg_dir, item))
            else:
                tokens = [
                    t.strip()
                    for t in re.split(r"[\s,;]+|(?<!^[A-Za-z]):", env_raw)
                    if t.strip()
                ]
                for tok in tokens:
                    p_tok = Path(tok).expanduser()
                    if p_tok.is_file():
                        tok_dir = p_tok.resolve().parent
                        for item in _parse_todo_projects_text(read_if_exists(p_tok)):
                            raw_entries.append((tok_dir, item))
                    else:
                        raw_entries.append((cfg_res, tok))

    if not has_config_source:
        return []

    projs = discovered if discovered is not None else discover_projects(ws_res)
    resolved: list[Path] = []
    seen: set[Path] = set()

    def _add(p: Path | None) -> None:
        if p is not None:
            p_res = p.resolve()
            if p_res not in seen and is_todo_project(p_res):
                seen.add(p_res)
                resolved.append(p_res)

    if is_todo_project(cfg_res):
        _add(cfg_res)
    for src_dir, entry in raw_entries:
        if is_todo_project(src_dir):
            _add(src_dir)
        _add(_resolve_todo_project_entry(entry, src_dir, ws_res, discovered=projs))
    return resolved


def has_local_todo_projects_config(directory: Path) -> bool:
    d_res = directory.resolve()
    for fname in TODO_PROJECTS_FILES:
        p = d_res / fname
        if p.is_file() or (fname == ".todo_projects" and p.is_dir()):
            return True
    return False


def is_orchestrator_project(
    base_dir: Path,
    ws_root: Path | None = None,
    explicit_dir: str | None = None,
) -> bool:
    b_res = base_dir.resolve()
    if has_local_todo_projects_config(b_res):
        return True
    env_raw = os.environ.get("TODO_MD_PROJECTS", "").strip()
    if not env_raw:
        return False
    p_env = Path(env_raw).expanduser()
    if p_env.is_file():
        return p_env.resolve().parent == b_res
    if explicit_dir is not None:
        return False
    ws_res = (ws_root or resolve_workspace_root(b_res)).resolve()
    projs = discover_projects(ws_res)
    for _, pdir in projs:
        p_res = pdir.resolve()
        if p_res != b_res and has_local_todo_projects_config(p_res):
            return False
    configured = read_configured_todo_projects(b_res, ws_res, include_env=True, discovered=projs)
    cfg_set = set(configured)

    def _has_cross_project_deps(proj_dir: Path) -> bool:
        for t in parse_tasks_in_text(read_if_exists(proj_dir / "TODO.md"), "TODO.md"):
            for dep in parse_task_dependencies(str(t["section"])):
                pm = PROJECT_TASK_RE.match(dep)
                if pm:
                    dep_proj = _resolve_todo_project_entry(pm.group(1), proj_dir, ws_res, discovered=projs)
                    if dep_proj is not None and dep_proj != proj_dir and dep_proj in cfg_set:
                        return True
        return False

    for p_res in configured:
        if p_res == b_res:
            continue
        for t in parse_tasks_in_text(read_if_exists(p_res / "TODO.md"), "TODO.md"):
            for dep in parse_task_dependencies(str(t["section"])):
                pm = PROJECT_TASK_RE.match(dep)
                if pm:
                    dep_proj = _resolve_todo_project_entry(pm.group(1), p_res, ws_res, discovered=projs)
                    if dep_proj == b_res:
                        return False
    if not _has_cross_project_deps(b_res) and any(
        p_res != b_res and _has_cross_project_deps(p_res) for p_res in configured
    ):
        return False
    return True


def discover_orchestrators_for_project(
    target_dir: Path,
    ws_root: Path | None = None,
) -> tuple[list[Path], list[Path]]:
    t_res = target_dir.resolve()
    ws_res = (ws_root or resolve_workspace_root(t_res)).resolve()
    projs = discover_projects(ws_res)

    probe_dirs: list[Path] = []
    seen_probes: set[Path] = set()

    def _add_probe(d: Path) -> None:
        d_res = d.resolve()
        if d_res not in seen_probes and d_res.is_dir():
            seen_probes.add(d_res)
            probe_dirs.append(d_res)

    _add_probe(ws_res)
    for anc in t_res.parents:
        _add_probe(anc)
        if anc.resolve() == ws_res:
            break
    for _, pdir in projs:
        _add_probe(pdir)

    orchestrators: list[Path] = []
    configured_union: list[Path] = []
    seen_orch: set[Path] = set()
    seen_cfg: set[Path] = set()

    for cand in probe_dirs:
        if not has_local_todo_projects_config(cand):
            continue
        cfg_list = read_configured_todo_projects(cand, ws_res, include_env=False, discovered=projs)
        if t_res in cfg_list:
            if is_todo_project(cand) and cand not in seen_orch:
                seen_orch.add(cand)
                orchestrators.append(cand)
            tp_dir = cand / ".todo_projects"
            if tp_dir.is_dir() and is_todo_project(tp_dir) and tp_dir.resolve() not in seen_orch:
                seen_orch.add(tp_dir.resolve())
                orchestrators.append(tp_dir.resolve())
            for p in cfg_list:
                if p not in seen_cfg:
                    seen_cfg.add(p)
                    configured_union.append(p)

    env_raw = os.environ.get("TODO_MD_PROJECTS", "").strip()
    if env_raw:
        env_cfg = read_configured_todo_projects(ws_res, ws_res, include_env=True, discovered=projs)
        if t_res in env_cfg:
            for p in env_cfg:
                if p not in seen_cfg:
                    seen_cfg.add(p)
                    configured_union.append(p)
                if p != t_res and is_todo_project(p) and p not in seen_orch:
                    seen_orch.add(p)
                    orchestrators.append(p)

    return orchestrators, configured_union


def resolve_workspace_chain_projects(
    base_dir: Path,
    ws_root: Path,
) -> list[tuple[str, Path]]:
    b_res = base_dir.resolve()
    ws_res = ws_root.resolve()
    all_projs = discover_projects(ws_res)

    configured: list[Path] = []
    seen: set[Path] = set()

    def _merge(paths: list[Path]) -> None:
        for p in paths:
            p_res = p.resolve()
            if p_res not in seen and is_todo_project(p_res):
                seen.add(p_res)
                configured.append(p_res)

    if has_local_todo_projects_config(b_res) or os.environ.get("TODO_MD_PROJECTS", "").strip():
        _merge(read_configured_todo_projects(b_res, ws_res, include_env=True, discovered=all_projs))
    if not configured and has_local_todo_projects_config(ws_res):
        _merge(read_configured_todo_projects(ws_res, ws_res, include_env=True, discovered=all_projs))
    if not configured:
        for _, pdir in all_projs:
            if has_local_todo_projects_config(pdir):
                _merge(read_configured_todo_projects(pdir, ws_res, include_env=False, discovered=all_projs))

    if not configured:
        return all_projs

    result: list[tuple[str, Path]] = []
    for p_res in configured:
        try:
            rel = p_res.relative_to(ws_res).as_posix()
            label = rel if (rel and rel != ".") else p_res.name
        except ValueError:
            label = p_res.name
        result.append((label, p_res))
    return result


def build_execution_chain_dag(
    base_dir: Path,
    workspace: bool = False,
    explicit_dir: str | None = None,
) -> dict[str, object]:
    b_res = base_dir.resolve()
    ws_root = resolve_workspace_root(b_res, explicit_dir=explicit_dir)
    ws_resolved = ws_root.resolve()
    cwd_resolved = Path.cwd().resolve()

    is_orch = (not workspace) and is_orchestrator_project(b_res, ws_resolved, explicit_dir=explicit_dir)
    disp_is_proj = (not workspace) and (b_res == cwd_resolved) and is_todo_project(cwd_resolved)
    disp_resolved = cwd_resolved

    all_ws_projects = discover_projects(ws_resolved)
    project_lookup: dict[str, Path] = {}
    for rel, pdir in all_ws_projects:
        p_res = pdir.resolve()
        project_lookup[rel] = p_res
        if "/" not in rel and p_res.name not in project_lookup:
            project_lookup[p_res.name] = p_res

    seed_dirs: list[Path] = []
    seen_seed_dirs: set[Path] = set()

    def _add_seed_dir(p: Path) -> None:
        p_res = p.resolve()
        if p_res not in seen_seed_dirs and is_todo_project(p_res):
            seen_seed_dirs.add(p_res)
            seed_dirs.append(p_res)
            try:
                rel = p_res.relative_to(ws_resolved).as_posix()
                if rel and rel != ".":
                    project_lookup.setdefault(rel, p_res)
            except ValueError:
                pass
            project_lookup.setdefault(p_res.name, p_res)

    if workspace:
        for _, proj_dir in resolve_workspace_chain_projects(b_res, ws_resolved):
            _add_seed_dir(proj_dir)
    elif is_orch:
        for proj_dir in read_configured_todo_projects(
            b_res, ws_resolved, include_env=True, discovered=all_ws_projects
        ):
            _add_seed_dir(proj_dir)
    else:
        _add_seed_dir(b_res)
        orch_dirs, cfg_dirs = discover_orchestrators_for_project(b_res, ws_resolved)
        for odir in orch_dirs:
            _add_seed_dir(odir)
        for cdir in cfg_dirs:
            _add_seed_dir(cdir)

    task_cache: dict[Path, dict[str, dict[str, object]]] = {}

    def _task_map(proj_dir: Path) -> dict[str, dict[str, object]]:
        p_res = proj_dir.resolve()
        if p_res not in task_cache:
            mapping: dict[str, dict[str, object]] = {}
            if is_todo_project(p_res):
                for t in collect_all_tasks(p_res):
                    mapping[str(t["id"]).upper()] = t
            task_cache[p_res] = mapping
        return task_cache[p_res]

    def _resolve_ref(cur_dir: Path, ref: str) -> tuple[Path, str]:
        pm = PROJECT_TASK_RE.match(ref)
        if pm:
            proj_name = pm.group(1).strip().replace("\\", "/").strip("/")
            cand = (ws_resolved / proj_name).resolve()
            if is_todo_project(cand):
                return cand, pm.group(2).upper()
            if ws_resolved.name == ".todo_projects":
                alt = (ws_resolved.parent / proj_name).resolve()
                if is_todo_project(alt):
                    return alt, pm.group(2).upper()
            if proj_name in project_lookup:
                return project_lookup[proj_name], pm.group(2).upper()
            return cand, pm.group(2).upper()
        return cur_dir.resolve(), ref.upper()

    def _format_ref(node_key: tuple[Path, str]) -> str:
        ndir, ntid = node_key
        if disp_is_proj and ndir == disp_resolved:
            return ntid
        try:
            rel = ndir.relative_to(ws_resolved).as_posix()
            if rel and rel != ".":
                return f"{rel}:{ntid}"
        except ValueError:
            pass
        return f"{ndir.name}:{ntid}"

    seeds: list[tuple[Path, str]] = []
    for p_res in seed_dirs:
        for t in parse_tasks_in_text(read_if_exists(p_res / "TODO.md"), "TODO.md"):
            seeds.append((p_res, str(t["id"]).upper()))

    nodes: dict[tuple[Path, str], dict[str, object]] = {}
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    prereq_sets: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    done_prereqs: dict[tuple[Path, str], list[str]] = {}
    done_prereq_sets: dict[tuple[Path, str], set[str]] = {}
    done_nodes: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    done_closure_cache: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    done_visiting: set[tuple[Path, str]] = set()
    order_idx: dict[tuple[Path, str], int] = {}
    syntax_errors: list[str] = []

    def _ensure_node_slot(k: tuple[Path, str]) -> None:
        if k not in prereqs:
            prereqs[k] = []
            prereq_sets[k] = set()
        if k not in done_prereqs:
            done_prereqs[k] = []
            done_prereq_sets[k] = set()
        if k not in done_nodes:
            done_nodes[k] = set()

    def _add_prereq(node: tuple[Path, str], dep: tuple[Path, str]) -> None:
        _ensure_node_slot(node)
        _ensure_node_slot(dep)
        if dep not in prereq_sets[node]:
            prereq_sets[node].add(dep)
            prereqs[node].append(dep)

    def _is_done(node_key: tuple[Path, str]) -> bool:
        tdict = _task_map(node_key[0]).get(node_key[1])
        return tdict is not None and str(tdict["status"]) == "DONE"

    def _collect_done_closure(done_key: tuple[Path, str]) -> set[tuple[Path, str]]:
        if not _is_done(done_key):
            return set()
        if done_key in done_closure_cache:
            return done_closure_cache[done_key]
        if done_key in done_visiting:
            return {done_key}
        done_visiting.add(done_key)
        closure: set[tuple[Path, str]] = {done_key}
        ddir, dtid = done_key
        tdict = _task_map(ddir).get(dtid)
        if tdict is not None:
            clauses, _ = parse_dependency_clauses(str(tdict.get("section", "")))
            for clause in clauses:
                for stage in clause:
                    for raw_ref in stage:
                        dep_k = _resolve_ref(ddir, raw_ref)
                        if _is_done(dep_k):
                            closure |= _collect_done_closure(dep_k)
        done_visiting.remove(done_key)
        done_closure_cache[done_key] = closure
        return closure

    def _add_done_prereq(node: tuple[Path, str], dep: tuple[Path, str]) -> None:
        _ensure_node_slot(node)
        dep_ref = _format_ref(dep)
        if dep_ref not in done_prereq_sets[node]:
            done_prereq_sets[node].add(dep_ref)
            done_prereqs[node].append(dep_ref)
        done_nodes[node] |= _collect_done_closure(dep)

    def _visit(node_key: tuple[Path, str]) -> None:
        if node_key in nodes:
            return
        ndir, ntid = node_key
        tdict = _task_map(ndir).get(ntid)
        if tdict is None:
            _ensure_node_slot(node_key)
            missing_title = "(missing task)" if is_todo_project(ndir) else "(unknown project)"
            nodes[node_key] = {
                "id": ntid,
                "status": "MISSING",
                "emoji": "",
                "title": missing_title,
                "exists": False,
                "ref": _format_ref(node_key),
            }
            order_idx[node_key] = len(order_idx)
            return

        st = str(tdict["status"])
        if st == "DONE":
            return

        _ensure_node_slot(node_key)
        nodes[node_key] = {
            **tdict,
            "exists": True,
            "ref": _format_ref(node_key),
        }
        clauses, errs = parse_dependency_clauses(str(tdict["section"]))
        for err in errs:
            syntax_errors.append(f"{_format_ref(node_key)}: {err}")

        to_visit: list[tuple[Path, str]] = []
        for clause in clauses:
            resolved_stages = [[_resolve_ref(ndir, r) for r in stage] for stage in clause]
            for i, stage_keys in enumerate(resolved_stages):
                for k in stage_keys:
                    if _is_done(k):
                        _add_done_prereq(node_key, k)
                        continue
                    _add_prereq(node_key, k)
                    to_visit.append(k)
                    if i > 0:
                        for prev_k in resolved_stages[i - 1]:
                            if _is_done(prev_k):
                                _add_done_prereq(k, prev_k)
                                continue
                            _add_prereq(k, prev_k)
        for k in to_visit:
            _visit(k)
        order_idx[node_key] = len(order_idx)

    for seed in seeds:
        _visit(seed)

    in_degree: dict[tuple[Path, str], int] = {u: len(prereqs[u]) for u in nodes}
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = {u: [] for u in nodes}
    for u in nodes:
        for p in prereqs[u]:
            dependents[p].append(u)

    unblocks = compute_unblock_counts(nodes, dependents)

    def _canon_ref_key(u: tuple[Path, str]) -> tuple[str, str, str]:
        return (str(nodes[u]["ref"]), u[0].as_posix(), u[1])

    def _sort_key(u: tuple[Path, str]) -> tuple[int, int, int, tuple[str, str, str], tuple[Path, str]]:
        st = str(nodes[u]["status"])
        prio = ACTIVE_STATUS_ORDER.get(st, 99)
        return (prio, -unblocks.get(u, 0), order_idx.get(u, 0), _canon_ref_key(u), u)

    avail = [_sort_key(u) for u in nodes if in_degree[u] == 0]
    heapq.heapify(avail)
    topo_order: list[tuple[Path, str]] = []
    while avail:
        _, _, _, _, u = heapq.heappop(avail)
        topo_order.append(u)
        for v in dependents[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                heapq.heappush(avail, _sort_key(v))

    for u in topo_order:
        _ensure_node_slot(u)
        for p in prereqs.get(u, []):
            done_nodes[u] |= done_nodes.get(p, set())

    cycle: list[str] = []
    if len(topo_order) < len(nodes):
        cyclic_nodes = {u for u, deg in in_degree.items() if deg > 0}
        state: dict[tuple[Path, str], int] = {}
        stack: list[tuple[Path, str]] = []

        def _find_cycle(u: tuple[Path, str]) -> list[tuple[Path, str]] | None:
            state[u] = 1
            stack.append(u)
            for nxt in prereqs[u]:
                if nxt not in cyclic_nodes:
                    continue
                st_nxt = state.get(nxt, 0)
                if st_nxt == 1:
                    idx_start = stack.index(nxt)
                    return list(reversed(stack[idx_start:] + [nxt]))
                if st_nxt == 0:
                    res = _find_cycle(nxt)
                    if res:
                        return res
            stack.pop()
            state[u] = 2
            return None

        ordered_cyclic = sorted(cyclic_nodes, key=lambda k: (order_idx.get(k, 0), _canon_ref_key(k)))
        for start_node in ordered_cyclic:
            if state.get(start_node, 0) == 0:
                found_cyc = _find_cycle(start_node)
                if found_cyc:
                    cycle = [str(nodes[k]["ref"]) for k in found_cyc]
                    break

    return {
        "nodes": nodes,
        "prereqs": prereqs,
        "done_prereqs": done_prereqs,
        "done_nodes": done_nodes,
        "dependents": dependents,
        "unblocks": unblocks,
        "order_idx": order_idx,
        "topo_order": topo_order,
        "cycle": cycle,
        "syntax_errors": syntax_errors,
        "is_orchestrator": is_orch,
        "target_project": None if (workspace or is_orch) else b_res,
    }


def compute_unblock_counts(
    nodes: dict[tuple[Path, str], dict[str, object]],
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]],
    allowed: set[tuple[Path, str]] | None = None,
) -> dict[tuple[Path, str], int]:
    unblocks: dict[tuple[Path, str], int] = {}
    for u in nodes:
        if allowed is not None and u not in allowed:
            continue
        visited: set[tuple[Path, str]] = set()
        stack = list(dependents.get(u, []))
        while stack:
            cur = stack.pop()
            if cur == u or cur in visited:
                continue
            if allowed is not None and cur not in allowed:
                continue
            visited.add(cur)
            for nxt in dependents.get(cur, []):
                if nxt != u and nxt not in visited and (allowed is None or nxt in allowed):
                    stack.append(nxt)
        unblocks[u] = len(visited)
    return unblocks


def _is_ready_in_dag(
    nodes: dict[tuple[Path, str], dict[str, object]],
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]],
    u: tuple[Path, str],
    include_hold: bool = False,
) -> bool:
    st = str(nodes[u]["status"])
    if st not in ACTIVE_STATUS_ORDER:
        return False
    if not include_hold and st == "HOLD":
        return False
    return not any(str(nodes[p]["status"]) != "DONE" for p in prereqs.get(u, []))


def _canonical_task_ref_key(
    nodes: dict[tuple[Path, str], dict[str, object]],
    u: tuple[Path, str],
) -> tuple[str, str, str]:
    nd = nodes.get(u)
    ref = str(nd["ref"]) if nd is not None and "ref" in nd else u[1]
    return (ref, u[0].as_posix(), u[1])


def _is_bug_task_node(
    nodes: dict[tuple[Path, str], dict[str, object]],
    u: tuple[Path, str],
) -> bool:
    nd = nodes.get(u)
    raw_id = str(nd.get("id") or u[1]) if nd is not None else u[1]
    tid = raw_id.split(":")[-1].strip().upper()
    return tid.startswith("B")


def _is_bug_node_key(u: tuple[Path, str]) -> bool:
    tid = u[1].split(":")[-1].strip().upper()
    return tid.startswith("B")


def _resolve_node_role(
    nodes: dict[tuple[Path, str], dict[str, object]],
    u: tuple[Path, str],
) -> str | None:
    nd = nodes.get(u)
    if nd is None or not nd.get("exists", True):
        return None
    raw_role = nd.get("role")
    if not raw_role:
        raw_id = str(nd.get("id") or u[1]).split(":")[-1].strip()
        raw_role = resolve_task_role(
            raw_id,
            str(nd.get("section", "")),
            status=str(nd.get("status", "")),
        )
    if not raw_role:
        return None
    return str(raw_role).strip().lower() or None


def _resolve_node_role_ease(
    nodes: dict[tuple[Path, str], dict[str, object]],
    u: tuple[Path, str],
) -> int:
    role = _resolve_node_role(nodes, u)
    if not role:
        return len(ROLE_EASE_ORDER)
    return ROLE_EASE_ORDER.get(role, len(ROLE_EASE_ORDER))


def _resolve_node_role_weight(
    nodes: dict[tuple[Path, str], dict[str, object]],
    u: tuple[Path, str],
) -> int:
    role = _resolve_node_role(nodes, u)
    if not role:
        return ROLE_EFFORT_WEIGHTS["design"]
    return ROLE_EFFORT_WEIGHTS.get(role, ROLE_EFFORT_WEIGHTS["design"])


def _prepare_active_plan(
    dag: dict[str, object],
    include_hold: bool = False,
) -> dict[str, object]:
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    done_prereqs: dict[tuple[Path, str], list[str]] = dag.get("done_prereqs", {})  # type: ignore[assignment]
    done_nodes: dict[tuple[Path, str], set[tuple[Path, str]]] = dag.get("done_nodes", {})  # type: ignore[assignment]
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["dependents"]  # type: ignore[assignment]
    topo_order: list[tuple[Path, str]] = dag["topo_order"]  # type: ignore[assignment]
    order_idx: dict[tuple[Path, str], int] = dag.get("order_idx", {})  # type: ignore[assignment]

    held_nodes: set[tuple[Path, str]] = set()
    hold_stack = [u for u in topo_order if str(nodes[u]["status"]) == "HOLD"]
    while hold_stack:
        cur = hold_stack.pop()
        if cur in held_nodes:
            continue
        held_nodes.add(cur)
        for nxt in dependents.get(cur, []):
            if nxt not in held_nodes:
                hold_stack.append(nxt)

    if include_hold:
        active_list = list(topo_order)
        excluded_hold: set[tuple[Path, str]] = set()
    else:
        active_list = [u for u in topo_order if u not in held_nodes]
        excluded_hold = held_nodes
    active_set = set(active_list)

    active_unblocks = compute_unblock_counts(nodes, dependents, allowed=active_set)
    finale_set: set[tuple[Path, str]] = {
        u
        for u in active_list
        if bool(done_prereqs.get(u) or done_nodes.get(u))
        and _is_ready_in_dag(nodes, prereqs, u, include_hold=include_hold)
        and active_unblocks.get(u, 0) == 0
        and _resolve_node_role(nodes, u) == "work"
    }

    def _node_rank(
        u: tuple[Path, str],
        ready_step: int = 0,
    ) -> tuple[int, int, int, int, int, tuple[str, str, str], tuple[Path, str]]:
        st = str(nodes[u]["status"])
        prio = ACTIVE_STATUS_ORDER.get(st, 99)
        is_fin = 0 if u in finale_set else 1
        return (
            prio,
            is_fin,
            -active_unblocks.get(u, 0),
            -ready_step,
            order_idx.get(u, 0),
            _canonical_task_ref_key(nodes, u),
            u,
        )

    in_deg = {u: sum(1 for p in prereqs.get(u, []) if p in active_set) for u in active_list}
    avail = [_node_rank(u, 0) for u in active_list if in_deg[u] == 0]
    heapq.heapify(avail)
    ranked_active: list[tuple[Path, str]] = []
    step_num = 0
    while avail:
        *_, u = heapq.heappop(avail)
        ranked_active.append(u)
        step_num += 1
        for v in dependents.get(u, []):
            if v in active_set:
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    heapq.heappush(avail, _node_rank(v, step_num))
    if len(ranked_active) < len(active_list):
        seen_ranked = set(ranked_active)
        rest = [u for u in active_list if u not in seen_ranked]
        rest.sort(key=_node_rank)
        ranked_active.extend(rest)

    return {
        "active_list": active_list,
        "active_set": active_set,
        "ranked_active": ranked_active,
        "active_unblocks": active_unblocks,
        "excluded_hold": excluded_hold,
        "finale_set": finale_set,
        "node_rank": _node_rank,
    }


def plan_execution_chains(
    dag: dict[str, object],
    include_hold: bool = False,
    ready_only: bool = False,
    limit: int | None = None,
) -> dict[str, object]:
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    done_nodes: dict[tuple[Path, str], set[tuple[Path, str]]] = dag.get("done_nodes", {})  # type: ignore[assignment]
    order_idx: dict[tuple[Path, str], int] = dag.get("order_idx", {})  # type: ignore[assignment]
    prep = _prepare_active_plan(dag, include_hold=include_hold)
    active_list: list[tuple[Path, str]] = prep["active_list"]  # type: ignore[assignment]
    active_set: set[tuple[Path, str]] = prep["active_set"]  # type: ignore[assignment]
    ranked_active: list[tuple[Path, str]] = prep["ranked_active"]  # type: ignore[assignment]
    active_unblocks: dict[tuple[Path, str], int] = prep["active_unblocks"]  # type: ignore[assignment]
    excluded_hold: set[tuple[Path, str]] = prep["excluded_hold"]  # type: ignore[assignment]
    finale_set: set[tuple[Path, str]] = prep["finale_set"]  # type: ignore[assignment]
    _node_rank = prep["node_rank"]  # type: ignore[assignment]

    if ready_only:
        ready_nodes = [
            u
            for u in ranked_active
            if _is_ready_in_dag(nodes, prereqs, u, include_hold=include_hold)
        ]
        ready_nodes.sort(key=_node_rank)
        if limit is not None:
            ready_nodes = ready_nodes[:limit]
        return {
            "active_nodes": ranked_active,
            "active_unblocks": active_unblocks,
            "excluded_hold": excluded_hold,
            "finale_set": finale_set,
            "finales": [],
            "chains": [],
            "chain_stats": [],
            "standalone": [],
            "ready_tasks": ready_nodes,
        }

    undirected_sets: dict[tuple[Path, str], set[tuple[Path, str]]] = {u: set() for u in active_list}
    for u in active_list:
        for p in prereqs.get(u, []):
            if p in active_set:
                undirected_sets[u].add(p)
                undirected_sets[p].add(u)
    undirected: dict[tuple[Path, str], list[tuple[Path, str]]] = {
        u: sorted(undirected_sets[u], key=lambda k: _canonical_task_ref_key(nodes, k))
        for u in active_list
    }

    rank_pos = {u: idx for idx, u in enumerate(ranked_active)}
    visited_comp: set[tuple[Path, str]] = set()
    finales: list[tuple[Path, str]] = []
    raw_chains: list[list[tuple[Path, str]]] = []
    standalone: list[tuple[Path, str]] = []
    for u in ranked_active:
        if u in visited_comp:
            continue
        comp: list[tuple[Path, str]] = []
        stack = [u]
        visited_comp.add(u)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in undirected[cur]:
                if nb not in visited_comp:
                    visited_comp.add(nb)
                    stack.append(nb)
        comp.sort(key=lambda k: (rank_pos[k], _canonical_task_ref_key(nodes, k)))
        if len(comp) >= 2:
            raw_chains.append(comp)
        elif comp[0] in finale_set:
            finales.append(comp[0])
        elif bool(done_nodes.get(comp[0]) or dag.get("done_prereqs", {}).get(comp[0])):  # type: ignore[union-attr]
            raw_chains.append(comp)
        else:
            standalone.append(comp[0])

    def _finale_sort_key(
        u: tuple[Path, str],
    ) -> tuple[int, int, int, int, tuple[str, str, str]]:
        return (
            0 if _is_bug_task_node(nodes, u) else 1,
            ACTIVE_STATUS_ORDER.get(str(nodes[u]["status"]), 99),
            -len(done_nodes.get(u, set())),
            order_idx.get(u, 0),
            _canonical_task_ref_key(nodes, u),
        )

    def _standalone_sort_key(
        u: tuple[Path, str],
    ) -> tuple[int, int, int, int, tuple[str, str, str]]:
        return (
            0 if _is_bug_task_node(nodes, u) else 1,
            _resolve_node_role_ease(nodes, u),
            ACTIVE_STATUS_ORDER.get(str(nodes[u]["status"]), 99),
            order_idx.get(u, 0),
            _canonical_task_ref_key(nodes, u),
        )

    def _build_chain_entry(comp: list[tuple[Path, str]]) -> dict[str, object]:
        comp_done: set[tuple[Path, str]] = set()
        for u in comp:
            comp_done |= done_nodes.get(u, set())
        open_count = len(comp)
        done_count = len(comp_done)
        total_tasks = done_count + open_count
        progress_pct = round(100 * done_count / total_tasks) if total_tasks > 0 else 0

        ready_in_comp = [
            u
            for u in comp
            if _is_ready_in_dag(nodes, prereqs, u, include_hold=include_hold)
        ]
        ready_set = set(ready_in_comp)
        ready_bugs = sum(1 for u in ready_in_comp if _is_bug_task_node(nodes, u))
        open_bugs = sum(1 for u in comp if _is_bug_task_node(nodes, u))
        done_bugs = sum(1 for d in comp_done if _is_bug_node_key(d))
        total_bugs = open_bugs + done_bugs

        dist: dict[tuple[Path, str], int] = {}
        for u in comp:
            if u in ready_set:
                dist[u] = 0
            else:
                parent_dists = [dist[p] for p in prereqs.get(u, []) if p in dist]
                dist[u] = (min(parent_dists) + 1) if parent_dists else 0
        open_bug_dists = [dist[u] for u in comp if _is_bug_task_node(nodes, u)]
        min_bug_dist = min(open_bug_dists) if open_bug_dists else None
        bug_dist_rank = min_bug_dist if min_bug_dist is not None else 10**9

        open_eases = [_resolve_node_role_ease(nodes, u) for u in comp]
        ready_eases = [_resolve_node_role_ease(nodes, u) for u in ready_in_comp] or open_eases
        rem_eases = [_resolve_node_role_ease(nodes, u) for u in comp if u not in ready_set] or open_eases
        ready_role_ease = min(ready_eases) if ready_eases else len(ROLE_EASE_ORDER)
        min_rem_ease = min(rem_eases) if rem_eases else len(ROLE_EASE_ORDER)
        max_rem_ease = max(rem_eases) if rem_eases else len(ROLE_EASE_ORDER)
        max_open_ease = max(open_eases) if open_eases else len(ROLE_EASE_ORDER)
        role_ease_key = (ready_role_ease, min_rem_ease, max_rem_ease, max_open_ease)

        remaining_effort = sum(_resolve_node_role_weight(nodes, u) for u in comp)
        weighted_denom = done_count + remaining_effort
        weighted_velocity = (done_count / weighted_denom) if weighted_denom > 0 else 0.0

        best_status = min(ACTIVE_STATUS_ORDER.get(str(nodes[u]["status"]), 99) for u in comp)
        canon_ref = _canonical_task_ref_key(nodes, comp[0])

        rank_key = (
            -ready_bugs,
            -total_bugs,
            bug_dist_rank,
            role_ease_key,
            best_status,
            -weighted_velocity,
            -total_tasks,
            -done_count,
            remaining_effort,
            canon_ref,
        )
        return {
            "nodes": comp,
            "done_nodes": comp_done,
            "open_count": open_count,
            "done_count": done_count,
            "total_tasks": total_tasks,
            "progress_pct": progress_pct,
            "remaining_effort": remaining_effort,
            "weighted_velocity": weighted_velocity,
            "ready_bugs": ready_bugs,
            "open_bugs": open_bugs,
            "done_bugs": done_bugs,
            "total_bugs": total_bugs,
            "min_bug_dist": min_bug_dist,
            "role_ease": role_ease_key,
            "best_status": best_status,
            "rank_key": rank_key,
        }

    finales.sort(key=_finale_sort_key)
    chain_entries = [_build_chain_entry(comp) for comp in raw_chains]
    chain_entries.sort(key=lambda entry: entry["rank_key"])  # type: ignore[arg-type, return-value]
    chains: list[list[tuple[Path, str]]] = [entry["nodes"] for entry in chain_entries]  # type: ignore[misc]
    standalone.sort(key=_standalone_sort_key)

    if limit is not None:
        rem = limit
        limited_finales = finales[:rem] if rem > 0 else []
        rem -= len(limited_finales)
        limited_chains: list[list[tuple[Path, str]]] = []
        limited_stats: list[dict[str, object]] = []
        for comp, entry in zip(chains, chain_entries):
            if rem <= 0:
                break
            take = comp[:rem]
            limited_chains.append(take)
            limited_stats.append({**entry, "nodes": take})
            rem -= len(take)
        limited_standalone = standalone[:rem] if rem > 0 else []
        finales = limited_finales
        chains = limited_chains
        chain_entries = limited_stats
        standalone = limited_standalone

    return {
        "active_nodes": ranked_active,
        "active_unblocks": active_unblocks,
        "excluded_hold": excluded_hold,
        "finale_set": finale_set,
        "finales": finales,
        "chains": chains,
        "chain_stats": chain_entries,
        "standalone": standalone,
        "ready_tasks": [],
    }

def plan_execution_chains_by_role(
    dag: dict[str, object],
    include_hold: bool = False,
    ready_only: bool = False,
    limit: int | None = None,
    role: str | None = None,
) -> dict[str, object]:
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    prep = _prepare_active_plan(dag, include_hold=include_hold)
    ranked_active: list[tuple[Path, str]] = prep["ranked_active"]  # type: ignore[assignment]
    active_unblocks: dict[tuple[Path, str], int] = prep["active_unblocks"]  # type: ignore[assignment]
    excluded_hold: set[tuple[Path, str]] = prep["excluded_hold"]  # type: ignore[assignment]
    finale_set: set[tuple[Path, str]] = prep["finale_set"]  # type: ignore[assignment]

    trans_cache: dict[tuple[Path, str], set[tuple[Path, str]]] = {}

    def _trans_prereqs(u: tuple[Path, str]) -> set[tuple[Path, str]]:
        if u not in trans_cache:
            seen: set[tuple[Path, str]] = set()
            stack = list(prereqs.get(u, []))
            while stack:
                cur = stack.pop()
                if cur == u or cur in seen:
                    continue
                seen.add(cur)
                for nxt in prereqs.get(cur, []):
                    if nxt != u and nxt not in seen:
                        stack.append(nxt)
            trans_cache[u] = seen
        return trans_cache[u]

    def _node_role(u: tuple[Path, str]) -> str | None:
        nd = nodes[u]
        if not nd.get("exists"):
            return None
        resolved = resolve_task_role(
            str(nd["id"]),
            str(nd["section"]),
            status=str(nd.get("status", "")),
        )
        return resolved.strip().lower() if resolved else None

    q_work: list[tuple[Path, str]] = []
    q_plan: list[tuple[Path, str]] = []
    q_design: list[tuple[Path, str]] = []
    q_deferred_work: list[tuple[Path, str]] = []
    q_other: list[tuple[Path, str]] = []

    wanted_role = role.strip().lower() if role is not None else None

    for u in ranked_active:
        if ready_only and not _is_ready_in_dag(nodes, prereqs, u, include_hold=include_hold):
            continue
        u_role = _node_role(u)
        if wanted_role is not None and u_role != wanted_role:
            continue
        dep_roles = {_node_role(p) for p in _trans_prereqs(u)}
        if u_role == "work":
            if not dep_roles or dep_roles <= {"work"}:
                q_work.append(u)
            elif not ready_only:
                q_deferred_work.append(u)
        elif u_role == "plan":
            if not dep_roles or dep_roles <= {"work", "plan"}:
                q_plan.append(u)
            else:
                q_other.append(u)
        elif u_role == "design":
            q_design.append(u)
        else:
            q_other.append(u)

    queues: list[tuple[str, str, list[tuple[Path, str]]]] = [
        ("work", "Queue 1 (work)", q_work),
        ("plan", "Queue 2 (plan)", q_plan),
        ("design", "Queue 3 (design)", q_design),
    ]
    if not ready_only:
        queues.append(("deferred_work", "Queue 4 (deferred work)", q_deferred_work))
    if q_other:
        queues.append(("other", "Other tasks", q_other))

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

    return {
        "active_nodes": ranked_active,
        "active_unblocks": active_unblocks,
        "excluded_hold": excluded_hold,
        "finale_set": finale_set,
        "queues": queues,
    }


def find_newly_unblocked_tasks(
    completed_dir: Path,
    completed_id: str,
) -> list[str]:
    comp_res = completed_dir.resolve()
    comp_tid = completed_id.strip().upper()
    ws_root = resolve_workspace_root(comp_res)
    ws_res = ws_root.resolve()

    candidate_dirs: list[Path] = []
    seen_dirs: set[Path] = set()

    def _add_project(p: Path) -> None:
        p_res = p.resolve()
        if p_res not in seen_dirs and is_todo_project(p_res):
            seen_dirs.add(p_res)
            candidate_dirs.append(p_res)

    _add_project(comp_res)
    _add_project(ws_res)
    for _, proj_dir in discover_projects(ws_res):
        _add_project(proj_dir)

    probe_roots: list[Path] = [comp_res]
    for anc in comp_res.parents:
        probe_roots.append(anc)
        if anc == ws_res:
            break
    if ws_res not in probe_roots:
        probe_roots.append(ws_res)

    for root in probe_roots:
        tp = root / ".todo_projects"
        if tp.is_dir():
            _add_project(tp)
            for _, proj_dir in discover_projects(tp):
                _add_project(proj_dir)
        elif tp.is_file():
            for raw_line in read_if_exists(tp).splitlines():
                entry = raw_line.strip()
                if not entry or entry.startswith("#"):
                    continue
                p_cand = Path(entry).expanduser()
                if not p_cand.is_absolute():
                    p_cand = root / p_cand
                _add_project(p_cand)

    def _format_unblocked_ref(proj_dir: Path, tid: str) -> str:
        if proj_dir == comp_res:
            return tid
        try:
            rel = proj_dir.relative_to(ws_res).as_posix()
            if rel and rel != ".":
                return f"{rel}:{tid}"
        except ValueError:
            pass
        return f"{proj_dir.name}:{tid}"

    unblocked: list[str] = []
    seen_refs: set[str] = set()
    for proj_dir in candidate_dirs:
        todo_path = proj_dir / "TODO.md"
        if not todo_path.is_file():
            continue
        proj_ws = resolve_workspace_root(proj_dir).resolve()
        for t in parse_tasks_in_text(read_if_exists(todo_path), "TODO.md"):
            tid = str(t["id"]).upper()
            if proj_dir == comp_res and tid == comp_tid:
                continue
            sec = str(t["section"])
            _, syntax_errs = parse_dependency_clauses(sec)
            if syntax_errs:
                continue
            deps = parse_task_dependencies(sec)
            if not deps:
                continue
            references_completed = False
            for ref in deps:
                pm = PROJECT_TASK_RE.match(ref)
                if pm:
                    p_name = pm.group(1).strip().replace("\\", "/").strip("/")
                    dep_tid = pm.group(2).upper()
                    cand_targets = {(proj_ws / p_name).resolve(), (ws_res / p_name).resolve()}
                    if proj_ws.name == ".todo_projects":
                        cand_targets.add((proj_ws.parent / p_name).resolve())
                    if comp_res in cand_targets and dep_tid == comp_tid:
                        references_completed = True
                        break
                else:
                    if proj_dir == comp_res and ref.upper() == comp_tid:
                        references_completed = True
                        break
            if not references_completed:
                continue
            resolved = resolve_dependency_statuses(proj_dir, deps)
            if resolved and all(st == "DONE" for _, st, _ in resolved):
                label = _format_unblocked_ref(proj_dir, tid)
                if label not in seen_refs:
                    seen_refs.add(label)
                    unblocked.append(label)
    return unblocked
