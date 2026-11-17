#!/usr/bin/env python3
"""Tests for todo_md and install.sh."""

from __future__ import annotations

import os
import pty
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "todo_md"
INSTALL_SH = ROOT / "install.sh"


class TestTodoMd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="todo_md_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(
        self, args: list[str], *, check: bool = False, **kwargs
    ) -> subprocess.CompletedProcess[str]:
        kwargs.setdefault("cwd", str(self.tmp))
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        proc = subprocess.run(args, check=False, **kwargs)
        if check:
            self.assertEqual(
                proc.returncode,
                0,
                msg=f"{args!r} failed (rc={proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            )
        return proc

    def test_help_version_and_agents(self):
        rh = self._run([str(SCRIPT), "-h"])
        self.assertEqual(rh.returncode, 0)
        self.assertIn("Usage:", rh.stdout)
        self.assertNotIn("resume", rh.stdout)
        self.assertNotIn("TODO_PLAN.md", rh.stdout)
        self.assertIn("next <ID>", rh.stdout)
        self.assertIn("reopen <ID>", rh.stdout)
        self.assertIn("--reopen", rh.stdout)
        self.assertIn("add", rh.stdout)
        self.assertIn("--role ROLE", rh.stdout)
        self.assertIn("opts: --role ROLE, --limit N, --full", rh.stdout)
        self.assertIn("edit", rh.stdout)
        self.assertIn("append", rh.stdout)

        rv = self._run([str(SCRIPT), "--version"])
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
        self.assertIn("list [active|archive|all|<STATUS>] [--role <role>]", rule_txt)
        self.assertIn("--max-total-lines N", rh.stdout)
        self.assertIn("queue <ID> [--all]", rh.stdout)
        self.assertIn("next-id [<ID>]", rh.stdout)
        self.assertIn("queue <ID> [--all]", rule_txt)
        self.assertIn("next-id [<ID>]", rule_txt)
        self.assertIn("A -> B -> C", rule_txt)
        self.assertIn("do not introduce a separate `- Order:` field", rule_txt)
        self.assertIn("[if task=last] var task=$(todo_md last-id DONE)", bundle_txt)
        self.assertIn("[if task=DONE] var task=$(todo_md last-id DONE)", bundle_txt)

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
        self._run(["git", "init"], check=True)
        self._run(["git", "config", "user.name", "Test User"], check=True)
        self._run(["git", "config", "user.email", "test@example.com"], check=True)

        # Create a staged non-TODO file to verify todo_md --commit commits ONLY TODO*.md
        other_file = self.tmp / "unrelated.txt"
        other_file.write_text("unrelated staged work\n", encoding="utf-8")
        self._run(["git", "add", "unrelated.txt"], check=True)

        # Default init does NOT git-commit
        r_init = self._run([str(SCRIPT), "init", "Initial idea"], check=True)
        self.assertNotIn("committed", r_init.stdout)

        # Add with -c / --commit commits TODO*.md (including the initialized files)
        r_add1 = self._run([str(SCRIPT), "add", "Task A", "-c"], check=True)
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_add1.stdout)

        # Verify unrelated.txt is still staged and was NOT included in the todo_md commit
        r_show = self._run(["git", "show", "--name-only", "--pretty=format:", "HEAD"], check=True)
        committed_files = r_show.stdout.strip().splitlines()
        self.assertEqual(committed_files, ["TODO.md", "TODO_ARCHIVE.md"])
        r_st = self._run(["git", "status", "--porcelain"], check=True)
        self.assertIn("A  unrelated.txt", r_st.stdout)

        # Default add without --commit does not commit; --no-commit is accepted as a no-op alias
        r_add2 = self._run([str(SCRIPT), "add", "Task B"], check=True)
        self.assertNotIn("committed", r_add2.stdout)
        r_add3 = self._run([str(SCRIPT), "add", "Task C", "--no-commit"], check=True)
        self.assertNotIn("committed", r_add3.stdout)

        # Done with --commit moves task to TODO_ARCHIVE.md and commits both files
        r_done = self._run([str(SCRIPT), "done", "F2", "-m", "1234567", "--commit"], check=True)
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_done.stdout)
        self.assertIn("Complete task F2: Task A", r_done.stdout)

        r_log = self._run(["git", "log", "--oneline"], check=True)
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
                    r_tty = self._run(
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

        # Prefix defaults: D -> design, F/B -> work, P -> omitted when unset
        self._run([str(SCRIPT), "add", "D", "Explore architecture", "-b", "Design body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Implement feature", "-b", "Feature body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Fix bug", "-b", "Bug body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "P", "Idea without role", "-b", "Idea body"], cwd=str(proj_a), check=True)

        resolved_proj_a = str(proj_a.resolve())
        for tid, expected_role in [("D1", "design"), ("F1", "work"), ("B1", "work"), ("P1", None)]:
            for cmd in ([str(SCRIPT), tid], [str(SCRIPT), "show", tid]):
                with self.subTest(tid=tid, cmd=cmd):
                    proc = self._run(cmd, cwd=str(proj_a), check=True)
                    lines = proc.stdout.splitlines()
                    if expected_role is not None:
                        self.assertEqual(
                            lines[:4],
                            [f"Task: {tid}", f"Role: {expected_role}", f"Workdir: {resolved_proj_a}", ""],
                        )
                        self.assertTrue(lines[4].startswith("# TODO.md:"), msg=proc.stdout)
                    else:
                        self.assertEqual(
                            lines[:3],
                            [f"Task: {tid}", f"Workdir: {resolved_proj_a}", ""],
                        )
                        self.assertNotIn("Role:", proc.stdout)
                        self.assertTrue(lines[3].startswith("# TODO.md:"), msg=proc.stdout)

        # Explicit --role overrides prefix fallback and works on unmapped prefixes
        self._run([str(SCRIPT), "add", "F", "Audit task", "--role", "review", "--depends", "D1", "-b", "Review body"], cwd=str(proj_a), check=True)
        r_f2 = self._run([str(SCRIPT), "proj_a:F2"], cwd=str(ws), check=True)
        self.assertEqual(
            r_f2.stdout.splitlines()[:4],
            ["Task: F2", "Role: review", f"Workdir: {resolved_proj_a}", ""],
        )
        self.assertIn("- Depends on: D1", r_f2.stdout)

        # edit --role updates or clears - Role: without dropping - Depends on:
        self._run([str(SCRIPT), "edit", "proj_a:F2", "--role", "plan"], cwd=str(ws), check=True)
        r_f2_plan = self._run([str(SCRIPT), "show", "proj_a:F2"], cwd=str(ws), check=True)
        self.assertEqual(r_f2_plan.stdout.splitlines()[:2], ["Task: F2", "Role: plan"])
        self.assertIn("- Depends on: D1", r_f2_plan.stdout)

        self._run([str(SCRIPT), "edit", "F2", "--role", ""], cwd=str(proj_a), check=True)
        r_f2_cleared = self._run([str(SCRIPT), "F2"], cwd=str(proj_a), check=True)
        self.assertEqual(r_f2_cleared.stdout.splitlines()[:2], ["Task: F2", "Role: work"])
        self.assertIn("- Depends on: D1", r_f2_cleared.stdout)

        self._run([str(SCRIPT), "edit", "P1", "--role", "design"], cwd=str(proj_a), check=True)
        r_p1 = self._run([str(SCRIPT), str(proj_a), "P1"], cwd=str(ws), check=True)
        self.assertEqual(
            r_p1.stdout.splitlines()[:4],
            ["Task: P1", "Role: design", f"Workdir: {resolved_proj_a}", ""],
        )

        # Fenced - Role: inside code block does not override prefix role
        fenced_body = "`" * 3 + "markdown\n- Role: custom\n" + "`" * 3 + "\nDetails."
        self._run([str(SCRIPT), "add", "F", "Fenced role test", "-b", fenced_body], cwd=str(proj_a), check=True)
        r_f3 = self._run([str(SCRIPT), "F3"], cwd=str(proj_a), check=True)
        self.assertEqual(r_f3.stdout.splitlines()[:2], ["Task: F3", "Role: work"])

        # last / show last emit headers too
        r_last = self._run([str(SCRIPT), "show", "last"], cwd=str(proj_a), check=True)
        self.assertEqual(
            r_last.stdout.splitlines()[:4],
            ["Task: F3", "Role: work", f"Workdir: {resolved_proj_a}", ""],
        )

        # Overview and list commands remain unchanged (no Task:/Role:/Workdir: headers)
        for cmd in (
            [str(SCRIPT)],
            [str(SCRIPT), "--full"],
            [str(SCRIPT), "list"],
        ):
            r_ov = self._run(cmd, cwd=str(proj_a), check=True)
            self.assertNotIn("Workdir:", r_ov.stdout, msg=f"cmd={cmd}")
            self.assertNotIn("Task:", r_ov.stdout, msg=f"cmd={cmd}")
        r_ws = self._run([str(SCRIPT), "-w"], cwd=str(ws), check=True)
        self.assertNotIn("Workdir:", r_ws.stdout)
        self.assertNotIn("Task:", r_ws.stdout)

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

    def test_install_sh(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
        r = self._run(["sh", str(INSTALL_SH), "--dir", str(bin_dir), "--yes"], env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((bin_dir / "todo_md").is_file())


if __name__ == "__main__":
    unittest.main()
