BUNDLE_PROTOCOL_VERSION = "1"
BUNDLE_NAME = "vitalio/todo-md"
BUNDLE_FLAGS = ("-B", "--bundle", "--plain")
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

def bundle_mode_enabled(bundle_flag: bool, plain_flag: bool) -> bool:
    if bundle_flag:
        return True
    if plain_flag or os.environ.get("TODO_MD_PLAIN") == "1":
        return False
    return os.environ.get("TODO_MD_BUNDLE") == "1"

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
