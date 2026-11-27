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

TODO_PROJECTS_FILES = (".todo_projects", ".todo_projects.local")

def has_local_todo_projects_config(directory: Path) -> bool:
    d_res = directory.resolve()
    if d_res.name == ".todo_projects" and is_todo_project(d_res):
        return True
    for fname in TODO_PROJECTS_FILES:
        p = d_res / fname
        if p.is_file() or (fname == ".todo_projects" and p.is_dir() and is_todo_project(p)):
            return True
    return False

def has_todo_projects_config(
    base_dir: Path,
    include_env: bool = True,
) -> bool:
    b_res = base_dir.resolve()
    if has_local_todo_projects_config(b_res):
        return True
    if not include_env:
        return False
    return bool(os.environ.get("TODO_MD_PROJECTS", "").strip())

def require_todo_projects_config(
    base_dir: Path,
    context: str,
    include_env: bool = True,
) -> None:
    if not has_todo_projects_config(base_dir, include_env=include_env):
        raise SystemExit(
            f"{prog_name()}: {context} requires .todo_projects "
            f"(or .todo_projects.local / TODO_MD_PROJECTS) in {base_dir}"
        )

def resolve_workspace_root(base_dir: Path, explicit_dir: str | None = None) -> Path:
    env_ws = os.environ.get("TODO_MD_WORKSPACE", "").strip()
    if env_ws:
        p = Path(env_ws).expanduser().resolve()
        if not p.is_dir():
            raise SystemExit(f"{prog_name()}: workspace directory not found: {env_ws}")
        return p
    b_res = base_dir.resolve()
    if is_todo_project(b_res) and has_todo_projects_config(
        b_res, include_env=(explicit_dir is None)
    ):
        return b_res.parent if b_res.parent != b_res else b_res
    return b_res

class _DiscoveryCache:
    def __init__(self) -> None:
        self.ws_roots = {}
        self.alias_maps = {}
        self.reverse_alias_maps = {}
        self.external_aliases = {}
        self.ambiguous_names = {}
        self.display_names = {}
        self.configured_entries = {}
        self.task_maps = {}

_ACTIVE_DISCOVERY = None

class discovery_session:
    """Share configured .todo_projects discovery across one render pass."""

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

def _split_project_alias_entry(entry: str) -> tuple[str | None, str]:
    raw = entry.strip()
    if "=" in raw:
        lhs, rhs = raw.split("=", 1)
        alias = lhs.strip().replace("\\", "/").strip("/")
        target = rhs.strip()
        if alias and target and ".." not in alias.split("/"):
            return alias, target
    return None, raw

def configured_project_alias_map(
    base_dir: Path,
    ws_root: Path | None = None,
) -> dict[str, Path]:
    b_res = base_dir.resolve()
    ws_res = (ws_root or _workspace_root_cached(b_res)).resolve()
    cache = _ACTIVE_DISCOVERY
    key = (b_res, ws_res)
    if cache is not None and key in cache.alias_maps:
        return dict(cache.alias_maps[key])
    mapping: dict[str, Path] = {}
    for alias, p_res in read_configured_todo_project_entries(
        b_res, ws_res, include_env=True
    ):
        if alias and alias not in mapping:
            mapping[alias] = p_res
            if "/" in alias:
                leaf = alias.rsplit("/", 1)[-1]
                if leaf:
                    mapping.setdefault(leaf, p_res)
    if cache is not None:
        cache.alias_maps[key] = dict(mapping)
    return mapping

def _reverse_project_alias_map(
    base_dir: Path,
    ws_root: Path,
) -> dict[Path, str]:
    b_res = base_dir.resolve()
    ws_res = ws_root.resolve()
    cache = _ACTIVE_DISCOVERY
    key = (b_res, ws_res)
    if cache is not None and key in cache.reverse_alias_maps:
        return cache.reverse_alias_maps[key]
    alias_map = configured_project_alias_map(b_res, ws_res)
    rev: dict[Path, str] = {}
    for alias, target in alias_map.items():
        rev.setdefault(target, alias)
    if cache is not None:
        cache.reverse_alias_maps[key] = rev
    return rev

