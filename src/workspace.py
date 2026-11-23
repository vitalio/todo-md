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

class _DiscoveryCache:
    def __init__(self) -> None:
        self.ws_roots = {}
        self.projects = {}
        self.orchestrators = {}
        self.task_maps = {}
        self.stage_edges = {}
        self.scans = {"projects": 0, "orchestrators": 0}

_ACTIVE_DISCOVERY = None

class discovery_session:
    """Share workspace/orchestrator discovery across one render pass."""

    def __enter__(self) -> "_DiscoveryCache":
        global _ACTIVE_DISCOVERY
        self._owner = _ACTIVE_DISCOVERY is None
        if self._owner:
            _ACTIVE_DISCOVERY = _DiscoveryCache()
        return _ACTIVE_DISCOVERY

    def __exit__(self, *exc: object) -> bool:
        global _ACTIVE_DISCOVERY
        if self._owner:
            _ACTIVE_DISCOVERY = None
        return False

def _discovery_scoped(fn):
    def wrapper(*args, **kwargs):
        with discovery_session():
            return fn(*args, **kwargs)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper

def _workspace_root_cached(base_dir: Path, explicit_dir: str | None = None) -> Path:
    cache = _ACTIVE_DISCOVERY
    if cache is None:
        return resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    key = (base_dir.resolve(), explicit_dir)
    if key not in cache.ws_roots:
        cache.ws_roots[key] = resolve_workspace_root(base_dir, explicit_dir=explicit_dir)
    return cache.ws_roots[key]

def discover_projects(
    workspace_root: Path,
    max_depth: int = WORKSPACE_MAX_DEPTH,
) -> list[tuple[str, Path]]:
    cache = _ACTIVE_DISCOVERY
    if cache is None or max_depth != WORKSPACE_MAX_DEPTH:
        return _scan_projects(workspace_root, max_depth)
    key = workspace_root.resolve()
    if key not in cache.projects:
        cache.scans["projects"] += 1
        cache.projects[key] = _scan_projects(workspace_root, max_depth)
    return list(cache.projects[key])

