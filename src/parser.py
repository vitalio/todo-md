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


def _first_actionable_in_dag(dag: dict[str, object]) -> str | None:
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    topo_order: list[tuple[Path, str]] = dag["topo_order"]  # type: ignore[assignment]
    for u in topo_order:
        nd = nodes[u]
        if str(nd["status"]) not in ACTIVE_STATUS_ORDER:
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
                return role
    return None


def resolve_task_role(task_id: str, section_text: str) -> str | None:
    explicit = parse_task_role(section_text)
    if explicit:
        return explicit
    prefix = task_id.strip().upper()[:1]
    return PREFIX_DEFAULT_ROLES.get(prefix)


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
            role = resolve_task_role(tid, section)
            header_lines = [f"Task: {tid}", f"Title: {base_title}"]
            if role:
                header_lines.append(f"Role: {role}")
            header_lines.append(f"Workdir: {workdir}")
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
    role = resolve_task_role(str(task["id"]), str(task["section"]))
    return f"[{role}]" if role else ""


def _task_matches_role(task: dict[str, object], wanted_role: str) -> bool:
    role = resolve_task_role(str(task["id"]), str(task["section"]))
    return role is not None and role.lower() == wanted_role


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
        for t in shown:
            is_blocked, dep_suffix = _dep_info(t)
            emoji = "⏳" if (str(t["status"]) in ("WIP", "NEXT") and is_blocked) else str(t["emoji"])
            badge = f"{emoji} [{t['status']}]"
            role_badge = _task_role_badge(t)
            loc = str(t["file"])
            sys.stdout.write(
                f"  {str(t['id']):<6}  {badge:<14}  {role_badge:<10}  {loc:<16}  {t['title']}{dep_suffix}\n"
            )
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
    for name, proj_dir, t in items:
        is_blocked, dep_suffix = _ws_dep_info(proj_dir, t)
        ref = f"{name}:{t['id']}"
        emoji = "⏳" if (str(t["status"]) in ("WIP", "NEXT") and is_blocked) else str(t["emoji"])
        badge = f"{emoji} [{t['status']}]"
        role_badge = _task_role_badge(t)
        sys.stdout.write(f"  {ref:<28}  {badge:<14}  {role_badge:<10}  {t['title']}{dep_suffix}\n")
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


def build_execution_chain_dag(
    base_dir: Path,
    workspace: bool = False,
    explicit_dir: str | None = None,
) -> dict[str, object]:
    ws_root = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    ws_resolved = ws_root.resolve()
    disp_resolved = ws_resolved if workspace else base_dir.resolve()
    disp_is_proj = (not workspace) and is_todo_project(disp_resolved)
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

    seeds: list[tuple[Path, str]] = []
    if workspace:
        for _, proj_dir in discover_projects(ws_resolved):
            p_res = proj_dir.resolve()
            for t in parse_tasks_in_text(read_if_exists(p_res / "TODO.md"), "TODO.md"):
                seeds.append((p_res, str(t["id"]).upper()))
    else:
        p_res = base_dir.resolve()
        for t in parse_tasks_in_text(read_if_exists(p_res / "TODO.md"), "TODO.md"):
            seeds.append((p_res, str(t["id"]).upper()))

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

    def _is_done(node_key: tuple[Path, str]) -> bool:
        tdict = _task_map(node_key[0]).get(node_key[1])
        return tdict is not None and str(tdict["status"]) == "DONE"

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
                        continue
                    _add_prereq(node_key, k)
                    to_visit.append(k)
                    if i > 0:
                        for prev_k in resolved_stages[i - 1]:
                            if _is_done(prev_k):
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

    def _sort_key(u: tuple[Path, str]) -> tuple[int, int, int, str, tuple[Path, str]]:
        st = str(nodes[u]["status"])
        prio = ACTIVE_STATUS_ORDER.get(st, 99)
        return (prio, -unblocks.get(u, 0), order_idx.get(u, 0), str(nodes[u]["ref"]), u)

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
        "nodes": nodes,
        "prereqs": prereqs,
        "dependents": dependents,
        "unblocks": unblocks,
        "order_idx": order_idx,
        "topo_order": topo_order,
        "cycle": cycle,
        "syntax_errors": syntax_errors,
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