def project_display_name(
    proj_dir: Path,
    ws_root: Path,
    base_dir: Path | None = None,
) -> str:
    p_res = proj_dir.resolve()
    ws_res = ws_root.resolve()
    b_res = base_dir.resolve() if base_dir is not None else None
    cache = _ACTIVE_DISCOVERY
    if cache is not None:
        d_key = (b_res, ws_res)
        d_map = cache.display_names.get(d_key)
        if d_map is not None and p_res in d_map:
            return d_map[p_res]
    if b_res is not None:
        alias = _reverse_project_alias_map(b_res, ws_res).get(p_res)
        if alias is not None:
            if cache is not None:
                cache.display_names.setdefault((b_res, ws_res), {})[p_res] = alias
            return alias
    label = project_label(p_res, ws_res)
    if cache is not None:
        cache.display_names.setdefault((b_res, ws_res), {})[p_res] = label
    return label

def _build_external_alias_maps(
    base_dir: Path,
    ws_root: Path,
) -> tuple[dict[str, Path], dict[str, list[str]]]:
    b_res = base_dir.resolve()
    ws_res = ws_root.resolve()
    cache = _ACTIVE_DISCOVERY
    key = (b_res, ws_res)
    if cache is not None and key in cache.external_aliases:
        return cache.external_aliases[key], cache.ambiguous_names.get(key, {})
    alias_map = configured_project_alias_map(b_res, ws_res)
    configured = read_configured_todo_projects(b_res, ws_res, include_env=True)
    by_key: dict[str, list[Path]] = {}
    seen_projs: set[Path] = set()
    for proj in configured:
        p_res = proj.resolve()
        if p_res in seen_projs:
            continue
        seen_projs.add(p_res)
        for k in (p_res.name, project_label(p_res, ws_res)):
            if k and p_res not in by_key.setdefault(k, []):
                by_key[k].append(p_res)
    lookup: dict[str, Path] = {
        k: matches[0] for k, matches in by_key.items() if len(matches) == 1
    }
    lookup.update(alias_map)
    ambiguous: dict[str, list[str]] = {
        k: [project_display_name(p, ws_res, b_res) for p in matches]
        for k, matches in by_key.items()
        if len(matches) > 1 and k not in alias_map
    }
    if cache is not None:
        cache.external_aliases[key] = lookup
        cache.ambiguous_names[key] = ambiguous
    return lookup, ambiguous

def _external_alias_lookup_map(base_dir: Path, ws_root: Path) -> dict[str, Path]:
    return _build_external_alias_maps(base_dir, ws_root)[0]

def _ambiguous_project_matches(base_dir: Path, ws_root: Path, name: str) -> list[str]:
    norm = name.strip().replace("\\", "/").strip("/")
    if not norm or ".." in norm.split("/"):
        return []
    return _build_external_alias_maps(base_dir, ws_root)[1].get(norm, [])

def lookup_external_alias(base_dir: Path, ws_root: Path, name: str) -> Path | None:
    norm = name.strip().replace("\\", "/").strip("/")
    if not norm or ".." in norm.split("/"):
        return None
    return _external_alias_lookup_map(base_dir, ws_root).get(norm)

def resolve_project_dir(
    base_dir: Path,
    project_name: str,
    explicit_dir: str | None = None,
) -> Path:
    norm = project_name.strip().replace("\\", "/").strip("/")
    if not norm or ".." in norm.split("/"):
        raise SystemExit(f"{prog_name()}: invalid project reference {project_name!r}")
    b_res = base_dir.resolve()
    require_todo_projects_config(b_res, f"cross-project reference {project_name!r}")
    ws_root = _workspace_root_cached(b_res, explicit_dir=explicit_dir)
    alias = lookup_external_alias(b_res, ws_root, norm)
    if alias is not None:
        return alias
    ambig = _ambiguous_project_matches(b_res, ws_root, norm)
    if ambig:
        matches = ", ".join(ambig)
        raise SystemExit(
            f"{prog_name()}: ambiguous project name {project_name!r}; matches: {matches}"
        )
    raise SystemExit(
        f"{prog_name()}: project {norm!r} not found in .todo_projects under {b_res}"
    )

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

    base = resolve_target_dir(None)
    require_todo_projects_config(base, f"project selector -p/--project {selector!r}")
    ws_root = _workspace_root_cached(base).resolve()
    ext = lookup_external_alias(base, ws_root, norm)
    if ext is not None:
        return str(ext)
    ambig = _ambiguous_project_matches(base, ws_root, norm)
    if ambig:
        matches = ", ".join(ambig)
        raise SystemExit(
            f"{prog_name()}: ambiguous project name {selector!r}; matches: {matches}"
        )
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

def _resolve_todo_project_path(
    target: str,
    config_dir: Path,
    ws_root: Path | None = None,
) -> Path | None:
    raw = target.strip()
    if not raw:
        return None
    cfg_res = config_dir.resolve()
    ws_res = (ws_root or _workspace_root_cached(cfg_res)).resolve()
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
    return None

