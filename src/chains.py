@_discovery_scoped
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

    latest_done_task: tuple[Path, str] | None = dag.get("latest_done_task")  # type: ignore[assignment]
    direct_done_deps: dict[tuple[Path, str], list[tuple[Path, str]]] = dag.get("direct_done_deps", {})  # type: ignore[assignment]

    def _is_done_node(n: tuple[Path, str]) -> bool:
        return str(nodes[n]["status"]) == "DONE"

    root_nodes = [
        u
        for u in active_list
        if not any(v in active_set for v in dependents.get(u, []))
        and (
            any(p in active_set for p in prereqs.get(u, []))
            or bool(done_prereqs.get(u) or done_nodes.get(u))
        )
    ]
    chain_counts: dict[tuple[Path, str], int] = {u: 0 for u in active_list}
    for root in root_nodes:
        cone = {root}
        cone_stack = [root]
        while cone_stack:
            cur = cone_stack.pop()
            for pre in prereqs.get(cur, []):
                if pre in active_set and pre not in cone:
                    cone.add(pre)
                    cone_stack.append(pre)
        for member in cone:
            chain_counts[member] += 1

    immediate_ready_targets: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    for u in active_list:
        immediate_ready_targets[u] = [
            v
            for v in dependents.get(u, [])
            if v in active_set and [pre for pre in prereqs.get(v, []) if not _is_done_node(pre)] == [u]
        ]
    ready_unblocks: dict[tuple[Path, str], int] = {
        u: len(targets) for u, targets in immediate_ready_targets.items()
    }
    done_counts: dict[tuple[Path, str], int] = {
        u: len(done_nodes.get(u, set())) for u in active_list
    }
    is_momentum_next: dict[tuple[Path, str], int] = {
        u: (
            0
            if latest_done_task is not None
            and (
                latest_done_task in done_nodes.get(u, set())
                or latest_done_task in direct_done_deps.get(u, [])
            )
            else 1
        )
        for u in active_list
    }

    best_chain_rank: dict[tuple[Path, str], int] = {}

    initial_in_deg = {u: sum(1 for p in prereqs.get(u, []) if p in active_set) for u in active_list}

    def _node_rank(
        u: tuple[Path, str],
        ready_step: int = 0,
    ) -> tuple[int, int, int, int, int, int, int, int, int, int, int, int, tuple[str, str, str], tuple[Path, str]]:
        st = str(nodes[u]["status"])
        prio = ACTIVE_STATUS_ORDER.get(st, 99)
        is_fin = 0 if u in finale_set else 1
        is_blocked = 0 if initial_in_deg.get(u, 0) == 0 else 1
        return (
            prio,
            is_fin,
            _resolve_node_role_ease(nodes, u),
            is_blocked,
            is_momentum_next.get(u, 1),
            best_chain_rank.get(u, 0),
            -chain_counts.get(u, 0),
            -done_counts.get(u, 0),
            -ready_unblocks.get(u, 0),
            -active_unblocks.get(u, 0),
            -ready_step,
            order_idx.get(u, 0),
            _canonical_task_ref_key(nodes, u),
            u,
        )

    in_deg = dict(initial_in_deg)
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
        "chain_counts": chain_counts,
        "done_counts": done_counts,
        "is_momentum_next": is_momentum_next,
        "ready_unblocks": ready_unblocks,
        "immediate_ready_targets": immediate_ready_targets,
        "node_rank": _node_rank,
        "best_chain_rank": best_chain_rank,
    }

