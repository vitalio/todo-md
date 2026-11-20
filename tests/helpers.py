#!/usr/bin/env python3
"""Shared test helpers and base test case for todo_md test modules."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "todo_md"
INSTALL_SH = ROOT / "install.sh"

_CACHED_TODO_MD_MOD: ModuleType | None = None


def _load_todo_md_module() -> ModuleType:
    global _CACHED_TODO_MD_MOD
    if _CACHED_TODO_MD_MOD is None:
        loader = importlib.machinery.SourceFileLoader("todo_md_cli", str(SCRIPT))
        spec = importlib.util.spec_from_loader("todo_md_cli", loader)
        if spec is None:
            raise RuntimeError(f"failed to load module spec from {SCRIPT}")
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _CACHED_TODO_MD_MOD = module
    return _CACHED_TODO_MD_MOD


class TodoMdTestCase(unittest.TestCase):
    todo_md_mod: ModuleType = _load_todo_md_module()

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.todo_md_mod = _load_todo_md_module()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="todo_md_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _table_rows(self, output: str) -> dict[str, str]:
        rows: dict[str, str] = {}
        cur_key: str | None = None
        for line in output.splitlines():
            if not line.startswith("  ") or line.strip().startswith("IDs"):
                cur_key = None
                continue
            if line.startswith("    ") and cur_key is not None:
                rows[cur_key] = f"{rows[cur_key]} {line.strip()}"
                continue
            parts = line.split()
            if parts:
                cur_key = parts[0]
                rows[cur_key] = line
        return rows

    def _assert_ok(
        self, args: list[str], proc: subprocess.CompletedProcess[str]
    ) -> None:
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"{args!r} failed (rc={proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        )

    def _run_subprocess(
        self, args: list[str], *, check: bool = False, **kwargs
    ) -> subprocess.CompletedProcess[str]:
        kwargs.setdefault("cwd", str(self.tmp))
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        proc = subprocess.run(args, check=False, **kwargs)
        if check:
            self._assert_ok(args, proc)
        return proc

    def _run_in_process(
        self, args: list[str], *, check: bool = False, **kwargs
    ) -> subprocess.CompletedProcess[str]:
        cwd = str(kwargs.pop("cwd", self.tmp))
        input_data = kwargs.pop("input", None)
        env = kwargs.pop("env", None)
        if kwargs:
            raise ValueError(f"unsupported in-process _run kwargs: {sorted(kwargs)}")

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        stdin_buf = io.StringIO("" if input_data is None else input_data)

        old_cwd = os.getcwd()
        old_argv = sys.argv
        old_stdin = sys.stdin
        old_env = os.environ.copy() if env is not None else None
        rc = 0
        try:
            os.chdir(cwd)
            if env is not None:
                os.environ.clear()
                os.environ.update(env)
            sys.argv = [str(SCRIPT), *args[1:]]
            sys.stdin = stdin_buf
            with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                try:
                    rc = int(self.todo_md_mod.main(args[1:]))
                except SystemExit as exc:
                    if exc.code is None:
                        rc = 0
                    elif isinstance(exc.code, int):
                        rc = exc.code
                    else:
                        err_buf.write(f"{exc.code}\n")
                        rc = 1
        finally:
            if old_env is not None:
                os.environ.clear()
                os.environ.update(old_env)
            sys.stdin = old_stdin
            sys.argv = old_argv
            os.chdir(old_cwd)

        proc = subprocess.CompletedProcess(
            args=args,
            returncode=rc,
            stdout=out_buf.getvalue(),
            stderr=err_buf.getvalue(),
        )
        if check:
            self._assert_ok(args, proc)
        return proc

    def _run(
        self, args: list[str], *, check: bool = False, **kwargs
    ) -> subprocess.CompletedProcess[str]:
        if (
            not args
            or args[0] != str(SCRIPT)
            or "stdin" in kwargs
            or "timeout" in kwargs
        ):
            return self._run_subprocess(args, check=check, **kwargs)
        return self._run_in_process(args, check=check, **kwargs)
