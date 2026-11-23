BUNDLE_PROTOCOL_VERSION = "1"
BUNDLE_NAME = "vitalio/todo-md"
BUNDLE_FLAGS = ("--bundle", "--plain")
BUNDLE_CHAIN = ["vitalio/todo-md"]
BUNDLE_RULE_ID = "vitalio/todo-md:todo"
CONTEXT_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z-]*: ")
TASK_SOURCE_RE = re.compile(r"^# (TODO(?:_ARCHIVE)?\.md):\d+", re.MULTILINE)

class BundleOptions:
    def __init__(self, enabled: bool | None = None, role: str | None = None,
                 argv: list[str] | None = None,
                 bundle_flag: bool = False, plain_flag: bool = False) -> None:
        self._enabled = enabled
        self._bundle_flag = bundle_flag
        self._plain_flag = plain_flag
        self.role = role
        self.argv = list(argv or [])

    @property
    def enabled(self) -> bool:
        if self._enabled is None:
            self._enabled = bundle_mode_enabled(self._bundle_flag, self._plain_flag)
        return self._enabled

BUNDLE_CONSUMER_NAMES = frozenset({
    "context",
    "agents_bundle",
    "agents-bundle",
    "run",
    "run_block",
    "run-block",
})
STANDARD_FILTER_NAMES = frozenset({
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "less",
    "more",
    "head",
    "tail",
    "wc",
    "awk",
    "gawk",
    "mawk",
    "nawk",
    "sed",
    "gsed",
    "sort",
    "cut",
    "tr",
    "uniq",
    "nl",
    "cat",
    "tee",
    "xargs",
    "jq",
    "column",
    "fmt",
    "fold",
    "paste",
    "join",
})
SHELL_WRAPPER_NAMES = frozenset({
    "python",
    "python3",
    "pypy",
    "pypy3",
    "sh",
    "bash",
    "zsh",
    "dash",
    "ksh",
    "fish",
    "env",
})

def _normalize_cmd_token(token: str) -> str:
    name = Path(token.strip()).name.lower()
    if name.startswith("-"):
        name = name.lstrip("-")
    for suf in (".py", ".sh", ".cmd", ".bat", ".exe"):
        if name.endswith(suf) and len(name) > len(suf):
            name = name[:-len(suf)]
            break
    if re.fullmatch(r"python3(?:\.\d+)+", name):
        return "python3"
    return name

def _argv_executable_name(tokens: list[str]) -> str | None:
    i = 0
    while i < len(tokens):
        tok = tokens[i].strip()
        if not tok:
            i += 1
            continue
        if "=" in tok and not tok.startswith("-") and i == 0:
            i += 1
            continue
        name = _normalize_cmd_token(tok)
        if name == "env":
            i += 1
            while i < len(tokens):
                t = tokens[i].strip()
                if not t or t.startswith("-") or "=" in t:
                    i += 1
                    continue
                break
            continue
        if name in SHELL_WRAPPER_NAMES:
            i += 1
            while i < len(tokens):
                t = tokens[i].strip()
                if not t:
                    i += 1
                    continue
                if t == "-c" and i + 1 < len(tokens):
                    return _pipeline_consumer_from_shell_c(tokens[i + 1]) or name
                if t in ("-c", "-m"):
                    return name
                if t.startswith("-"):
                    i += 1
                    continue
                return _normalize_cmd_token(t)
            return name
        return name
    return None

def _pipeline_consumer_from_shell_c(script: str) -> str | None:
    if "|" not in script:
        return None
    stages = [s.strip() for s in script.split("|") if s.strip()]
    if len(stages) < 2:
        return None
    for stage in stages[1:]:
        try:
            tokens = shlex.split(stage)
        except ValueError:
            tokens = stage.split()
        exe = _argv_executable_name(tokens)
        if exe:
            return exe
    return None

def _classify_process_tokens(tokens: list[str]) -> str | None:
    exe = _argv_executable_name(tokens)
    if not exe:
        return None
    if exe in BUNDLE_CONSUMER_NAMES:
        return "bundle"
    if exe in STANDARD_FILTER_NAMES:
        return "filter"
    return "other"

def _read_proc_tokens(pid: int) -> list[str]:
    try:
        raw_cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        raw_cmd = b""
    tokens = [t.decode("utf-8", errors="replace") for t in raw_cmd.split(b"\0") if t]
    if not tokens:
        try:
            comm = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            comm = ""
        if comm:
            tokens = [comm]
    return tokens

