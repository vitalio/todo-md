def resolve_dependency_statuses(
    base_dir: Path,
    deps: list[str],
    explicit_dir: str | None = None,
) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    ws_root = _workspace_root_cached(base_dir, explicit_dir=explicit_dir)
    shared = _ACTIVE_DISCOVERY
    task_cache: dict[Path, dict[str, dict[str, object]]] = (
        shared.task_maps if shared is not None else {}
    )

    def _task_map(proj_dir: Path) -> dict[str, dict[str, object]]:
        p_res = proj_dir.resolve()
        if p_res not in task_cache:
            mapping: dict[str, dict[str, object]] = {}
            for t in collect_all_tasks(p_res):
                mapping[str(t["id"]).upper()] = t
            task_cache[p_res] = mapping
        return task_cache[p_res]

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
                ext_dir = lookup_external_alias(base_dir, ws_root, proj_name)
                if ext_dir is not None:
                    target_dir = ext_dir
            if not is_todo_project(target_dir):
                results.append((ref, "MISSING", ""))
                continue
        else:
            target_dir = base_dir
            tid = ref.upper()
        t = _task_map(target_dir).get(tid)
        if t is None:
            results.append((ref, "MISSING", ""))
        else:
            st = str(t["status"])
            results.append((ref, st, VALID_STATUSES.get(st, "")))
    return results

def build_dependency_dag(
    base_dir: Path,
    target_dir: Path,
    task_id: str,
    explicit_dir: str | None = None,
    stop_at_done: bool = False,
) -> dict[str, object]:
    ws_root = _workspace_root_cached(base_dir, explicit_dir=explicit_dir)
    ws_resolved = ws_root.resolve()
    disp_resolved = base_dir.resolve()
    shared = _ACTIVE_DISCOVERY
    disp_is_proj = is_todo_project(disp_resolved)
    task_cache: dict[Path, dict[str, dict[str, object]]] = (
        shared.task_maps if shared is not None else {}
    )

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
            if not is_todo_project(cand) and ws_resolved.name == ".todo_projects":
                alt = (ws_resolved.parent / proj_name).resolve()
                if is_todo_project(alt):
                    cand = alt
            if not is_todo_project(cand):
                alias = lookup_external_alias(cur_dir, ws_resolved, proj_name)
                if alias is not None:
                    cand = alias
            return cand, pm.group(2).upper()
        return cur_dir.resolve(), ref.upper()

    def _format_ref(node_key: tuple[Path, str]) -> str:
        ndir, ntid = node_key
        if disp_is_proj and ndir == disp_resolved:
            return ntid
        return f"{project_label(ndir, ws_resolved)}:{ntid}"

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

    orch_cache: dict[Path, list[Path]] = {}
    orch_edge_cache: dict[Path, dict[tuple[Path, str], list[tuple[Path, str]]]] = (
        shared.stage_edges.setdefault(ws_resolved, {})
        if shared is not None
        else {}
    )

    def _is_done_key(k: tuple[Path, str]) -> bool:
        kt = _task_map(k[0]).get(k[1])
        return kt is not None and str(kt["status"]) == "DONE"

    def _orchestrators_of(proj_dir: Path) -> list[Path]:
        p_res = proj_dir.resolve()
        if p_res not in orch_cache:
            found: list[Path] = []
            if is_todo_project(p_res):
                found, _ = discover_orchestrators_for_project(p_res, ws_resolved)
            orch_cache[p_res] = found
        return orch_cache[p_res]

    def _orch_stage_edges(orch_dir: Path) -> dict[tuple[Path, str], list[tuple[Path, str]]]:
        o_res = orch_dir.resolve()
        if o_res not in orch_edge_cache:
            edges: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
            for ot in _task_map(o_res).values():
                if str(ot["status"]) not in ACTIVE_STATUS_ORDER:
                    continue
                o_clauses, _ = parse_dependency_clauses(str(ot["section"]))
                for o_clause in o_clauses:
                    o_stages = [[_resolve_ref(o_res, r) for r in stage] for stage in o_clause]
                    for i, stage_keys in enumerate(o_stages):
                        if i == 0:
                            continue
                        for k in stage_keys:
                            lst = edges.setdefault(k, [])
                            for prev_k in o_stages[i - 1]:
                                if prev_k != k and prev_k not in lst:
                                    lst.append(prev_k)
            orch_edge_cache[o_res] = edges
        return orch_edge_cache[o_res]

    def _inbound_prereqs(node_key: tuple[Path, str]) -> list[tuple[Path, str]]:
        out: list[tuple[Path, str]] = []
        for orch_dir in _orchestrators_of(node_key[0]):
            for prev_k in _orch_stage_edges(orch_dir).get(node_key, []):
                if prev_k not in out:
                    out.append(prev_k)
        return out

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
            for prev_k in _inbound_prereqs(node_key):
                if _is_done_key(prev_k):
                    _add_prereq(node_key, prev_k)
                    done_refs_to_visit.append(prev_k)
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
        for prev_k in _inbound_prereqs(node_key):
            _add_prereq(node_key, prev_k)
            to_visit.append(prev_k)
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

