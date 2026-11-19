#!/usr/bin/env python3
"""Tests for todo_md and install.sh."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import pty
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "todo_md"
INSTALL_SH = ROOT / "install.sh"


class TestTodoMd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("todo_md_cli", str(SCRIPT))
        spec = importlib.util.spec_from_loader("todo_md_cli", loader)
        if spec is None:
            raise RuntimeError(f"failed to load module spec from {SCRIPT}")
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        cls.todo_md_mod = module

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

    def test_help_version_and_agents(self):
        rh = self._run_subprocess([str(SCRIPT), "-h"])
        self.assertEqual(rh.returncode, 0)
        self.assertIn("Usage:", rh.stdout)
        self.assertNotIn("resume", rh.stdout)
        self.assertNotIn("TODO_PLAN.md", rh.stdout)
        self.assertIn("next <ID>", rh.stdout)
        self.assertIn("reopen <ID>", rh.stdout)
        self.assertIn("--reopen", rh.stdout)
        self.assertIn("-C DIR|PROJ, --project NAME", rh.stdout)
        self.assertIn("add", rh.stdout)
        self.assertIn("--role ROLE", rh.stdout)
        self.assertIn("opts: --role ROLE, --ready, --tree, --limit N, --full", rh.stdout)
        self.assertIn("edit", rh.stdout)
        self.assertIn("append", rh.stdout)

        rv = self._run_subprocess([str(SCRIPT), "--version"])
        self.assertEqual(rv.returncode, 0)
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(rv.stdout.strip(), f"todo_md {ver}")

        self.assertNotIn("--agents", rh.stdout)
        rule_txt = (ROOT / "src/rules/todo_md.md").read_text(encoding="utf-8")
        self.assertIn("Repository scope only", rule_txt)
        self.assertIn("🎯 [NEXT]", rule_txt)
        self.assertIn("TODO_ARCHIVE.md", rule_txt)
        self.assertIn("reopen <ID>", rule_txt)
        self.assertIn("--reopen", rule_txt)
        bundle_txt = (ROOT / "src/bundles/todo_md.bundle").read_text(encoding="utf-8")
        self.assertIn("rule vitalio/todo_md:todo_md", bundle_txt)
        self.assertNotIn("task=next", bundle_txt)
        self.assertIn("$ todo_md status {task:} WIP", bundle_txt)
        self.assertIn("todo_md next-id", bundle_txt)
        self.assertIn("[if task=] var task=$(todo_md next-id)", bundle_txt)
        self.assertIn("Emit your first run_block in this very first reply", bundle_txt)
        self.assertIn("propose the top task shown in the todo_md overview above", bundle_txt)
        self.assertIn("include $(todo_md files {task:} --max-lines 400 --max-total-lines 1200 --max-bytes 32768)", bundle_txt)
        self.assertIn("key symbol names (functions/classes) in backticks", bundle_txt)
        self.assertIn("--max-total-bytes N", rule_txt)
        self.assertIn("key symbol names in backticks", rule_txt)
        self.assertIn("-C <dir|project>` or `--project <name>`", rule_txt)
        self.assertIn("list [active|archive|all|<STATUS>] [--role <role>] [--ready] [--tree]", rule_txt)
        self.assertIn("⏳ [WIP]` / `⏳ [NEXT]", rule_txt)
        self.assertIn("[blocked: A (<STATUS>) -> B (<STATUS>)]", rule_txt)
        self.assertIn("--max-total-lines N", rh.stdout)
        self.assertIn("queue <ID> [--all]", rh.stdout)
        self.assertIn("chain [--by-role] [--role ROLE] [--ready] [--limit N] [--include-hold]", rh.stdout)
        self.assertIn("next-id [<ID>]", rh.stdout)
        self.assertIn("queue <ID> [--all]", rule_txt)
        self.assertIn("chain [--by-role] [--role <role>] [--ready] [--limit N] [--include-hold]", rule_txt)
        self.assertIn("next-id [<ID>]", rule_txt)
        self.assertIn("A -> B -> C", rule_txt)
        self.assertIn("do not introduce a separate `- Order:` field", rule_txt)
        self.assertIn("[if task=last] var task=$(todo_md last-id DONE)", bundle_txt)
        self.assertIn("[if task=DONE] var task=$(todo_md last-id DONE)", bundle_txt)
        self.assertIn("[if role=work]", bundle_txt)
        self.assertIn("[if role=review]", bundle_txt)
        self.assertNotIn("role=execute", bundle_txt)
        self.assertNotIn("role=audit", bundle_txt)
        self.assertIn("role=work", rule_txt)
        self.assertIn("role=review", rule_txt)
        self.assertNotIn("role=execute", rule_txt)
        self.assertNotIn("role=audit", rule_txt)

    def test_init_summary_priority_smart_truncation_and_check(self):
        r_init = self._run([str(SCRIPT), "init"])
        self.assertEqual(r_init.returncode, 0)
        self.assertTrue((self.tmp / "TODO.md").is_file())
        self.assertFalse((self.tmp / "TODO_PLAN.md").exists())
        self.assertTrue((self.tmp / "TODO_ARCHIVE.md").is_file())

        # Add 6 tasks using prefix / default auto-numbering; task P1 has a multi-line body
        long_body = "\n".join(f"Detail line {i}" for i in range(1, 10))
        self._run([str(SCRIPT), "add", "P", "Long backlog item", "-b", long_body], check=True)
        for idx in range(1, 6):
            self._run([str(SCRIPT), "add", f"Feature {idx}", "-b", f"Body {idx}"], check=True)

        # Promote F3 to NEXT priority
        r_nxt = self._run([str(SCRIPT), "next", "F3", "-m", "top priority"])
        self.assertEqual(r_nxt.returncode, 0, r_nxt.stderr)
        todo_content = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertLess(todo_content.index("F3:"), todo_content.index("P1:"))
        self.assertIn("# 🎯 [NEXT] F3: Feature 3 — *top priority*", todo_content)

        # Default summary truncates long NEW task P1 (>5 tasks total), while --full shows all lines
        r_sum = self._run([str(SCRIPT)])
        self.assertEqual(r_sum.returncode, 0)
        self.assertIn("Body 3", r_sum.stdout)
        self.assertIn("Detail line 1", r_sum.stdout)
        self.assertNotIn("Detail line 8", r_sum.stdout)
        self.assertIn("+8 more lines", r_sum.stdout)

        r_full = self._run([str(SCRIPT), "--full"])
        self.assertEqual(r_full.returncode, 0)
        self.assertIn("Detail line 8", r_full.stdout)

        # Done automatically stamps ISO date
        today = date.today().isoformat()
        r_done = self._run([str(SCRIPT), "done", "F3", "-m", "abc1234"])
        self.assertEqual(r_done.returncode, 0, r_done.stderr)
        arch_txt = (self.tmp / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn(f"# ✅ [DONE] F3: Feature 3 — *{today}, abc1234*", arch_txt)

        r_chk = self._run([str(SCRIPT), "check"])
        self.assertEqual(r_chk.returncode, 0, r_chk.stderr)

    def test_add_edit_append_cli(self):
        r_idea = self._run(
            [str(SCRIPT), "init"],
            input="Initial project idea from stdin.\n",
            check=True,
        )
        self.assertEqual(r_idea.returncode, 0)
        self.assertIn("# 🎯 [NEXT] F1: Project concept and initial design", (self.tmp / "TODO.md").read_text(encoding="utf-8"))
        self.assertIn("Initial project idea from stdin.", (self.tmp / "TODO.md").read_text(encoding="utf-8"))
        self._run([str(SCRIPT), "init", "--force"], check=True)

        r_add = self._run(
            [str(SCRIPT), "add", "F", "First feature", "--status", "WIP", "-m", "active now"],
            input="Feature body line 1.\n",
        )
        self.assertEqual(r_add.returncode, 0, r_add.stderr)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🔵 [WIP] F1: First feature — *active now*", todo_txt)

        r_app = self._run(
            [str(SCRIPT), "append", "F1", "-b", "- [x] Substep 1"],
        )
        self.assertEqual(r_app.returncode, 0, r_app.stderr)
        self.assertIn("Substep 1", (self.tmp / "TODO.md").read_text(encoding="utf-8"))

        r_ed = self._run(
            [str(SCRIPT), "edit", "F1", "-t", "Renamed feature", "-m", "updated note", "-b", "Replaced body."],
        )
        self.assertEqual(r_ed.returncode, 0, r_ed.stderr)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🔵 [WIP] F1: Renamed feature — *updated note*", todo_txt)
        self.assertIn("Replaced body.", todo_txt)

        # Passing an already-used explicit ID (e.g. F1) auto-assigns next free ID (F2) without failing
        r_dup = self._run(
            [str(SCRIPT), "add", "F1", "Second feature auto-numbered"],
        )
        self.assertEqual(r_dup.returncode, 0, r_dup.stderr)
        self.assertIn("added F2", r_dup.stdout)
        self.assertIn("ignoring explicit ID F1; auto-assigned F2", r_dup.stderr)

        # -p / --prefix flag assigns next free ID for that prefix
        r_pfx = self._run(
            [str(SCRIPT), "add", "-p", "B", "Bugfix task"],
        )
        self.assertEqual(r_pfx.returncode, 0, r_pfx.stderr)
        self.assertIn("added B1", r_pfx.stdout)

        r_chk = self._run([str(SCRIPT), "check"])
        self.assertEqual(r_chk.returncode, 0, r_chk.stderr)

    def test_status_ordering_and_archive_prepend(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run([str(SCRIPT), "add", "Hold task", "--status", "HOLD", "-b", "Hold line 1\nHold line 2"], check=True)
        self._run([str(SCRIPT), "add", "New task", "--status", "NEW", "-b", "New line 1\nNew line 2"], check=True)
        self._run([str(SCRIPT), "add", "Question task", "--status", "QUESTION", "-b", "Q line 1\nQ line 2"], check=True)

        # Transition F1 (HOLD) -> WIP and F2 (NEW) -> NEXT; verify TODO.md is ordered WIP -> NEXT -> QUESTION
        self._run([str(SCRIPT), "status", "F2", "NEXT"], check=True)
        self._run([str(SCRIPT), "status", "F1", "WIP"], check=True)
        self._run([str(SCRIPT), "add", "Another new", "--status", "NEW", "-b", "Compact line 1\nCompact line 2"], check=True)
        self._run([str(SCRIPT), "add", "Another hold", "--status", "HOLD", "-b", "Hold body 1\nHold body 2"], check=True)

        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertLess(todo_txt.index("F1:"), todo_txt.index("F2:"))
        self.assertLess(todo_txt.index("F2:"), todo_txt.index("F3:"))
        self.assertLess(todo_txt.index("F3:"), todo_txt.index("F4:"))
        self.assertLess(todo_txt.index("F4:"), todo_txt.index("F5:"))

        # Summary compacts NEW/HOLD even when <= 5 tasks total, while expanding WIP/NEXT/QUESTION
        r_sum = self._run([str(SCRIPT)], check=True)
        self.assertIn("Q line 2", r_sum.stdout)
        self.assertIn("Compact line 1", r_sum.stdout)
        self.assertNotIn("Compact line 2", r_sum.stdout)
        self.assertNotIn("Hold body 2", r_sum.stdout)

        # Archiving tasks prepends newest to the top of TODO_ARCHIVE.md
        self._run([str(SCRIPT), "done", "F1", "-m", "first"], check=True)
        self._run([str(SCRIPT), "cancel", "F5", "-m", "second"], check=True)
        arch_txt = (self.tmp / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertLess(arch_txt.index("F5:"), arch_txt.index("F1:"))

    def test_git_default_no_commit_and_opt_in_commit(self):
        self._run_subprocess(["git", "init"], check=True)
        self._run_subprocess(["git", "config", "user.name", "Test User"], check=True)
        self._run_subprocess(["git", "config", "user.email", "test@example.com"], check=True)

        # Create a staged non-TODO file to verify todo_md --commit commits ONLY TODO*.md
        other_file = self.tmp / "unrelated.txt"
        other_file.write_text("unrelated staged work\n", encoding="utf-8")
        self._run_subprocess(["git", "add", "unrelated.txt"], check=True)

        # Default init does NOT git-commit
        r_init = self._run_subprocess([str(SCRIPT), "init", "Initial idea"], check=True)
        self.assertNotIn("committed", r_init.stdout)

        # Add with -c / --commit commits TODO*.md (including the initialized files)
        r_add1 = self._run_subprocess([str(SCRIPT), "add", "Task A", "-c"], check=True)
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_add1.stdout)

        # Verify unrelated.txt is still staged and was NOT included in the todo_md commit
        r_show = self._run_subprocess(["git", "show", "--name-only", "--pretty=format:", "HEAD"], check=True)
        committed_files = r_show.stdout.strip().splitlines()
        self.assertEqual(committed_files, ["TODO.md", "TODO_ARCHIVE.md"])
        r_st = self._run_subprocess(["git", "status", "--porcelain"], check=True)
        self.assertIn("A  unrelated.txt", r_st.stdout)

        # Default add without --commit does not commit; --no-commit is accepted as a no-op alias
        r_add2 = self._run_subprocess([str(SCRIPT), "add", "Task B"], check=True)
        self.assertNotIn("committed", r_add2.stdout)
        r_add3 = self._run_subprocess([str(SCRIPT), "add", "Task C", "--no-commit"], check=True)
        self.assertNotIn("committed", r_add3.stdout)

        # Done with --commit moves task to TODO_ARCHIVE.md and commits both files
        r_done = self._run_subprocess([str(SCRIPT), "done", "F2", "-m", "1234567", "--commit"], check=True)
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_done.stdout)
        self.assertIn("Complete task F2: Task A", r_done.stdout)

        r_log = self._run_subprocess(["git", "log", "--oneline"], check=True)
        self.assertEqual(len(r_log.stdout.strip().splitlines()), 2)

    def test_next_id_files_and_pipe_output(self):
        self._run([str(SCRIPT), "init"], check=True)
        r_empty = self._run([str(SCRIPT), "next-id"])
        self.assertEqual(r_empty.returncode, 1)
        self.assertIn("no active WIP or NEXT task", r_empty.stderr)

        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# Demo\n", encoding="utf-8")
        body = (
            "- Update `src/app.py:10` and `README.md` (and `src/app.py` again).\n"
            "- Ignore missing `src/missing.py` and external `../outside.py`.\n"
            "```text\n"
            "Ignore fenced `build.py`\n"
            "```\n"
        )
        (self.tmp / "build.py").write_text("# fenced\n", encoding="utf-8")
        self._run([str(SCRIPT), "add", "Next task", "--next", "-b", body], check=True)
        self._run([str(SCRIPT), "add", "Wip task", "--status", "WIP", "-b", "Touch `README.md`."], check=True)

        for flag in ("next-id", "--next-id", "--top"):
            r_tid = self._run([str(SCRIPT), flag])
            self.assertEqual(r_tid.returncode, 0, r_tid.stderr)
            self.assertEqual(r_tid.stdout.strip(), "F2")

        r_files = self._run([str(SCRIPT), "files", "F1"])
        self.assertEqual(r_files.returncode, 0, r_files.stderr)
        self.assertEqual(r_files.stdout.splitlines(), ["src/app.py", "README.md"])

        r_files_top = self._run([str(SCRIPT), "--files"])
        self.assertEqual(r_files_top.returncode, 0, r_files_top.stderr)
        self.assertEqual(r_files_top.stdout.splitlines(), ["README.md"])

        r_pipe = self._run([str(SCRIPT), "F1"])
        self.assertEqual(r_pipe.returncode, 0)
        self.assertIn("# 🎯 [NEXT] F1: Next task", r_pipe.stdout)
        self.assertEqual(r_pipe.stderr, "")

    def test_last_last_id_and_list_options(self):
        self._run([str(SCRIPT), "init"], check=True)
        for status, title, body in [
            ("WIP", "Wip one", "Body W1"),
            ("WIP", "Wip two", "Body W2"),
            ("NEXT", "Next one", "Body N1"),
            ("NEXT", "Next two", "Body N2"),
            ("QUESTION", "Question one", "Body Q1"),
            ("QUESTION", "Question two", "Body Q2"),
            ("NEW", "New one", "Body U1"),
            ("NEW", "New two", "Body U2"),
            ("HOLD", "Hold one", "Body H1"),
            ("HOLD", "Hold two", "Body H2"),
        ]:
            self._run(
                [str(SCRIPT), "add", title, "--status", status, "-b", body],
                check=True,
            )

        # Add two archived tasks (F11 done first, F12 canceled second -> F12 is top of TODO_ARCHIVE.md)
        self._run([str(SCRIPT), "add", "Done task", "-b", "Body D1"], check=True)
        self._run([str(SCRIPT), "done", "F11", "-m", "done1"], check=True)
        self._run([str(SCRIPT), "add", "Canceled task", "-b", "Body C1"], check=True)
        self._run([str(SCRIPT), "cancel", "F12", "-m", "drop1"], check=True)

        # Default last-id resolves to bottom-most NEW task (F8)
        r_def = self._run([str(SCRIPT), "last-id"])
        self.assertEqual(r_def.returncode, 0, r_def.stderr)
        self.assertEqual(r_def.stdout.strip(), "F8")

        # Group-specific last-id resolution
        # add --status WIP/NEXT prepends to top of group (F2 above F1, F4 above F3)
        expected_ids = {
            "WIP": "F2",
            "NEXT": "F4",
            "QUESTION": "F6",
            "NEW": "F8",
            "HOLD": "F10",
            "DONE": "F11",
            "CANCELED": "F12",
            "archive": "F12",
        }
        for filt, exp in expected_ids.items():
            r = self._run([str(SCRIPT), "last-id", filt])
            self.assertEqual(r.returncode, 0, f"{filt}: {r.stderr}")
            self.assertEqual(r.stdout.strip(), exp, f"last-id {filt}")

        # last and show last render full section for resolved task
        r_last = self._run([str(SCRIPT), "last", "DONE"])
        self.assertEqual(r_last.returncode, 0, r_last.stderr)
        self.assertIn("# TODO_ARCHIVE.md:", r_last.stdout)
        self.assertIn("# ✅ [DONE] F11: Done task", r_last.stdout)
        self.assertIn("Body D1", r_last.stdout)
        self.assertIn("IDs in use:", r_last.stdout)

        r_show_last = self._run([str(SCRIPT), "show", "last"])
        self.assertEqual(r_show_last.returncode, 0, r_show_last.stderr)
        self.assertIn("# TODO.md:", r_show_last.stdout)
        self.assertIn("# ⚪ [NEW] F8: New two", r_show_last.stdout)
        self.assertIn("Body U2", r_show_last.stdout)

        # list and list -w display active tasks in exact TODO.md file order (top to bottom)
        r_list_new = self._run([str(SCRIPT), "list", "NEW"], check=True)
        self.assertLess(r_list_new.stdout.index("F7"), r_list_new.stdout.index("F8"))

        r_list_act = self._run([str(SCRIPT), "list", "active"], check=True)
        out = r_list_act.stdout
        self.assertLess(out.index("F2"), out.index("F1"))
        self.assertLess(out.index("F4"), out.index("F3"))
        self.assertLess(out.index("F5"), out.index("F6"))
        self.assertLess(out.index("F7"), out.index("F8"))
        self.assertLess(out.index("F9"), out.index("F10"))

        ws_dir = self.tmp / "ws_order"
        ws_proj = ws_dir / "proj"
        ws_proj.mkdir(parents=True)
        shutil.copy2(self.tmp / "TODO.md", ws_proj / "TODO.md")
        shutil.copy2(self.tmp / "TODO_ARCHIVE.md", ws_proj / "TODO_ARCHIVE.md")
        r_ws_act = self._run(
            [str(SCRIPT), "list", "-w", "active"],
            cwd=str(ws_dir),
            env={**os.environ, "TODO_MD_WORKSPACE": str(ws_dir)},
            check=True,
        )
        ws_out = r_ws_act.stdout
        self.assertLess(ws_out.index("proj:F2"), ws_out.index("proj:F1"))
        self.assertLess(ws_out.index("proj:F4"), ws_out.index("proj:F3"))
        self.assertLess(ws_out.index("proj:F5"), ws_out.index("proj:F6"))
        self.assertLess(ws_out.index("proj:F7"), ws_out.index("proj:F8"))
        self.assertLess(ws_out.index("proj:F9"), ws_out.index("proj:F10"))

        # list --limit N and --full
        r_lim = self._run([str(SCRIPT), "list", "NEW", "--limit", "1", "--full"], check=True)
        self.assertIn("# ⚪ [NEW] F7: New one", r_lim.stdout)
        self.assertIn("Body U1", r_lim.stdout)
        self.assertNotIn("F8", r_lim.stdout)

        r_lim_short = self._run([str(SCRIPT), "list", "archive", "-n", "1"], check=True)
        self.assertIn("F12", r_lim_short.stdout)
        self.assertNotIn("F11", r_lim_short.stdout)

    def test_body_dash_stdin_and_tty_error(self):
        self._run([str(SCRIPT), "init"], check=True)

        # add with -b - and --body - from piped stdin
        r_add = self._run(
            [str(SCRIPT), "add", "Dash body task", "-b", "-"],
            input="Line from dash\n",
        )
        self.assertEqual(r_add.returncode, 0, r_add.stderr)
        self.assertIn("Line from dash", (self.tmp / "TODO.md").read_text(encoding="utf-8"))

        # add with --body - and empty stdin creates task without body
        r_add_empty = self._run(
            [str(SCRIPT), "add", "Empty dash body", "--body", "-"],
            input="   \n",
        )
        self.assertEqual(r_add_empty.returncode, 0, r_add_empty.stderr)
        self.assertIn("# ⚪ [NEW] F2: Empty dash body", (self.tmp / "TODO.md").read_text(encoding="utf-8"))

        # append with --body - from piped stdin, and empty stdin rejection
        r_app = self._run(
            [str(SCRIPT), "append", "F1", "--body", "-"],
            input="- [x] Appended via dash\n",
        )
        self.assertEqual(r_app.returncode, 0, r_app.stderr)
        self.assertIn("Appended via dash", (self.tmp / "TODO.md").read_text(encoding="utf-8"))

        r_app_empty = self._run(
            [str(SCRIPT), "append", "F1", "-b", "-"],
            input="  \n",
        )
        self.assertNotEqual(r_app_empty.returncode, 0)
        self.assertIn("requires non-empty text", r_app_empty.stderr)

        # edit with --body - updates body, and empty stdin clears body like -b ""
        r_ed = self._run(
            [str(SCRIPT), "edit", "F1", "--body", "-"],
            input="Replaced via dash\n",
        )
        self.assertEqual(r_ed.returncode, 0, r_ed.stderr)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("Replaced via dash", todo_txt)
        self.assertNotIn("Line from dash", todo_txt)

        r_ed_clear = self._run(
            [str(SCRIPT), "edit", "F1", "-b", "-"],
            input="",
        )
        self.assertEqual(r_ed_clear.returncode, 0, r_ed_clear.stderr)
        self.assertNotIn("Replaced via dash", (self.tmp / "TODO.md").read_text(encoding="utf-8"))

        # TTY stdin fails fast for add, edit, and append with -b - / --body -
        cases = [
            (["add", "TTY task", "-b", "-"], "-b -"),
            (["edit", "F1", "--body", "-"], "--body -"),
            (["append", "F1", "-b", "-"], "-b -"),
        ]
        for args, label in cases:
            with self.subTest(cmd=args[0], flag=label):
                master_fd, slave_fd = pty.openpty()
                try:
                    r_tty = self._run_subprocess(
                        [str(SCRIPT), *args],
                        stdin=slave_fd,
                        timeout=5,
                    )
                finally:
                    os.close(slave_fd)
                    os.close(master_fd)
                self.assertNotEqual(r_tty.returncode, 0, msg=r_tty.stdout)
                self.assertIn("requires non-TTY stdin", r_tty.stderr)

    def test_summary_expands_first_task_when_only_new_or_hold(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run(
            [str(SCRIPT), "add", "First new", "-b", "N1 line 1\nN1 line 2\nN1 line 3"],
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Second new", "-b", "N2 line 1\nN2 line 2\nN2 line 3"],
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "First hold", "--status", "HOLD", "-b", "H1 line 1\nH1 line 2\nH1 line 3"],
            check=True,
        )

        # No WIP/NEXT/QUESTION -> first ordered task (F1) is expanded, subsequent NEW/HOLD are compacted
        r_only_new = self._run([str(SCRIPT)], check=True)
        self.assertIn("N1 line 3", r_only_new.stdout)
        self.assertIn("N2 line 1", r_only_new.stdout)
        self.assertNotIn("N2 line 3", r_only_new.stdout)
        self.assertIn("todo_md F2", r_only_new.stdout)
        self.assertNotIn("H1 line 3", r_only_new.stdout)
        self.assertIn("todo_md F3", r_only_new.stdout)

        # Adding a WIP/NEXT/QUESTION task compacts all NEW/HOLD tasks including F1
        self._run(
            [str(SCRIPT), "add", "Active question", "--status", "QUESTION", "-b", "Q1 line 1\nQ1 line 2"],
            check=True,
        )
        r_with_q = self._run([str(SCRIPT)], check=True)
        self.assertIn("Q1 line 2", r_with_q.stdout)
        self.assertIn("N1 line 1", r_with_q.stdout)
        self.assertNotIn("N1 line 3", r_with_q.stdout)
        self.assertIn("todo_md F1", r_with_q.stdout)

        # When only HOLD tasks exist, the first HOLD task is expanded and later HOLD tasks stay compact
        self._run([str(SCRIPT), "init", "--force"], check=True)
        self._run(
            [str(SCRIPT), "add", "Hold one", "--status", "HOLD", "-b", "H1 line 1\nH1 line 2\nH1 line 3"],
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Hold two", "--status", "HOLD", "-b", "H2 line 1\nH2 line 2\nH2 line 3"],
            check=True,
        )
        r_only_hold = self._run([str(SCRIPT)], check=True)
        self.assertIn("H1 line 3", r_only_hold.stdout)
        self.assertIn("H2 line 1", r_only_hold.stdout)
        self.assertNotIn("H2 line 3", r_only_hold.stdout)
        self.assertIn("todo_md F2", r_only_hold.stdout)

    def test_workspace_discovery_addressing_and_depends(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        proj_a = ws / "proj_a"
        proj_b = ws / "parent_proj"
        proj_c = ws / "parent_proj" / "sub_proj"
        hidden = ws / ".hidden_proj"
        vendor = ws / "node_modules" / "pkg"
        for d in (proj_a, proj_b, proj_c, hidden, vendor):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), str(d), "init"], check=True)

        # Nested subproject without TODO.md does NOT climb to parent git root
        sub_no_todo = proj_b / "sub_empty"
        sub_no_todo.mkdir()
        self._run(["git", "init"], cwd=str(proj_b), check=True)
        r_sub_chk = self._run([str(SCRIPT), "check"], cwd=str(sub_no_todo))
        self.assertNotEqual(r_sub_chk.returncode, 0)

        # Add tasks in projects
        self._run([str(SCRIPT), "add", "proj_a", "Base rule", "--next"], cwd=str(ws), check=True)
        self._run([str(SCRIPT), "add", "Base parent task"], cwd=str(proj_b), check=True)

        # Missing dependency fails validation immediately on add
        r_bad_dep = self._run(
            [str(SCRIPT), "add", "Sub feature", "--depends", "proj_a:F1,F99"],
            cwd=str(proj_c),
        )
        self.assertNotEqual(r_bad_dep.returncode, 0)
        self.assertIn("missing task 'F99'", r_bad_dep.stderr)

        # Edit F1 in proj_c to depend only on proj_a:F1 (cross-project)
        self._run(
            [str(SCRIPT), "edit", "parent_proj/sub_proj:F1", "--depends", "proj_a:F1"],
            cwd=str(ws),
            check=True,
        )
        self._run([str(SCRIPT), "check"], cwd=str(proj_c), check=True)

        # Show surfaces blocked dependency status, then DONE after proj_a:F1 is completed
        r_show_blocked = self._run([str(SCRIPT), "parent_proj/sub_proj:F1"], cwd=str(ws), check=True)
        self.assertIn("Dependencies (blocked): proj_a:F1", r_show_blocked.stdout)
        self._run([str(SCRIPT), "done", "proj_a:F1", "-m", "done"], cwd=str(ws), check=True)
        r_show_ready = self._run([str(SCRIPT), "parent_proj/sub_proj:F1"], cwd=str(ws), check=True)
        self.assertIn("Dependencies (ready): proj_a:F1 ✅ [DONE]", r_show_ready.stdout)

        # Workspace projects listing skips .hidden_proj and node_modules, includes parent_proj and parent_proj/sub_proj
        r_projs = self._run([str(SCRIPT), "projects"], cwd=str(ws), check=True)
        self.assertIn("proj_a", r_projs.stdout)
        self.assertIn("parent_proj", r_projs.stdout)
        self.assertIn("parent_proj/sub_proj", r_projs.stdout)
        self.assertNotIn(".hidden_proj", r_projs.stdout)
        self.assertNotIn("node_modules", r_projs.stdout)

        # Workspace overview (-w from inside a project, and auto-workspace from ws root)
        r_ws_flag = self._run([str(SCRIPT), "-w"], cwd=str(proj_b), check=True)
        self.assertIn("parent_proj/sub_proj:F1", r_ws_flag.stdout)
        r_ws_auto = self._run([str(SCRIPT)], cwd=str(ws), check=True)
        self.assertIn("## parent_proj/sub_proj", r_ws_auto.stdout)

        # Workspace list and check
        r_ws_list = self._run([str(SCRIPT), "-w", "list", "active"], cwd=str(proj_b), check=True)
        self.assertIn("parent_proj/sub_proj:F1", r_ws_list.stdout)
        self._run([str(SCRIPT), "-w", "check"], cwd=str(proj_b), check=True)

        # todo_md.bundle runs todo_md -w when workspace=1
        bundle_txt = (ROOT / "src/bundles/todo_md.bundle").read_text(encoding="utf-8")
        self.assertIn("[if workspace=1] $ todo_md -w", bundle_txt)

    def test_single_task_headers_role_and_workdir(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        proj_a = ws / "proj_a"
        proj_a.mkdir()
        self._run([str(SCRIPT), str(proj_a), "init"], check=True)

        # Prefix defaults: D -> design, F/B -> work, P -> omitted when unset; heading note stripped from Title:
        self._run([str(SCRIPT), "add", "D", "Explore architecture", "-m", "rfc draft", "-b", "Design body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Implement feature", "-b", "Feature body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Fix bug", "-b", "Bug body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "P", "Idea without role", "-b", "Idea body"], cwd=str(proj_a), check=True)

        resolved_proj_a = str(proj_a.resolve())
        cases = [
            ("D1", "Explore architecture", "design"),
            ("F1", "Implement feature", "work"),
            ("B1", "Fix bug", "work"),
            ("P1", "Idea without role", None),
        ]
        for tid, expected_title, expected_role in cases:
            for cmd in ([str(SCRIPT), tid], [str(SCRIPT), "show", tid]):
                with self.subTest(tid=tid, cmd=cmd):
                    proc = self._run(cmd, cwd=str(proj_a), check=True)
                    lines = proc.stdout.splitlines()
                    if expected_role is not None:
                        self.assertEqual(
                            lines[:5],
                            [f"Task: {tid}", f"Title: {expected_title}", f"Role: {expected_role}", f"Workdir: {resolved_proj_a}", ""],
                        )
                        self.assertTrue(lines[5].startswith("# TODO.md:"), msg=proc.stdout)
                    else:
                        self.assertEqual(
                            lines[:4],
                            [f"Task: {tid}", f"Title: {expected_title}", f"Workdir: {resolved_proj_a}", ""],
                        )
                        self.assertNotIn("Role:", proc.stdout)
                        self.assertTrue(lines[4].startswith("# TODO.md:"), msg=proc.stdout)
        r_d1_note = self._run([str(SCRIPT), "D1"], cwd=str(proj_a), check=True)
        self.assertIn("# ⚪ [NEW] D1: Explore architecture — *rfc draft*", r_d1_note.stdout)

        # Explicit --role overrides prefix fallback and works on unmapped prefixes
        self._run([str(SCRIPT), "add", "F", "Audit task", "--role", "review", "--depends", "D1", "-b", "Review body"], cwd=str(proj_a), check=True)
        r_f2 = self._run([str(SCRIPT), "proj_a:F2"], cwd=str(ws), check=True)
        self.assertEqual(
            r_f2.stdout.splitlines()[:5],
            ["Task: F2", "Title: Audit task", "Role: review", f"Workdir: {resolved_proj_a}", ""],
        )
        self.assertIn("- Depends on: D1", r_f2.stdout)

        # edit --role updates or clears - Role: without dropping - Depends on:
        self._run([str(SCRIPT), "edit", "proj_a:F2", "--role", "plan"], cwd=str(ws), check=True)
        r_f2_plan = self._run([str(SCRIPT), "show", "proj_a:F2"], cwd=str(ws), check=True)
        self.assertEqual(r_f2_plan.stdout.splitlines()[:3], ["Task: F2", "Title: Audit task", "Role: plan"])
        self.assertIn("- Depends on: D1", r_f2_plan.stdout)

        self._run([str(SCRIPT), "edit", "F2", "--role", ""], cwd=str(proj_a), check=True)
        r_f2_cleared = self._run([str(SCRIPT), "F2"], cwd=str(proj_a), check=True)
        self.assertEqual(r_f2_cleared.stdout.splitlines()[:3], ["Task: F2", "Title: Audit task", "Role: work"])
        self.assertIn("- Depends on: D1", r_f2_cleared.stdout)

        self._run([str(SCRIPT), "edit", "P1", "--role", "design"], cwd=str(proj_a), check=True)
        r_p1 = self._run([str(SCRIPT), str(proj_a), "P1"], cwd=str(ws), check=True)
        self.assertEqual(
            r_p1.stdout.splitlines()[:5],
            ["Task: P1", "Title: Idea without role", "Role: design", f"Workdir: {resolved_proj_a}", ""],
        )

        # Fenced - Role: inside code block does not override prefix role
        fenced_body = "`" * 3 + "markdown\n- Role: custom\n" + "`" * 3 + "\nDetails."
        self._run([str(SCRIPT), "add", "F", "Fenced role test", "-b", fenced_body], cwd=str(proj_a), check=True)
        r_f3 = self._run([str(SCRIPT), "F3"], cwd=str(proj_a), check=True)
        self.assertEqual(r_f3.stdout.splitlines()[:3], ["Task: F3", "Title: Fenced role test", "Role: work"])

        # last / show last emit headers too
        r_last = self._run([str(SCRIPT), "show", "last"], cwd=str(proj_a), check=True)
        self.assertEqual(
            r_last.stdout.splitlines()[:5],
            ["Task: F3", "Title: Fenced role test", "Role: work", f"Workdir: {resolved_proj_a}", ""],
        )

        # Overview and list commands remain unchanged (no Task:/Title:/Role:/Workdir: headers)
        for cmd in (
            [str(SCRIPT)],
            [str(SCRIPT), "--full"],
            [str(SCRIPT), "list"],
        ):
            r_ov = self._run(cmd, cwd=str(proj_a), check=True)
            self.assertNotIn("Workdir:", r_ov.stdout, msg=f"cmd={cmd}")
            self.assertNotIn("Task:", r_ov.stdout, msg=f"cmd={cmd}")
            self.assertNotIn("Title:", r_ov.stdout, msg=f"cmd={cmd}")
        r_ws = self._run([str(SCRIPT), "-w"], cwd=str(ws), check=True)
        self.assertNotIn("Workdir:", r_ws.stdout)
        self.assertNotIn("Task:", r_ws.stdout)
        self.assertNotIn("Title:", r_ws.stdout)

        # Invalid multi-line --role fails explicitly
        r_bad_role = self._run([str(SCRIPT), "add", "Bad role", "--role", "a\nb"], cwd=str(proj_a))
        self.assertNotEqual(r_bad_role.returncode, 0)
        self.assertIn("single line", r_bad_role.stderr)

    def test_forbid_implicit_reopen_and_reopen_command(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        proj = ws / "proj"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        (proj / "app.py").write_text("print('ok')\n", encoding="utf-8")
        self._run([str(SCRIPT), "add", "Done task", "-b", "See `app.py`."], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Canceled task", "-b", "Body 2"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Second done", "-b", "Body 3"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Second canceled", "-b", "Body 4"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "done", "F1", "-m", "abc1234"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "cancel", "F2", "-m", "obsolete"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "done", "F3", "-m", "def5678"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "cancel", "F4", "-m", "wontfix"], cwd=str(proj), check=True)

        todo_before = (proj / "TODO.md").read_text(encoding="utf-8")
        arch_before = (proj / "TODO_ARCHIVE.md").read_text(encoding="utf-8")

        # Reject implicit reopening via status / next and reject re-archiving
        reject_cases = [
            (["status", "F1", "WIP"], "DONE", "abc1234"),
            (["status", "F1", "NEW"], "DONE", "abc1234"),
            (["next", "F1"], "DONE", "abc1234"),
            (["status", "F2", "HOLD"], "CANCELED", "obsolete"),
            (["next", "F2"], "CANCELED", "obsolete"),
            (["done", "F1"], "DONE", "abc1234"),
            (["cancel", "F1"], "DONE", "abc1234"),
            (["archive", "F1"], "DONE", "abc1234"),
            (["archive", "F2", "--canceled"], "CANCELED", "obsolete"),
            (["status", "F1", "DONE"], "DONE", "abc1234"),
            (["status", "F2", "CANCELED"], "CANCELED", "obsolete"),
        ]
        for args, exp_status, exp_note in reject_cases:
            with self.subTest(args=args):
                proc = self._run([str(SCRIPT), *args], cwd=str(proj))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)
                self.assertIn(exp_status, proc.stderr)
                self.assertIn(exp_note, proc.stderr)
                self.assertIn("--reopen", proc.stderr)
                self.assertIn("reopen", proc.stderr)

        self.assertEqual((proj / "TODO.md").read_text(encoding="utf-8"), todo_before)
        self.assertEqual((proj / "TODO_ARCHIVE.md").read_text(encoding="utf-8"), arch_before)

        # Read/audit commands continue to work on archived tasks
        for cmd in ([str(SCRIPT), "F1"], [str(SCRIPT), "show", "F1"], [str(SCRIPT), "files", "F1"]):
            r_read = self._run(cmd, cwd=str(proj), check=True)
            self.assertTrue(r_read.stdout.strip())

        # status --reopen clears prior closing note unless -m is provided
        r_reopen_wip = self._run([str(SCRIPT), "status", "F1", "WIP", "--reopen"], cwd=str(proj), check=True)
        self.assertIn("moved F1 ([WIP])", r_reopen_wip.stdout)
        todo_after_f1 = (proj / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🔵 [WIP] F1: Done task\n", todo_after_f1)
        self.assertNotIn("abc1234", todo_after_f1)
        self.assertNotIn("F1:", (proj / "TODO_ARCHIVE.md").read_text(encoding="utf-8"))

        # next --reopen with -m replaces closing note
        self._run([str(SCRIPT), "next", "F2", "--reopen", "-m", "retrying"], cwd=str(proj), check=True)
        todo_after_f2 = (proj / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🎯 [NEXT] F2: Canceled task — *retrying*", todo_after_f2)
        self.assertNotIn("obsolete", todo_after_f2)

        # reopen defaults to NEW and clears closing note; --status and -m customize it
        self._run([str(SCRIPT), "reopen", "proj:F3"], cwd=str(ws), check=True)
        todo_after_f3 = (proj / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# ⚪ [NEW] F3: Second done\n", todo_after_f3)
        self.assertNotIn("def5678", todo_after_f3)

        self._run([str(SCRIPT), "reopen", "F4", "--status", "HOLD", "-m", "paused"], cwd=str(proj), check=True)
        todo_after_f4 = (proj / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# ⏸️ [HOLD] F4: Second canceled — *paused*", todo_after_f4)
        self.assertNotIn("wontfix", todo_after_f4)

        # Reopening an already-active task or passing an archive status to reopen fails explicitly
        r_active = self._run([str(SCRIPT), "reopen", "F3"], cwd=str(proj))
        self.assertNotEqual(r_active.returncode, 0)
        self.assertIn("already active", r_active.stderr)
        r_bad_st = self._run([str(SCRIPT), "reopen", "F3", "--status", "DONE"], cwd=str(proj))
        self.assertNotEqual(r_bad_st.returncode, 0)
        self.assertIn("active status", r_bad_st.stderr)

        self._run([str(SCRIPT), "check"], cwd=str(proj), check=True)

    def test_files_budget_options(self):
        ws = self.tmp / "ws"
        proj = ws / "proj"
        proj.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)

        (proj / "small_a.py").write_text("\n".join(f"a{i}" for i in range(5)) + "\n", encoding="utf-8")
        (proj / "big.py").write_text("\n".join(f"b{i}" for i in range(25)) + "\n", encoding="utf-8")
        (proj / "small_b.py").write_text("\n".join(f"c{i}" for i in range(4)) + "\n", encoding="utf-8")
        (proj / "wide.txt").write_text("x" * 200 + "\n", encoding="utf-8")

        body = "Inspect `small_a.py`, `big.py`, `small_b.py`, and `wide.txt`."
        self._run([str(SCRIPT), "add", "Budget test", "--next", "-b", body], cwd=str(proj), check=True)

        # Bare files remains uncapped
        r_all = self._run([str(SCRIPT), "files", "F1"], cwd=str(proj), check=True)
        self.assertEqual(r_all.stdout.splitlines(), ["small_a.py", "big.py", "small_b.py", "wide.txt"])

        # Per-file line cap skips big.py while keeping small files
        r_ml = self._run([str(SCRIPT), "files", "--max-lines", "10", "F1"], cwd=str(proj), check=True)
        self.assertEqual(r_ml.stdout.splitlines(), ["small_a.py", "small_b.py", "wide.txt"])

        # Per-file byte cap skips big.py and wide.txt
        r_mb = self._run([str(SCRIPT), "files", "F1", "--max-bytes=50"], cwd=str(proj), check=True)
        self.assertEqual(r_mb.stdout.splitlines(), ["small_a.py", "small_b.py"])

        # Total line cap skips big.py (5 + 25 > 10) and still fits small_b.py (5 + 4 <= 10) and wide.txt (9 + 1 <= 10)
        r_mtl = self._run([str(SCRIPT), "files", "--max-total-lines", "10"], cwd=str(proj), check=True)
        self.assertEqual(r_mtl.stdout.splitlines(), ["small_a.py", "small_b.py", "wide.txt"])

        # Combined total byte cap + project:ID addressing
        r_mtb = self._run(
            [str(SCRIPT), "files", "proj:F1", "--max-bytes", "50", "--max-total-bytes", "20"],
            cwd=str(ws),
            check=True,
        )
        self.assertEqual(r_mtb.stdout.splitlines(), ["small_a.py"])

        # Invalid budget flags fail explicitly
        for bad_args in (
            ["files", "F1", "--max-lines", "0"],
            ["files", "F1", "--max-bytes=abc"],
            ["files", "F1", "--max-total-lines"],
            ["files", "F1", "--unknown"],
            ["files", "F1", "F2"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

    def test_list_role_display_and_filter(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        self._run([str(SCRIPT), "add", "D", "Design API", "-b", "Design body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Build CLI", "-b", "Work body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Fix crash", "-b", "Bug body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "P", "Unassigned role", "-b", "Proposal body"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Audit diff", "--role", "review", "-b", "Review body"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "D", "Done design", "-b", "Done body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "D2", "-m", "done"], cwd=str(proj_a), check=True)

        self._run([str(SCRIPT), "add", "F", "Other work", "-b", "B body"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "P", "Other review", "--role", "Review", "-b", "B review"],
            cwd=str(proj_b),
            check=True,
        )

        r_list = self._run([str(SCRIPT), "list"], cwd=str(proj_a), check=True)
        rows = {
            line.split()[0]: line
            for line in r_list.stdout.splitlines()
            if line.startswith("  ") and not line.strip().startswith("IDs")
        }
        self.assertIn("[design]", rows["D1"])
        self.assertIn("[work]", rows["F1"])
        self.assertIn("[work]", rows["B1"])
        self.assertIn("[review]", rows["F2"])
        self.assertNotIn("[design]", rows["P1"])
        self.assertNotIn("[work]", rows["P1"])
        self.assertNotIn("[review]", rows["P1"])

        r_design = self._run([str(SCRIPT), "list", "--role", "design"], cwd=str(proj_a), check=True)
        self.assertIn("D1", r_design.stdout)
        self.assertNotIn("F1", r_design.stdout)
        self.assertNotIn("F2", r_design.stdout)
        self.assertNotIn("P1", r_design.stdout)

        r_work = self._run([str(SCRIPT), "list", "active", "--role=WORK"], cwd=str(proj_a), check=True)
        self.assertIn("F1", r_work.stdout)
        self.assertIn("B1", r_work.stdout)
        self.assertNotIn("F2", r_work.stdout)
        self.assertNotIn("D1", r_work.stdout)

        r_review_full = self._run(
            [str(SCRIPT), "list", "--role", "REVIEW", "--limit", "1", "--full"],
            cwd=str(proj_a),
            check=True,
        )
        self.assertIn("# ⚪ [NEW] F2: Audit diff", r_review_full.stdout)
        self.assertIn("Review body", r_review_full.stdout)
        self.assertNotIn("F1", r_review_full.stdout)

        r_arch_design = self._run([str(SCRIPT), "list", "archive", "--role", "design"], cwd=str(proj_a), check=True)
        self.assertIn("D2", r_arch_design.stdout)
        self.assertIn("[design]", r_arch_design.stdout)

        r_none = self._run([str(SCRIPT), "list", "--role", "unknown"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (active, role=unknown)", r_none.stdout)

        r_ws_all = self._run([str(SCRIPT), "list", "-w"], cwd=str(proj_a), check=True)
        ws_rows = {
            line.split()[0]: line
            for line in r_ws_all.stdout.splitlines()
            if line.startswith("  ")
        }
        self.assertIn("[design]", ws_rows["proj_a:D1"])
        self.assertIn("[work]", ws_rows["proj_a:F1"])
        self.assertIn("[review]", ws_rows["proj_a:F2"])
        self.assertNotIn("[work]", ws_rows["proj_a:P1"])
        self.assertIn("[work]", ws_rows["proj_b:F1"])
        self.assertIn("[Review]", ws_rows["proj_b:P1"])

        r_ws_rev = self._run([str(SCRIPT), "-w", "list", "--role=review"], cwd=str(proj_a), check=True)
        self.assertIn("proj_a:F2", r_ws_rev.stdout)
        self.assertIn("proj_b:P1", r_ws_rev.stdout)
        self.assertNotIn("proj_a:F1", r_ws_rev.stdout)
        self.assertNotIn("proj_b:F1", r_ws_rev.stdout)

        r_ws_lim = self._run(
            [str(SCRIPT), "list", "-w", "--role", "work", "--limit", "1"],
            cwd=str(proj_a),
            check=True,
        )
        self.assertEqual(len(r_ws_lim.stdout.strip().splitlines()), 1)
        self.assertIn("[work]", r_ws_lim.stdout)

        r_ws_none = self._run([str(SCRIPT), "list", "-w", "--role", "missing"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (active, role=missing)", r_ws_none.stdout)

        for bad_args in (
            ["list", "--role"],
            ["list", "--role", ""],
            ["list", "--role="],
            ["list", "--role", "a\nb"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj_a))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

    def test_dependency_sequencing_queue_next_id_and_cycles(self):
        ws = self.tmp / "ws"
        orch = ws / "orch"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        for d in (orch, proj_a, proj_b):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Intra-project sequential stages + parallel commas + multiple Depends on lines
        self._run([str(SCRIPT), "add", "Stage 1A"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Stage 1B"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Stage 2C"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Branch 2X"], cwd=str(proj_a), check=True)
        self._run(
            [
                str(SCRIPT),
                "add",
                "Target T",
                "--depends",
                "F1, F2 -> F3",
                "--depends",
                "F4",
            ],
            cwd=str(proj_a),
            check=True,
        )
        todo_a = (proj_a / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Depends on: F1, F2 -> F3", todo_a)
        self.assertIn("- Depends on: F4", todo_a)

        r_show_f5 = self._run([str(SCRIPT), "F5"], cwd=str(proj_a), check=True)
        self.assertIn(
            "Dependencies (blocked): F1 ⚪ [NEW], F2 ⚪ [NEW] -> F3 ⚪ [NEW]; F4 ⚪ [NEW]",
            r_show_f5.stdout,
        )

        # Queue shows stable topological order with [ready] / [blocked by: ...] and Next actionable
        r_q1 = self._run([str(SCRIPT), "queue", "F5"], cwd=str(proj_a), check=True)
        q1_lines = r_q1.stdout.splitlines()
        self.assertLess(r_q1.stdout.index("F1"), r_q1.stdout.index("F3"))
        self.assertLess(r_q1.stdout.index("F2"), r_q1.stdout.index("F3"))
        self.assertLess(r_q1.stdout.index("F3"), r_q1.stdout.index("F5"))
        self.assertIn("[ready]", q1_lines[0])
        self.assertIn("[blocked by: F1, F2]", r_q1.stdout)
        self.assertIn("Next actionable: F1", r_q1.stdout)

        r_nid1 = self._run([str(SCRIPT), "next-id", "F5"], cwd=str(proj_a), check=True)
        self.assertEqual(r_nid1.stdout.strip(), "F1")

        # Complete F1 and F2 -> DONE tasks hidden by default, shown with --all; F3 becomes ready
        self._run([str(SCRIPT), "done", "F1", "-m", "done1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "F2", "-m", "done2"], cwd=str(proj_a), check=True)
        r_q2 = self._run([str(SCRIPT), "queue", "F5"], cwd=str(proj_a), check=True)
        self.assertNotIn("F1", r_q2.stdout)
        self.assertNotIn("F2", r_q2.stdout)
        self.assertIn("Next actionable: F3", r_q2.stdout)

        r_q2_all = self._run([str(SCRIPT), "queue", "F5", "--all"], cwd=str(proj_a), check=True)
        self.assertIn("F1", r_q2_all.stdout)
        self.assertIn("✅ [DONE]", r_q2_all.stdout)
        self.assertIn("Next actionable: F3", r_q2_all.stdout)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F5"], cwd=str(proj_a), check=True).stdout.strip(), "F3")

        # Complete F3 and F4 -> Dependencies (ready), next-id F5 returns F5 itself
        self._run([str(SCRIPT), "done", "F3", "-m", "done3"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "F4", "-m", "done4"], cwd=str(proj_a), check=True)
        r_show_ready = self._run([str(SCRIPT), "F5"], cwd=str(proj_a), check=True)
        self.assertIn(
            "Dependencies (ready): F1 ✅ [DONE], F2 ✅ [DONE] -> F3 ✅ [DONE]; F4 ✅ [DONE]",
            r_show_ready.stdout,
        )
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F5"], cwd=str(proj_a), check=True).stdout.strip(), "F5")

        # Cross-project orchestrator preserving one-way boundaries + transitive intra-project deps
        self._run([str(SCRIPT), "add", "Repo A base"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Repo B prereq"], cwd=str(proj_b), check=True)
        self._run([str(SCRIPT), "add", "Repo B child", "--depends", "F1"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Release orch", "--depends", "proj_a:F6 -> proj_b:F2"],
            cwd=str(orch),
            check=True,
        )
        proj_b_before = (proj_b / "TODO.md").read_text(encoding="utf-8")

        r_orch_q = self._run([str(SCRIPT), "queue", "F1"], cwd=str(orch), check=True)
        self.assertLess(r_orch_q.stdout.index("proj_a:F6"), r_orch_q.stdout.index("proj_b:F2"))
        self.assertLess(r_orch_q.stdout.index("proj_b:F1"), r_orch_q.stdout.index("proj_b:F2"))
        self.assertIn("[blocked by: proj_a:F6, proj_b:F1]", r_orch_q.stdout)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_a:F6")
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "orch:F1"], cwd=str(ws), check=True).stdout.strip(),
            "proj_a:F6",
        )
        self.assertEqual((proj_b / "TODO.md").read_text(encoding="utf-8"), proj_b_before)

        # Complete proj_a:F6 -> proj_b:F1 is next; complete proj_b:F1 -> proj_b:F2 is next
        self._run([str(SCRIPT), "done", "proj_a:F6", "-m", "d6"], cwd=str(ws), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_b:F1")
        self._run([str(SCRIPT), "done", "proj_b:F1", "-m", "db1"], cwd=str(ws), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_b:F2")

        # CANCELED blocker causes next-id to fail non-zero and queue to mark [blocked]
        self._run([str(SCRIPT), "cancel", "proj_b:F2", "-m", "dropped"], cwd=str(ws), check=True)
        r_q_can = self._run([str(SCRIPT), "queue", "F1"], cwd=str(orch), check=True)
        self.assertIn("[CANCELED]", r_q_can.stdout)
        self.assertIn("[blocked by: proj_b:F2]", r_q_can.stdout)
        self.assertIn("Next actionable: none", r_q_can.stdout)
        r_nid_can = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch))
        self.assertNotEqual(r_nid_can.returncode, 0)
        self.assertIn("CANCELED", r_nid_can.stderr)

        # Already-closed target fails non-zero in next-id
        r_nid_done = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(proj_a))
        self.assertNotEqual(r_nid_done.returncode, 0)
        self.assertIn("already closed", r_nid_done.stderr)

        # Syntax errors rejected by --depends
        for bad_dep in ("F1 ->", "-> F1", "F1, -> F2", "badref"):
            with self.subTest(bad_dep=bad_dep):
                r_bad = self._run([str(SCRIPT), "add", "Bad dep", "--depends", bad_dep], cwd=str(proj_a))
                self.assertNotEqual(r_bad.returncode, 0)

        # Transitive cycle detection in todo_md check, queue, and next-id
        cyc_dir = ws / "cyc"
        cyc_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc_dir), check=True)
        self._run([str(SCRIPT), "add", "Node A"], cwd=str(cyc_dir), check=True)
        self._run([str(SCRIPT), "add", "Node B", "--depends", "F1"], cwd=str(cyc_dir), check=True)
        r_cyc_edit = self._run([str(SCRIPT), "edit", "F1", "--depends", "F2"], cwd=str(cyc_dir))
        self.assertNotEqual(r_cyc_edit.returncode, 0)
        self.assertIn("dependency cycle", r_cyc_edit.stderr)
        r_chk_cyc = self._run([str(SCRIPT), "check"], cwd=str(cyc_dir))
        self.assertNotEqual(r_chk_cyc.returncode, 0)
        self.assertIn("dependency cycle", r_chk_cyc.stderr)
        r_q_cyc = self._run([str(SCRIPT), "queue", "F1"], cwd=str(cyc_dir))
        self.assertNotEqual(r_q_cyc.returncode, 0)
        self.assertIn("dependency cycle", r_q_cyc.stderr)
        r_nid_cyc = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(cyc_dir))
        self.assertNotEqual(r_nid_cyc.returncode, 0)
        self.assertIn("dependency cycle", r_nid_cyc.stderr)

        # Stage-induced cycle (A depends on B, target says A -> B) caught by check
        cyc_stage = ws / "cyc_stage"
        cyc_stage.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc_stage), check=True)
        self._run([str(SCRIPT), "add", "S2"], cwd=str(cyc_stage), check=True)
        self._run([str(SCRIPT), "add", "S1", "--depends", "F1"], cwd=str(cyc_stage), check=True)
        r_st_cyc = self._run([str(SCRIPT), "add", "S3", "--depends", "F2 -> F1"], cwd=str(cyc_stage))
        self.assertNotEqual(r_st_cyc.returncode, 0)
        self.assertIn("dependency cycle", r_st_cyc.stderr)

        # Syntax error in TODO.md caught by check
        syn_dir = ws / "syn"
        syn_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(syn_dir), check=True)
        (syn_dir / "TODO.md").write_text("# ⚪ [NEW] F1: Broken\n\n- Depends on: F2 -> \n", encoding="utf-8")
        r_syn = self._run([str(SCRIPT), "check"], cwd=str(syn_dir))
        self.assertNotEqual(r_syn.returncode, 0)
        self.assertIn("syntax error", r_syn.stderr)

    def test_list_topo_order_blocked_next_badges_and_ready_filter(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Build chain F1 -> F2 -> F3 and independent F4 in proj_a, with promoted blocked order
        self._run([str(SCRIPT), "add", "Base task", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Middle task", "--depends", "F1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Top task", "--depends", "F2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Ready task", "--next"], cwd=str(proj_a), check=True)
        # Promote F3 then F2 via next: F2 depends on F1 and F3 depends on F2, so TODO.md must keep
        # ready tasks (F4, F1) before blocked tasks (F2, F3), and F2 before F3
        self._run([str(SCRIPT), "next", "F3"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "next", "F2"], cwd=str(proj_a), check=True)

        todo_txt = (proj_a / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🎯 [NEXT] F3:", todo_txt)
        self.assertLess(todo_txt.index("F4:"), todo_txt.index("F2:"))
        self.assertLess(todo_txt.index("F1:"), todo_txt.index("F2:"))
        self.assertLess(todo_txt.index("F2:"), todo_txt.index("F3:"))

        # Local list: blocked NEXT items render with ⏳ [NEXT], chain F3 shows full path, single-step F2 stays single-hop
        r_list = self._run([str(SCRIPT), "list"], cwd=str(proj_a), check=True)
        rows = {
            line.split()[0]: line
            for line in r_list.stdout.splitlines()
            if line.startswith("  ")
        }
        self.assertIn("🎯 [NEXT]", rows["F4"])
        self.assertIn("🎯 [NEXT]", rows["F1"])
        self.assertIn("⏳ [NEXT]", rows["F2"])
        self.assertIn("[blocked: F1 (NEXT)]", rows["F2"])
        self.assertNotIn("->", rows["F2"])
        self.assertIn("⏳ [NEXT]", rows["F3"])
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", rows["F3"])
        self.assertLess(r_list.stdout.index("F4"), r_list.stdout.index("F2"))
        self.assertLess(r_list.stdout.index("F1"), r_list.stdout.index("F2"))
        self.assertLess(r_list.stdout.index("F2"), r_list.stdout.index("F3"))

        # Multi-stage Depends on: F1 -> F2 on a single task also surfaces the full ordered chain
        self._run([str(SCRIPT), "add", "Stage task", "--next", "--depends", "F1 -> F2"], cwd=str(proj_a), check=True)
        r_list_stage = self._run([str(SCRIPT), "list", "NEXT"], cwd=str(proj_a), check=True)
        stage_line = next(l for l in r_list_stage.stdout.splitlines() if l.strip().startswith("F5"))
        self.assertIn("⏳ [NEXT]", stage_line)
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", stage_line)

        # --ready filters local list to active tasks without unresolved deps
        r_ready = self._run([str(SCRIPT), "list", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("F1", r_ready.stdout)
        self.assertIn("F4", r_ready.stdout)
        self.assertNotIn("F2", r_ready.stdout)
        self.assertNotIn("F3", r_ready.stdout)
        self.assertNotIn("F5", r_ready.stdout)

        # Cross-project dependency in proj_b + workspace list -w and -w --ready
        self._run([str(SCRIPT), "add", "Cross ready", "--next"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Cross blocked", "--next", "--depends", "proj_a:F3"],
            cwd=str(proj_b),
            check=True,
        )
        r_ws = self._run([str(SCRIPT), "list", "-w"], cwd=str(proj_a), check=True)
        ws_rows = self._table_rows(r_ws.stdout)
        self.assertIn("⏳ [NEXT]", ws_rows["proj_a:F3"])
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", ws_rows["proj_a:F3"])
        self.assertIn("⏳ [NEXT]", ws_rows["proj_b:F2"])
        self.assertIn("[blocked: proj_a:F1 (NEXT) -> proj_a:F2 (NEXT) -> proj_a:F3 (NEXT)]", ws_rows["proj_b:F2"])
        self.assertIn("🎯 [NEXT]", ws_rows["proj_b:F1"])

        r_ws_ready = self._run([str(SCRIPT), "-w", "list", "NEXT", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("proj_a:F1", r_ws_ready.stdout)
        self.assertIn("proj_a:F4", r_ws_ready.stdout)
        self.assertIn("proj_b:F1", r_ws_ready.stdout)
        self.assertNotIn("proj_a:F2", r_ws_ready.stdout)
        self.assertNotIn("proj_b:F2", r_ws_ready.stdout)

        # Completing F1 unblocks F2 -> F2 becomes ready with [deps: DONE] and moves before F3/F5
        self._run([str(SCRIPT), "done", "F1", "-m", "d1"], cwd=str(proj_a), check=True)
        r_after_done = self._run([str(SCRIPT), "list", "-w"], cwd=str(proj_a), check=True)
        ws_after = {
            line.split()[0]: line
            for line in r_after_done.stdout.splitlines()
            if line.startswith("  ")
        }
        self.assertIn("🎯 [NEXT]", ws_after["proj_a:F2"])
        self.assertIn("[deps: DONE]", ws_after["proj_a:F2"])
        self.assertIn("⏳ [NEXT]", ws_after["proj_a:F3"])
        self.assertIn("[blocked: F2 (NEXT)]", ws_after["proj_a:F3"])
        self.assertNotIn("<- start:", ws_after["proj_a:F3"])

        r_none_ready = self._run([str(SCRIPT), "list", "archive", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (archive, ready)", r_none_ready.stdout)

        # CANCELED blocker does not append <- start: and cycle falls back safely to file order
        cyc = ws / "cyc_list"
        cyc.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc), check=True)
        (cyc / "TODO.md").write_text(
            "# 🎯 [NEXT] F1: Cycle A\n\n- Depends on: F2\n\n"
            "# 🎯 [NEXT] F2: Cycle B\n\n- Depends on: F1\n\n"
            "# 🎯 [NEXT] F3: Ready C\n\nBody C\n",
            encoding="utf-8",
        )
        r_cyc_list = self._run([str(SCRIPT), "list"], cwd=str(cyc), check=True)
        self.assertLess(r_cyc_list.stdout.index("F3"), r_cyc_list.stdout.index("F1"))
        self.assertLess(r_cyc_list.stdout.index("F1"), r_cyc_list.stdout.index("F2"))
        self.assertIn("⏳ [NEXT]", r_cyc_list.stdout)

        # Blocked WIP badge (⏳ [WIP]) and full mixed-status unblock chain in local and workspace list
        wip_ws = ws / "wip_chain_ws"
        wip_proj = wip_ws / "alpha"
        wip_proj.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Root WIP", "--status", "WIP"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Mid NEXT", "--next", "--depends", "F1"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Child WIP", "--status", "WIP", "--depends", "F2"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Leaf NEXT", "--next", "--depends", "F3"], cwd=str(wip_proj), check=True)

        r_wip_local = self._run([str(SCRIPT), "list"], cwd=str(wip_proj), check=True)
        wip_rows = self._table_rows(r_wip_local.stdout)
        self.assertIn("🔵 [WIP]", wip_rows["F1"])
        self.assertIn("⏳ [WIP]", wip_rows["F3"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT)]", wip_rows["F3"])
        self.assertIn("⏳ [NEXT]", wip_rows["F2"])
        self.assertIn("[blocked: F1 (WIP)]", wip_rows["F2"])
        self.assertIn("⏳ [NEXT]", wip_rows["F4"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT) -> F3 (WIP)]", wip_rows["F4"])

        r_wip_ws = self._run([str(SCRIPT), "list", "-w"], cwd=str(wip_ws), check=True)
        wip_ws_rows = self._table_rows(r_wip_ws.stdout)
        self.assertIn("🔵 [WIP]", wip_ws_rows["alpha:F1"])
        self.assertIn("⏳ [WIP]", wip_ws_rows["alpha:F3"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT)]", wip_ws_rows["alpha:F3"])
        self.assertIn("⏳ [NEXT]", wip_ws_rows["alpha:F4"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT) -> F3 (WIP)]", wip_ws_rows["alpha:F4"])

    def test_lazy_urllib_import_and_offline_update(self):
        probe = (
            "import contextlib, importlib.machinery, importlib.util, io, sys\n"
            "loader = importlib.machinery.SourceFileLoader('todo_md_probe', sys.argv[1])\n"
            "spec = importlib.util.spec_from_loader('todo_md_probe', loader)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "loader.exec_module(mod)\n"
            "buf = io.StringIO()\n"
            "with contextlib.redirect_stdout(buf):\n"
            "    assert mod.main(['--version']) == 0\n"
            "    assert mod.main(['init']) == 0\n"
            "    assert mod.main(['add', 'Lazy import task']) == 0\n"
            "    assert mod.main(['check']) == 0\n"
            "    assert mod.main(['list']) == 0\n"
            "for banned in ('urllib.request', 'http.client', 'ssl'):\n"
            "    assert banned not in sys.modules, f'unexpectedly imported {banned}'\n"
        )
        r_probe = self._run_subprocess([sys.executable, "-c", probe, str(SCRIPT)])
        self.assertEqual(r_probe.returncode, 0, msg=r_probe.stderr)

        remote_file = self.tmp / "remote_todo_md"
        remote_payload = (
            "#!/usr/bin/env python3\n"
            "# todo_md-repo: vitalio/todo_md\n"
            "VERSION = '99.0.0'\n"
        )
        remote_file.write_text(remote_payload, encoding="utf-8")
        env = {**os.environ, "TODO_MD_UPDATE_URL": remote_file.as_uri()}

        r_chk = self._run_subprocess([str(SCRIPT), "check-update"], env=env)
        self.assertEqual(r_chk.returncode, 0, msg=r_chk.stderr)
        self.assertIn("update available:", r_chk.stdout)
        self.assertIn("99.0.0", r_chk.stdout)

        dest_bin = self.tmp / "todo_md_local"
        dest_bin.write_text("# old\n", encoding="utf-8")
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = self.todo_md_mod.cmd_update(url=remote_file.as_uri(), target_path=dest_bin)
        self.assertEqual(rc, 0, msg=err_buf.getvalue())
        self.assertIn("-> 99.0.0", out_buf.getvalue())
        self.assertEqual(dest_bin.read_text(encoding="utf-8"), remote_payload)

    def test_global_project_selector_and_precedence(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "parent_proj" / "sub_proj"
        proj_c = ws / "proj_c"
        dup_1 = ws / "g1" / "shared"
        dup_2 = ws / "g2" / "shared"
        outside = self.tmp / "outside"
        for d in (proj_a, proj_b, proj_c, dup_1, dup_2, outside):
            d.mkdir(parents=True)
        for d in (proj_a, proj_b, proj_c, dup_1, dup_2):
            self._run([str(SCRIPT), "-C", str(d), "init"], cwd=str(outside), check=True)

        (proj_a / "mod.py").write_text("x = 1\n", encoding="utf-8")
        env_ws = {**os.environ, "TODO_MD_WORKSPACE": str(ws)}

        # -C <dir> and --project <name> across mutating and read-only subcommands from outside
        self._run(
            [str(SCRIPT), "-C", str(proj_a), "add", "-p", "B", "Bug from -C", "-b", "See `mod.py`."],
            cwd=str(outside),
            check=True,
        )
        self._run(
            [str(SCRIPT), "--project", "parent_proj/sub_proj", "add", "Sub task", "--depends", "proj_a:B1"],
            cwd=str(outside),
            env=env_ws,
            check=True,
        )
        # Unique leaf project name resolves across workspace
        self._run(
            [str(SCRIPT), "--project=sub_proj", "edit", "F1", "-t", "Sub task updated"],
            cwd=str(outside),
            env=env_ws,
            check=True,
        )
        self._run([str(SCRIPT), "-C", "sub_proj", "append", "F1", "-b", "More notes."], cwd=str(outside), env=env_ws, check=True)
        self._run([str(SCRIPT), "-C", "sub_proj", "status", "F1", "HOLD"], cwd=str(outside), env=env_ws, check=True)
        self._run([str(SCRIPT), "-C", "sub_proj", "next", "F1"], cwd=str(outside), env=env_ws, check=True)

        # Read-only commands with -C / --project from outside
        r_ids = self._run([str(SCRIPT), "-C", "proj_a", "ids"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("B:1", r_ids.stdout)
        r_list = self._run([str(SCRIPT), "-C", "proj_a", "list"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("B1", r_list.stdout)
        r_show = self._run([str(SCRIPT), "-C", "proj_a", "show", "B1"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("Bug from -C", r_show.stdout)
        r_files = self._run([str(SCRIPT), "-C", "proj_a", "files", "B1"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_files.stdout.splitlines(), ["mod.py"])
        r_last_id = self._run([str(SCRIPT), "-C", "proj_a", "last-id", "NEW"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_last_id.stdout.strip(), "B1")
        r_last = self._run([str(SCRIPT), "-C", "proj_a", "last", "NEW"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("Bug from -C", r_last.stdout)
        self._run([str(SCRIPT), "-C", "proj_a", "check"], cwd=str(outside), env=env_ws, check=True)
        r_nid_sub = self._run([str(SCRIPT), "-C", "sub_proj", "next-id", "F1"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_nid_sub.stdout.strip(), "proj_a:B1")
        r_nid_top = self._run([str(SCRIPT), "-C", "sub_proj", "next-id"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_nid_top.stdout.strip(), "F1")

        # Complete and archive via -C, then inspect archive and reopen
        self._run([str(SCRIPT), "-C", "proj_a", "done", "B1", "-m", "fixed"], cwd=str(outside), env=env_ws, check=True)
        r_arch = self._run([str(SCRIPT), "-C", "proj_a", "archive"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("B1: Bug from -C", r_arch.stdout)
        self._run([str(SCRIPT), "-C", "sub_proj", "cancel", "F1", "-m", "dropped"], cwd=str(outside), env=env_ws, check=True)
        r_sub_arch = self._run([str(SCRIPT), "-C", "sub_proj", "archive"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("F1: Sub task updated", r_sub_arch.stdout)

        # Overview, queue, and reopen with -C from outside
        r_sum = self._run([str(SCRIPT), "-C", "proj_a"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("Archived in TODO_ARCHIVE.md: 1 task(s)", r_sum.stdout)
        r_q = self._run([str(SCRIPT), "-C", "sub_proj", "queue", "F1", "--all"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("proj_a:B1", r_q.stdout)
        self._run([str(SCRIPT), "-C", "proj_a", "reopen", "B1"], cwd=str(outside), env=env_ws, check=True)

        # Workspace discovery from sibling project without TODO_MD_WORKSPACE env var
        r_sib = self._run([str(SCRIPT), "-C", "proj_a", "ids"], cwd=str(proj_c), check=True)
        self.assertIn("B:1", r_sib.stdout)

        # Precedence: -C/--project > TODO_MD_CWD > <project>:<ID> > cwd
        env_cwd_a = {**os.environ, "TODO_MD_WORKSPACE": str(ws), "TODO_MD_CWD": str(proj_a)}
        r_prec_env = self._run([str(SCRIPT), "ids"], cwd=str(proj_b), env=env_cwd_a, check=True)
        self.assertIn("B:1", r_prec_env.stdout)
        self.assertNotIn("F:1", r_prec_env.stdout)

        r_prec_cli = self._run([str(SCRIPT), "-C", "sub_proj", "ids"], cwd=str(outside), env=env_cwd_a, check=True)
        self.assertIn("F:1", r_prec_cli.stdout)
        self.assertNotIn("B:1", r_prec_cli.stdout)

        r_prec_ref = self._run([str(SCRIPT), "show", "proj_a:B1"], cwd=str(proj_c), check=True)
        self.assertIn("Bug from -C", r_prec_ref.stdout)

        # Explicit error on missing/empty/ambiguous targets and invalid <project>: on non-task commands
        for bad_args in (
            ["-C"],
            ["--project"],
            ["--project="],
            ["-C", ""],
            ["-C", "/nonexistent_todo_md_dir"],
            ["-C", "does_not_exist", "list"],
            ["--project", "shared", "list"],
            ["list", "proj_a:"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(outside), env=env_ws)
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

    def test_install_sh(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
        r = self._run_subprocess(["sh", str(INSTALL_SH), "--dir", str(bin_dir), "--yes"], env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((bin_dir / "todo_md").is_file())

    def test_chain_command_local_workspace_hold_and_diagnostics(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        for d in (proj_a, proj_b):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Local chain with parallel stage + sequential stage + DONE prerequisite + HOLD branch
        self._run([str(SCRIPT), "add", "Completed base"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "F1", "-m", "done1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Step A", "--next", "--depends", "F1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Step B", "--depends", "F2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Step C", "--depends", "F3"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Paused root", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Blocked by hold", "--depends", "F5"], cwd=str(proj_a), check=True)

        r_local = self._run([str(SCRIPT), "chain"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: F2 -> F3 -> F4", r_local.stdout)
        self.assertNotIn("F1", r_local.stdout)
        self.assertIn("Held branches:", r_local.stdout)
        self.assertIn("F5 (HOLD) -> F6 (NEW)", r_local.stdout)
        self.assertLess(r_local.stdout.index("1. F2"), r_local.stdout.index("2. F3"))
        self.assertLess(r_local.stdout.index("2. F3"), r_local.stdout.index("3. F4"))

        # --limit N truncates chain summary and rows
        r_lim = self._run([str(SCRIPT), "chain", "--limit", "2"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: F2 -> F3", r_lim.stdout)
        self.assertNotIn("F4", r_lim.stdout)
        self.assertIn("Held branches:", r_lim.stdout)

        # --include-hold brings HOLD tasks and their dependents into the main chain
        r_inc = self._run([str(SCRIPT), "chain", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertIn("F5 -> F6", r_inc.stdout)
        self.assertNotIn("Held branches:", r_inc.stdout)

        # Cross-project dependency in proj_b resolved locally and across workspace (-w / auto-workspace)
        self._run(
            [str(SCRIPT), "add", "Cross child", "--depends", "proj_a:F3"],
            cwd=str(proj_b),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Cross leaf", "--depends", "F1"],
            cwd=str(proj_b),
            check=True,
        )
        r_b_local = self._run([str(SCRIPT), "chain"], cwd=str(proj_b), check=True)
        self.assertIn("Chain: proj_a:F2 -> proj_a:F3 -> F1 -> F2", r_b_local.stdout)

        r_ws = self._run([str(SCRIPT), "chain", "-w"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: proj_a:F2 -> proj_a:F3 ->", r_ws.stdout)
        self.assertIn("proj_b:F1 -> proj_b:F2", r_ws.stdout)
        self.assertIn("proj_a:F5 (HOLD) -> proj_a:F6 (NEW)", r_ws.stdout)

        # Auto-workspace from workspace root and -C selector
        r_ws_root = self._run([str(SCRIPT), "chain"], cwd=str(ws), check=True)
        self.assertIn("proj_b:F1 -> proj_b:F2", r_ws_root.stdout)
        r_c = self._run([str(SCRIPT), "-C", "proj_b", "chain"], cwd=str(ws), check=True)
        self.assertIn("Chain: proj_a:F2 -> proj_a:F3 -> F1 -> F2", r_c.stdout)

        # Diagnostics on CANCELED blocker
        can_dir = ws / "can_chain"
        can_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(can_dir), check=True)
        self._run([str(SCRIPT), "add", "Dropped base"], cwd=str(can_dir), check=True)
        self._run([str(SCRIPT), "add", "Waiting child", "--depends", "F1"], cwd=str(can_dir), check=True)
        self._run([str(SCRIPT), "cancel", "F1", "-m", "wontfix"], cwd=str(can_dir), check=True)
        r_can = self._run([str(SCRIPT), "chain"], cwd=str(can_dir))
        self.assertNotEqual(r_can.returncode, 0)
        self.assertIn("CANCELED", r_can.stderr)

        # Diagnostics on MISSING blocker
        miss_dir = ws / "miss_chain"
        miss_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(miss_dir), check=True)
        (miss_dir / "TODO.md").write_text("# ⚪ [NEW] F1: Orphan\n\n- Depends on: F99\n", encoding="utf-8")
        r_miss = self._run([str(SCRIPT), "chain"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss.returncode, 0)
        self.assertIn("MISSING", r_miss.stderr)

        # Diagnostics on cycle and syntax error
        cyc_dir = ws / "cyc_chain"
        cyc_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc_dir), check=True)
        (cyc_dir / "TODO.md").write_text(
            "# ⚪ [NEW] F1: A\n\n- Depends on: F2\n\n# ⚪ [NEW] F2: B\n\n- Depends on: F1\n",
            encoding="utf-8",
        )
        r_cyc = self._run([str(SCRIPT), "chain"], cwd=str(cyc_dir))
        self.assertNotEqual(r_cyc.returncode, 0)
        self.assertIn("dependency cycle", r_cyc.stderr)

        syn_dir = ws / "syn_chain"
        syn_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(syn_dir), check=True)
        (syn_dir / "TODO.md").write_text("# ⚪ [NEW] F1: Bad\n\n- Depends on: F2 -> \n", encoding="utf-8")
        r_syn = self._run([str(SCRIPT), "chain"], cwd=str(syn_dir))
        self.assertNotEqual(r_syn.returncode, 0)
        self.assertIn("empty stage in dependency clause", r_syn.stderr)

        # Invalid flags fail explicitly
        for bad_args in (
            ["chain", "--limit", "0"],
            ["chain", "--limit=abc"],
            ["chain", "--unknown"],
            ["chain", "extra"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj_a))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)


    def test_chain_critical_path_ranking_ready_filter_and_standalone_grouping(self):
        ws = self.tmp / "ws_rank"
        proj = ws / "proj"
        proj.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)

        # Standalone tasks only -> no false '->' arrows in Chain: header
        self._run([str(SCRIPT), "add", "Solo A"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Solo B"], cwd=str(proj), check=True)
        r_solo = self._run([str(SCRIPT), "chain"], cwd=str(proj), check=True)
        self.assertIn("Standalone tasks:", r_solo.stdout)
        self.assertNotIn("Chain:", r_solo.stdout)
        self.assertNotIn("F1 -> F2", r_solo.stdout)

        # Add a medium chain F3 -> F4 (F3 unblocks 1) and a deep chain F5 -> F6 -> F7 (F5 unblocks 2)
        self._run([str(SCRIPT), "add", "Med root"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Med leaf", "--depends", "F3"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Deep root"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Deep mid", "--depends", "F5"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Deep leaf", "--depends", "F6"], cwd=str(proj), check=True)

        r_chain = self._run([str(SCRIPT), "chain"], cwd=str(proj), check=True)
        out = r_chain.stdout
        # Deep chain (unblocks 2) ranks before medium chain (unblocks 1), both before Standalone tasks
        self.assertIn("Chain: F5 -> F6 -> F7", out)
        self.assertIn("Chain: F3 -> F4", out)
        self.assertIn("Standalone tasks:", out)
        self.assertLess(out.index("Chain: F5 -> F6 -> F7"), out.index("Chain: F3 -> F4"))
        self.assertLess(out.index("Chain: F3 -> F4"), out.index("Standalone tasks:"))
        self.assertNotIn("F7 -> F3", out)
        self.assertNotIn("F4 -> F1", out)
        self.assertNotIn("F1 -> F2", out)
        self.assertIn("[unblocks 2]", out)
        self.assertIn("[unblocks 1]", out)

        # --ready filters to ready tasks only, ranks highest-leverage ready tasks first,
        # and shows immediate unblocked targets inline for chain continuation context
        r_ready = self._run([str(SCRIPT), "chain", "--ready"], cwd=str(proj), check=True)
        r_out = r_ready.stdout
        self.assertIn("Ready tasks:", r_out)
        ready_rows = self._table_rows(r_out)
        self.assertEqual(sorted(ready_rows), ["1.", "2.", "3.", "4."], msg=r_out)
        self.assertIn("F5", ready_rows["1."])
        self.assertIn("[ready | unblocks 2 -> F6]", ready_rows["1."])
        self.assertNotIn("F7", r_out)
        self.assertIn("F3", ready_rows["2."])
        self.assertIn("[ready | unblocks 1 -> F4]", ready_rows["2."])
        self.assertIn("F1", ready_rows["3."])
        self.assertIn("[ready]", ready_rows["3."])
        self.assertNotIn("unblocks", ready_rows["3."])
        self.assertIn("F2", ready_rows["4."])
        self.assertIn("[ready]", ready_rows["4."])
        self.assertNotIn("unblocks", ready_rows["4."])

    def test_chain_role_badges_and_role_filter(self):
        ws = self.tmp / "ws_chain_role"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Chain in proj_a: D1 (design) -> F1 (work) -> F2 (plan, explicit)
        # Standalone in proj_a: P1 (no role), B1 (work)
        # Held branch in proj_a: D2 (HOLD, design) -> F3 (NEW, work)
        self._run([str(SCRIPT), "add", "D", "Design schema", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Build backend", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Plan rollout", "--role", "plan", "--depends", "F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "P", "Unassigned idea"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Ready bugfix", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "D", "Paused design", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Waiting work", "--depends", "D2"], cwd=str(proj_a), check=True)

        # Cross-project task in proj_b: F1 (work, depends on proj_a:F1)
        self._run(
            [str(SCRIPT), "add", "F", "Cross repo work", "--depends", "proj_a:F1"],
            cwd=str(proj_b),
            check=True,
        )

        # 1. Default chain displays aligned [role] column across Chain:, Standalone tasks:, and --ready
        r_all = self._run([str(SCRIPT), "chain"], cwd=str(proj_a), env={**os.environ, "COLUMNS": "160"}, check=True)
        rows = self._table_rows(r_all.stdout)
        self.assertIn("[design]", rows["1."])
        self.assertIn("[work]", rows["2."])
        self.assertIn("[plan]", rows["3."])
        self.assertIn("[work]", rows["4."])
        self.assertNotIn("[design]", rows["5."])
        self.assertNotIn("[work]", rows["5."])
        self.assertNotIn("[plan]", rows["5."])
        role_cols = {
            line.index("[design]" if "[design]" in line else ("[work]" if "[work]" in line else "[plan]"))
            for k, line in rows.items()
            if k in ("1.", "2.", "3.", "4.")
        }
        self.assertEqual(len(role_cols), 1, msg=f"misaligned role column: {rows!r}")

        r_ready_all = self._run([str(SCRIPT), "chain", "--ready"], cwd=str(proj_a), check=True)
        ready_rows = self._table_rows(r_ready_all.stdout)
        self.assertIn("[design]", ready_rows["1."])
        self.assertIn("[work]", ready_rows["2."])

        # 2. --role work filters Chain:, Standalone tasks:, and preserves unblock/blocker context & Held branches
        r_work = self._run([str(SCRIPT), "chain", "--role", "WORK"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: F1", r_work.stdout)
        self.assertIn("[work]", r_work.stdout)
        self.assertIn("[blocked by: D1]", r_work.stdout)
        self.assertIn("[unblocks 1]", r_work.stdout)
        self.assertIn("Standalone tasks:", r_work.stdout)
        self.assertIn("B1", r_work.stdout)
        self.assertNotIn("D1: Design schema", r_work.stdout)
        self.assertNotIn("F2", r_work.stdout)
        self.assertNotIn("P1", r_work.stdout)
        self.assertIn("Held branches:", r_work.stdout)
        self.assertIn("D2 (HOLD) -> F3 (NEW)", r_work.stdout)

        # 3. --role plan hides unrelated held branches and standalone tasks
        r_plan = self._run([str(SCRIPT), "chain", "--role=plan"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: F2", r_plan.stdout)
        self.assertIn("[plan]", r_plan.stdout)
        self.assertIn("[blocked by: F1]", r_plan.stdout)
        self.assertNotIn("Standalone tasks:", r_plan.stdout)
        self.assertNotIn("Held branches:", r_plan.stdout)
        self.assertNotIn("D1", r_plan.stdout)
        self.assertNotIn("B1", r_plan.stdout)

        # 4. --role with --ready and -w (workspace) and --limit
        r_ws_work_ready = self._run(
            [str(SCRIPT), "chain", "-w", "--role", "work", "--ready"],
            cwd=str(ws),
            check=True,
        )
        self.assertIn("Ready tasks:", r_ws_work_ready.stdout)
        self.assertIn("proj_a:B1", r_ws_work_ready.stdout)
        self.assertIn("[work]", r_ws_work_ready.stdout)
        self.assertNotIn("proj_a:D1", r_ws_work_ready.stdout)
        self.assertNotIn("proj_a:F1", r_ws_work_ready.stdout)
        self.assertNotIn("proj_b:F1", r_ws_work_ready.stdout)

        r_ws_work_lim = self._run(
            [str(SCRIPT), "chain", "-w", "--role", "work", "--limit", "2"],
            cwd=str(ws),
            check=True,
        )
        lim_rows = {
            k: v for k, v in self._table_rows(r_ws_work_lim.stdout).items() if k.endswith(".")
        }
        self.assertEqual(sorted(lim_rows), ["1.", "2."], msg=r_ws_work_lim.stdout)

        # 5. Empty role match reports clean message; --include-hold brings in held matching tasks
        r_none = self._run([str(SCRIPT), "chain", "--role", "review"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: (none matching role=review)", r_none.stdout)

        r_none_ready = self._run([str(SCRIPT), "chain", "--role", "plan", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("Ready tasks: (none matching role=plan)", r_none_ready.stdout)

        r_work_hold = self._run([str(SCRIPT), "chain", "--role", "work", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertIn("F3", r_work_hold.stdout)
        self.assertNotIn("Held branches:", r_work_hold.stdout)

        # 6. MISSING placeholder leaves role column blank without crashing and still surfaces DAG error
        miss_dir = ws / "miss_role"
        miss_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(miss_dir), check=True)
        (miss_dir / "TODO.md").write_text("# ⚪ [NEW] F1: Orphan\n\n- Depends on: F99\n", encoding="utf-8")
        r_miss = self._run([str(SCRIPT), "chain"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss.returncode, 0)
        self.assertIn("[MISSING]", r_miss.stdout)
        self.assertIn("[work]", r_miss.stdout)
        self.assertIn("unresolved blocker F99 (MISSING)", r_miss.stderr)
        miss_rows = self._table_rows(r_miss.stdout)
        self.assertNotIn("[work]", miss_rows["1."])
        self.assertIn("[work]", miss_rows["2."])

        r_miss_role = self._run([str(SCRIPT), "chain", "--role", "work"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss_role.returncode, 0)
        self.assertIn("F1", r_miss_role.stdout)
        self.assertNotIn("[MISSING]", r_miss_role.stdout)
        self.assertIn("unresolved blocker F99 (MISSING)", r_miss_role.stderr)

        # 7. Invalid --role values fail explicitly
        for bad_args in (
            ["chain", "--role"],
            ["chain", "--role", ""],
            ["chain", "--role="],
            ["chain", "--role", "a\nb"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj_a))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

    def test_done_prints_newly_unblocked_local_and_orchestrator_tasks(self):
        ws = self.tmp / "ws_done"
        repo_a = ws / "repo_a"
        repo_b = ws / "repo_b"
        orch_dir = ws / ".todo_projects"
        for d in (repo_a, repo_b, orch_dir):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Local chain in repo_a: F1 and F2 both required for F4; F3 depends only on F1
        self._run([str(SCRIPT), "add", "Prereq 1"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Prereq 2"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Single waiter", "--depends", "F1"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Dual waiter", "--depends", "F1, F2"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Already ready"], cwd=str(repo_a), check=True)

        # Workspace orchestrator task in .todo_projects depending on repo_a:F1 -> repo_b:F1
        self._run([str(SCRIPT), "add", "Repo B step"], cwd=str(repo_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Orch release", "--depends", "repo_a:F1, repo_b:F1"],
            cwd=str(orch_dir),
            check=True,
        )

        # Completing F1 unblocks local F3, does NOT unblock F4 (still waiting on F2) or F5 (had no deps)
        r_done1 = self._run([str(SCRIPT), "done", "F1", "-m", "d1"], cwd=str(repo_a), check=True)
        self.assertIn("Unblocked: F3", r_done1.stdout)
        self.assertNotIn("F4", r_done1.stdout)
        self.assertNotIn("F5", r_done1.stdout)
        self.assertNotIn(".todo_projects:F1", r_done1.stdout)

        # Completing F2 unblocks local F4
        r_done2 = self._run([str(SCRIPT), "done", "F2", "-m", "d2"], cwd=str(repo_a), check=True)
        self.assertIn("Unblocked: F4", r_done2.stdout)

        # Completing F3 has no downstream dependents -> no Unblocked: line
        r_done3 = self._run([str(SCRIPT), "done", "F3", "-m", "d3"], cwd=str(repo_a), check=True)
        self.assertNotIn("Unblocked:", r_done3.stdout)

        # Completing repo_b:F1 completes all deps for .todo_projects:F1 and reports it
        r_done_b = self._run([str(SCRIPT), "done", "F1", "-m", "db1"], cwd=str(repo_b), check=True)
        self.assertIn("Unblocked: .todo_projects:F1", r_done_b.stdout)

    def test_check_detects_stale_completion_date_note_on_active_tasks(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run([str(SCRIPT), "add", "Valid priority note", "--next", "-m", "top priority"], check=True)
        self._run([str(SCRIPT), "add", "Target milestone", "-m", "target 2026-12-01"], check=True)
        fenced_example = "`" * 3 + "markdown\n# ⚪ [NEW] F99: Fenced — *2026-11-18*\n" + "`" * 3
        self._run([str(SCRIPT), "add", "Fenced snippet", "-b", fenced_example], check=True)
        self._run([str(SCRIPT), "add", "Archived item"], check=True)
        self._run([str(SCRIPT), "done", "F4", "-m", "completed cleanly"], check=True)
        self._run([str(SCRIPT), "check"], check=True)

        # Active tasks with stale completion date stamps fail check across active statuses
        for status, emoji, note in (
            ("NEW", "⚪", "2026-11-18"),
            ("WIP", "🔵", "2026-11-18, commit abc1234"),
            ("NEXT", "🎯", "2026-11-18 — implemented"),
            ("HOLD", "⏸️", "2026-11-18"),
            ("QUESTION", "❓", "2026-11-18, check"),
        ):
            with self.subTest(status=status, note=note):
                case_dir = self.tmp / f"stale_{status.lower()}"
                case_dir.mkdir()
                self._run([str(SCRIPT), "init"], cwd=str(case_dir), check=True)
                (case_dir / "TODO.md").write_text(
                    f"# {emoji} [{status}] F1: Reverted task — *{note}*\n\nBody text.\n",
                    encoding="utf-8",
                )
                r_chk = self._run([str(SCRIPT), "check"], cwd=str(case_dir))
                self.assertNotEqual(r_chk.returncode, 0, msg=r_chk.stdout)
                self.assertIn("TODO.md:1", r_chk.stderr)
                self.assertIn("F1", r_chk.stderr)
                self.assertIn(note, r_chk.stderr)
                self.assertIn("TODO_ARCHIVE.md", r_chk.stderr)
                self.assertIn("clear the stale note", r_chk.stderr)

                # Automatic post-mutation validation also catches the stale note
                r_app = self._run([str(SCRIPT), "append", "F1", "-b", "Extra line"], cwd=str(case_dir))
                self.assertNotEqual(r_app.returncode, 0, msg=r_app.stdout)
                self.assertIn("TODO_ARCHIVE.md", r_app.stderr)

        # Clearing the stale note via edit -m "" or moving back via done resolves the error
        fix_clear = self.tmp / "fix_clear"
        fix_clear.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(fix_clear), check=True)
        (fix_clear / "TODO.md").write_text(
            "# ⚪ [NEW] F1: Reopened manually — *2026-11-18, old sha*\n\nBody.\n",
            encoding="utf-8",
        )
        self._run([str(SCRIPT), "edit", "F1", "-m", ""], cwd=str(fix_clear), check=True)
        self._run([str(SCRIPT), "check"], cwd=str(fix_clear), check=True)

        fix_arch = self.tmp / "fix_arch"
        fix_arch.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(fix_arch), check=True)
        (fix_arch / "TODO.md").write_text(
            "# ⚪ [NEW] F1: Accidentally restored — *2026-11-18*\n\nBody.\n",
            encoding="utf-8",
        )
        self._run([str(SCRIPT), "done", "F1"], cwd=str(fix_arch), check=True)
        self._run([str(SCRIPT), "check"], cwd=str(fix_arch), check=True)


    def test_list_tree_hierarchy_shared_deps_and_terminal_width_truncation(self):
        ws = self.tmp / "ws_tree"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Build multi-step chain across status buckets + shared dependency:
        # F1 (NEW) -> F2 (NEXT) -> F3 (WIP)
        # F1 (NEW) -> F4 (NEXT)
        # F2, F4 -> F5 (NEW, shared dependent)
        # F6 (NEXT, standalone ready)
        self._run(
            [str(SCRIPT), "add", "Foundation schema migration and storage layer"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Backend service endpoints", "--next", "--depends", "F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Active UI implementation", "--status", "WIP", "--depends", "F2"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Auth middleware adapter", "--next", "--depends", "F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "End-to-end integration verification", "--depends", "F2, F4"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Standalone ready task", "--next"],
            cwd=str(proj_a),
            check=True,
        )

        # Wide terminal (COLUMNS=160): prerequisites placed above dependents across status buckets,
        # multi-step connectors (├─ / └─ / │), and shared dependent marked (shared) without duplicating subtree
        # Note: add --next prepends newer NEXT items above older NEXT items, so F4 precedes F2 in TODO.md.
        r_wide = self._run(
            [str(SCRIPT), "list", "--tree"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out = r_wide.stdout
        self.assertLess(out.index("F6"), out.index("F1"))
        self.assertLess(out.index("F1"), out.index("F4"))
        self.assertLess(out.index("F4"), out.index("F5"))
        self.assertLess(out.index("F4"), out.index("F2"))
        self.assertLess(out.index("F2"), out.index("F3"))
        self.assertIn("├─ F4", out)
        self.assertIn("│   └─ F5", out)
        self.assertIn("└─ F2", out)
        self.assertIn("    ├─ F3", out)
        self.assertIn("    └─ F5", out)
        self.assertIn("(shared)", out)
        self.assertIn("Foundation schema migration and storage layer", out)
        self.assertIn("End-to-end integration verification", out)
        self.assertNotIn("...", out)

        # Non-TTY fallback (no COLUMNS set): renders tree cleanly within default 100 columns
        env_no_cols = {k: v for k, v in os.environ.items() if k != "COLUMNS"}
        r_nontty = self._run(
            [str(SCRIPT), "list", "--tree"],
            cwd=str(proj_a),
            env=env_no_cols,
            check=True,
        )
        self.assertIn("├─ F4", r_nontty.stdout)
        self.assertIn("└─ F2", r_nontty.stdout)

        # Narrow terminal with room for truncated titles (COLUMNS=58): truncates titles with '...'
        # and keeps every row within 58 display columns on a single line
        r_trunc = self._run(
            [str(SCRIPT), "list", "--tree"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "58"},
            check=True,
        )
        tree_rows_trunc = [
            l for l in r_trunc.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertEqual(len(tree_rows_trunc), 7)
        self.assertIn("...", r_trunc.stdout)
        self.assertIn("├─ F4", r_trunc.stdout)
        for row in tree_rows_trunc:
            self.assertLessEqual(self.todo_md_mod._display_width(row), 58, msg=f"row overflow: {row!r}")

        # Very narrow terminal (COLUMNS=30): falls back to compact ID-only tree lines
        r_narrow = self._run(
            [str(SCRIPT), "list", "--tree"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "30"},
            check=True,
        )
        narrow_rows = [
            l for l in r_narrow.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertEqual(
            narrow_rows,
            [
                "  F6",
                "  F1",
                "  ├─ F4",
                "  │   └─ F5",
                "  └─ F2",
                "      ├─ F3",
                "      └─ F5 (shared)",
            ],
        )
        self.assertNotIn("Foundation schema", r_narrow.stdout)
        self.assertNotIn("[work]", r_narrow.stdout)

        # Status filter + --tree renders only matching status tasks cleanly
        r_next_tree = self._run(
            [str(SCRIPT), "list", "NEXT", "--tree"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "140"},
            check=True,
        )
        next_ids = [
            l.split()[0] for l in r_next_tree.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertEqual(next_ids, ["F6", "F4", "F2"])

        # Workspace list -w --tree connects cross-project prerequisite -> dependent
        self._run(
            [str(SCRIPT), "add", "Cross-project consumer", "--next", "--depends", "proj_a:F3"],
            cwd=str(proj_b),
            check=True,
        )
        r_ws_tree = self._run(
            [str(SCRIPT), "list", "-w", "--tree"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "140"},
            check=True,
        )
        self.assertIn("proj_a:F1", r_ws_tree.stdout)
        self.assertIn("proj_b:F1", r_ws_tree.stdout)
        self.assertLess(r_ws_tree.stdout.index("proj_a:F3"), r_ws_tree.stdout.index("proj_b:F1"))
        self.assertIn("└─ proj_b:F1", r_ws_tree.stdout)

        # --limit N caps rendered tree rows
        r_lim = self._run(
            [str(SCRIPT), "list", "--tree", "--limit", "3"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "30"},
            check=True,
        )
        lim_rows = [
            l for l in r_lim.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertEqual(lim_rows, ["  F6", "  F1", "  ├─ F4"])

        # Cycle safety in list --tree: renders all tasks without infinite recursion
        cyc_tree = ws / "cyc_tree"
        cyc_tree.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc_tree), check=True)
        (cyc_tree / "TODO.md").write_text(
            "# ⚪ [NEW] F1: Cycle one\n\n- Depends on: F2\n\n"
            "# ⚪ [NEW] F2: Cycle two\n\n- Depends on: F1\n",
            encoding="utf-8",
        )
        r_cyc_tree = self._run(
            [str(SCRIPT), "list", "--tree"],
            cwd=str(cyc_tree),
            env={**os.environ, "COLUMNS": "120"},
            check=True,
        )
        self.assertIn("F1", r_cyc_tree.stdout)
        self.assertIn("F2", r_cyc_tree.stdout)


    def test_tabular_column_wrapping_and_emoji_alignment(self):
        ws = self.tmp / "ws_wrap"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        long_title_1 = "Wrap long task descriptions cleanly across aligned tabular output columns without breaking words"
        long_title_2 = "Second chained task with multi-word description verifying hanging indent and emoji width alignment"
        self._run([str(SCRIPT), "add", long_title_1, "--status", "WIP"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", long_title_2, "--next", "--depends", "F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "Question item for alignment check", "--status", "QUESTION"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Hold item for alignment check", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "New item for alignment check", "--status", "NEW"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Done item for alignment check"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "F6", "-m", "done"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Canceled item for alignment check"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "cancel", "F7", "-m", "canceled"], cwd=str(proj_a), check=True)

        self._run(
            [str(SCRIPT), "add", "Cross-project dependent task with a lengthy title for workspace views", "--next", "--depends", "proj_a:F2"],
            cwd=str(proj_b),
            check=True,
        )
        self._run([str(SCRIPT), "add", "Second question in proj_b", "--status", "QUESTION"], cwd=str(proj_b), check=True)

        disp_w = self.todo_md_mod._display_width

        # 1. Emoji alignment across all statuses in list all at wide width (COLUMNS=220)
        r_all_wide = self._run(
            [str(SCRIPT), "list", "all"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "220"},
            check=True,
        )
        task_lines = [
            l for l in r_all_wide.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertEqual(len(task_lines), 7)
        desc_starts = {disp_w(l.split("TODO")[0]) for l in task_lines}
        self.assertEqual(desc_starts, {38}, msg=f"misaligned loc column: {task_lines!r}")
        title_starts = set()
        for l in task_lines:
            marker = "TODO_ARCHIVE.md   " if "TODO_ARCHIVE.md" in l else "TODO.md           "
            idx = l.index(marker) + len(marker)
            title_starts.add(disp_w(l[:idx]))
        self.assertEqual(title_starts, {56}, msg=f"misaligned title column: {task_lines!r}")

        # 2. Wrapped columns in list (COLUMNS=90 -> avail_first = 90 - 56 = 34 >= 20)
        r_list_wrap = self._run(
            [str(SCRIPT), "list", "active"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "90"},
            check=True,
        )
        list_body_lines = [
            l for l in r_list_wrap.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertGreater(len(list_body_lines), 5)
        cont_lines = [l for l in list_body_lines if l.startswith("    ")]
        self.assertTrue(cont_lines)
        for cl in cont_lines:
            leading_spaces = len(cl) - len(cl.lstrip(" "))
            self.assertEqual(leading_spaces, 56, msg=f"unexpected list continuation indent: {cl!r}")
        for l in list_body_lines:
            self.assertLessEqual(disp_w(l), 90, msg=f"line overflowed 90 cols: {l!r}")

        # 3. Wrapped columns in list -w (COLUMNS=92 -> avail_first = 92 - 60 = 32 >= 20)
        r_ws_list_wrap = self._run(
            [str(SCRIPT), "list", "-w", "active"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "92"},
            check=True,
        )
        ws_lines = [l for l in r_ws_list_wrap.stdout.splitlines() if l.startswith("  ")]
        ws_cont = [l for l in ws_lines if l.startswith("    ")]
        self.assertTrue(ws_cont)
        for cl in ws_cont:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 60, msg=f"unexpected list -w indent: {cl!r}")
        for l in ws_lines:
            self.assertLessEqual(disp_w(l), 92, msg=f"list -w overflowed 92 cols: {l!r}")

        # 4. Wrapped columns in chain and chain -w (COLUMNS=80 -> avail_first = 80 - 56 = 24 >= 20)
        for chain_args in (["chain"], ["chain", "-w"]):
            with self.subTest(args=chain_args):
                r_ch = self._run(
                    [str(SCRIPT), *chain_args],
                    cwd=str(proj_a),
                    env={**os.environ, "COLUMNS": "80"},
                    check=True,
                )
                row_lines = [
                    l for l in r_ch.stdout.splitlines()
                    if l.startswith("  ") and not l.lstrip().startswith("F4 (HOLD)") and not l.lstrip().startswith("proj_a:F4 (HOLD)")
                ]
                ch_cont = [l for l in row_lines if l.startswith("    ")]
                self.assertTrue(ch_cont, msg=r_ch.stdout)
                for cl in ch_cont:
                    self.assertEqual(len(cl) - len(cl.lstrip(" ")), 56, msg=f"unexpected chain indent: {cl!r}")
                for l in row_lines:
                    self.assertLessEqual(disp_w(l), 80, msg=f"chain row overflowed 80 cols: {l!r}")

        # 5. Wrapped columns in queue (COLUMNS=78 -> avail_first = 78 - 44 = 34 >= 20)
        r_q = self._run(
            [str(SCRIPT), "queue", "F2", "--all"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "78"},
            check=True,
        )
        q_rows = [l for l in r_q.stdout.splitlines() if l.startswith("  ")]
        q_cont = [l for l in q_rows if l.startswith("    ")]
        self.assertTrue(q_cont, msg=r_q.stdout)
        for cl in q_cont:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 44, msg=f"unexpected queue indent: {cl!r}")
        for l in q_rows:
            self.assertLessEqual(disp_w(l), 78, msg=f"queue row overflowed 78 cols: {l!r}")

        # 6. Wrapped columns in projects (COLUMNS=60 -> avail_first = 60 - 39 = 21 >= 20)
        r_proj_wrap = self._run(
            [str(SCRIPT), "projects"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "60"},
            check=True,
        )
        proj_rows = [l for l in r_proj_wrap.stdout.splitlines() if l.startswith("  ")]
        proj_cont = [l for l in proj_rows if l.startswith("    ")]
        self.assertTrue(proj_cont, msg=r_proj_wrap.stdout)
        for cl in proj_cont:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 39, msg=f"unexpected projects indent: {cl!r}")
        for l in proj_rows:
            self.assertLessEqual(disp_w(l), 60, msg=f"projects row overflowed 60 cols: {l!r}")

        # 7. Narrow terminal fallback to 4-space continuation indent when < 20 cols remain
        r_narrow_list = self._run(
            [str(SCRIPT), "list", "WIP"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "68"},
            check=True,
        )
        narrow_lines = [
            l for l in r_narrow_list.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertGreaterEqual(len(narrow_lines), 2)
        for cl in narrow_lines[1:]:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 4, msg=f"expected 4-space fallback indent: {cl!r}")
        for l in narrow_lines:
            self.assertLessEqual(disp_w(l), 68, msg=f"narrow line overflowed 68 cols: {l!r}")

        # Very narrow terminal where prefix itself exceeds COLUMNS (COLUMNS=42)
        r_very_narrow = self._run(
            [str(SCRIPT), "list", "WIP"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "42"},
            check=True,
        )
        vn_lines = [
            l for l in r_very_narrow.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertGreaterEqual(len(vn_lines), 2)
        self.assertEqual(vn_lines[0].strip(), "F1      🔵 [WIP]        [work]      TODO.md")
        for cl in vn_lines[1:]:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 4)
            self.assertLessEqual(disp_w(cl), 42, msg=f"very narrow line overflowed 42 cols: {cl!r}")

        # 8. CJK / wide Unicode text and long unbroken tokens wrap cleanly without overflowing
        cjk_dir = ws / "cjk_proj"
        cjk_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cjk_dir), check=True)
        self._run(
            [str(SCRIPT), "add", "日本語の長いタスク説明文をテーブル列幅に合わせて折り返すテスト https://example.com/very/long/unbroken/path/segment"],
            cwd=str(cjk_dir),
            check=True,
        )
        r_cjk = self._run(
            [str(SCRIPT), "list"],
            cwd=str(cjk_dir),
            env={**os.environ, "COLUMNS": "82"},
            check=True,
        )
        cjk_lines = [l for l in r_cjk.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")]
        self.assertGreaterEqual(len(cjk_lines), 2)
        for l in cjk_lines:
            self.assertLessEqual(disp_w(l), 82, msg=f"CJK/URL line overflowed 82 cols: {l!r}")

        # 9. Full Markdown section views remain unwrapped even on narrow terminals
        for cmd in ([str(SCRIPT)], [str(SCRIPT), "show", "F1"], [str(SCRIPT), "last", "NEW"], [str(SCRIPT), "archive"]):
            r_unwrapped = self._run(
                cmd,
                cwd=str(proj_a),
                env={**os.environ, "COLUMNS": "65"},
                check=True,
            )
            if cmd[-1] == "archive":
                self.assertIn("Canceled item for alignment check", r_unwrapped.stdout)
            elif cmd[-1] == "NEW":
                self.assertIn("New item for alignment check", r_unwrapped.stdout)
            else:
                self.assertIn(long_title_1, r_unwrapped.stdout)

    def test_chain_by_role_queues_and_composition(self):
        ws = self.tmp / "ws_by_role"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Completed prerequisite should not block Queue 1 (work) or Queue 2 (plan)
        self._run([str(SCRIPT), "add", "D", "Done design prereq"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(proj_a), check=True)

        # Queue 1 (work): ready work (F1), work blocked only by work/DONE (F2), standalone work (B1)
        self._run([str(SCRIPT), "add", "F", "Ready work root", "--next", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Work after work", "--depends", "F1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Standalone bugfix"], cwd=str(proj_a), check=True)

        # Queue 2 (plan): ready plan (F3), plan depending on work (F4), plan depending on plan (F5)
        self._run([str(SCRIPT), "add", "F", "Ready plan", "--role", "plan", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Plan after work", "--role", "plan", "--depends", "F2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Plan after plan", "--role", "plan", "--depends", "F4"], cwd=str(proj_a), check=True)

        # Queue 3 (design): ready design (D2), design depending on design (D3)
        self._run([str(SCRIPT), "add", "D", "Core design", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "D", "Followup design", "--depends", "D2"], cwd=str(proj_a), check=True)

        # Queue 4 (deferred work): work blocked by plan (F6), work blocked by design (F7),
        # and work blocked transitively by design through work (F8 -> F7 -> D2)
        self._run([str(SCRIPT), "add", "F", "Work after plan", "--depends", "F4"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Work after design", "--depends", "D2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Work transitively after design", "--depends", "F7"], cwd=str(proj_a), check=True)

        # Held branch: D4 (HOLD, design) -> F9 (NEW, work)
        self._run([str(SCRIPT), "add", "D", "Paused design", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Waiting on held design", "--depends", "D4"], cwd=str(proj_a), check=True)

        # 1. Default --by-role renders all 4 queues in topological order + Held branches
        r_by_role = self._run(
            [str(SCRIPT), "chain", "--by-role"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out = r_by_role.stdout
        self.assertIn("Queue 1 (work):", out)
        self.assertIn("Queue 2 (plan):", out)
        self.assertIn("Queue 3 (design):", out)
        self.assertIn("Queue 4 (deferred work):", out)
        self.assertIn("Held branches:", out)
        self.assertIn("D4 (HOLD) -> F9 (NEW)", out)
        self.assertNotIn("D1", out)

        # Order between queues
        self.assertLess(out.index("Queue 1 (work):"), out.index("Queue 2 (plan):"))
        self.assertLess(out.index("Queue 2 (plan):"), out.index("Queue 3 (design):"))
        self.assertLess(out.index("Queue 3 (design):"), out.index("Queue 4 (deferred work):"))

        # Topological order and membership within queues
        q1_sec = out[out.index("Queue 1 (work):"):out.index("Queue 2 (plan):")]
        q2_sec = out[out.index("Queue 2 (plan):"):out.index("Queue 3 (design):")]
        q3_sec = out[out.index("Queue 3 (design):"):out.index("Queue 4 (deferred work):")]
        q4_sec = out[out.index("Queue 4 (deferred work):"):out.index("Held branches:")]

        self.assertIn("F1", q1_sec)
        self.assertIn("F2", q1_sec)
        self.assertIn("B1", q1_sec)
        self.assertLess(q1_sec.index("F1"), q1_sec.index("F2"))
        self.assertIn("[ready]", q1_sec)
        self.assertIn("[blocked by: F1]", q1_sec)
        self.assertIn("[unblocks 3]", q1_sec)
        self.assertNotIn("F6", q1_sec)
        self.assertNotIn("F7", q1_sec)

        self.assertIn("F3", q2_sec)
        self.assertIn("F4", q2_sec)
        self.assertIn("F5", q2_sec)
        self.assertLess(q2_sec.index("F4"), q2_sec.index("F5"))
        self.assertIn("[plan]", q2_sec)
        self.assertIn("[blocked by: F2]", q2_sec)

        self.assertIn("D2", q3_sec)
        self.assertIn("D3", q3_sec)
        self.assertLess(q3_sec.index("D2"), q3_sec.index("D3"))
        self.assertIn("[design]", q3_sec)

        self.assertIn("F6", q4_sec)
        self.assertIn("F7", q4_sec)
        self.assertIn("F8", q4_sec)
        self.assertLess(q4_sec.index("F7"), q4_sec.index("F8"))
        self.assertIn("[blocked by: F4]", q4_sec)
        self.assertIn("[blocked by: D2]", q4_sec)
        self.assertIn("[blocked by: F7]", q4_sec)

        # 2. --by-role --ready filters to ready tasks and omits Queue 4 (deferred work)
        r_ready = self._run([str(SCRIPT), "chain", "--by-role", "--ready"], cwd=str(proj_a), check=True)
        r_out = r_ready.stdout
        self.assertIn("Queue 1 (work):", r_out)
        self.assertIn("Queue 2 (plan):", r_out)
        self.assertIn("Queue 3 (design):", r_out)
        self.assertNotIn("Queue 4 (deferred work):", r_out)
        self.assertIn("F1", r_out)
        self.assertIn("B1", r_out)
        self.assertIn("F3", r_out)
        self.assertIn("D2", r_out)
        for blocked_id in ("F2", "F4", "F5", "D3", "F6", "F7", "F8"):
            self.assertNotIn(blocked_id, r_out)

        # 3. --by-role with --role filters cleanly and omits empty queues
        r_role_work = self._run([str(SCRIPT), "chain", "--by-role", "--role", "work"], cwd=str(proj_a), check=True)
        self.assertIn("Queue 1 (work):", r_role_work.stdout)
        self.assertIn("Queue 4 (deferred work):", r_role_work.stdout)
        self.assertNotIn("Queue 2 (plan):", r_role_work.stdout)
        self.assertNotIn("Queue 3 (design):", r_role_work.stdout)
        self.assertIn("Held branches:", r_role_work.stdout)

        r_role_plan = self._run([str(SCRIPT), "chain", "--by-role", "--role", "plan"], cwd=str(proj_a), check=True)
        self.assertIn("Queue 2 (plan):", r_role_plan.stdout)
        self.assertNotIn("Queue 1 (work):", r_role_plan.stdout)
        self.assertNotIn("Queue 3 (design):", r_role_plan.stdout)
        self.assertNotIn("Queue 4 (deferred work):", r_role_plan.stdout)
        self.assertNotIn("Held branches:", r_role_plan.stdout)

        r_role_none = self._run([str(SCRIPT), "chain", "--by-role", "--role", "review"], cwd=str(proj_a), check=True)
        self.assertIn("Queues: (none matching role=review)", r_role_none.stdout)

        # 4. --by-role with --limit and --include-hold
        r_lim = self._run([str(SCRIPT), "chain", "--by-role", "--limit", "4"], cwd=str(proj_a), check=True)
        lim_rows = {k: v for k, v in self._table_rows(r_lim.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(lim_rows), ["1.", "2.", "3.", "4."], msg=r_lim.stdout)
        self.assertNotIn("Queue 3 (design):", r_lim.stdout)

        r_hold = self._run([str(SCRIPT), "chain", "--by-role", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertNotIn("Held branches:", r_hold.stdout)
        h_q3 = r_hold.stdout[r_hold.stdout.index("Queue 3 (design):"):r_hold.stdout.index("Queue 4 (deferred work):")]
        h_q4 = r_hold.stdout[r_hold.stdout.index("Queue 4 (deferred work):"):]
        self.assertIn("D4", h_q3)
        self.assertIn("F9", h_q4)

        # 5. Workspace -w --by-role with cross-project design -> work dependency
        self._run(
            [str(SCRIPT), "add", "F", "Cross-project deferred work", "--depends", "proj_a:D2"],
            cwd=str(proj_b),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Cross-project ready work"],
            cwd=str(proj_b),
            check=True,
        )
        r_ws = self._run([str(SCRIPT), "chain", "-w", "--by-role"], cwd=str(ws), check=True)
        ws_q1 = r_ws.stdout[r_ws.stdout.index("Queue 1 (work):"):r_ws.stdout.index("Queue 2 (plan):")]
        ws_q4 = r_ws.stdout[r_ws.stdout.index("Queue 4 (deferred work):"):r_ws.stdout.index("Held branches:")]
        self.assertIn("proj_b:F2", ws_q1)
        self.assertIn("proj_b:F1", ws_q4)
        self.assertIn("[blocked by: proj_a:D2]", ws_q4)

        # 6. Plan blocked by design and unassigned/custom role tasks go to Other tasks without failing
        other_dir = ws / "other_roles"
        other_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(other_dir), check=True)
        self._run([str(SCRIPT), "add", "D", "Design first"], cwd=str(other_dir), check=True)
        self._run([str(SCRIPT), "add", "F", "Plan after design", "--role", "plan", "--depends", "D1"], cwd=str(other_dir), check=True)
        self._run([str(SCRIPT), "add", "P", "Unassigned idea"], cwd=str(other_dir), check=True)
        self._run([str(SCRIPT), "add", "F", "Review diff", "--role", "review"], cwd=str(other_dir), check=True)
        r_other = self._run([str(SCRIPT), "chain", "--by-role"], cwd=str(other_dir), check=True)
        self.assertIn("Queue 3 (design):", r_other.stdout)
        self.assertNotIn("Queue 2 (plan):", r_other.stdout)
        self.assertIn("Other tasks:", r_other.stdout)
        other_sec = r_other.stdout[r_other.stdout.index("Other tasks:"):]
        self.assertIn("F1", other_sec)
        self.assertIn("P1", other_sec)
        self.assertIn("F2", other_sec)

    def test_chain_ready_downstream_targets(self):
        ws = self.tmp / "ws_ready_downstream"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Root D1 (design) unblocks 4 immediate dependents:
        # F1 (NEW, unblocks 0), F2 (NEXT, unblocks 1 -> F5), F3 (WIP, unblocks 0), F4 (NEW, unblocks 0)
        # Expected rank order of immediate dependents: F3 (WIP) -> F2 (NEXT) -> F1 (NEW) -> F4 (NEW)
        self._run([str(SCRIPT), "add", "D", "Root design", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Low leaf", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Next mid", "--next", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Active branch", "--status", "WIP", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Fourth branch", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Transitive leaf", "--depends", "F2"], cwd=str(proj_a), check=True)

        # Standalone task with a held dependent (excluded by default, included with --include-hold)
        self._run([str(SCRIPT), "add", "B", "Ready bugfix", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Held child", "--status", "HOLD", "--depends", "B1"], cwd=str(proj_a), check=True)

        # Cross-project dependent in proj_b
        self._run([str(SCRIPT), "add", "F", "Cross repo child", "--depends", "proj_a:B1"], cwd=str(proj_b), check=True)

        r_local = self._run(
            [str(SCRIPT), "chain", "--ready"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        rows = {k: v for k, v in self._table_rows(r_local.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(rows), ["1.", "2."], msg=r_local.stdout)
        # D1 has 5 active downstream tasks (F3, F2, F1, F4, F5) and 4 immediate dependents -> top 3 + ...
        self.assertIn("D1", rows["1."])
        self.assertIn("[ready | unblocks 5 -> F3, F2, F1, ...]", rows["1."])
        # B1's only local dependent is HOLD, so without --include-hold it shows plain [ready]
        self.assertIn("B1", rows["2."])
        self.assertIn("[ready]", rows["2."])
        self.assertNotIn("unblocks", rows["2."])

        # --role design --ready keeps downstream targets of mixed roles visible on D1
        r_role = self._run(
            [str(SCRIPT), "chain", "--ready", "--role", "design"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        role_rows = {k: v for k, v in self._table_rows(r_role.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(role_rows), ["1."], msg=r_role.stdout)
        self.assertIn("[ready | unblocks 5 -> F3, F2, F1, ...]", role_rows["1."])

        # --include-hold includes the held dependent in --ready downstream targets
        r_hold = self._run(
            [str(SCRIPT), "chain", "--ready", "--include-hold"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        hold_rows = {k: v for k, v in self._table_rows(r_hold.stdout).items() if k.endswith(".")}
        self.assertIn("B1", hold_rows["2."])
        self.assertIn("[ready | unblocks 1 -> F6]", hold_rows["2."])

        # Workspace -w --ready renders cross-project downstream target refs
        r_ws = self._run(
            [str(SCRIPT), "chain", "-w", "--ready"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        ws_rows = {k: v for k, v in self._table_rows(r_ws.stdout).items() if k.endswith(".")}
        self.assertIn("proj_a:D1", ws_rows["1."])
        self.assertIn("[ready | unblocks 5 -> proj_a:F3, proj_a:F2, proj_a:F1, ...]", ws_rows["1."])
        self.assertIn("proj_a:B1", ws_rows["2."])
        self.assertIn("[ready | unblocks 1 -> proj_b:F1]", ws_rows["2."])

if __name__ == "__main__":
    unittest.main()