def _resolve_todo_project_entry(
    entry: str,
    config_dir: Path,
    ws_root: Path | None = None,
) -> Path | None:
    ws_res = (ws_root or _workspace_root_cached(config_dir.resolve())).resolve()
    alias, target = _split_project_alias_entry(entry)
    resolved = _resolve_todo_project_path(target, config_dir, ws_res)
    if resolved is not None:
        return resolved
    if alias is None:
        norm = target.strip().replace("\\", "/").strip("/")
        if norm and ".." not in norm.split("/"):
            for fname in TODO_PROJECTS_FILES:
                fpath = config_dir.resolve() / fname
                if fpath.is_file():
                    for item in _parse_todo_projects_text(read_if_exists(fpath)):
                        item_alias, item_target = _split_project_alias_entry(item)
                        if item_alias and (item_alias == norm or item_alias.rsplit("/", 1)[-1] == norm):
                            r = _resolve_todo_project_path(item_target, config_dir, ws_res)
                            if r is not None:
                                return r
    return None

def read_configured_todo_project_entries(
    config_dir: Path,
    ws_root: Path | None = None,
    include_env: bool = True,
    _visited: set[Path] | None = None,
) -> list[tuple[str | None, Path]]:
    cfg_res = config_dir.resolve()
    ws_res = (ws_root or _workspace_root_cached(cfg_res)).resolve()
    cache = _ACTIVE_DISCOVERY
    cache_key = (cfg_res, ws_res, bool(include_env))
    if cache is not None and _visited is None and cache_key in cache.configured_entries:
        return list(cache.configured_entries[cache_key])
    visited = _visited if _visited is not None else set()
    if cfg_res in visited:
        return []
    visited.add(cfg_res)
    raw_entries: list[tuple[Path, str]] = []
    has_config_source = False

    for fname in TODO_PROJECTS_FILES:
        fpath = cfg_res / fname
        if fpath.is_file():
            has_config_source = True
            for item in _parse_todo_projects_text(read_if_exists(fpath)):
                raw_entries.append((cfg_res, item))
        elif fname == ".todo_projects" and fpath.is_dir() and is_todo_project(fpath):
            has_config_source = True
            raw_entries.append((fpath.resolve(), "."))

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
        if cache is not None and _visited is None:
            cache.configured_entries[cache_key] = []
        return []

    resolved: list[tuple[str | None, Path]] = []
    idx_by_path: dict[Path, int] = {}

    def _add(alias: str | None, p: Path | None) -> None:
        if p is None:
            return
        p_res = p.resolve()
        if not is_todo_project(p_res):
            return
        if p_res in idx_by_path:
            idx = idx_by_path[p_res]
            old_alias, _ = resolved[idx]
            if old_alias is None and alias is not None:
                resolved[idx] = (alias, p_res)
            return
        idx_by_path[p_res] = len(resolved)
        resolved.append((alias, p_res))

    if is_todo_project(cfg_res):
        _add(None, cfg_res)
    for src_dir, entry in raw_entries:
        if is_todo_project(src_dir):
            _add(None, src_dir)
        alias, target = _split_project_alias_entry(entry)
        _add(alias, _resolve_todo_project_path(target, src_dir, ws_res))
    for _, child in list(resolved):
        if child != cfg_res and has_local_todo_projects_config(child):
            child_ws = _workspace_root_cached(child)
            for grand_alias, grand in read_configured_todo_project_entries(
                child, child_ws, include_env=False, _visited=visited
            ):
                _add(grand_alias, grand)
    if cache is not None and _visited is None:
        cache.configured_entries[cache_key] = list(resolved)
    return resolved

def read_configured_todo_projects(
    config_dir: Path,
    ws_root: Path | None = None,
    include_env: bool = True,
    _visited: set[Path] | None = None,
) -> list[Path]:
    return [
        p
        for _, p in read_configured_todo_project_entries(
            config_dir,
            ws_root=ws_root,
            include_env=include_env,
            _visited=_visited,
        )
    ]

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
    return explicit_dir is None

def resolve_workspace_chain_projects(
    base_dir: Path,
    ws_root: Path | None = None,
) -> list[tuple[str, Path]]:
    b_res = base_dir.resolve()
    ws_res = (ws_root or _workspace_root_cached(b_res)).resolve()
    entries = read_configured_todo_project_entries(b_res, ws_res, include_env=True)
    return [
        (alias if alias else project_display_name(p_res, ws_res, b_res), p_res)
        for alias, p_res in entries
    ]