def _task_dag(
    base_dir: Path,
    task: dict[str, object],
    explicit_dir: str | None = None,
) -> dict[str, object] | None:
    if str(task.get("status", "")) not in ACTIVE_STATUS_ORDER:
        return None
    dag = build_dependency_dag(
        base_dir,
        base_dir,
        str(task["id"]),
        explicit_dir=explicit_dir,
        stop_at_done=True,
    )
    if dag["syntax_errors"] or dag["cycle"]:
        return None
    return dag

def _dag_blocked_suffix(dag: dict[str, object]) -> str:
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
            for sub_path in _paths_to(p):
                out.append(sub_path + [u])
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
    return f" [blocked: {', '.join(chain_strs)}]" if chain_strs else ""

def _task_dependency_info(
    base_dir: Path,
    task: dict[str, object],
    explicit_dir: str | None = None,
) -> tuple[bool, str]:
    sec = str(task["section"])
    _, syntax_errs = parse_dependency_clauses(sec)
    deps = parse_task_dependencies(sec)
    dag = None if syntax_errs else _task_dag(base_dir, task, explicit_dir=explicit_dir)
    dag_suffix = _dag_blocked_suffix(dag) if dag is not None else ""
    if not deps and not syntax_errs:
        return (True, dag_suffix) if dag_suffix else (False, "")
    resolved = resolve_dependency_statuses(base_dir, deps, explicit_dir=explicit_dir) if deps else []
    blocked = [f"{r} ({st})" for r, st, _ in resolved if st != "DONE"]
    if syntax_errs and not blocked:
        return True, f" [blocked: syntax error: {'; '.join(syntax_errs)}]"
    if dag_suffix:
        return True, dag_suffix
    if not blocked and not syntax_errs:
        return False, " [deps: DONE]"
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
    if deps:
        resolved = resolve_dependency_statuses(base_dir, deps, explicit_dir=explicit_dir)
        if any(st != "DONE" for _, st, _ in resolved):
            return True
    dag = _task_dag(base_dir, task, explicit_dir=explicit_dir)
    if dag is None:
        return False
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    root_key: tuple[Path, str] = dag["root"]  # type: ignore[assignment]
    return any(str(nodes[p]["status"]) != "DONE" for p in prereqs.get(root_key, []))