def _read_proc_ppid_pgid(pid: int) -> tuple[int, int] | None:
    try:
        stat_txt = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        rparen = stat_txt.rfind(")")
        if rparen == -1:
            return None
        fields = stat_txt[rparen + 2:].split()
        if len(fields) < 3:
            return None
        return int(fields[1]), int(fields[2])
    except (OSError, ValueError):
        return None

def _ancestor_pids(my_pid: int, proc_map: dict[int, tuple[int, int, list[str]]]) -> set[int]:
    ancestors: set[int] = set()
    cur = my_pid
    while cur in proc_map:
        ppid = proc_map[cur][0]
        if ppid <= 0 or ppid == cur or ppid in ancestors:
            break
        ancestors.add(ppid)
        cur = ppid
    return ancestors

def _linux_fifo_is_standard_filter(fifo_dev: int, fifo_ino: int) -> bool | None:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return None
    my_pid = os.getpid()
    my_ppid = os.getppid()
    try:
        my_pgrp = os.getpgrp()
    except OSError:
        my_pgrp = -1

    # Fast check 1: parent process (e.g. sh -c "todo | grep ..." or python unittest)
    parent_tokens = _read_proc_tokens(my_ppid) if my_ppid > 0 else []
    if parent_tokens:
        parent_kind = _classify_process_tokens(parent_tokens)
        if parent_kind == "bundle":
            return False
        if parent_kind == "filter":
            return True

    # Fast check 2: scan /proc/<pid>/fd/0 for direct pipe reader
    try:
        entries = [int(e.name) for e in proc_root.iterdir() if e.name.isdigit()]
    except OSError:
        return None

    stdin_peers: list[list[str]] = []
    for pid in entries:
        if pid == my_pid:
            continue
        try:
            st0 = os.stat(f"/proc/{pid}/fd/0")
            if st0.st_dev == fifo_dev and st0.st_ino == fifo_ino:
                tokens = _read_proc_tokens(pid)
                if tokens:
                    stdin_peers.append(tokens)
        except OSError:
            pass

    if stdin_peers:
        kinds = [_classify_process_tokens(t) for t in stdin_peers]
        if "bundle" in kinds:
            return False
        if "filter" in kinds:
            return True
        return False

    # Fast check 3: sibling processes in the same pipeline (ppid == my_ppid or pgid == my_pid)
    ancestors: set[int] = set()
    cur = my_ppid
    while cur > 0 and cur not in ancestors:
        ancestors.add(cur)
        ids = _read_proc_ppid_pgid(cur)
        if ids is None or ids[0] == cur:
            break
        cur = ids[0]

    sibling_cmds: list[list[str]] = []
    for pid in entries:
        if pid == my_pid or pid in ancestors or pid < my_ppid:
            continue
        ids = _read_proc_ppid_pgid(pid)
        if ids is None:
            continue
        ppid, pgid = ids
        if ppid == my_ppid or (my_pgrp == my_pid and pgid == my_pgrp):
            tokens = _read_proc_tokens(pid)
            if tokens:
                sibling_cmds.append(tokens)

    if sibling_cmds:
        kinds = [_classify_process_tokens(t) for t in sibling_cmds]
        if "bundle" in kinds:
            return False
        if "filter" in kinds:
            return True

    return False

def _ps_fifo_is_standard_filter() -> bool:
    my_pid = os.getpid()
    my_ppid = os.getppid()
    try:
        my_pgrp = os.getpgrp()
    except OSError:
        my_pgrp = -1
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,pgid=,args="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    proc_map: dict[int, tuple[int, int, list[str]]] = {}
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            pgid = int(parts[2])
        except ValueError:
            continue
        try:
            tokens = shlex.split(parts[3])
        except ValueError:
            tokens = parts[3].split()
        if tokens:
            proc_map[pid] = (ppid, pgid, tokens)
    ancestors = _ancestor_pids(my_pid, proc_map)
    sibling_cmds = [
        tokens
        for pid, (ppid, pgid, tokens) in proc_map.items()
        if pid != my_pid and pid not in ancestors and (ppid == my_ppid or (my_pgrp == my_pid and pgid == my_pgrp))
    ]
    if sibling_cmds:
        kinds = [_classify_process_tokens(t) for t in sibling_cmds]
        if "bundle" in kinds:
            return False
        if "filter" in kinds:
            return True
    if my_ppid in proc_map:
        parent_kind = _classify_process_tokens(proc_map[my_ppid][2])
        if parent_kind == "bundle":
            return False
        if parent_kind == "filter":
            return True
    return False

