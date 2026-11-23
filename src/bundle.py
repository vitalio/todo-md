BUNDLE_PROTOCOL_VERSION = "1"
BUNDLE_NAME = "vitalio/todo-md"
BUNDLE_FLAGS = ("--bundle", "--plain")
BUNDLE_CHAIN = ["vitalio/todo-md"]
BUNDLE_RULE_ID = "vitalio/todo-md:todo"
CONTEXT_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z-]*: ")
TASK_SOURCE_RE = re.compile(r"^# (TODO(?:_ARCHIVE)?\.md):\d+", re.MULTILINE)

class BundleOptions:
    def __init__(self, enabled: bool, role: str | None = None,
                 argv: list[str] | None = None) -> None:
        self.enabled = enabled
        self.role = role
        self.argv = list(argv or [])

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
    if step_ino:
        return step_ino != f"{st.st_dev}:{st.st_ino}"
    return env.get("IN_RUN_BLOCK") != "1"

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
