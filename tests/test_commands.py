#!/usr/bin/env python3
"""Tests for todo_md task lifecycle subcommands."""

import os
import pty
import shutil
import unittest
from tests.helpers import SCRIPT, TodoMdTestCase


class TestCommands(TodoMdTestCase):
    def test_add_edit_append_cli(self):
        r_idea = self._run(
            [str(SCRIPT), "init"],
            input="Initial project idea from stdin.\n",
            check=True,
        )
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
        r_sum = self._run([str(SCRIPT), "overview"], check=True)
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

    def test_upstream_sync_before_mutation(self):
        def git(cwd, *args):
            return self._run_subprocess(["git", *args], cwd=str(cwd), check=True)

        def tmd(cwd, *args, **kwargs):
            return self._run_subprocess([str(SCRIPT), *args], cwd=str(cwd), **kwargs)

        def identify(cwd):
            git(cwd, "config", "user.name", "Test User")
            git(cwd, "config", "user.email", "test@example.com")

        no_pull = dict(os.environ, TODO_MD_NO_GIT_PULL="1")
        remote = self.tmp / "remote.git"
        repo_a = self.tmp / "a"
        repo_b = self.tmp / "b"
        remote.mkdir()
        repo_a.mkdir()
        git(remote, "init", "--bare")
        git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        git(repo_a, "init")
        git(repo_a, "symbolic-ref", "HEAD", "refs/heads/main")
        identify(repo_a)
        git(repo_a, "remote", "add", "origin", str(remote))
        (repo_a / "code.txt").write_text("code\n", encoding="utf-8")
        git(repo_a, "add", "code.txt")
        git(repo_a, "commit", "-m", "Add code")
        tmd(repo_a, "init", input="", check=True)
        tmd(repo_a, "add", "Task A", "-c", check=True)
        git(repo_a, "push", "-u", "origin", "main")
        git(self.tmp, "clone", str(remote), "b")
        identify(repo_b)

        # Upstream moved ahead: the mutation pulls first, so the new ID is not a duplicate
        tmd(repo_a, "add", "Task B", "-c", check=True)
        git(repo_a, "push")
        r_c = tmd(repo_b, "add", "Task C", "-c", check=True)
        self.assertIn("added F3", r_c.stdout)
        self.assertIn("Task B", (repo_b / "TODO.md").read_text(encoding="utf-8"))
        git(repo_b, "push")

        # Uncommitted tracked code changes without --commit: the sync is skipped
        (repo_b / "code.txt").write_text("dirty\n", encoding="utf-8")
        tmd(repo_a, "add", "Task D", "-c", check=True)
        git(repo_a, "push")
        r_e = tmd(repo_b, "add", "Task E", check=True)
        self.assertIn("added F4", r_e.stdout)
        self.assertNotIn("Task D", (repo_b / "TODO.md").read_text(encoding="utf-8"))

        # Diverged branch: fail fast without touching TODO.md; TODO_MD_NO_GIT_PULL skips the sync
        git(repo_b, "checkout", "--", ".")
        tmd(repo_b, "add", "Local F", "-c", env=no_pull, check=True)
        r_div = tmd(repo_b, "add", "Task G", "-c")
        self.assertNotEqual(r_div.returncode, 0, msg=r_div.stdout)
        self.assertIn("git pull --ff-only failed", r_div.stderr)
        self.assertNotIn("Task G", (repo_b / "TODO.md").read_text(encoding="utf-8"))
        r_skip = tmd(repo_b, "add", "Task G", env=no_pull)
        self.assertEqual(r_skip.returncode, 0, msg=r_skip.stderr)

    def test_next_id_files_and_pipe_output(self):
        self._run([str(SCRIPT), "init"], check=True)
        r_empty = self._run([str(SCRIPT), "next-id"])
        self.assertEqual(r_empty.returncode, 1, msg=r_empty.stderr)
        self.assertIn("no active WIP or NEXT task", r_empty.stderr)

        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "app.py").write_text("".join(f"line{i}\n" for i in range(1, 13)), encoding="utf-8")
        (self.tmp / "README.md").write_text("# Demo\n", encoding="utf-8")
        body = (
            "- Prose mention of `build.py` is ignored.\n"
            "- Target files: `src/app.py:10`, `README.md`, `src/app.py`, `src/missing.py`, `../outside.py`.\n"
            "```text\n"
            "Ignore fenced `build.py`\n"
            "```\n"
        )
        (self.tmp / "build.py").write_text("# fenced\n", encoding="utf-8")
        self._run([str(SCRIPT), "add", "Next task", "--next", "-b", body], check=True)
        self._run([str(SCRIPT), "add", "Wip task", "--status", "WIP", "-b", "- Target files: `README.md`."], check=True)

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

        r_pipe = self._run([str(SCRIPT), "F1"], check=True)
        self.assertIn("# 🎯 [NEXT] F1: Next task", r_pipe.stdout)
        self.assertEqual(r_pipe.stderr, "")

        # next-id filters by readiness (skips blocked WIP/NEXT) and --role / --role=
        role_dir = self.tmp / "role_ready_nid"
        role_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(role_dir), check=True)
        # D1 is a ready NEXT design task (prefix D defaults to role=design)
        self._run([str(SCRIPT), "add", "D", "Design spec", "--next"], cwd=str(role_dir), check=True)
        # F1 is a NEXT work task blocked by D1
        self._run([str(SCRIPT), "add", "F", "Blocked work", "--next", "--depends", "D1"], cwd=str(role_dir), check=True)

        # Unfiltered next-id skips blocked F1 and picks the top ready NEXT task (D1)
        r_unfiltered = self._run([str(SCRIPT), "next-id"], cwd=str(role_dir), check=True)
        self.assertEqual(r_unfiltered.stdout.strip(), "D1")
        r_design = self._run([str(SCRIPT), "next-id", "--role", "design"], cwd=str(role_dir), check=True)
        self.assertEqual(r_design.stdout.strip(), "D1")
        # NEXT/WIP tasks always resolve to work or design, so no ready plan task exists
        r_plan = self._run([str(SCRIPT), "next-id", "--role=plan"], cwd=str(role_dir))
        self.assertEqual(r_plan.returncode, 1, msg=r_plan.stderr)
        # Work task F1 is blocked by D1, so next-id --role work finds no ready work task
        r_work_blocked = self._run([str(SCRIPT), "next-id", "--role", "work"], cwd=str(role_dir))
        self.assertEqual(r_work_blocked.returncode, 1, msg=r_work_blocked.stderr)
        self.assertIn("no active WIP or NEXT task (role=work)", r_work_blocked.stderr)

        # Even if blocked F1 is promoted to WIP, unfiltered next-id skips it and returns ready D1
        self._run([str(SCRIPT), "status", "F1", "WIP"], cwd=str(role_dir), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id"], cwd=str(role_dir), check=True).stdout.strip(), "D1")
        r_work_wip = self._run([str(SCRIPT), "next-id", "--role", "work"], cwd=str(role_dir))
        self.assertEqual(r_work_wip.returncode, 1, msg=r_work_wip.stderr)

        # Add ready NEXT work task B1 -> next-id --role work skips blocked WIP F1 and returns B1
        self._run([str(SCRIPT), "add", "B", "Ready bugfix", "--next"], cwd=str(role_dir), check=True)
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "--role", "work"], cwd=str(role_dir), check=True).stdout.strip(),
            "B1",
        )
        # With target <ID>, next-id <ID> --role filters actionable tasks in <ID>'s queue
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "F1", "--role", "design"], cwd=str(role_dir), check=True).stdout.strip(),
            "D1",
        )
        r_f1_work = self._run([str(SCRIPT), "next-id", "F1", "--role=work"], cwd=str(role_dir))
        self.assertEqual(r_f1_work.returncode, 1, msg=r_f1_work.stderr)

        # Once D1 is done, F1 is unblocked and becomes the top WIP work task
        self._run([str(SCRIPT), "done", "D1", "-m", "designed"], cwd=str(role_dir), check=True)
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "--role", "work"], cwd=str(role_dir), check=True).stdout.strip(),
            "F1",
        )
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "F1", "--role=work"], cwd=str(role_dir), check=True).stdout.strip(),
            "F1",
        )

        # Invalid next-id options rejected
        for bad_args in (
            ["next-id", "--role"],
            ["next-id", "--role="],
            ["next-id", "--unknown"],
            ["next-id", "F1", "B1"],
        ):
            with self.subTest(bad_args=bad_args):
                r_bad = self._run([str(SCRIPT), *bad_args], cwd=str(role_dir))
                self.assertNotEqual(r_bad.returncode, 0, msg=r_bad.stderr)

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
        self.assertNotEqual(r_app_empty.returncode, 0, msg=r_app_empty.stderr)
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

    def test_forbid_implicit_reopen_and_reopen_command(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        proj = ws / "proj"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        (proj / "app.py").write_text("print('ok')\n", encoding="utf-8")
        self._run([str(SCRIPT), "add", "Done task", "-b", "- Target files: `app.py`."], cwd=str(proj), check=True)
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
        self.assertNotEqual(r_active.returncode, 0, msg=r_active.stderr)
        self.assertIn("already active", r_active.stderr)
        r_bad_st = self._run([str(SCRIPT), "reopen", "F3", "--status", "DONE"], cwd=str(proj))
        self.assertNotEqual(r_bad_st.returncode, 0, msg=r_bad_st.stderr)
        self.assertIn("active status", r_bad_st.stderr)

        self._run([str(SCRIPT), "check"], cwd=str(proj), check=True)

    def test_list_role_display_and_filter(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        self._run([str(SCRIPT), "add", "D", "Design API", "-b", "Design body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Build CLI", "--next", "-b", "Work body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Fix crash", "--next", "-b", "Bug body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "P", "Unassigned role", "-b", "Proposal body"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Audit diff", "-b", "Review body"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "D", "Done design", "-b", "Done body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "D2", "-m", "done"], cwd=str(proj_a), check=True)

        self._run([str(SCRIPT), "add", "F", "Other work", "--next", "-b", "B body"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "P", "Other review", "-b", "B review"],
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
        self.assertIn("[plan]", rows["F2"])
        self.assertIn("[plan]", rows["P1"])

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
            [str(SCRIPT), "list", "--role", "PLAN", "--limit", "2", "--full"],
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
        self.assertIn("[plan]", ws_rows["proj_a:F2"])
        self.assertNotIn("[work]", ws_rows["proj_a:P1"])
        self.assertIn("[work]", ws_rows["proj_b:F1"])
        self.assertIn("[plan]", ws_rows["proj_a:P1"])
        self.assertIn("[plan]", ws_rows["proj_b:P1"])

        r_ws_rev = self._run([str(SCRIPT), "-w", "list", "--role=plan"], cwd=str(proj_a), check=True)
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

    def test_files_glob_patterns_and_line_slices(self):
        self._run([str(SCRIPT), "init"], check=True)
        src = self.tmp / "src"
        src.mkdir()
        (src / "big.py").write_text("".join(f"l{i}\n" for i in range(1, 101)), encoding="utf-8")
        (src / "a.py").write_text("a\n", encoding="utf-8")
        (src / "b.py").write_text("b\n", encoding="utf-8")
        cache = src / "__pycache__"
        cache.mkdir()
        (cache / "a.pyc").write_text("x\n", encoding="utf-8")
        docs = self.tmp / "docs"
        docs.mkdir()
        (docs / "x.md").write_text("x\n", encoding="utf-8")
        (docs / "y.md").write_text("y\n", encoding="utf-8")
        (self.tmp / "todo_md").write_text("compiled\n", encoding="utf-8")
        body = (
            "- Target files: slices `src/big.py:10-20`, `src/big.py:50`, `src/big.py#L60-L70`, "
            "`src/big.py#L80`, `src/big.py:95-200`.\n"
            "- Target files: globs `src/?.py`, `src/**/*.pyc`, and `docs/*.md`.\n"
            "- Target files: ignored: cross-project ref `todo_md:D5`, bare `D*` and `*`, `src/*.py:1-2`, "
            "`../*.py`, `src/big.py:0-5`, `src/big.py:20-10`, `src/big.py:500-600`.\n"
        )
        self._run([str(SCRIPT), "add", "Glob task", "--next", "-b", body], check=True)
        r = self._run([str(SCRIPT), "files", "F1"], check=True)
        self.assertEqual(
            r.stdout.splitlines(),
            [
                "src/big.py:10-20",
                "src/big.py:50-50",
                "src/big.py:60-70",
                "src/big.py:80-80",
                "src/big.py:95-100",
                "src/a.py",
                "src/b.py",
                "docs/x.md",
                "docs/y.md",
            ],
        )
        self.assertNotIn("__pycache__", r.stdout)

    def test_files_line_slice_budgets(self):
        self._run([str(SCRIPT), "init"], check=True)
        (self.tmp / "big.py").write_text("".join(f"l{i}\n" for i in range(1, 101)), encoding="utf-8")
        self._run(
            [str(SCRIPT), "add", "Slice budgets", "--next", "-b", "- Target files: `big.py:1-5`, `big.py:10-40`, `big.py:60-100`."],
            check=True,
        )
        cases = (
            ([], ["big.py:1-5", "big.py:10-40", "big.py:60-100"]),
            (["--max-lines", "10"], ["big.py:1-5"]),
            (["--max-lines", "40"], ["big.py:1-5", "big.py:10-40"]),
            (["--max-total-lines", "40"], ["big.py:1-5", "big.py:10-40"]),
            (["--max-bytes", "20"], ["big.py:1-5"]),
            (["--max-total-bytes", "15"], ["big.py:1-5"]),
        )
        for extra, expected in cases:
            with self.subTest(extra=extra):
                r = self._run([str(SCRIPT), "files", "F1", *extra], check=True)
                self.assertEqual(r.stdout.splitlines(), expected)

    def test_files_symbol_slices_and_range_normalization(self):
        self._run([str(SCRIPT), "init"], check=True)
        src_lines = [
            "X = 1", "", "@deco", "def foo(a):", "    return a", "", "",
            "class Foo:", "    def bar(self):", "        return 1", "",
            "    def baz(self):", "        return 2", "", "", "def last():", "    pass",
        ]
        (self.tmp / "a.py").write_text("\n".join(src_lines) + "\n", encoding="utf-8")
        cases = (
            ("- Target files: `a.py:foo`.", ["a.py:3-5"]),
            ("- Target files: `a.py:Foo.bar`, `a.py:last`, `a.py:X`.", ["a.py:1-1", "a.py:9-10", "a.py:16-17"]),
            ("- Target files: `a.py:foo..Foo`, `a.py:Foo.baz`.", ["a.py:3-13"]),
            ("- Target files: `a.py:Foo`, `a.py`.", ["a.py"]),
            ("- Target files: `a.py:2-4`, `a.py:3-6`, `a.py:6-8`, `a.py:20-30`.", ["a.py:2-8"]),
            ("Mentions `a.py:1-2` in prose only.", []),
            ("- Target files: `a.py:missing`.", []),
        )
        for n, (body, expected) in enumerate(cases, start=1):
            self._run([str(SCRIPT), "add", f"Sym {n}", "--next", "-b", body], check=True)
            with self.subTest(body=body):
                r = self._run([str(SCRIPT), "files", f"F{n}"], check=True)
                self.assertEqual(r.stdout.splitlines(), expected, msg=r.stderr)
        r_missing = self._run([str(SCRIPT), "files", "F7"], check=True)
        self.assertIn("symbol slice 'a.py:missing' not found in a.py", r_missing.stderr)

    def test_list_rejects_retired_tree_flag(self):
        proj = self.tmp / "proj_no_tree"
        proj.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        r = self._run([str(SCRIPT), "list", "--tree"], cwd=str(proj), check=False)
        self.assertNotEqual(r.returncode, 0, msg=r.stdout)
        self.assertIn("unknown option for list: --tree", r.stderr)


if __name__ == "__main__":
    unittest.main()