def _fifo_is_standard_filter(st: os.stat_result) -> bool:
    linux_res = _linux_fifo_is_standard_filter(st.st_dev, st.st_ino)
    if linux_res is not None:
        return linux_res
    return _ps_fifo_is_standard_filter()

def bundle_mode_enabled(bundle_flag: bool, plain_flag: bool) -> bool:
    env = os.environ
    if bundle_flag:
        return True
    if plain_flag:
        return False
    if env.get("TODO_MD_BUNDLE") == "1":
        return True
    if env.get("TODO_MD_PLAIN") == "1":
        return False
    try:
        st = os.fstat(sys.stdout.fileno())
    except (AttributeError, OSError, ValueError):
        return False
    if not stat.S_ISFIFO(st.st_mode):
        return False
    step_ino = env.get("RUN_BLOCK_STEP_STDOUT_INO")
    if step_ino and step_ino == f"{st.st_dev}:{st.st_ino}":
        return False
    if not step_ino and env.get("IN_RUN_BLOCK") == "1":
        return False
    if _fifo_is_standard_filter(st):
        return False
    return True

def _capture(render) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = int(render())
    return rc, buf.getvalue()

def _fragment(nonce: str, meta: dict[str, object], body: str) -> str:
    marker = json.dumps(meta, ensure_ascii=False)
    return f"<!-- bundle:{nonce}:part {marker} -->\n{body.rstrip(chr(10))}\n<!-- bundle:{nonce}:end -->\n"

def _with_task_headers(headers: list[str], role: str | None) -> list[str]:
    out = [h for h in headers if not h.startswith("Role: ")]
    if role:
        out.append(f"Role: {role}")
    return out

def _write_stream(
    opts: BundleOptions,
    headers: list[str],
    prompt_meta: dict[str, object],
    prompt_body: str,
) -> None:
    nonce = secrets.token_hex(16)
    headers = _with_task_headers(headers, opts.role)
    preamble = [
        f"Bundle-Protocol: {BUNDLE_PROTOCOL_VERSION}",
        f"Bundle-Name: {BUNDLE_NAME}",
        f"Bundle-Command: {shlex.join([prog_name(), *opts.argv])}",
        f"Bundle-Boundary: {nonce}",
        *headers,
    ]
    rule_meta = {"kind": "rule", "id": BUNDLE_RULE_ID, "chain": BUNDLE_CHAIN}
    parts = [
        _fragment(nonce, rule_meta, get_embedded_todo_rule()),
        _fragment(nonce, prompt_meta, "===== Prompt =====\n" + prompt_body),
    ]
    sys.stdout.write("\n".join(preamble) + "\n\n===== Rules =====\n" + "\n".join(parts))

def emit_context_bundle(opts: BundleOptions, base_dir: Path, render) -> int:
    rc, out = _capture(render)
    if rc != 0 or not out.strip():
        sys.stdout.write(out)
        return rc
    meta = {"kind": "prompt", "name": "todo", "chain": BUNDLE_CHAIN}
    _write_stream(opts, [f"Workdir: {base_dir.resolve()}"], meta, out)
    return 0

def emit_task_bundle(opts: BundleOptions, task_dir: Path, task_id: str | None, render) -> int:
    rc, out = _capture(render)
    head, sep, body = out.partition("\n\n")
    headers = head.splitlines()
    if rc != 0 or not sep or not headers or not all(CONTEXT_HEADER_RE.match(h) for h in headers):
        sys.stdout.write(out)
        return rc
    tid = next((h.split(": ", 1)[1] for h in headers if h.startswith("Task: ")), task_id or "")
    src = TASK_SOURCE_RE.search(body)
    meta = {
        "kind": "prompt",
        "id": tid,
        "name": f"{src.group(1) if src else 'TODO.md'}:{tid}",
        "chain": BUNDLE_CHAIN,
    }
    _write_stream(opts, headers, meta, body)
    return 0