def _scan_projects(
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

def _home_dir() -> Path | None:
    try:
        return Path.home().resolve()
    except (RuntimeError, OSError):
        return None

def project_label(proj_dir: Path, ws_root: Path) -> str:
    p_res = proj_dir.resolve()
    for base in (ws_root.resolve(), _home_dir()):
        if base is None:
            continue
        try:
            rel = p_res.relative_to(base).as_posix()
        except ValueError:
            continue
        return rel if rel and rel != "." else p_res.name
    return p_res.name

def lookup_external_alias(base_dir: Path, ws_root: Path, name: str) -> Path | None:
    norm = name.strip().replace("\\", "/").strip("/")
    if not norm or ".." in norm.split("/"):
        return None
    ws_res = ws_root.resolve()
    b_res = base_dir.resolve()
    projs = discover_projects(ws_res)
    configured: list[Path] = []
    for cfg_dir in (b_res, ws_res):
        configured.extend(
            read_configured_todo_projects(cfg_dir, ws_res, include_env=True, discovered=projs)
        )
    configured.extend(discover_orchestrators_for_project(b_res, ws_res)[1])
    matches: list[Path] = []
    for proj in configured:
        p_res = proj.resolve()
        if p_res in matches:
            continue
        try:
            p_res.relative_to(ws_res)
            continue
        except ValueError:
            pass
        if p_res.name == norm or project_label(p_res, ws_res) == norm:
            matches.append(p_res)
    return matches[0] if len(matches) == 1 else None

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
    inside = True
    try:
        candidate.relative_to(ws_root.resolve())
    except ValueError:
        inside = False
    if inside and is_todo_project(candidate):
        return candidate
    alias = lookup_external_alias(base_dir, ws_root, norm)
    if alias is not None:
        return alias
    if not inside:
        raise SystemExit(f"{prog_name()}: project {project_name!r} escapes workspace {ws_root}")
    raise SystemExit(f"{prog_name()}: project {norm!r} not found under workspace {ws_root}")

def resolve_project_selector(selector: str) -> str:
    raw = selector.strip()
    if not raw:
        raise SystemExit(f"{prog_name()}: empty project selector")
    norm = raw.replace("\\", "/").strip("/")
    if (
        not norm
        or ".." in norm.split("/")
        or raw.startswith(("/", "~", "./", "../", ".\\", "..\\"))
        or Path(raw).expanduser().is_absolute()
    ):
        raise SystemExit(f"{prog_name()}: project not found: {selector}")

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
        ext = lookup_external_alias(base, ws_root, norm)
        if ext is not None:
            return str(ext)

    raise SystemExit(f"{prog_name()}: project not found: {selector}")

def resolve_project_or_dir(selector: str) -> str:
    p_cand = Path(selector.strip()).expanduser()
    if p_cand.is_dir():
        return str(p_cand.resolve())
    return resolve_project_selector(selector)

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

def _is_valid_task_ref_token(tok: str) -> bool:
    raw = tok.strip()
    if not raw:
        return False
    if re.fullmatch(r"[A-Za-z]\d+", raw):
        return True
    pm = PROJECT_TASK_RE.match(raw)
    if pm:
        proj_part = pm.group(1).strip().replace("\\", "/").strip("/")
        return bool(proj_part) and ".." not in proj_part.split("/")
    return False

def _split_task_ref_arg(arg: str) -> list[str] | None:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        return None
    if not all(_is_valid_task_ref_token(p) for p in parts):
        return None
    return parts

def resolve_filter_task_ref(
    base_dir: Path,
    ref: str,
    explicit_dir: str | None = None,
) -> tuple[Path, str]:
    raw = ref.strip()
    m = PROJECT_TASK_RE.match(raw)
    if m:
        proj_name, tid = m.group(1), m.group(2).upper()
        r_dir = resolve_project_dir(base_dir, proj_name, explicit_dir=explicit_dir)
        return r_dir, f".:{tid}"
    return base_dir, raw.upper()

def _normalize_target_refs(
    base_dir: Path,
    targets: list[tuple[Path, str]] | None,
    explicit_dir: str | None = None,
) -> tuple[set[tuple[Path, str]], set[str]]:
    target_set: set[tuple[Path, str]] = set()
    unscoped_ids: set[str] = set()
    for tdir, raw_tid in targets or []:
        tok = raw_tid.strip()
        if not tok:
            continue
        if tok.startswith(".:"):
            tid_up = tok[2:].strip().upper()
            if tid_up:
                target_set.add((tdir.resolve(), tid_up))
            continue
        pm = PROJECT_TASK_RE.match(tok)
        if pm:
            r_dir, r_tid = resolve_project_task_ref(base_dir, tok, explicit_dir=explicit_dir)
            target_set.add((r_dir.resolve(), r_tid.upper()))
        else:
            t_res = tdir.resolve()
            tid_up = tok.upper()
            target_set.add((t_res, tid_up))
            unscoped_ids.add(tid_up)
    return target_set, unscoped_ids

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
    _visited: set[Path] | None = None,
) -> list[Path]:
    cfg_res = config_dir.resolve()
    visited = _visited if _visited is not None else set()
    if cfg_res in visited:
        return []
    visited.add(cfg_res)
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
    for child in list(resolved):
        if child != cfg_res and has_local_todo_projects_config(child):
            for grand in read_configured_todo_projects(
                child, ws_res, include_env=False, discovered=projs, _visited=visited
            ):
                _add(grand)
    return resolved

def has_local_todo_projects_config(directory: Path) -> bool:
    d_res = directory.resolve()
    if d_res.name == ".todo_projects" and is_todo_project(d_res):
        return True
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
    cache = _ACTIVE_DISCOVERY
    if cache is None:
        return _scan_orchestrators_for_project(target_dir, ws_root)
    t_res = target_dir.resolve()
    ws_res = (ws_root or _workspace_root_cached(t_res)).resolve()
    key = (t_res, ws_res)
    if key not in cache.orchestrators:
        cache.scans["orchestrators"] += 1
        cache.orchestrators[key] = _scan_orchestrators_for_project(t_res, ws_res)
    orchestrators, configured = cache.orchestrators[key]
    return list(orchestrators), list(configured)

def _scan_orchestrators_for_project(
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

    def _add_enclosing_probes(d: Path) -> None:
        home = _home_dir()
        for anc in d.parents:
            _add_probe(anc)
            if anc.resolve() in (ws_res, home):
                break

    probe_idx = 0
    while probe_idx < len(probe_dirs):
        cand = probe_dirs[probe_idx]
        probe_idx += 1
        if not has_local_todo_projects_config(cand):
            continue
        cfg_list = read_configured_todo_projects(cand, ws_res, include_env=False, discovered=projs)
        if t_res in cfg_list:
            if is_todo_project(cand) and cand not in seen_orch:
                seen_orch.add(cand)
                orchestrators.append(cand)
                _add_enclosing_probes(cand)
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
        if (b_res / "TODO.md").is_file() or (b_res / "TODO_ARCHIVE.md").is_file():
            _merge([b_res])
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
        result.append((project_label(p_res, ws_res), p_res))
    return result