def plan_execution_chains(
    dag: dict[str, object],
    include_hold: bool = False,
    ready_only: bool = False,
    limit: int | None = None,
) -> dict[str, object]:
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
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
        active_set = set(topo_order)
        excluded_hold: set[tuple[Path, str]] = set()
    else:
        active_set = {u for u in topo_order if u not in held_nodes}
        excluded_hold = held_nodes

    active_unblocks = compute_unblock_counts(nodes, dependents, allowed=active_set)

    def _node_rank(
        u: tuple[Path, str],
        ready_step: int = 0,
    ) -> tuple[int, int, int, int, str, tuple[Path, str]]:
        st = str(nodes[u]["status"])
        prio = ACTIVE_STATUS_ORDER.get(st, 99)
        return (prio, -active_unblocks.get(u, 0), -ready_step, order_idx.get(u, 0), str(nodes[u]["ref"]), u)

    in_deg = {u: sum(1 for p in prereqs.get(u, []) if p in active_set) for u in active_set}
    avail = [_node_rank(u, 0) for u in active_set if in_deg[u] == 0]
    heapq.heapify(avail)
    ranked_active: list[tuple[Path, str]] = []
    step_num = 0
    while avail:
        _, _, _, _, _, u = heapq.heappop(avail)
        ranked_active.append(u)
        step_num += 1
        for v in dependents.get(u, []):
            if v in active_set:
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    heapq.heappush(avail, _node_rank(v, step_num))
    if len(ranked_active) < len(active_set):
        seen_ranked = set(ranked_active)
        rest = [u for u in topo_order if u in active_set and u not in seen_ranked]
        rest.sort(key=_node_rank)
        ranked_active.extend(rest)

    if ready_only:
        ready_nodes = [
            u
            for u in ranked_active
            if str(nodes[u]["status"]) in ACTIVE_STATUS_ORDER
            and (include_hold or str(nodes[u]["status"]) != "HOLD")
            and not any(str(nodes[p]["status"]) != "DONE" for p in prereqs.get(u, []))
        ]
        ready_nodes.sort(key=_node_rank)
        if limit is not None:
            ready_nodes = ready_nodes[:limit]
        return {
            "active_nodes": ranked_active,
            "active_unblocks": active_unblocks,
            "excluded_hold": excluded_hold,
            "chains": [],
            "standalone": [],
            "ready_tasks": ready_nodes,
        }

    undirected: dict[tuple[Path, str], set[tuple[Path, str]]] = {u: set() for u in active_set}
    for u in active_set:
        for p in prereqs.get(u, []):
            if p in active_set:
                undirected[u].add(p)
                undirected[p].add(u)

    rank_pos = {u: idx for idx, u in enumerate(ranked_active)}
    visited_comp: set[tuple[Path, str]] = set()
    chains: list[list[tuple[Path, str]]] = []
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
        comp.sort(key=lambda k: rank_pos[k])
        if len(comp) >= 2:
            chains.append(comp)
        else:
            standalone.append(comp[0])

    chains.sort(key=lambda comp: min(_node_rank(k) for k in comp))
    standalone.sort(key=_node_rank)

    if limit is not None:
        rem = limit
        limited_chains: list[list[tuple[Path, str]]] = []
        for comp in chains:
            if rem <= 0:
                break
            take = comp[:rem]
            limited_chains.append(take)
            rem -= len(take)
        limited_standalone = standalone[:rem] if rem > 0 else []
        chains = limited_chains
        standalone = limited_standalone

    return {
        "active_nodes": ranked_active,
        "active_unblocks": active_unblocks,
        "excluded_hold": excluded_hold,
        "chains": chains,
        "standalone": standalone,
        "ready_tasks": [],
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