def build_execution_chain_dag(
    base_dir: Path,
    workspace: bool = False,
    explicit_dir: str | None = None,
    include_done: bool = False,
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
            project_lookup.setdefault(project_label(p_res, ws_resolved), p_res)
            project_lookup.setdefault(p_res.name, p_res)

    if workspace:
        for _, proj_dir in resolve_workspace_chain_projects(b_res, ws_resolved):
            _add_seed_dir(proj_dir)
    elif is_orch:
        if (b_res / "TODO.md").is_file() or (b_res / "TODO_ARCHIVE.md").is_file():
            _add_seed_dir(b_res)
        for proj_dir in read_configured_todo_projects(
            b_res, ws_resolved, include_env=True, discovered=all_ws_projects
        ):
            _add_seed_dir(proj_dir)
        enclosing_orchs, enclosing_cfg = discover_orchestrators_for_project(b_res, ws_resolved)
        for extra_dir in (*enclosing_orchs, *enclosing_cfg):
            _add_seed_dir(extra_dir)
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
        return f"{project_label(ndir, ws_resolved)}:{ntid}"

    seeds: list[tuple[Path, str]] = []
    for p_res in seed_dirs:
        for t in parse_tasks_in_text(read_if_exists(p_res / "TODO.md"), "TODO.md"):
            seeds.append((p_res, str(t["id"]).upper()))

    nodes: dict[tuple[Path, str], dict[str, object]] = {}
    open_nodes: list[tuple[Path, str]] = []
    open_node_set: set[tuple[Path, str]] = set()
    done_visited: set[tuple[Path, str]] = set()
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    prereq_sets: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    done_graph_prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    done_graph_prereq_sets: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    direct_done_deps: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    direct_done_dep_sets: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    done_prereqs: dict[tuple[Path, str], list[str]] = {}
    done_prereq_sets: dict[tuple[Path, str], set[str]] = {}
    done_nodes: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    order_idx: dict[tuple[Path, str], int] = {}
    done_order_idx: dict[tuple[Path, str], int] = {}
    syntax_errors: list[str] = []

    def _ensure_node_slot(k: tuple[Path, str]) -> None:
        if k not in prereqs:
            prereqs[k] = []
            prereq_sets[k] = set()
        if k not in done_graph_prereqs:
            done_graph_prereqs[k] = []
            done_graph_prereq_sets[k] = set()
        if k not in direct_done_deps:
            direct_done_deps[k] = []
            direct_done_dep_sets[k] = set()
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

    def _add_done_graph_edge(node: tuple[Path, str], dep: tuple[Path, str]) -> None:
        if node == dep:
            return
        _ensure_node_slot(node)
        _ensure_node_slot(dep)
        if dep not in done_graph_prereq_sets[node]:
            done_graph_prereq_sets[node].add(dep)
            done_graph_prereqs[node].append(dep)

    def _visit_done(done_key: tuple[Path, str]) -> None:
        if not _is_done(done_key) or done_key in done_visited:
            return
        done_visited.add(done_key)
        _ensure_node_slot(done_key)
        ddir, dtid = done_key
        tdict = _task_map(ddir).get(dtid)
        if tdict is not None:
            nodes[done_key] = {
                **tdict,
                "exists": True,
                "ref": _format_ref(done_key),
            }
            clauses, _ = parse_dependency_clauses(str(tdict.get("section", "")))
            to_visit_done: list[tuple[Path, str]] = []
            for clause in clauses:
                resolved_stages = [[_resolve_ref(ddir, r) for r in stage] for stage in clause]
                for i, stage_keys in enumerate(resolved_stages):
                    for k in stage_keys:
                        if _is_done(k):
                            _add_done_graph_edge(done_key, k)
                            to_visit_done.append(k)
                            if i > 0:
                                for prev_k in resolved_stages[i - 1]:
                                    if _is_done(prev_k):
                                        _add_done_graph_edge(k, prev_k)
            for k in to_visit_done:
                _visit_done(k)
        done_order_idx[done_key] = len(done_order_idx)

    def _add_done_prereq(node: tuple[Path, str], dep: tuple[Path, str]) -> None:
        _ensure_node_slot(node)
        _visit_done(dep)
        dep_ref = _format_ref(dep)
        if dep_ref not in done_prereq_sets[node]:
            done_prereq_sets[node].add(dep_ref)
            done_prereqs[node].append(dep_ref)
        if dep not in direct_done_dep_sets[node]:
            direct_done_dep_sets[node].add(dep)
            direct_done_deps[node].append(dep)

    def _visit(node_key: tuple[Path, str]) -> None:
        if node_key in open_node_set:
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
            open_node_set.add(node_key)
            open_nodes.append(node_key)
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
        open_node_set.add(node_key)
        open_nodes.append(node_key)
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
                        if i > 0:
                            for prev_k in resolved_stages[i - 1]:
                                if _is_done(prev_k):
                                    _add_done_graph_edge(k, prev_k)
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

    def _canon_ref_key(u: tuple[Path, str]) -> tuple[str, str, str]:
        return (str(nodes[u]["ref"]), u[0].as_posix(), u[1])

    done_in_deg: dict[tuple[Path, str], int] = {
        d: len(done_graph_prereqs.get(d, [])) for d in done_visited
    }
    done_dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = {
        d: [] for d in done_visited
    }
    for d in done_visited:
        for p in done_graph_prereqs.get(d, []):
            if p in done_dependents:
                done_dependents[p].append(d)
    done_avail = [
        (done_order_idx.get(d, 0), _canon_ref_key(d), d)
        for d in done_visited
        if done_in_deg[d] == 0
    ]
    heapq.heapify(done_avail)
    done_topo_order: list[tuple[Path, str]] = []
    while done_avail:
        _, _, d = heapq.heappop(done_avail)
        done_topo_order.append(d)
        for v in done_dependents.get(d, []):
            done_in_deg[v] -= 1
            if done_in_deg[v] == 0:
                heapq.heappush(done_avail, (done_order_idx.get(v, 0), _canon_ref_key(v), v))
    if len(done_topo_order) < len(done_visited):
        seen_done_topo = set(done_topo_order)
        rest_done = sorted(
            [d for d in done_visited if d not in seen_done_topo],
            key=lambda d: (done_order_idx.get(d, 0), _canon_ref_key(d)),
        )
        done_topo_order.extend(rest_done)

    for d in done_topo_order:
        _ensure_node_slot(d)
        done_nodes[d].add(d)
        for p in done_graph_prereqs.get(d, []):
            done_nodes[d] |= done_nodes.get(p, {p})

    in_degree: dict[tuple[Path, str], int] = {u: len(prereqs[u]) for u in open_nodes}
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = {u: [] for u in open_nodes}
    for u in open_nodes:
        for p in prereqs[u]:
            if p in dependents:
                dependents[p].append(u)

    unblocks = compute_unblock_counts(nodes, dependents, allowed=open_node_set)

    def _sort_key(u: tuple[Path, str]) -> tuple[int, int, int, tuple[str, str, str], tuple[Path, str]]:
        st = str(nodes[u]["status"])
        prio = ACTIVE_STATUS_ORDER.get(st, 99)
        return (prio, -unblocks.get(u, 0), order_idx.get(u, 0), _canon_ref_key(u), u)

    avail = [_sort_key(u) for u in open_nodes if in_degree[u] == 0]
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
        for d in direct_done_deps.get(u, []):
            done_nodes[u] |= done_nodes.get(d, {d})
        for p in prereqs.get(u, []):
            done_nodes[u] |= done_nodes.get(p, set())

    cycle: list[str] = []
    if len(topo_order) < len(open_nodes):
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

    target_project = None if (workspace or is_orch) else b_res
    scope_dirs = [target_project] if target_project is not None else list(seed_dirs)
    top_done_candidates: list[tuple[int, int, tuple[Path, str]]] = []
    for s_idx, p_res in enumerate(scope_dirs):
        if p_res is None:
            continue
        arch_path = p_res / "TODO_ARCHIVE.md"
        if not arch_path.is_file():
            continue
        try:
            mtime_ns = arch_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        for t in parse_tasks_in_text(read_if_exists(arch_path), "TODO_ARCHIVE.md"):
            if str(t["status"]) == "DONE":
                top_done_candidates.append((mtime_ns, -s_idx, (p_res.resolve(), str(t["id"]).upper())))
                break
    latest_done_task: tuple[Path, str] | None = (
        max(top_done_candidates)[2] if top_done_candidates else None
    )

    archived_tasks: list[tuple[Path, str]] = []
    if include_done:
        seen_arch: set[tuple[Path, str]] = set()
        for p_res in seed_dirs:
            arch_path = p_res / "TODO_ARCHIVE.md"
            if not arch_path.is_file():
                continue
            for t in parse_tasks_in_text(read_if_exists(arch_path), "TODO_ARCHIVE.md"):
                arch_key = (p_res.resolve(), str(t["id"]).upper())
                if arch_key in seen_arch:
                    continue
                seen_arch.add(arch_key)
                if arch_key not in nodes:
                    _ensure_node_slot(arch_key)
                    nodes[arch_key] = {
                        **t,
                        "exists": True,
                        "ref": _format_ref(arch_key),
                    }
                archived_tasks.append(arch_key)

    return {
        "nodes": nodes,
        "archived_tasks": archived_tasks,
        "prereqs": prereqs,
        "done_prereqs": done_prereqs,
        "done_graph_prereqs": done_graph_prereqs,
        "direct_done_deps": direct_done_deps,
        "done_nodes": done_nodes,
        "done_topo_order": done_topo_order,
        "dependents": dependents,
        "unblocks": unblocks,
        "order_idx": order_idx,
        "topo_order": topo_order,
        "cycle": cycle,
        "syntax_errors": syntax_errors,
        "is_orchestrator": is_orch,
        "target_project": target_project,
        "latest_done_task": latest_done_task,
        "include_done": include_done,
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
        return f"{project_label(proj_dir, ws_res)}:{tid}"

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
                    if comp_res not in cand_targets:
                        ext_target = lookup_external_alias(proj_dir, ws_res, p_name)
                        if ext_target is not None:
                            cand_targets.add(ext_target)
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
