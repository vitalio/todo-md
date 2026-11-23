@_discovery_scoped
def cmd_chain(
    base_dir: Path,
    limit: int | None = None,
    include_hold: bool = False,
    include_done: bool = False,
    ready: bool = False,
    prefix: str | None = None,
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
    ws_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
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

    plan = plan_execution_chains(
        dag,
        include_hold=include_hold,
        ready_only=ready,
        limit=(None if (prefix is not None or row_scoped or target_project is not None) else limit),
        include_done=include_done,
    )
    active_nodes: list[tuple[Path, str]] = plan["active_nodes"]  # type: ignore[assignment]
    active_unblocks: dict[tuple[Path, str], int] = plan["active_unblocks"]  # type: ignore[assignment]
    excluded_hold: set[tuple[Path, str]] = plan["excluded_hold"]  # type: ignore[assignment]
    chain_counts: dict[tuple[Path, str], int] = plan.get("chain_counts", {})  # type: ignore[assignment]
    done_counts: dict[tuple[Path, str], int] = plan.get("done_counts", {})  # type: ignore[assignment]
    is_momentum_next: dict[tuple[Path, str], int] = plan.get("is_momentum_next", {})  # type: ignore[assignment]
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
    wanted_prefix = prefix.strip().upper() if prefix is not None else None

    def _is_highlighted_node(u: tuple[Path, str]) -> bool:
        return (u[0].resolve(), u[1].upper()) in target_set or u[1].upper() in unscoped_target_ids

    def _matches_prefix(u: tuple[Path, str]) -> bool:
        if wanted_prefix is None:
            return True
        nd = nodes[u]
        return bool(nd.get("exists")) and _task_matches_prefix(nd, wanted_prefix)

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
        impact = active_unblocks.get(u, 0)
        done_c = done_counts.get(u, len(done_nodes.get(u, set())))
        tag_parts: list[str] = []
        if st == "MISSING":
            badge = "⚠️ MISSING"
            tag_parts.append("🔒 blocked")
            if impact > 0:
                tag_parts.append(f"🔓 unblocks: {impact}")
        elif st == "CANCELED":
            badge = f"{nd['emoji']} CANCELED"
            if u in active_set:
                tag_parts.append("🔒 blocked")
                if impact > 0:
                    tag_parts.append(f"🔓 unblocks: {impact}")
        elif st == "DONE":
            badge = f"{nd['emoji']} DONE"
        else:
            emoji = "⏳" if (st in ("WIP", "NEXT") and blockers) else str(nd["emoji"])
            badge = f"{emoji} {st}"
            if blockers:
                tag_parts.append(f"🔒 blocked by: {', '.join(blockers)}")
                if impact > 0:
                    tag_parts.append(f"🔓 unblocks: {impact}")
            else:
                if not show_downstream:
                    tag_parts.append("🟢 ready")
                if done_c > 0 and impact == 0:
                    tag_parts.append("🏁 FINAL")
                elif done_c > 0 and impact > 0:
                    tag_parts.append("⚡ STAGE")
                if is_momentum_next.get(u, 1) == 0:
                    tag_parts.append("🔥 COMBO")
                if show_downstream:
                    n_chains = chain_counts.get(u, 0)
                    if n_chains > 1:
                        tag_parts.append(f"⛓️ chain: {n_chains}")
                    if impact > 0:
                        imm_count = len(immediate_ready_targets.get(u, []))
                        if imm_count > 0:
                            tag_parts.append(f"🟢 ready: +{imm_count}")
                        tag_parts.append(f"🔓 unblocks: {impact}")
                else:
                    if impact > 0:
                        tag_parts.append(f"🔓 unblocks: {impact}")
        if also_in_refs:
            tag_parts.append(f"🔗 also in: {', '.join(also_in_refs)}")
        status_tag = " · ".join(tag_parts)
        lead_cell = _lead_cell(tree_prefix, idx, ref)
        row_prefix = (
            f"  {_pad_display(lead_cell, lead_col_width)}  "
            f"{_pad_display(badge, 14)}  "
        )
        desc = f"{title}  · {status_tag}" if status_tag else title
        rendered = _wrap_table_row(row_prefix, desc, term_width, cont_prefix=cont_prefix) + "\n"
        return _style_chain_task_row(
            rendered,
            row_prefix=row_prefix,
            title=title,
            has_tags=bool(status_tag),
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
        if wanted_prefix is not None:
            held_paths = [path for path in held_paths if any(_matches_prefix(k) for k in path)]
        if focus_active:
            held_paths = [path for path in held_paths if any(_is_focus_node(k) for k in path)]
        if status is not None:
            held_paths = [path for path in held_paths if any(_status_ok(k) for k in path)]

    scoped_excluded_hold = {
        u
        for u in excluded_hold
        if _is_target_node(u) or any(u in path for path in held_paths)
    }

    def _filter_note() -> str:
        return f" matching prefix={wanted_prefix}" if wanted_prefix is not None else ""

    scope_done_tasks: list[dict[str, object]] = dag.get("scope_done_tasks", [])  # type: ignore[assignment]
    if wanted_prefix is not None:
        overall_done = sum(1 for t in scope_done_tasks if _task_matches_prefix(t, wanted_prefix))
    else:
        overall_done = len(scope_done_tasks)

    scope_active_nodes = [
        u
        for u in topo_order
        if _is_target_node(u)
        and bool(nodes[u].get("exists"))
        and nodes[u].get("file") == "TODO.md"
        and str(nodes[u]["status"]) in ACTIVE_STATUS_ORDER
        and _matches_prefix(u)
    ]
    overall_open_nodes = [u for u in scope_active_nodes if u not in excluded_hold]
    overall_held = sum(1 for u in scope_active_nodes if u in excluded_hold)
    overall_ready_nodes = [
        u
        for u in overall_open_nodes
        if _is_ready_in_dag(nodes, prereqs, u, include_hold=include_hold)
    ]
    overall_ready = len(overall_ready_nodes)
    overall_open = len(overall_open_nodes)
    overall_blocked = overall_open - overall_ready
    overall_total = overall_done + overall_open
    overall_pct = round(100 * overall_done / overall_total) if overall_total > 0 else 0

    ready_by_status: dict[str, int] = {}
    for u in overall_ready_nodes:
        st_u = str(nodes[u]["status"])
        ready_by_status[st_u] = ready_by_status.get(st_u, 0) + 1
    ready_breakdown = [
        f"{ready_by_status[st_k]} {VALID_STATUSES[st_k]} {st_k}"
        for st_k in ACTIVE_STATUS_ORDER
        if ready_by_status.get(st_k, 0) > 0
    ]
    if ready_breakdown:
        ready_summary = f"🟢 {overall_ready} ready ({', '.join(ready_breakdown)})"
    else:
        ready_summary = f"🟢 {overall_ready} ready"
    open_summary_parts = [ready_summary]
    if overall_blocked > 0:
        open_summary_parts.append(f"⏳ {overall_blocked} blocked")
    if overall_held > 0:
        open_summary_parts.append(f"⏸️ {overall_held} held")
    overall_header_plain = (
        f"{overall_pct}% · ✅ {overall_done}/{overall_total} · "
        f"{overall_open} open: {' · '.join(open_summary_parts)}"
    )
    sys.stdout.write(_style_overall_progress_header(overall_header_plain, use_color=use_color) + "\n\n")

    if ready:
        ready_tasks: list[tuple[Path, str]] = plan["ready_tasks"]  # type: ignore[assignment]
        if target_project is not None:
            ready_tasks = [u for u in ready_tasks if _is_target_node(u)]
        if wanted_prefix is not None:
            ready_tasks = [u for u in ready_tasks if _matches_prefix(u)]
        if row_scoped:
            ready_tasks = [u for u in ready_tasks if _row_ok(u)]
        if (target_project is not None or wanted_prefix is not None or row_scoped) and limit is not None:
            ready_tasks = ready_tasks[:limit]
        matching_held = [u for u in scoped_excluded_hold if _matches_prefix(u) and _is_target_node(u) and _row_ok(u)]
        num_w_box[0] = len(str(max(1, len(ready_tasks))))
        f_note = _filter_note()
        if ready_tasks:
            sys.stdout.write("Ready tasks:\n")
            for idx, u in enumerate(ready_tasks, start=1):
                sys.stdout.write(_format_row(idx, u, show_downstream=True))
        elif matching_held:
            sys.stdout.write(
                f"Ready tasks: (none{f_note} — {len(matching_held)} held task(s); pass --include-hold to include)\n"
            )
        elif f_note:
            sys.stdout.write(f"Ready tasks: (none{f_note})\n")
        else:
            sys.stdout.write("Ready tasks: (none)\n")
    else:
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
            chains_with_stats = [
                (comp, st_info)
                for comp, st_info in chains_with_stats
                if _chain_has_target_node(comp, st_info)
            ]
            standalone = [u for u in standalone if _is_target_node(u)]
        if wanted_prefix is not None:
            filtered_chains_with_stats: list[tuple[list[tuple[Path, str]], dict[str, object]]] = []
            for comp, st_info in chains_with_stats:
                f_comp = [u for u in comp if _matches_prefix(u)]
                if f_comp and (target_project is None or any(_is_target_node(u) for u in f_comp)):
                    filtered_chains_with_stats.append((f_comp, st_info))
            chains_with_stats = filtered_chains_with_stats
            standalone = [u for u in standalone if _matches_prefix(u)]
        if row_scoped:
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
        if (target_project is not None or wanted_prefix is not None or row_scoped) and limit is not None:
            rem = limit
            limited_chains_with_stats: list[tuple[list[tuple[Path, str]], dict[str, object]]] = []
            for comp, st_info in chains_with_stats:
                if rem <= 0:
                    break
                take = comp[:rem]
                limited_chains_with_stats.append((take, st_info))
                rem -= len(take)
            standalone = standalone[:rem] if rem > 0 else []
            chains_with_stats = limited_chains_with_stats
        matching_held = [u for u in scoped_excluded_hold if _matches_prefix(u) and _is_target_node(u) and _row_ok(u)]
        if chains_with_stats or standalone:
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

            def _is_done_subchain(ch_item: dict[str, object]) -> bool:
                if ch_item.get("kind") != "subchain":
                    return False
                m_node = ch_item.get("milestone")
                if not isinstance(m_node, tuple) or str(nodes.get(m_node, {}).get("status", "")) != "DONE":
                    return False
                if int(ch_item.get("open_count", 0)) != 0:
                    return False
                sub_nodes: set[tuple[Path, str]] = ch_item.get("subtree_nodes", {m_node})  # type: ignore[assignment]
                return all(str(nodes.get(su, {}).get("status", "")) == "DONE" for su in sub_nodes)

            def _should_collapse_done_subchain(
                ch_item: dict[str, object],
                seen_done_milestones: set[tuple[Path, str]],
            ) -> bool:
                if not _is_done_subchain(ch_item):
                    return False
                m_node: tuple[Path, str] = ch_item["milestone"]  # type: ignore[assignment]
                sub_nodes: set[tuple[Path, str]] = ch_item.get("subtree_nodes", {m_node})  # type: ignore[assignment]
                if any(_is_highlighted_node(su) for su in sub_nodes):
                    return False
                return m_node in seen_done_milestones

            def _count_tree_rows(
                t_node: dict[str, object],
                seen_done: set[tuple[Path, str]],
            ) -> int:
                cnt = 0
                for ch_item in t_node.get("children", []):  # type: ignore[attr-defined]
                    if ch_item.get("kind") == "subchain":
                        m_node: tuple[Path, str] = ch_item["milestone"]  # type: ignore[assignment]
                        if _should_collapse_done_subchain(ch_item, seen_done):
                            seen_done.add(m_node)
                            continue
                        if _is_done_subchain(ch_item):
                            seen_done.add(m_node)
                        cnt += _count_tree_rows(ch_item, seen_done)
                    else:
                        cnt += 1
                return cnt

            chain_trees = [_build_chain_tree(c_nodes, c_info) for c_nodes, c_info in chains_with_stats]
            sim_seen_done_count: set[tuple[Path, str]] = set()
            total_rows = len(standalone) + sum(
                _count_tree_rows(ct, sim_seen_done_count) if tree else len(c_nodes)
                for (c_nodes, _), ct in zip(chains_with_stats, chain_trees)
            )
            rendered_done_milestones: set[tuple[Path, str]] = set()
            num_w_box[0] = len(str(max(1, total_rows)))
            for chain_idx, (comp, st_info) in enumerate(chains_with_stats, start=1):
                if wrote_section:
                    sys.stdout.write("\n")
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
                total_c = done_c + open_c
                chain_stat_tag = f"{pct}% · {done_c}/{total_c} ·"
                header_line = f"{chain_stat_tag} Chain {chain_idx} -> {root_ref}: {root_title}:\n"
                sys.stdout.write(
                    _style_chain_header_line(
                        header_line,
                        is_highlighted=chain_highlighted,
                        use_color=use_color,
                    )
                )
                chain_tree = chain_trees[chain_idx - 1]

                sim_seen_lead = set(rendered_done_milestones)

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
                            m_node: tuple[Path, str] = ch_item["milestone"]  # type: ignore[assignment]
                            if _should_collapse_done_subchain(ch_item, sim_seen_lead):
                                sim_seen_lead.add(m_node)
                                continue
                            if _is_done_subchain(ch_item):
                                sim_seen_lead.add(m_node)
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
                            collapsed_done = _should_collapse_done_subchain(ch_item, rendered_done_milestones)
                            if _is_done_subchain(ch_item):
                                rendered_done_milestones.add(m_node)
                            sub_conn = "└── " if is_last_c else "├── "
                            sub_prefix = f"  {bars}{sub_conn}"
                            sub_cont_bars = "".join(
                                "│   " if b else "    " for b in [*active_bars, not is_last_c]
                            )
                            sub_cont_prefix = f"  {sub_cont_bars}" if sub_cont_bars.strip() else "    "
                            m_total = m_done + m_open
                            sub_stat_tag = f"{m_pct}% · {m_done}/{m_total} ·"
                            if collapsed_done:
                                sub_desc = f"{sub_stat_tag} Sub-chain -> {m_ref}: {m_title} (✅ DONE — see above)"
                            else:
                                sub_desc = f"{sub_stat_tag} Sub-chain -> {m_ref}: {m_title}:"
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
                                _style_chain_header_line(
                                    sub_hdr,
                                    is_external=not _is_target_node(m_node),
                                    is_done=(str(nodes[m_node]["status"]) == "DONE"),
                                    is_highlighted=sub_hl,
                                    use_color=use_color,
                                )
                            )
                            if not collapsed_done:
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
                    flat_nodes = list(comp)
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
            f_note = _filter_note()
            sys.stdout.write(
                f"Chain: (none{f_note} — {len(matching_held)} held task(s); pass --include-hold to include)\n"
            )
        elif _filter_note():
            sys.stdout.write(f"Chain: (none{_filter_note()})\n")
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