def build_chain_milestone_tree(
    root: tuple[Path, str],
    display_nodes: list[tuple[Path, str]],
    nodes: dict[tuple[Path, str], dict[str, object]],
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]],
    done_nodes: dict[tuple[Path, str], set[tuple[Path, str]]] | None = None,
    direct_done_deps: dict[tuple[Path, str], list[tuple[Path, str]]] | None = None,
    done_graph_prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] | None = None,
    include_done: bool = False,
) -> dict[str, object]:
    done_map = done_nodes or {}
    direct_done_map = direct_done_deps or {}
    done_graph_map = done_graph_prereqs or {}
    display_set = set(display_nodes)
    pos_map = {u: idx for idx, u in enumerate(display_nodes)}

    raw_prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = {u: [] for u in display_nodes}
    for u in display_nodes:
        seen_p: set[tuple[Path, str]] = set()
        st = str(nodes.get(u, {}).get("status", ""))
        cand_prereqs: list[tuple[Path, str]] = []
        if st == "DONE":
            if include_done:
                cand_prereqs.extend(done_graph_map.get(u, []))
        else:
            if include_done:
                cand_prereqs.extend(direct_done_map.get(u, []))
            cand_prereqs.extend(prereqs.get(u, []))
        for p in cand_prereqs:
            if p != u and p in display_set and p not in seen_p:
                seen_p.add(p)
                raw_prereqs[u].append(p)
        raw_prereqs[u].sort(key=lambda p: pos_map.get(p, len(display_nodes)))

    anc_cache: dict[tuple[Path, str], set[tuple[Path, str]]] = {}

    def _ancestors(u: tuple[Path, str]) -> set[tuple[Path, str]]:
        if u not in anc_cache:
            found: set[tuple[Path, str]] = set()
            stack = list(raw_prereqs.get(u, []))
            while stack:
                cur = stack.pop()
                if cur == u or cur in found:
                    continue
                found.add(cur)
                for nxt in raw_prereqs.get(cur, []):
                    if nxt != u and nxt not in found:
                        stack.append(nxt)
            anc_cache[u] = found
        return anc_cache[u]

    reduced_prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    for u in display_nodes:
        direct = raw_prereqs.get(u, [])
        reduced_prereqs[u] = [
            p
            for p in direct
            if not any(p in _ancestors(other) for other in direct if other != p)
        ]

    full_open_cache: dict[tuple[Path, str], set[tuple[Path, str]]] = {}
    full_done_cache: dict[tuple[Path, str], set[tuple[Path, str]]] = {}

    def _milestone_stats(m: tuple[Path, str]) -> tuple[int, int, int, int]:
        if m not in full_open_cache:
            st_m = str(nodes.get(m, {}).get("status", ""))
            if st_m == "DONE":
                open_cone: set[tuple[Path, str]] = set()
                done_cone = set(done_map.get(m, {m}))
            else:
                open_cone = {m}
                stk = [m]
                while stk:
                    cur = stk.pop()
                    for p in prereqs.get(cur, []):
                        if p in nodes and str(nodes[p].get("status", "")) != "DONE" and p not in open_cone:
                            open_cone.add(p)
                            stk.append(p)
                done_cone = set()
                for u_open in open_cone:
                    done_cone |= set(done_map.get(u_open, set()))
            full_open_cache[m] = open_cone
            full_done_cache[m] = done_cone
        open_c = len(full_open_cache[m])
        done_c = len(full_done_cache[m])
        total_c = done_c + open_c
        pct_c = round(100 * done_c / total_c) if total_c > 0 else 0
        return total_c, pct_c, done_c, open_c

    emitted: set[tuple[Path, str]] = set()

    def _collect_subtree_nodes(u: tuple[Path, str]) -> set[tuple[Path, str]]:
        return (_ancestors(u) | {u}) & display_set

    def _is_done(u: tuple[Path, str]) -> bool:
        return str(nodes.get(u, {}).get("status", "")) == "DONE"

    def _done_claims(us: set[tuple[Path, str]]) -> set[tuple[Path, str]]:
        claimed: set[tuple[Path, str]] = set()
        for u in us:
            if _is_done(u):
                claimed |= set(done_map.get(u, {u}))
            else:
                claimed |= set(done_map.get(u, set()))
        return claimed

    def _build_node(target: tuple[Path, str], is_root: bool) -> dict[str, object]:
        claimed_before = _done_claims(emitted)
        children_items: list[dict[str, object]] = []
        direct_children = [p for p in reduced_prereqs.get(target, []) if p not in emitted]
        def _child_subtree_sort_key(c: tuple[Path, str]) -> tuple[int, int]:
            c_nodes = [u for u in (_ancestors(c) | {c}) if u in display_set and u not in emitted]
            min_pos = min((pos_map.get(u, len(display_nodes)) for u in c_nodes), default=pos_map.get(c, len(display_nodes)))
            return (min_pos, pos_map.get(c, len(display_nodes)))

        while True:
            pending_children = [c for c in direct_children if c not in emitted]
            if not pending_children:
                break
            child = min(pending_children, key=_child_subtree_sort_key)
            unemitted_prereqs = [p for p in reduced_prereqs.get(child, []) if p not in emitted]
            if unemitted_prereqs:
                children_items.append(_build_node(child, is_root=False))
            else:
                emitted.add(child)
                children_items.append(
                    {
                        "kind": "task",
                        "node": child,
                        "is_closing": False,
                    }
                )
        if target not in emitted and target in display_set:
            emitted.add(target)
            children_items.append(
                {
                    "kind": "task",
                    "node": target,
                    "is_closing": True,
                }
            )
        nd = nodes.get(target, {})
        if is_root:
            total_c, pct_c, done_c, open_c = _milestone_stats(target)
            subtree = _collect_subtree_nodes(target)
        else:
            subtree = set()
            for item in children_items:
                if item.get("kind") == "subchain":
                    subtree |= item["subtree_nodes"]  # type: ignore[arg-type]
                else:
                    subtree.add(item["node"])  # type: ignore[arg-type]
            open_c = sum(1 for u in subtree if not _is_done(u))
            done_c = len(_done_claims(subtree) - claimed_before)
            total_c = done_c + open_c
            pct_c = round(100 * done_c / total_c) if total_c > 0 else 0
        return {
            "kind": "chain" if is_root else "subchain",
            "milestone": target,
            "milestone_ref": str(nd.get("ref", target[1])),
            "milestone_title": str(nd.get("title", "")),
            "total_tasks": total_c,
            "progress_pct": pct_c,
            "done_count": done_c,
            "open_count": open_c,
            "subtree_nodes": subtree,
            "children": children_items,
        }

    if root in display_set:
        tree = _build_node(root, is_root=True)
        remaining = [u for u in display_nodes if u not in emitted]
        if remaining:
            extra_children: list[dict[str, object]] = []
            for rem_u in remaining:
                if rem_u in emitted:
                    continue
                unemitted_p = [p for p in reduced_prereqs.get(rem_u, []) if p not in emitted]
                if unemitted_p:
                    extra_children.append(_build_node(rem_u, is_root=False))
                else:
                    emitted.add(rem_u)
                    extra_children.append(
                        {
                            "kind": "task",
                            "node": rem_u,
                            "is_closing": False,
                        }
                    )
            cur_children: list[dict[str, object]] = tree["children"]  # type: ignore[assignment]
            if cur_children and cur_children[-1].get("kind") == "task" and cur_children[-1].get("node") == root:
                tree["children"] = [*cur_children[:-1], *extra_children, cur_children[-1]]
            else:
                tree["children"] = [*cur_children, *extra_children]
        return tree

    # Fallback when root itself was filtered out (e.g. --role filter or --limit truncation)
    fallback_children: list[dict[str, object]] = []
    out_deg_in_disp: dict[tuple[Path, str], int] = {u: 0 for u in display_nodes}
    for u in display_nodes:
        for p in reduced_prereqs.get(u, []):
            if p in out_deg_in_disp:
                out_deg_in_disp[p] += 1
    sinks = [u for u in display_nodes if out_deg_in_disp.get(u, 0) == 0]
    for s in sinks:
        if s in emitted:
            continue
        unemitted_p = [p for p in reduced_prereqs.get(s, []) if p not in emitted]
        if unemitted_p and len(sinks) > 1:
            fallback_children.append(_build_node(s, is_root=False))
        elif unemitted_p and len(sinks) == 1:
            sub = _build_node(s, is_root=True)
            fallback_children.extend(sub["children"])  # type: ignore[arg-type]
        else:
            emitted.add(s)
            fallback_children.append(
                {
                    "kind": "task",
                    "node": s,
                    "is_closing": (s == display_nodes[-1]),
                }
            )
    for rem_u in display_nodes:
        if rem_u not in emitted:
            emitted.add(rem_u)
            fallback_children.append(
                {
                    "kind": "task",
                    "node": rem_u,
                    "is_closing": (rem_u == root),
                }
            )
    total_c, pct_c, done_c, open_c = _milestone_stats(root)
    nd = nodes.get(root, {})
    return {
        "kind": "chain",
        "milestone": root,
        "milestone_ref": str(nd.get("ref", root[1])),
        "milestone_title": str(nd.get("title", "")),
        "total_tasks": total_c,
        "progress_pct": pct_c,
        "done_count": done_c,
        "open_count": open_c,
        "subtree_nodes": set(display_nodes),
        "children": fallback_children,
    }

