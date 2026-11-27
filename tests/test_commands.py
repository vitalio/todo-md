#!/usr/bin/env python3
"""Tests for todo_md task lifecycle subcommands."""

import os
import pty
import shutil
import unittest
from tests.helpers import SCRIPT, TodoMdTestCase


class TestCommands(TodoMdTestCase):
    def _seed_edit_body_tasks(self):
        self._run([str(SCRIPT), "add", "F", "Base"], check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Target", "-b", "Old intro.\n- Depends on: F1"],
            check=True,
        )

    def test_edit_body_preserves_depends(self):
        self._seed_edit_body_tasks()
        self._run([str(SCRIPT), "edit", "F2", "-b", "New body."], check=True)
        txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("New body.", txt)
        self.assertNotIn("Old intro.", txt)
        self.assertIn("- Depends on: F1", txt)

    def test_edit_body_replacement_lines_override_preserved(self):
        self._seed_edit_body_tasks()
        self._run([str(SCRIPT), "add", "F", "Other"], check=True)
        new_body = "New body.\n- Depends on: F3"
        self._run([str(SCRIPT), "edit", "F2", "-b", new_body], check=True)
        txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Depends on: F3", txt)
        self.assertNotIn("- Depends on: F1", txt)

    def test_edit_body_empty_depends_clears_depends(self):
        self._seed_edit_body_tasks()
        self._run([str(SCRIPT), "edit", "F2", "-b", "New body.", "--depends", ""], check=True)
        txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertNotIn("Depends on", txt)

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

        # -q / --quiet / --id-only prints only <ID>\n to stdout
        for qflag, expected_id in (("-q", "F3"), ("--quiet", "F4"), ("--id-only", "B2")):
            with self.subTest(qflag=qflag):
                args = [str(SCRIPT), "add", qflag]
                if expected_id.startswith("B"):
                    args.extend(["-p", "B"])
                args.extend([f"Quiet task {expected_id}", "--depends", "F1"])
                r_q = self._run(args)
                self.assertEqual(r_q.returncode, 0, r_q.stderr)
                self.assertEqual(r_q.stdout, f"{expected_id}\n")

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

    def test_non_git_directory_skips_git_subprocess(self):
        from unittest import mock

        with mock.patch.object(self.todo_md_mod.subprocess, "run") as mock_run:
            self._run([str(SCRIPT), "init", "Initial idea"], check=True)
            self._run([str(SCRIPT), "add", "Task A", "-c"], check=True)
            self._run([str(SCRIPT), "status", "F2", "WIP", "-c"], check=True)
            self._run([str(SCRIPT), "done", "F2", "-c"], check=True)
            self.assertEqual(mock_run.call_count, 0)

        # Subdirectory inside a git worktree / submodule (.git file or ancestor .git dir) still runs git
        git_root = self.tmp / "repo"
        sub_dir = git_root / "nested" / "sub"
        sub_dir.mkdir(parents=True)
        self._run_subprocess(["git", "init"], cwd=str(git_root), check=True)
        self._run_subprocess(["git", "config", "user.name", "Test User"], cwd=str(git_root), check=True)
        self._run_subprocess(["git", "config", "user.email", "test@example.com"], cwd=str(git_root), check=True)
        r_sub = self._run([str(SCRIPT), "init", "Subproject", "-c"], cwd=str(sub_dir), check=True)
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_sub.stdout)

        # GIT_DIR / GIT_WORK_TREE override without .git in ancestor path still invokes git
        ext_git = self.tmp / "detached_git_dir"
        work_tree = self.tmp / "detached_work_tree"
        work_tree.mkdir()
        self._run_subprocess(
            ["git", f"--git-dir={ext_git}", f"--work-tree={work_tree}", "init"],
            check=True,
        )
        self._run_subprocess(
            ["git", f"--git-dir={ext_git}", "config", "user.name", "Test User"],
            check=True,
        )
        self._run_subprocess(
            ["git", f"--git-dir={ext_git}", "config", "user.email", "test@example.com"],
            check=True,
        )
        git_env = dict(os.environ, GIT_DIR=str(ext_git), GIT_WORK_TREE=str(work_tree))
        r_env = self._run(
            [str(SCRIPT), "init", "Detached repo", "-c"],
            cwd=str(work_tree),
            env=git_env,
            check=True,
        )
        self.assertIn("committed TODO.md, TODO_ARCHIVE.md", r_env.stdout)

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

        # Uncommitted tracked code changes or earlier uncommitted TODO*.md mutation: sync is skipped
        git(repo_b, "config", "pull.rebase", "true")
        (repo_b / "code.txt").write_text("dirty\n", encoding="utf-8")
        tmd(repo_a, "add", "Task D", "-c", check=True)
        git(repo_a, "push")
        r_e = tmd(repo_b, "add", "Task E", check=True)
        self.assertIn("added F4", r_e.stdout)
        self.assertNotIn("Task D", (repo_b / "TODO.md").read_text(encoding="utf-8"))
        # Clean code.txt while TODO.md remains dirty from the uncommitted batch: sync is still skipped
        git(repo_b, "checkout", "--", "code.txt")
        r_e2 = tmd(repo_b, "next", "F4", check=True)
        self.assertIn("promoted F4", r_e2.stdout)
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

    def test_next_id_and_pipe_output(self):
        self._run([str(SCRIPT), "init"], check=True)
        r_empty = self._run([str(SCRIPT), "next-id"])
        self.assertEqual(r_empty.returncode, 1, msg=r_empty.stderr)
        self.assertIn("no active WIP or NEXT task", r_empty.stderr)

        self._run([str(SCRIPT), "add", "Next task", "--next", "-b", "Next body."], check=True)
        self._run([str(SCRIPT), "add", "Wip task", "--status", "WIP", "-b", "Wip body."], check=True)

        for flag in ("next-id", "--next-id", "--top"):
            r_tid = self._run([str(SCRIPT), flag])
            self.assertEqual(r_tid.returncode, 0, r_tid.stderr)
            self.assertEqual(r_tid.stdout.strip(), "F2")

        r_pipe = self._run([str(SCRIPT), "F1"], check=True)
        self.assertIn("# 🎯 [NEXT] F1: Next task", r_pipe.stdout)
        self.assertEqual(r_pipe.stderr, "")

        # next-id filters by readiness (skips blocked WIP/NEXT) and --prefix / --status
        nid_dir = self.tmp / "prefix_status_nid"
        nid_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(nid_dir), check=True)
        # D1 is a ready NEXT design task
        self._run([str(SCRIPT), "add", "D", "Design spec", "--next"], cwd=str(nid_dir), check=True)
        # F1 is a NEXT feature task blocked by D1
        self._run([str(SCRIPT), "add", "F", "Blocked work", "--next", "--depends", "D1"], cwd=str(nid_dir), check=True)
        # L1 is a NEW legislative task
        self._run([str(SCRIPT), "add", "L", "Draft rule"], cwd=str(nid_dir), check=True)

        # Unfiltered next-id skips blocked F1 and picks the top ready NEXT task (D1)
        r_unfiltered = self._run([str(SCRIPT), "next-id"], cwd=str(nid_dir), check=True)
        self.assertEqual(r_unfiltered.stdout.strip(), "D1")
        r_d = self._run([str(SCRIPT), "next-id", "--prefix", "D"], cwd=str(nid_dir), check=True)
        self.assertEqual(r_d.stdout.strip(), "D1")
        r_l_new = self._run([str(SCRIPT), "next-id", "--status=NEW"], cwd=str(nid_dir), check=True)
        self.assertEqual(r_l_new.stdout.strip(), "L1")
        # Feature task F1 is blocked by D1, so next-id --prefix F finds no readyWIP/NEXT F task
        r_f_blocked = self._run([str(SCRIPT), "next-id", "--prefix", "F"], cwd=str(nid_dir))
        self.assertEqual(r_f_blocked.returncode, 1, msg=r_f_blocked.stderr)
        self.assertIn("no active WIP or NEXT task (prefix=F)", r_f_blocked.stderr)

        # Even if blocked F1 is promoted to WIP, unfiltered next-id skips it and returns ready D1
        self._run([str(SCRIPT), "status", "F1", "WIP"], cwd=str(nid_dir), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id"], cwd=str(nid_dir), check=True).stdout.strip(), "D1")
        r_f_wip = self._run([str(SCRIPT), "next-id", "--prefix", "F"], cwd=str(nid_dir))
        self.assertEqual(r_f_wip.returncode, 1, msg=r_f_wip.stderr)

        # Add ready NEXT bugfix task B1 -> next-id --prefix B skips blocked WIP F1 and returns B1
        self._run([str(SCRIPT), "add", "B", "Ready bugfix", "--next"], cwd=str(nid_dir), check=True)
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "--prefix", "B"], cwd=str(nid_dir), check=True).stdout.strip(),
            "B1",
        )
        # With target <ID>, next-id <ID> --prefix / --status filters actionable tasks in <ID>'s queue
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "F1", "--prefix", "D"], cwd=str(nid_dir), check=True).stdout.strip(),
            "D1",
        )
        r_f1_f = self._run([str(SCRIPT), "next-id", "F1", "--prefix=F"], cwd=str(nid_dir))
        self.assertEqual(r_f1_f.returncode, 1, msg=r_f1_f.stderr)

        # Once D1 is done, F1 is unblocked and becomes the top WIP F task
        self._run([str(SCRIPT), "done", "D1", "-m", "designed"], cwd=str(nid_dir), check=True)
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "--prefix", "F"], cwd=str(nid_dir), check=True).stdout.strip(),
            "F1",
        )
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "F1", "--prefix=F", "--status=WIP"], cwd=str(nid_dir), check=True).stdout.strip(),
            "F1",
        )

        # Invalid next-id options rejected
        for bad_args in (
            ["next-id", "--prefix"],
            ["next-id", "--prefix="],
            ["next-id", "--prefix", "AB"],
            ["next-id", "--status"],
            ["next-id", "--status=DONE"],
            ["next-id", "--role", "work"],
            ["next-id", "--unknown"],
            ["next-id", "F1", "B1"],
        ):
            with self.subTest(bad_args=bad_args):
                r_bad = self._run([str(SCRIPT), *bad_args], cwd=str(nid_dir))
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

        # last and show last render full section for resolved task without IDs-in-use footer
        r_last = self._run([str(SCRIPT), "last", "DONE"])
        self.assertEqual(r_last.returncode, 0, r_last.stderr)
        self.assertIn("# TODO_ARCHIVE.md:", r_last.stdout)
        self.assertIn("# ✅ [DONE] F11: Done task", r_last.stdout)
        self.assertIn("Body D1", r_last.stdout)
        self.assertNotIn("IDs in use:", r_last.stdout)

        r_show_last = self._run([str(SCRIPT), "show", "last"])
        self.assertEqual(r_show_last.returncode, 0, r_show_last.stderr)
        self.assertIn("# TODO.md:", r_show_last.stdout)
        self.assertIn("# ⚪ [NEW] F8: New two", r_show_last.stdout)
        self.assertIn("Body U2", r_show_last.stdout)
        self.assertNotIn("IDs in use:", r_show_last.stdout)

        # list and list -w display active tasks in exact TODO.md file order (top to bottom) without IDs-in-use footer
        r_list_new = self._run([str(SCRIPT), "list", "NEW"], check=True)
        self.assertLess(r_list_new.stdout.index("F7"), r_list_new.stdout.index("F8"))
        self.assertNotIn("IDs in use:", r_list_new.stdout)

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
        (ws_dir / ".todo_projects").write_text("proj\n", encoding="utf-8")
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
        self._run([str(SCRIPT), "add", "Done task", "-b", "Body 1"], cwd=str(proj), check=True)
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
        for cmd in ([str(SCRIPT), "F1"], [str(SCRIPT), "show", "F1"]):
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
        (ws / ".todo_projects").write_text("proj\n", encoding="utf-8")
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

    def test_list_prefix_and_status_filters(self):
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
        self._run([str(SCRIPT), "add", "L", "Rule update", "-b", "Law body"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Audit diff", "-b", "Review body"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "D", "Done design", "-b", "Done body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "D2", "-m", "done"], cwd=str(proj_a), check=True)

        self._run([str(SCRIPT), "add", "F", "Other work", "--next", "-b", "B body"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "L", "Other rule", "-b", "B rule"],
            cwd=str(proj_b),
            check=True,
        )

        r_list = self._run([str(SCRIPT), "list"], cwd=str(proj_a), check=True)
        for role_tag in ("[design]", "[work]", "[plan]"):
            self.assertNotIn(role_tag, r_list.stdout)

        r_d = self._run([str(SCRIPT), "list", "--prefix", "D"], cwd=str(proj_a), check=True)
        self.assertIn("D1", r_d.stdout)
        self.assertNotIn("F1", r_d.stdout)
        self.assertNotIn("F2", r_d.stdout)
        self.assertNotIn("L1", r_d.stdout)

        r_next = self._run([str(SCRIPT), "list", "active", "--status=NEXT"], cwd=str(proj_a), check=True)
        self.assertIn("F1", r_next.stdout)
        self.assertIn("B1", r_next.stdout)
        self.assertNotIn("F2", r_next.stdout)
        self.assertNotIn("D1", r_next.stdout)

        r_f_new_full = self._run(
            [str(SCRIPT), "list", "--prefix", "f", "--status", "NEW", "--limit", "2", "--full"],
            cwd=str(proj_a),
            check=True,
        )
        self.assertIn("# ⚪ [NEW] F2: Audit diff", r_f_new_full.stdout)
        self.assertIn("Review body", r_f_new_full.stdout)
        self.assertNotIn("F1", r_f_new_full.stdout)

        r_arch_d = self._run([str(SCRIPT), "list", "archive", "--prefix", "D"], cwd=str(proj_a), check=True)
        self.assertIn("D2", r_arch_d.stdout)

        r_none = self._run([str(SCRIPT), "list", "--prefix", "Z"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (active, prefix=Z)", r_none.stdout)

        (proj_a / ".todo_projects.local").write_text("proj_a\nproj_b\n", encoding="utf-8")
        r_ws_l = self._run([str(SCRIPT), "-w", "list", "--prefix=L"], cwd=str(proj_a), check=True)
        self.assertIn("proj_a:L1", r_ws_l.stdout)
        self.assertIn("proj_b:L1", r_ws_l.stdout)
        self.assertNotIn("proj_a:F1", r_ws_l.stdout)
        self.assertNotIn("proj_b:F1", r_ws_l.stdout)

        r_ws_lim = self._run(
            [str(SCRIPT), "list", "-w", "--status", "NEXT", "--limit", "1"],
            cwd=str(proj_a),
            check=True,
        )
        self.assertEqual(len(r_ws_lim.stdout.strip().splitlines()), 1)
        self.assertIn("🎯 NEXT", r_ws_lim.stdout)

        r_ws_none = self._run([str(SCRIPT), "list", "-w", "--prefix", "Z"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (active, prefix=Z)", r_ws_none.stdout)

        # list -s / --search (ID, <project>:<ID>, title, body), -H / --highlight, and -l N
        r_s_body = self._run([str(SCRIPT), "list", "-s", "law body"], cwd=str(proj_a), check=True)
        self.assertIn("L1", r_s_body.stdout)
        self.assertNotIn("F1", r_s_body.stdout)
        self.assertNotIn("D1", r_s_body.stdout)

        r_s_id = self._run([str(SCRIPT), "list", "--search=proj_a:b1"], cwd=str(proj_a), check=True)
        self.assertIn("B1", r_s_id.stdout)
        self.assertNotIn("F1", r_s_id.stdout)

        r_s_arch = self._run([str(SCRIPT), "list", "archive", "--search", "Done body"], cwd=str(proj_a), check=True)
        self.assertIn("D2", r_s_arch.stdout)

        r_s_lim = self._run([str(SCRIPT), "list", "-s", "body", "-l", "2"], cwd=str(proj_a), check=True)
        s_lim_rows = [ln for ln in r_s_lim.stdout.splitlines() if ln.startswith("  ")]
        self.assertEqual(len(s_lim_rows), 2)

        color_env = {**os.environ, "FORCE_COLOR": "1"}
        r_s_hl = self._run([str(SCRIPT), "list", "-s", "Bug body", "-H"], cwd=str(proj_a), env=color_env, check=True)
        hl_lines = r_s_hl.stdout.splitlines()
        self.assertTrue(any(ln.startswith("\033[1;93m") and "  B1 " in ln for ln in hl_lines), msg=r_s_hl.stdout)
        self.assertTrue(
            any(ln.startswith("  ") and not ln.startswith("\033[") and "  F1 " in ln for ln in hl_lines),
            msg=r_s_hl.stdout,
        )

        r_s_none = self._run([str(SCRIPT), "list", "--prefix", "D", "-s", "no-such-needle"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (active, prefix=D, search='no-such-needle')", r_s_none.stdout)

        r_ws_s = self._run([str(SCRIPT), "-w", "list", "-s", "proj_b:L1"], cwd=str(proj_a), check=True)
        self.assertIn("proj_b:L1", r_ws_s.stdout)
        self.assertNotIn("proj_a:L1", r_ws_s.stdout)

        r_ws_s_hl = self._run(
            [str(SCRIPT), "-w", "list", "--search", "B rule", "--highlight"],
            cwd=str(proj_a),
            env=color_env,
            check=True,
        )
        ws_hl_lines = r_ws_s_hl.stdout.splitlines()
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and "proj_b:L1 " in ln for ln in ws_hl_lines),
            msg=r_ws_s_hl.stdout,
        )
        self.assertTrue(
            any(ln.startswith("  ") and not ln.startswith("\033[") and "proj_a:F1 " in ln for ln in ws_hl_lines),
            msg=r_ws_s_hl.stdout,
        )

        r_ws_s_none = self._run([str(SCRIPT), "-w", "list", "-s", "missing-ws-query"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (active, search='missing-ws-query') across workspace", r_ws_s_none.stdout)

        for bad_args, exp_err in (
            (["list", "--prefix"], "requires a prefix argument"),
            (["list", "--prefix", ""], "invalid --prefix"),
            (["list", "--prefix="], "invalid --prefix"),
            (["list", "--prefix", "AB"], "invalid --prefix"),
            (["list", "--status"], "requires a status argument"),
            (["list", "--status=UNKNOWN"], "invalid status"),
            (["list", "--role", "work"], "unknown option"),
            (["list", "-s"], "-s requires a non-empty query argument"),
            (["list", "--search"], "--search requires a non-empty query argument"),
            (["list", "--search", "   "], "--search requires a non-empty query argument"),
            (["list", "--search="], "--search requires a non-empty query argument"),
            (["list", "-l"], "-l requires an integer argument"),
            (["list", "-l", "0"], "invalid limit"),
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj_a))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)
                self.assertIn(exp_err, proc.stderr)

    def test_list_rejects_retired_tree_flag(self):
        proj = self.tmp / "proj_no_tree"
        proj.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        r = self._run([str(SCRIPT), "list", "--tree"], cwd=str(proj), check=False)
        self.assertNotEqual(r.returncode, 0, msg=r.stdout)
        self.assertIn("unknown option for list: --tree", r.stderr)

    def test_rename_subcommand_swaps_prefixes_dependencies_and_orchestrator(self):
        ws = self.tmp / "ws_rename"
        orch = ws / "orch"
        child = ws / "child"
        orch.mkdir(parents=True)
        child.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(orch), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(child), check=True)
        (orch / ".todo_projects").write_text("child\n", encoding="utf-8")

        self._run([str(SCRIPT), "add", "F", "First active"], cwd=str(child), check=True)
        self._run([str(SCRIPT), "add", "F", "Second active", "--depends", "F1"], cwd=str(child), check=True)
        self._run([str(SCRIPT), "add", "D", "Archived design"], cwd=str(child), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done design"], cwd=str(child), check=True)
        self._run([str(SCRIPT), "add", "F", "Third active", "--depends", "D1 -> F1, F2"], cwd=str(child), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Orchestrator wave", "--depends", "child:D1 -> child:F1, child:F2"],
            cwd=str(orch),
            check=True,
        )

        orch_todo_before = (orch / "TODO.md").read_text(encoding="utf-8")

        # 1. Single pair rename (<OLD> <NEW_ID>) across archive and local dependencies
        # without mutating external orchestrator files (strict one-way boundary)
        r_single = self._run([str(SCRIPT), "rename", "D1", "D5"], cwd=str(child), check=True)
        self.assertIn("renamed D1 -> D5", r_single.stdout)
        self.assertIn("# ✅ [DONE] D5: Archived design", (child / "TODO_ARCHIVE.md").read_text(encoding="utf-8"))
        self.assertIn("- Depends on: D5 -> F1, F2", (child / "TODO.md").read_text(encoding="utf-8"))
        self.assertEqual((orch / "TODO.md").read_text(encoding="utf-8"), orch_todo_before)

        # 2. Swap cycle (F1=F2 F2=F1) and prefix auto-allocation (F3=B, D5=B) in one batch
        r_swap = self._run([str(SCRIPT), "rename", "F1=F2,F2=F1", "F3=B", "D5=B"], cwd=str(child), check=True)
        self.assertIn("renamed F1 -> F2", r_swap.stdout)
        self.assertIn("renamed F2 -> F1", r_swap.stdout)
        self.assertIn("renamed F3 -> B1", r_swap.stdout)
        self.assertIn("renamed D5 -> B2", r_swap.stdout)
        child_todo = (child / "TODO.md").read_text(encoding="utf-8")
        child_arch = (child / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn("F2: First active", child_todo)
        self.assertIn("F1: Second active", child_todo)
        self.assertIn("- Depends on: F2", child_todo)
        self.assertIn("B1: Third active", child_todo)
        self.assertIn("- Depends on: B2 -> F2, F1", child_todo)
        self.assertIn("B2: Archived design", child_arch)
        self.assertEqual((orch / "TODO.md").read_text(encoding="utf-8"), orch_todo_before)

        # 3. Cross-project <project>:<OLD> rename from orchestrator with .todo_projects
        r_no_cfg = self._run([str(SCRIPT), "rename", "child:B1", "L"], cwd=str(ws))
        self.assertNotEqual(r_no_cfg.returncode, 0, msg=r_no_cfg.stdout)
        self.assertIn(".todo_projects", r_no_cfg.stderr)
        r_proj = self._run(
            [str(SCRIPT), "rename", "child:B1", "L"],
            cwd=str(orch),
            check=True,
        )
        self.assertIn("renamed B1 -> L1", r_proj.stdout)
        self.assertIn("L1: Third active", (child / "TODO.md").read_text(encoding="utf-8"))

        # 4. Prefix allocation reuses highest remaining ID when highest ID of that prefix was freed
        r_free = self._run([str(SCRIPT), "rename", "B2=D", "L1=B"], cwd=str(child), check=True)
        self.assertIn("renamed B2 -> D1", r_free.stdout)
        self.assertIn("renamed L1 -> B1", r_free.stdout)

        # 5. Error cases: collision with existing ID, duplicate target, duplicate source, missing task, bad syntax
        for bad_args, err_sub in (
            (["rename", "F1", "F2"], "already in use"),
            (["rename", "F1=F9,F2=F9"], "already in use"),
            (["rename", "F1=F8,F1=F9"], "duplicate source"),
            (["rename", "F99", "F100"], "not found"),
            (["rename", "F1", "INVALID"], "invalid rename target"),
            (["rename", "BAD", "F10"], "invalid task ID"),
            (["rename", "F1"], "usage:"),
            (["rename", "--unknown", "F1", "F2"], "unknown option"),
        ):
            with self.subTest(bad_args=bad_args):
                r_err = self._run([str(SCRIPT), *bad_args], cwd=str(child))
                self.assertNotEqual(r_err.returncode, 0, msg=r_err.stdout)
                self.assertIn(err_sub, r_err.stderr)

        self._run([str(SCRIPT), "check"], cwd=str(child), check=True)
        self._run(
            [str(SCRIPT), "edit", "F1", "--depends", "child:D1 -> child:F2, child:F1"],
            cwd=str(orch),
            check=True,
        )
        self._run([str(SCRIPT), "check"], cwd=str(orch), check=True)

    def test_batch_edit_and_append(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run([str(SCRIPT), "add", "Task 1", "-b", "Body 1."], check=True)
        self._run([str(SCRIPT), "add", "Task 2", "-b", "Body 2."], check=True)
        self._run([str(SCRIPT), "add", "Task 3", "-b", "Body 3."], check=True)

        # Batch edit across space- and comma-separated IDs
        self._run([str(SCRIPT), "edit", "F1,F2", "F3", "-m", "batch note"], check=True)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        for tid in ("F1", "F2", "F3"):
            self.assertIn(f"{tid}: Task {tid[1]} — *batch note*", todo_txt)

        # Batch append across space- and comma-separated IDs
        self._run([str(SCRIPT), "append", "F1", "F2,F3", "-b", "- Batch bullet"], check=True)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertEqual(todo_txt.count("- Batch bullet"), 3)

    def test_edit_next_and_status_flags(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run([str(SCRIPT), "add", "First new", "-b", "Body 1."], check=True)
        self._run([str(SCRIPT), "add", "Existing next", "--next", "-b", "Body 2."], check=True)
        self._run([str(SCRIPT), "add", "Second new", "-b", "Body 3."], check=True)
        self._run([str(SCRIPT), "add", "Third new", "-b", "Body 4."], check=True)

        # Standalone --next promotes edited task to NEXT at top of NEXT tier (above F2)
        self._run([str(SCRIPT), "edit", "F1", "--next"], check=True)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🎯 [NEXT] F1: First new", todo_txt)
        self.assertLess(todo_txt.index("F1:"), todo_txt.index("F2:"))

        # Short -n alias combined with title/note/body updates promotes above F1
        self._run(
            [str(SCRIPT), "edit", "F3", "-n", "-t", "Second promoted", "-m", "top next", "-b", "Updated body 3."],
            check=True,
        )
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🎯 [NEXT] F3: Second promoted — *top next*", todo_txt)
        self.assertIn("Updated body 3.", todo_txt)
        self.assertLess(todo_txt.index("F3:"), todo_txt.index("F1:"))

        # --top alias promotes F4 above F3
        self._run([str(SCRIPT), "edit", "F4", "--top"], check=True)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🎯 [NEXT] F4: Third new", todo_txt)
        self.assertLess(todo_txt.index("F4:"), todo_txt.index("F3:"))

        # --status / -s with active statuses (WIP, NEXT, QUESTION, NEW, HOLD)
        self._run([str(SCRIPT), "edit", "F2", "--status", "WIP"], check=True)
        self._run([str(SCRIPT), "edit", "F1", "-s", "WIP", "-m", "now wip"], check=True)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🔵 [WIP] F1: First new — *now wip*", todo_txt)
        self.assertIn("# 🔵 [WIP] F2: Existing next", todo_txt)
        # F1 promoted to WIP after F2 sits above F2 at top of WIP tier
        self.assertLess(todo_txt.index("F1:"), todo_txt.index("F2:"))

        self._run([str(SCRIPT), "edit", "F4", "--status=HOLD"], check=True)
        self._run([str(SCRIPT), "edit", "F3", "--status", "QUESTION", "--depends", "F1"], check=True)
        self._run([str(SCRIPT), "edit", "F2", "--status", "NEW"], check=True)
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# ❓ [QUESTION] F3: Second promoted — *top next*", todo_txt)
        self.assertIn("- Depends on: F1", todo_txt)
        self.assertIn("# ⚪ [NEW] F2: Existing next", todo_txt)
        self.assertIn("# ⏸️ [HOLD] F4: Third new", todo_txt)

        # Reject archive statuses (DONE, CANCELED) and unknown statuses
        for bad_args, exp_err in (
            (["edit", "F1", "--status", "DONE"], "use 'todo done' or 'todo cancel'"),
            (["edit", "F1", "-s", "CANCELED"], "use 'todo done' or 'todo cancel'"),
            (["edit", "F1", "--status=DONE"], "active status"),
            (["edit", "F1", "--status", "INVALID"], "edit status must be WIP, NEXT, NEW, HOLD, or QUESTION"),
            (["edit", "F1", "--status"], "requires an argument"),
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args])
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)
                self.assertIn(exp_err, proc.stderr)

        # Archived tasks cannot have their status changed via edit --next / --status without reopen
        self._run([str(SCRIPT), "done", "F1", "-m", "finished"], check=True)
        for arch_args in (["edit", "F1", "--next"], ["edit", "F1", "--status", "WIP"]):
            with self.subTest(arch_args=arch_args):
                proc = self._run([str(SCRIPT), *arch_args])
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)
                self.assertIn("archived as [DONE]", proc.stderr)
                self.assertIn("reopen", proc.stderr)

        self._run([str(SCRIPT), "check"], check=True)

    def test_repeated_body_flags_and_add_usage_depends(self):
        self._run([str(SCRIPT), "init"], check=True)

        # Repeated -b / --body flags on add are joined in order with '\n'
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Repeated body task",
                "-b",
                "- Line 1",
                "--body",
                "- Line 2",
                "-b",
                "- Line 3",
            ],
            check=True,
        )
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Line 1\n- Line 2\n- Line 3", todo_txt)

        # Repeated -b / --body flags on edit join in order and preserve existing Depends on
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Dependent task",
                "--depends",
                "F1",
                "-b",
                "- Initial body",
            ],
            check=True,
        )
        self._run(
            [
                str(SCRIPT),
                "edit",
                "F2",
                "-b",
                "- Edited line A",
                "--body",
                "- Edited line B",
            ],
            check=True,
        )
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Depends on: F1\n- Edited line A\n- Edited line B", todo_txt)
        self.assertNotIn("- Initial body", todo_txt)

        # Repeated -b / --body / -m flags on append join in order with '\n'
        self._run(
            [
                str(SCRIPT),
                "append",
                "F2",
                "-b",
                "- Appended 1",
                "--body",
                "- Appended 2",
            ],
            check=True,
        )
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Edited line B\n\n- Appended 1\n- Appended 2", todo_txt)

        # Mixing literal -b and '-b -' joins literal and piped stdin in order
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Mixed dash and literal",
                "-b",
                "- Header bullet",
                "--body",
                "-",
                "-b",
                "- Footer bullet",
            ],
            input="- Piped middle bullet",
            check=True,
        )
        todo_txt = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Header bullet\n- Piped middle bullet\n- Footer bullet", todo_txt)

        # Short usage error for 'todo add' includes [--depends SPEC]
        for bad_add in (["add"], ["add", "F", "Title", "ExtraPositional"]):
            with self.subTest(bad_add=bad_add):
                r_err = self._run([str(SCRIPT), *bad_add])
                self.assertNotEqual(r_err.returncode, 0, msg=r_err.stdout)
                self.assertIn("usage: todo add", r_err.stderr)
                self.assertIn("[--depends SPEC]", r_err.stderr)

        self._run([str(SCRIPT), "check"], check=True)



    def test_pre_write_validation_rejects_swallowed_expansions_in_add_edit_append(self):
        self._run([str(SCRIPT), "init"], check=True)
        fence = chr(96) * 3

        # Valid add, edit, and append with inline code, fenced blocks, and tables succeed
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Valid task with `code()`",
                "-b",
                "- Check `validate_all()` and `a  b`.\n| Col 1  | Col 2  |\n"
                + fence + "sh\necho  () `ok\n" + fence,
            ],
            check=True,
        )
        todo_before = (self.tmp / "TODO.md").read_text(encoding="utf-8")

        # Pre-write validation on add rejects corrupted title, note, or body without modifying TODO.md
        bad_add_cases = [
            (["add", "F", "Swallowed  token in title", "-b", "- Clean body."], "consecutive spaces"),
            (["add", "F", "Unpaired `tick in title", "-b", "- Clean body."], "unpaired inline backtick"),
            (["add", "F", "Empty () in title", "-b", "- Clean body."], "empty '()'"),
            (["add", "F", "Clean title", "-m", "bad  note", "-b", "- Clean body."], "consecutive spaces"),
            (["add", "F", "Clean title", "-b", "- Vanished `src/parser.py` () artifact."], "empty '()'"),
            (["add", "F", "Clean title", "-b", "- Empty [] brackets outside code."], "empty '[]'"),
            (["add", "F", "Clean title", "-b", "- Empty `` inline code span."], "empty inline code span"),
            (["add", "F", "Clean title", "-b", "- Unpaired `inline backtick."], "unpaired inline backtick"),
            (["add", "F", "Clean title", "-b", "- Double  space in prose."], "consecutive spaces"),
            (["add", "F", "Clean title", "-b", "- Space before comma , here."], "space before punctuation"),
        ]
        for args, exp_err in bad_add_cases:
            with self.subTest(cmd="add", args=args):
                r = self._run([str(SCRIPT), *args])
                self.assertNotEqual(r.returncode, 0, msg=r.stdout)
                self.assertIn(exp_err, r.stderr)
                self.assertIn("-b '...'", r.stderr)
                self.assertIn("<<'EOF'", r.stderr)
                self.assertEqual((self.tmp / "TODO.md").read_text(encoding="utf-8"), todo_before)

        # Pre-write validation on edit rejects corrupted title, note, or body without modifying TODO.md
        bad_edit_cases = [
            (["edit", "F1", "-t", "Broken  title"], "consecutive spaces"),
            (["edit", "F1", "-t", "Broken () title"], "empty '()'"),
            (["edit", "F1", "-m", "note with `unpaired"], "unpaired inline backtick"),
            (["edit", "F1", "-b", "- Swallowed () parens."], "empty '()'"),
            (["edit", "F1", "-b", "- Swallowed `` code span."], "empty inline code span"),
            (["edit", "F1", "-b", "- Swallowed  word in prose."], "consecutive spaces"),
            (["edit", "F1", "-b", "- Swallowed word before period ."], "space before punctuation"),
        ]
        for args, exp_err in bad_edit_cases:
            with self.subTest(cmd="edit", args=args):
                r = self._run([str(SCRIPT), *args])
                self.assertNotEqual(r.returncode, 0, msg=r.stdout)
                self.assertIn(exp_err, r.stderr)
                self.assertIn("-b '...'", r.stderr)
                self.assertEqual((self.tmp / "TODO.md").read_text(encoding="utf-8"), todo_before)

        # Pre-write validation on append rejects corrupted appended text without modifying TODO.md
        bad_append_cases = [
            (["append", "F1", "-b", "- Appended () empty parens."], "empty '()'"),
            (["append", "F1", "-b", "- Appended `` empty code span."], "empty inline code span"),
            (["append", "F1", "-b", "- Appended `unpaired backtick."], "unpaired inline backtick"),
            (["append", "F1", "-b", "- Appended  double space."], "consecutive spaces"),
            (["append", "F1", "-b", "- Appended space before colon : value."], "space before punctuation"),
        ]
        for args, exp_err in bad_append_cases:
            with self.subTest(cmd="append", args=args):
                r = self._run([str(SCRIPT), *args])
                self.assertNotEqual(r.returncode, 0, msg=r.stdout)
                self.assertIn(exp_err, r.stderr)
                self.assertIn("-b '...'", r.stderr)
                self.assertEqual((self.tmp / "TODO.md").read_text(encoding="utf-8"), todo_before)

        # Pre-write validation on transition commands (status, next, done, cancel, archive, reopen)
        # rejects corrupted -m notes before writing to disk
        bad_transition_cases = [
            (["status", "F1", "WIP", "-m", "bad  note"], "consecutive spaces"),
            (["next", "F1", "-m", "unpaired `tick"], "unpaired inline backtick"),
            (["done", "F1", "-m", "empty () parens"], "empty '()'"),
            (["cancel", "F1", "-m", "empty `` span"], "empty inline code span"),
            (["archive", "F1", "-m", "space before period ."], "space before punctuation"),
        ]
        for args, exp_err in bad_transition_cases:
            with self.subTest(cmd="transition", args=args):
                r = self._run([str(SCRIPT), *args])
                self.assertNotEqual(r.returncode, 0, msg=r.stdout)
                self.assertIn(exp_err, r.stderr)
                self.assertIn("-b '...'", r.stderr)
                self.assertEqual((self.tmp / "TODO.md").read_text(encoding="utf-8"), todo_before)

        # Auto-normalization on add, edit, append, and transitions (status/done/reopen -m):
        # escaped nested backticks, sentence double spaces, and trailing unclosed code fences
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                r"Title with `cmd \`<id>\` ok`.  Second sentence",
                "-m",
                r"Note one.  Note `\`<sha>\``",
                "-b",
                r"- Run `foo \`<sha12>\` bar`.  Next sentence!  `code()`."
                + "\n"
                + fence
                + "py\nx = 1",
            ],
            check=True,
        )
        todo_after_add = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn(
            "# ⚪ [NEW] F2: Title with ``cmd `<id>` ok``. Second sentence — *Note one. Note `` `<sha>` ``*",
            todo_after_add,
        )
        self.assertIn(
            "- Run ``foo `<sha12>` bar``. Next sentence! `code()`.\n" + fence + "py\nx = 1\n" + fence,
            todo_after_add,
        )

        # Edit auto-normalizes escaped backticks, sentence double spaces, and trailing unclosed fence
        self._run(
            [
                str(SCRIPT),
                "edit",
                "F2",
                "-t",
                r"Edited `\`<id>\` tail`.  Clean",
                "-b",
                r"- Wrapped `span \`<sha>\`"
                + "\n  line 2`.  Done.\n"
                + fence
                + "sh\necho hi",
            ],
            check=True,
        )
        todo_after_edit = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# ⚪ [NEW] F2: Edited `` `<id>` tail``. Clean", todo_after_edit)
        self.assertIn(
            "- Wrapped ``span `<sha>`\n  line 2``. Done.\n" + fence + "sh\necho hi\n" + fence,
            todo_after_edit,
        )

        # Append auto-normalizes escaped backticks, sentence double spaces, and trailing unclosed fence
        self._run(
            [
                str(SCRIPT),
                "append",
                "F2",
                "-b",
                r"- Appended `a \`b\` c`!  Great." + "\n" + fence + "txt\ntrailing block",
            ],
            check=True,
        )
        todo_after_append = (self.tmp / "TODO.md").read_text(encoding="utf-8")
        self.assertIn(
            "- Appended ``a `b` c``! Great.\n" + fence + "txt\ntrailing block\n" + fence,
            todo_after_append,
        )

        # Transition -m note auto-normalizes escaped backticks and sentence double spaces,
        # while reopen rejects invalid -m notes
        self._run(
            [str(SCRIPT), "done", "F2", "-m", r"Closed (`\`<sha12>\``).  Verified"],
            check=True,
        )
        arch_txt = (self.tmp / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn("Closed (`` `<sha12>` ``). Verified*", arch_txt)

        r_bad_reopen = self._run([str(SCRIPT), "reopen", "F2", "-m", "bad  reopen note"])
        self.assertNotEqual(r_bad_reopen.returncode, 0, msg=r_bad_reopen.stdout)
        self.assertIn("consecutive spaces", r_bad_reopen.stderr)

        self._run([str(SCRIPT), "check"], check=True)


if __name__ == "__main__":
    unittest.main()
