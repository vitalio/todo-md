#!/usr/bin/env python3
"""Tests for todo_md and install.sh."""

from __future__ import annotations

import os
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

    def test_help_version_and_agents(self):
        rh = subprocess.run([str(SCRIPT), "-h"], capture_output=True, text=True, check=False)
        self.assertEqual(rh.returncode, 0)
        self.assertIn("Usage:", rh.stdout)
        self.assertNotIn("resume", rh.stdout)
        self.assertNotIn("TODO_PLAN.md", rh.stdout)
        self.assertIn("next <ID>", rh.stdout)
        self.assertIn("add", rh.stdout)
        self.assertIn("edit", rh.stdout)
        self.assertIn("append", rh.stdout)

        rv = subprocess.run([str(SCRIPT), "--version"], capture_output=True, text=True, check=False)
        self.assertEqual(rv.returncode, 0)
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(rv.stdout.strip(), f"todo_md {ver}")

        self.assertNotIn("--agents", rh.stdout)
        rule_txt = (ROOT / "src/rules/todo_md.md").read_text(encoding="utf-8")
        self.assertIn("Repository scope only", rule_txt)
        self.assertIn("🎯 [NEXT]", rule_txt)
        self.assertIn("TODO_ARCHIVE.md", rule_txt)
        bundle_txt = (ROOT / "src/bundles/todo_md.bundle").read_text(encoding="utf-8")
        self.assertIn("rule vitalio/todo_md:todo_md", bundle_txt)
        self.assertNotIn("task=next", bundle_txt)
        self.assertIn("$ todo_md status {task:} WIP", bundle_txt)
        self.assertIn("todo_md next-id", bundle_txt)
        self.assertIn("var task=$(todo_md next-id)", bundle_txt)
        self.assertIn("include $(todo_md files {task:})", bundle_txt)

    def test_init_summary_priority_smart_truncation_and_check(self):
        r_init = subprocess.run([str(SCRIPT), "init"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_init.returncode, 0)
        self.assertTrue((self.tmp / "TODO.md").is_file())
        self.assertFalse((self.tmp / "TODO_PLAN.md").exists())
        self.assertTrue((self.tmp / "TODO_ARCHIVE.md").is_file())

        # Add 6 tasks using prefix / default auto-numbering; task P1 has a multi-line body
        long_body = "\n".join(f"Detail line {i}" for i in range(1, 10))
        subprocess.run([str(SCRIPT), "add", "P", "Long backlog item", "-b", long_body], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        for idx in range(1, 6):
            subprocess.run([str(SCRIPT), "add", f"Feature {idx}", "-b", f"Body {idx}"], cwd=str(self.tmp), capture_output=True, text=True, check=True)

        # Promote F3 to NEXT priority
        r_nxt = subprocess.run([str(SCRIPT), "next", "F3", "-m", "top priority"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_nxt.returncode, 0, r_nxt.stderr)
        todo_content = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertLess(todo_content.index("F3:"), todo_content.index("P1:"))
        self.assertIn("# 🎯 [NEXT] F3: Feature 3 — *top priority*", todo_content)

        # Default summary truncates long NEW task P1 (>5 tasks total), while --full shows all lines
        r_sum = subprocess.run([str(SCRIPT)], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_sum.returncode, 0)
        self.assertIn("Body 3", r_sum.stdout)
        self.assertIn("Detail line 1", r_sum.stdout)
        self.assertNotIn("Detail line 8", r_sum.stdout)
        self.assertIn("+8 more lines", r_sum.stdout)

        r_full = subprocess.run([str(SCRIPT), "--full"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_full.returncode, 0)
        self.assertIn("Detail line 8", r_full.stdout)

        # Done automatically stamps ISO date
        today = date.today().isoformat()
        r_done = subprocess.run([str(SCRIPT), "done", "F3", "-m", "abc1234"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_done.returncode, 0, r_done.stderr)
        arch_txt = (self.tmp / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn(f"# ✅ [DONE] F3: Feature 3 — *{today}, abc1234*", arch_txt)

        r_chk = subprocess.run([str(SCRIPT), "check"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_chk.returncode, 0, r_chk.stderr)

    def test_add_edit_append_cli(self):
        r_idea = subprocess.run(
            [str(SCRIPT), "init"],
            input="Initial project idea from stdin.\n",
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(r_idea.returncode, 0)
        self.assertIn("# 🎯 [NEXT] F1: Project concept and initial design", (self.tmp / "TODO.md").read_text(encoding="utf-8"))
        self.assertIn("Initial project idea from stdin.", (self.tmp / "TODO.md").read_text(encoding="utf-8"))
        subprocess.run([str(SCRIPT), "init", "--force"], cwd=str(self.tmp), capture_output=True, text=True, check=True)

        r_add = subprocess.run(
            [str(SCRIPT), "add", "F", "First feature", "--status", "WIP", "-m", "active now"],
            input="Feature body line 1.\n",
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r_add.returncode, 0, r_add.stderr)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🔵 [WIP] F1: First feature — *active now*", todo_txt)

        r_app = subprocess.run(
            [str(SCRIPT), "append", "F1", "-b", "- [x] Substep 1"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r_app.returncode, 0, r_app.stderr)
        self.assertIn("Substep 1", (self.tmp / "TODO.md").read_text(encoding="utf-8"))

        r_ed = subprocess.run(
            [str(SCRIPT), "edit", "F1", "-t", "Renamed feature", "-m", "updated note", "-b", "Replaced body."],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r_ed.returncode, 0, r_ed.stderr)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🔵 [WIP] F1: Renamed feature — *updated note*", todo_txt)
        self.assertIn("Replaced body.", todo_txt)

        # Passing an already-used explicit ID (e.g. F1) auto-assigns next free ID (F2) without failing
        r_dup = subprocess.run(
            [str(SCRIPT), "add", "F1", "Second feature auto-numbered"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r_dup.returncode, 0, r_dup.stderr)
        self.assertIn("added F2", r_dup.stdout)
        self.assertIn("ignoring explicit ID F1; auto-assigned F2", r_dup.stderr)

        # -p / --prefix flag assigns next free ID for that prefix
        r_pfx = subprocess.run(
            [str(SCRIPT), "add", "-p", "B", "Bugfix task"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r_pfx.returncode, 0, r_pfx.stderr)
        self.assertIn("added B1", r_pfx.stdout)

        r_chk = subprocess.run([str(SCRIPT), "check"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_chk.returncode, 0, r_chk.stderr)

    def test_status_ordering_and_archive_prepend(self):
        subprocess.run([str(SCRIPT), "init"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        subprocess.run([str(SCRIPT), "add", "Hold task", "--status", "HOLD", "-b", "Hold line 1\nHold line 2"], cwd=str(self.tmp), check=True)
        subprocess.run([str(SCRIPT), "add", "New task", "--status", "NEW", "-b", "New line 1\nNew line 2"], cwd=str(self.tmp), check=True)
        subprocess.run([str(SCRIPT), "add", "Question task", "--status", "QUESTION", "-b", "Q line 1\nQ line 2"], cwd=str(self.tmp), check=True)

        # Transition F1 (HOLD) -> WIP and F2 (NEW) -> NEXT; verify TODO.md is ordered WIP -> NEXT -> QUESTION
        subprocess.run([str(SCRIPT), "status", "F2", "NEXT"], cwd=str(self.tmp), check=True)
        subprocess.run([str(SCRIPT), "status", "F1", "WIP"], cwd=str(self.tmp), check=True)
        subprocess.run([str(SCRIPT), "add", "Another new", "--status", "NEW", "-b", "Compact line 1\nCompact line 2"], cwd=str(self.tmp), check=True)
        subprocess.run([str(SCRIPT), "add", "Another hold", "--status", "HOLD", "-b", "Hold body 1\nHold body 2"], cwd=str(self.tmp), check=True)

        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertLess(todo_txt.index("F1:"), todo_txt.index("F2:"))
        self.assertLess(todo_txt.index("F2:"), todo_txt.index("F3:"))
        self.assertLess(todo_txt.index("F3:"), todo_txt.index("F4:"))
        self.assertLess(todo_txt.index("F4:"), todo_txt.index("F5:"))

        # Summary compacts NEW/HOLD even when <= 5 tasks total, while expanding WIP/NEXT/QUESTION
        r_sum = subprocess.run([str(SCRIPT)], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertIn("Q line 2", r_sum.stdout)
        self.assertIn("Compact line 1", r_sum.stdout)
        self.assertNotIn("Compact line 2", r_sum.stdout)
        self.assertNotIn("Hold body 2", r_sum.stdout)

        # Archiving tasks prepends newest to the top of TODO_ARCHIVE.md
        subprocess.run([str(SCRIPT), "done", "F1", "-m", "first"], cwd=str(self.tmp), check=True)
        subprocess.run([str(SCRIPT), "cancel", "F5", "-m", "second"], cwd=str(self.tmp), check=True)
        arch_txt = (self.tmp / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertLess(arch_txt.index("F5:"), arch_txt.index("F1:"))

    def test_git_default_no_commit_and_opt_in_commit(self):
        subprocess.run(["git", "init"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(self.tmp), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.tmp), check=True)

        # Create a staged non-TODO file to verify todo_md --commit commits ONLY TODO*.md
        other_file = self.tmp / "unrelated.txt"
        other_file.write_text("unrelated staged work\n", encoding="utf-8")
        subprocess.run(["git", "add", "unrelated.txt"], cwd=str(self.tmp), check=True)

        # Default init does NOT git-commit
        r_init = subprocess.run([str(SCRIPT), "init", "Initial idea"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertNotIn("committed", r_init.stdout)

        # Add with -c / --commit commits TODO*.md (including the initialized files)
        r_add1 = subprocess.run([str(SCRIPT), "add", "Task A", "-c"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_add1.stdout)

        # Verify unrelated.txt is still staged and was NOT included in the todo_md commit
        r_show = subprocess.run(["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        committed_files = r_show.stdout.strip().splitlines()
        self.assertEqual(committed_files, ["TODO.md", "TODO_ARCHIVE.md"])
        r_st = subprocess.run(["git", "status", "--porcelain"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertIn("A  unrelated.txt", r_st.stdout)

        # Default add without --commit does not commit; --no-commit is accepted as a no-op alias
        r_add2 = subprocess.run([str(SCRIPT), "add", "Task B"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertNotIn("committed", r_add2.stdout)
        r_add3 = subprocess.run([str(SCRIPT), "add", "Task C", "--no-commit"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertNotIn("committed", r_add3.stdout)

        # Done with --commit moves task to TODO_ARCHIVE.md and commits both files
        r_done = subprocess.run([str(SCRIPT), "done", "F2", "-m", "1234567", "--commit"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_done.stdout)
        self.assertIn("Complete task F2: Task A", r_done.stdout)

        r_log = subprocess.run(["git", "log", "--oneline"], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        self.assertEqual(len(r_log.stdout.strip().splitlines()), 2)

    def test_next_id_files_and_pipe_output(self):
        subprocess.run([str(SCRIPT), "init"], cwd=str(self.tmp), check=True)
        r_empty = subprocess.run([str(SCRIPT), "next-id"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
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
        subprocess.run([str(SCRIPT), "add", "Next task", "--next", "-b", body], cwd=str(self.tmp), check=True)
        subprocess.run([str(SCRIPT), "add", "Wip task", "--status", "WIP", "-b", "Touch `README.md`."], cwd=str(self.tmp), check=True)

        for flag in ("next-id", "--next-id", "--top"):
            r_tid = subprocess.run([str(SCRIPT), flag], cwd=str(self.tmp), capture_output=True, text=True, check=False)
            self.assertEqual(r_tid.returncode, 0, r_tid.stderr)
            self.assertEqual(r_tid.stdout.strip(), "F2")

        r_files = subprocess.run([str(SCRIPT), "files", "F1"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_files.returncode, 0, r_files.stderr)
        self.assertEqual(r_files.stdout.splitlines(), ["src/app.py", "README.md"])

        r_files_top = subprocess.run([str(SCRIPT), "--files"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_files_top.returncode, 0, r_files_top.stderr)
        self.assertEqual(r_files_top.stdout.splitlines(), ["README.md"])

        r_pipe = subprocess.run([str(SCRIPT), "F1"], cwd=str(self.tmp), capture_output=True, text=True, check=False)
        self.assertEqual(r_pipe.returncode, 0)
        self.assertIn("# 🎯 [NEXT] F1: Next task", r_pipe.stdout)
        self.assertEqual(r_pipe.stderr, "")

    def test_install_sh(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
        r = subprocess.run(["sh", str(INSTALL_SH), "--dir", str(bin_dir), "--yes"], capture_output=True, text=True, env=env, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((bin_dir / "todo_md").is_file())


if __name__ == "__main__":
    unittest.main()