def flatten_chain_tree_ordered_nodes(tree: dict[str, object]) -> list[tuple[Path, str]]:
    ordered: list[tuple[Path, str]] = []
    for child in tree.get("children", []):  # type: ignore[union-attr]
        if not isinstance(child, dict):
            continue
        if child.get("kind") == "subchain":
            ordered.extend(flatten_chain_tree_ordered_nodes(child))
        elif child.get("kind") == "task":
            u = child.get("node")
            if isinstance(u, tuple):
                ordered.append(u)
    return ordered

def plan_execution_chains(
    dag: dict[str, object],
    include_hold: bool = False,
    ready_only: bool = False,
    limit: int | None = None,
    include_done: bool = False,
) -> dict[str, object]:
    nodes: dict[tuple[Path, str], dict[str, object]] = dag["nodes"]  # type: ignore[assignment]
    prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["prereqs"]  # type: ignore[assignment]
    dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = dag["dependents"]  # type: ignore[assignment]
    done_prereqs: dict[tuple[Path, str], list[str]] = dag.get("done_prereqs", {})  # type: ignore[assignment]
    direct_done_deps: dict[tuple[Path, str], list[tuple[Path, str]]] = dag.get("direct_done_deps", {})  # type: ignore[assignment]
    done_graph_prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = dag.get("done_graph_prereqs", {})  # type: ignore[assignment]
    done_nodes: dict[tuple[Path, str], set[tuple[Path, str]]] = dag.get("done_nodes", {})  # type: ignore[assignment]
    done_topo_order: list[tuple[Path, str]] = dag.get("done_topo_order", [])  # type: ignore[assignment]
    order_idx: dict[tuple[Path, str], int] = dag.get("order_idx", {})  # type: ignore[assignment]
    show_done = include_done or bool(dag.get("include_done", False))
    prep = _prepare_active_plan(dag, include_hold=include_hold)
    active_list: list[tuple[Path, str]] = prep["active_list"]  # type: ignore[assignment]
    active_set: set[tuple[Path, str]] = prep["active_set"]  # type: ignore[assignment]
    ranked_active: list[tuple[Path, str]] = prep["ranked_active"]  # type: ignore[assignment]
    active_unblocks: dict[tuple[Path, str], int] = prep["active_unblocks"]  # type: ignore[assignment]
    excluded_hold: set[tuple[Path, str]] = prep["excluded_hold"]  # type: ignore[assignment]
    finale_set: set[tuple[Path, str]] = prep["finale_set"]  # type: ignore[assignment]
    chain_counts: dict[tuple[Path, str], int] = prep["chain_counts"]  # type: ignore[assignment]
    done_counts: dict[tuple[Path, str], int] = prep["done_counts"]  # type: ignore[assignment]
    is_momentum_next: dict[tuple[Path, str], int] = prep["is_momentum_next"]  # type: ignore[assignment]
    ready_unblocks: dict[tuple[Path, str], int] = prep["ready_unblocks"]  # type: ignore[assignment]
    immediate_ready_targets: dict[tuple[Path, str], list[tuple[Path, str]]] = prep["immediate_ready_targets"]  # type: ignore[assignment]
    _node_rank = prep["node_rank"]  # type: ignore[assignment]
    best_chain_rank: dict[tuple[Path, str], int] = prep["best_chain_rank"]  # type: ignore[assignment]

    latest_done_task: tuple[Path, str] | None = dag.get("latest_done_task")  # type: ignore[assignment]
    if latest_done_task is None and "latest_done_task" not in dag:
        proj_dirs: list[Path] = []
        seen_pdirs: set[Path] = set()
        for p_dir, _ in active_list:
            p_res = p_dir.resolve()
            if p_res not in seen_pdirs:
                seen_pdirs.add(p_res)
                proj_dirs.append(p_res)
        top_cands: list[tuple[int, int, tuple[Path, str]]] = []
        for s_idx, p_res in enumerate(proj_dirs):
            arch_path = p_res / "TODO_ARCHIVE.md"
            if not arch_path.is_file():
                continue
            try:
                mtime_ns = arch_path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0
            for t in parse_tasks_in_text(read_if_exists(arch_path), "TODO_ARCHIVE.md"):
                if str(t["status"]) == "DONE":
                    top_cands.append((mtime_ns, -s_idx, (p_res, str(t["id"]).upper())))
                    break
        if top_cands:
            latest_done_task = max(top_cands)[2]

    act_prereqs: dict[tuple[Path, str], list[tuple[Path, str]]] = {
        u: [p for p in prereqs.get(u, []) if p in active_set]
        for u in active_list
    }
    act_dependents: dict[tuple[Path, str], list[tuple[Path, str]]] = {
        u: [v for v in dependents.get(u, []) if v in active_set]
        for u in active_list
    }

    rank_pos = {u: idx for idx, u in enumerate(ranked_active)}
    root_cones: list[tuple[tuple[Path, str], list[tuple[Path, str]]]] = []
    standalone: list[tuple[Path, str]] = []

    for u in ranked_active:
        out_deg = len(act_dependents.get(u, []))
        in_deg = len(act_prereqs.get(u, []))
        has_done = bool(done_nodes.get(u) or done_prereqs.get(u))
        if out_deg > 0:
            continue
        if in_deg > 0 or has_done:
            cone_set: set[tuple[Path, str]] = {u}
            stack = [u]
            while stack:
                cur = stack.pop()
                for p in act_prereqs.get(cur, []):
                    if p not in cone_set:
                        cone_set.add(p)
                        stack.append(p)
            comp_open = sorted(
                cone_set,
                key=lambda k: (rank_pos[k], _canonical_task_ref_key(nodes, k)),
            )
            root_cones.append((u, comp_open))
        else:
            standalone.append(u)

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

    done_topo_pos = {d: idx for idx, d in enumerate(done_topo_order)}

    def _build_chain_entry(
        root: tuple[Path, str],
        comp_open: list[tuple[Path, str]],
    ) -> dict[str, object]:
        comp_done: set[tuple[Path, str]] = set()
        for u in comp_open:
            comp_done |= done_nodes.get(u, set())
        open_count = len(comp_open)
        done_count = len(comp_done)
        total_tasks = done_count + open_count
        progress_pct = round(100 * done_count / total_tasks) if total_tasks > 0 else 0

        if show_done and comp_done:
            ordered_done = sorted(
                comp_done,
                key=lambda d: (done_topo_pos.get(d, len(done_topo_pos)), _canonical_task_ref_key(nodes, d)),
            )
            base_display_nodes = [*ordered_done, *comp_open]
        else:
            base_display_nodes = list(comp_open)
        chain_tree = build_chain_milestone_tree(
            root=root,
            display_nodes=base_display_nodes,
            nodes=nodes,
            prereqs=prereqs,
            done_nodes=done_nodes,
            direct_done_deps=direct_done_deps,
            done_graph_prereqs=done_graph_prereqs,
            include_done=show_done,
        )
        display_nodes = list(base_display_nodes)

        ready_in_comp = [
            u
            for u in comp_open
            if _is_ready_in_dag(nodes, prereqs, u, include_hold=include_hold)
        ]
        ready_set = set(ready_in_comp)
        ready_bugs = sum(1 for u in ready_in_comp if _is_bug_task_node(nodes, u))
        open_bugs = sum(1 for u in comp_open if _is_bug_task_node(nodes, u))
        done_bugs = sum(1 for d in comp_done if _is_bug_node_key(d))
        total_bugs = open_bugs + done_bugs

        dist: dict[tuple[Path, str], int] = {}
        for u in comp_open:
            if u in ready_set:
                dist[u] = 0
            else:
                parent_dists = [dist[p] for p in prereqs.get(u, []) if p in dist]
                dist[u] = (min(parent_dists) + 1) if parent_dists else 0
        open_bug_dists = [dist[u] for u in comp_open if _is_bug_task_node(nodes, u)]
        if open_bug_dists:
            min_bug_dist: int | None = min(open_bug_dists)
        elif done_bugs > 0:
            min_bug_dist = 0
        else:
            min_bug_dist = None
        bug_dist_rank = min_bug_dist if min_bug_dist is not None else 10**9

        open_eases = [_resolve_node_role_ease(nodes, u) for u in comp_open]
        ready_eases = [_resolve_node_role_ease(nodes, u) for u in ready_in_comp] or open_eases
        rem_eases = [_resolve_node_role_ease(nodes, u) for u in comp_open if u not in ready_set] or open_eases
        ready_role_ease = min(ready_eases) if ready_eases else len(ROLE_EASE_ORDER)
        min_rem_ease = min(rem_eases) if rem_eases else len(ROLE_EASE_ORDER)
        max_rem_ease = max(rem_eases) if rem_eases else len(ROLE_EASE_ORDER)
        max_open_ease = max(open_eases) if open_eases else len(ROLE_EASE_ORDER)
        role_ease_key = (ready_role_ease, min_rem_ease, max_rem_ease, max_open_ease)

        remaining_effort = sum(_resolve_node_role_weight(nodes, u) for u in comp_open)
        weighted_denom = done_count + remaining_effort
        weighted_velocity = (done_count / weighted_denom) if weighted_denom > 0 else 0.0

        raw_best_status = min(
            (ACTIVE_STATUS_ORDER.get(str(nodes[u]["status"]), 99) for u in comp_open),
            default=99,
        )
        has_wip = any(str(nodes[u]["status"]) == "WIP" for u in comp_open)
        is_active_quest = has_wip or (
            latest_done_task is not None and latest_done_task in comp_done
        )
        if is_active_quest:
            best_status = ACTIVE_STATUS_ORDER["WIP"]
        elif done_count > 0:
            best_status = min(raw_best_status, ACTIVE_STATUS_ORDER["NEXT"])
        else:
            best_status = raw_best_status

        canon_ref = _canonical_task_ref_key(nodes, root)
        root_nd = nodes[root]
        root_ref = str(root_nd["ref"])
        root_title = str(root_nd["title"])

        is_work_finale = root in finale_set and len(comp_open) == 1
        finale_tier = 0 if is_work_finale else 1
        finale_order_key: tuple[int, int, int, int, tuple[str, str, str]] = (
            (
                0 if _is_bug_task_node(nodes, root) else 1,
                ACTIVE_STATUS_ORDER.get(str(root_nd["status"]), 99),
                -done_count,
                order_idx.get(root, 0),
                canon_ref,
            )
            if is_work_finale
            else (0, 0, 0, 0, ("", "", ""))
        )
        rank_key = (
            finale_tier,
            finale_order_key,
            -(ready_bugs + done_bugs),
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
            "root": root,
            "root_ref": root_ref,
            "root_title": root_title,
            "also_in": {},
            "tree": chain_tree,
            "is_active_quest": is_active_quest,
            "nodes": display_nodes,
            "open_nodes": comp_open,
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

    chain_entries = [_build_chain_entry(root, comp_open) for root, comp_open in root_cones]
    chain_entries.sort(key=lambda entry: entry["rank_key"])  # type: ignore[arg-type, return-value]

    if ready_only:
        for rank_idx, chain_entry in enumerate(chain_entries):
            members: list[tuple[Path, str]] = chain_entry["open_nodes"]  # type: ignore[assignment]
            for member in members:
                best_chain_rank.setdefault(member, rank_idx)
        for member in active_list:
            best_chain_rank.setdefault(member, len(chain_entries))
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
            "chain_counts": chain_counts,
            "done_counts": done_counts,
            "is_momentum_next": is_momentum_next,
            "ready_unblocks": ready_unblocks,
            "immediate_ready_targets": immediate_ready_targets,
            "chains": [],
            "chain_stats": [],
            "standalone": [],
            "ready_tasks": ready_nodes,
        }

    node_chain_refs: dict[tuple[Path, str], list[str]] = {}
    for entry in chain_entries:
        r_ref = str(entry["root_ref"])
        cone_members = set(entry["open_nodes"]) | set(entry["done_nodes"])  # type: ignore[arg-type]
        for u in cone_members:
            refs_for_u = node_chain_refs.setdefault(u, [])
            if r_ref not in refs_for_u:
                refs_for_u.append(r_ref)

    for entry in chain_entries:
        r_ref = str(entry["root_ref"])
        cone_members = set(entry["open_nodes"]) | set(entry["done_nodes"])  # type: ignore[arg-type]
        also_in_map: dict[tuple[Path, str], list[str]] = {}
        for u in cone_members:
            others = [ref for ref in node_chain_refs.get(u, []) if ref != r_ref]
            if others:
                also_in_map[u] = others
        entry["also_in"] = also_in_map

    chains: list[list[tuple[Path, str]]] = [entry["nodes"] for entry in chain_entries]  # type: ignore[misc]
    standalone.sort(key=_standalone_sort_key)
    if show_done:
        in_any_chain: set[tuple[Path, str]] = set()
        for entry in chain_entries:
            in_any_chain |= set(entry["open_nodes"]) | set(entry["done_nodes"])  # type: ignore[arg-type]
        already_placed = set(standalone) | in_any_chain | excluded_hold
        for arch_key in dag.get("archived_tasks", []):  # type: ignore[union-attr]
            if arch_key not in already_placed:
                already_placed.add(arch_key)
                standalone.append(arch_key)

    if limit is not None:
        rem = limit
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
        chains = limited_chains
        chain_entries = limited_stats
        standalone = limited_standalone

    return {
        "active_nodes": ranked_active,
        "active_unblocks": active_unblocks,
        "excluded_hold": excluded_hold,
        "finale_set": finale_set,
        "chain_counts": chain_counts,
        "done_counts": done_counts,
        "is_momentum_next": is_momentum_next,
        "ready_unblocks": ready_unblocks,
        "immediate_ready_targets": immediate_ready_targets,
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
        "chain_counts": prep["chain_counts"],
        "done_counts": prep["done_counts"],
        "is_momentum_next": prep["is_momentum_next"],
        "ready_unblocks": prep["ready_unblocks"],
        "immediate_ready_targets": prep["immediate_ready_targets"],
        "queues": queues,
    }
