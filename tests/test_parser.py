#!/usr/bin/env python3
"""Tests for todo_md parser, overview, headers, files budget, check validation, and table rendering."""

from datetime import date
import os
import unittest
from tests.helpers import SCRIPT, TodoMdTestCase


class TestParser(TodoMdTestCase):
    def test_init_summary_priority_smart_truncation_and_check(self):
        r_init = self._run([str(SCRIPT), "init"], check=True)
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
        r_sum = self._run([str(SCRIPT), "overview"], check=True)
        self.assertIn("Body 3", r_sum.stdout)
        self.assertIn("Detail line 1", r_sum.stdout)
        self.assertNotIn("Detail line 8", r_sum.stdout)
        self.assertIn("+8 more lines", r_sum.stdout)

        r_full = self._run([str(SCRIPT), "--full"], check=True)
        self.assertIn("Detail line 8", r_full.stdout)

        # Done automatically stamps ISO date
        today = date.today().isoformat()
        r_done = self._run([str(SCRIPT), "done", "F3", "-m", "abc1234"])
        self.assertEqual(r_done.returncode, 0, r_done.stderr)
        arch_txt = (self.tmp / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn(f"# ✅ [DONE] F3: Feature 3 — *{today}, abc1234*", arch_txt)

        r_chk = self._run([str(SCRIPT), "check"])
        self.assertEqual(r_chk.returncode, 0, r_chk.stderr)

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
        r_only_new = self._run([str(SCRIPT), "overview"], check=True)
        self.assertIn("N1 line 3", r_only_new.stdout)
        self.assertIn("N2 line 1", r_only_new.stdout)
        self.assertNotIn("N2 line 3", r_only_new.stdout)
        self.assertIn("todo F2", r_only_new.stdout)
        self.assertNotIn("H1 line 3", r_only_new.stdout)
        self.assertIn("todo F3", r_only_new.stdout)

        # Adding a WIP/NEXT/QUESTION task compacts all NEW/HOLD tasks including F1
        self._run(
            [str(SCRIPT), "add", "Active question", "--status", "QUESTION", "-b", "Q1 line 1\nQ1 line 2"],
            check=True,
        )
        r_with_q = self._run([str(SCRIPT), "overview"], check=True)
        self.assertIn("Q1 line 2", r_with_q.stdout)
        self.assertIn("N1 line 1", r_with_q.stdout)
        self.assertNotIn("N1 line 3", r_with_q.stdout)
        self.assertIn("todo F1", r_with_q.stdout)

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
        r_only_hold = self._run([str(SCRIPT), "overview"], check=True)
        self.assertIn("H1 line 3", r_only_hold.stdout)
        self.assertIn("H2 line 1", r_only_hold.stdout)
        self.assertNotIn("H2 line 3", r_only_hold.stdout)
        self.assertIn("todo F2", r_only_hold.stdout)

    def test_single_task_headers_prefix_status_and_workdir(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        proj_a = ws / "proj_a"
        proj_a.mkdir()
        self._run([str(SCRIPT), str(proj_a), "init"], check=True)

        self._run([str(SCRIPT), "add", "D", "Explore architecture", "-m", "rfc draft", "-b", "Design body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Implement feature", "-b", "Feature body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Fix bug", "-b", "Bug body"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "L", "Draft rule update", "-b", "Law body"], cwd=str(proj_a), check=True)

        resolved_proj_a = str(proj_a.resolve())
        cases = [
            ("D1", "D", "NEW", "Explore architecture"),
            ("F1", "F", "NEW", "Implement feature"),
            ("B1", "B", "NEW", "Fix bug"),
            ("L1", "L", "NEW", "Draft rule update"),
        ]
        for tid, expected_prefix, expected_status, expected_title in cases:
            for cmd in ([str(SCRIPT), tid], [str(SCRIPT), "show", tid]):
                with self.subTest(tid=tid, cmd=cmd):
                    proc = self._run(cmd, cwd=str(proj_a), check=True)
                    lines = proc.stdout.splitlines()
                    self.assertEqual(
                        lines[:6],
                        [
                            f"Task: {tid}",
                            f"Prefix: {expected_prefix}",
                            f"Status: {expected_status}",
                            f"Title: {expected_title}",
                            f"Workdir: {resolved_proj_a}",
                            "",
                        ],
                    )
                    self.assertTrue(lines[6].startswith("# TODO.md:"), msg=proc.stdout)
        r_d1_note = self._run([str(SCRIPT), "D1"], cwd=str(proj_a), check=True)
        self.assertIn("# ⚪ [NEW] D1: Explore architecture — *rfc draft*", r_d1_note.stdout)

        for st in ("QUESTION", "HOLD", "NEXT", "WIP", "NEW"):
            self._run([str(SCRIPT), "status", "L1", st], cwd=str(proj_a), check=True)
            r_l1_st = self._run([str(SCRIPT), "L1"], cwd=str(proj_a), check=True)
            self.assertEqual(
                r_l1_st.stdout.splitlines()[:4],
                ["Task: L1", "Prefix: L", f"Status: {st}", "Title: Draft rule update"],
                msg=f"status={st}",
            )

        self._run([str(SCRIPT), "add", "F", "Audit task", "--depends", "D1", "-b", "Review body"], cwd=str(proj_a), check=True)
        r_f2 = self._run([str(SCRIPT), "proj_a:F2"], cwd=str(ws), check=True)
        self.assertEqual(
            r_f2.stdout.splitlines()[:6],
            ["Task: F2", "Prefix: F", "Status: NEW", "Title: Audit task", f"Workdir: {resolved_proj_a}", ""],
        )
        self.assertNotIn("Role:", r_f2.stdout)
        self.assertIn("- Depends on: D1", r_f2.stdout)

        self._run([str(SCRIPT), "next", "F2"], cwd=str(proj_a), check=True)
        r_f2_next = self._run([str(SCRIPT), "F2"], cwd=str(proj_a), check=True)
        self.assertEqual(r_f2_next.stdout.splitlines()[:4], ["Task: F2", "Prefix: F", "Status: NEXT", "Title: Audit task"])
        self.assertIn("- Depends on: D1", r_f2_next.stdout)

        # Commands reject removed --role / --by-role options
        for bad_cmd in (
            ["add", "F", "Role override", "--role", "work"],
            ["add", "F", "Role override", "--role=work"],
            ["edit", "F2", "--role", "plan"],
            ["list", "--role", "work"],
            ["chain", "--role", "work"],
            ["chain", "--by-role"],
            ["next-id", "--role", "work"],
        ):
            with self.subTest(bad_cmd=bad_cmd):
                r_bad = self._run([str(SCRIPT), *bad_cmd], cwd=str(proj_a))
                self.assertNotEqual(r_bad.returncode, 0, msg=r_bad.stdout)
                self.assertIn("unknown option", r_bad.stderr)

        # Fenced - Role: inside code block is ignored by check
        fenced_body = "`" * 3 + "markdown\n- Role: custom\n" + "`" * 3 + "\nDetails."
        self._run([str(SCRIPT), "add", "F", "Fenced role test", "-b", fenced_body], cwd=str(proj_a), check=True)
        r_f3 = self._run([str(SCRIPT), "F3"], cwd=str(proj_a), check=True)
        self.assertEqual(r_f3.stdout.splitlines()[:4], ["Task: F3", "Prefix: F", "Status: NEW", "Title: Fenced role test"])

        # last / show last emit headers too
        r_last = self._run([str(SCRIPT), "show", "last"], cwd=str(proj_a), check=True)
        self.assertEqual(
            r_last.stdout.splitlines()[:6],
            ["Task: F3", "Prefix: F", "Status: NEW", "Title: Fenced role test", f"Workdir: {resolved_proj_a}", ""],
        )

        # Overview and list commands remain unchanged (no Task:/Prefix:/Status:/Title:/Workdir: headers)
        for cmd in (
            [str(SCRIPT), "overview"],
            [str(SCRIPT), "--full"],
            [str(SCRIPT), "list"],
        ):
            r_ov = self._run(cmd, cwd=str(proj_a), check=True)
            self.assertNotIn("Workdir:", r_ov.stdout, msg=f"cmd={cmd}")
            self.assertNotIn("Task:", r_ov.stdout, msg=f"cmd={cmd}")
            self.assertNotIn("Title:", r_ov.stdout, msg=f"cmd={cmd}")
        r_ws = self._run([str(SCRIPT), "-w", "overview"], cwd=str(ws), check=True)
        self.assertNotIn("Workdir:", r_ws.stdout)
        self.assertNotIn("Task:", r_ws.stdout)
        self.assertNotIn("Title:", r_ws.stdout)

        # Backlog validation (`todo_md check`) rejects in-body Role: and Target files: lines
        # across both TODO.md and TODO_ARCHIVE.md (outside code fences)
        chk_dir = ws / "role_check_proj"
        chk_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(chk_dir), check=True)
        fence = "`" * 3
        (chk_dir / "TODO.md").write_text(
            "# ⚪ [NEW] F1: In-body role\n\n- Role: plan\n\n"
            "# ⚪ [NEW] F2: Target files line\n\n- Target files: `src/cli.py`\n\n"
            "# ⚪ [NEW] F3: Fenced lines are ignored\n\n"
            + fence + "markdown\n- Role: work\n- Target files: `src/cli.py`\n" + fence + "\n\n"
            "# ⚪ [NEW] F4: Empty role line\n\n- Role:\n",
            encoding="utf-8",
        )
        (chk_dir / "TODO_ARCHIVE.md").write_text(
            "# ✅ [DONE] U20: Archived task with legacy role — *2026-01-01*\n\n"
            "- Role: execute\n\n"
            "# ✅ [DONE] U21: Archived task with legacy target files — *2026-01-01*\n\n"
            "- Target files: `src/parser.py`\n",
            encoding="utf-8",
        )
        r_chk_fail = self._run([str(SCRIPT), "check"], cwd=str(chk_dir))
        self.assertNotEqual(r_chk_fail.returncode, 0, msg=r_chk_fail.stdout)
        for bad_tid in ("F1", "F4", "U20"):
            with self.subTest(bad_tid=bad_tid):
                self.assertIn(f"task {bad_tid} has an in-body 'Role:' line", r_chk_fail.stderr)
        for bad_tid in ("F2", "U21"):
            with self.subTest(bad_tid=bad_tid):
                self.assertIn(f"task {bad_tid} has an in-body 'Target files:' line", r_chk_fail.stderr)
        self.assertNotIn("task F3 ", r_chk_fail.stderr)

        (chk_dir / "TODO.md").write_text(
            "# 🎯 [NEXT] O4: Subsystem task\n\nBody without legacy lines.\n",
            encoding="utf-8",
        )
        (chk_dir / "TODO_ARCHIVE.md").write_text(
            "# ✅ [DONE] U20: Clean archived task — *2026-01-01*\n\nClean body.\n",
            encoding="utf-8",
        )
        r_chk_ok = self._run([str(SCRIPT), "check"], cwd=str(chk_dir), check=True)
        self.assertIn("OK", r_chk_ok.stdout)

    def test_ids_prefix_legend(self):
        proj = self.tmp / "legend"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        r_ids = self._run([str(SCRIPT), "ids"], cwd=str(proj), check=True)
        lines = r_ids.stdout.splitlines()
        self.assertTrue(lines[0].startswith("IDs in use:"), msg=r_ids.stdout)
        self.assertEqual(
            lines[1],
            "Prefixes: F=feature (default), B=bugfix, D=design, L=legislative rule, other A-Z=custom domain",
        )
        self.assertEqual(len(lines), 2, msg=r_ids.stdout)

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
        self.assertEqual(desc_starts, {26}, msg=f"misaligned loc column: {task_lines!r}")
        title_starts = set()
        for l in task_lines:
            marker = "TODO_ARCHIVE.md   " if "TODO_ARCHIVE.md" in l else "TODO.md           "
            idx = l.index(marker) + len(marker)
            title_starts.add(disp_w(l[:idx]))
        self.assertEqual(title_starts, {44}, msg=f"misaligned title column: {task_lines!r}")

        # 2. Wrapped columns in list (COLUMNS=78 -> avail_first = 78 - 44 = 34 >= 20)
        r_list_wrap = self._run(
            [str(SCRIPT), "list", "active"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "78"},
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
            self.assertEqual(leading_spaces, 44, msg=f"unexpected list continuation indent: {cl!r}")
        for l in list_body_lines:
            self.assertLessEqual(disp_w(l), 78, msg=f"line overflowed 78 cols: {l!r}")

        # 3. Wrapped columns in list -w (COLUMNS=80 -> avail_first = 80 - 48 = 32 >= 20)
        r_ws_list_wrap = self._run(
            [str(SCRIPT), "list", "-w", "active"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "80"},
            check=True,
        )
        ws_lines = [l for l in r_ws_list_wrap.stdout.splitlines() if l.startswith("  ")]
        ws_cont = [l for l in ws_lines if l.startswith("    ")]
        self.assertTrue(ws_cont)
        for cl in ws_cont:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 48, msg=f"unexpected list -w indent: {cl!r}")
        for l in ws_lines:
            self.assertLessEqual(disp_w(l), 80, msg=f"list -w overflowed 80 cols: {l!r}")

        # 4. Wrapped columns in chain and chain -w (COLUMNS=68 -> avail_first = 68 - 44 = 24 >= 20)
        for chain_args in (["chain"], ["chain", "-w"]):
            with self.subTest(args=chain_args):
                r_ch = self._run(
                    [str(SCRIPT), *chain_args],
                    cwd=str(proj_a),
                    env={**os.environ, "COLUMNS": "68"},
                    check=True,
                )
                row_lines = [
                    l for l in r_ch.stdout.splitlines()
                    if l.startswith("  ") and not l.lstrip().startswith("F4 (HOLD)") and not l.lstrip().startswith("proj_a:F4 (HOLD)")
                ]
                ch_cont = [l for l in row_lines if l.startswith("    ")]
                self.assertTrue(ch_cont, msg=r_ch.stdout)
                for cl in ch_cont:
                    self.assertEqual(len(cl) - len(cl.lstrip(" ")), 44, msg=f"unexpected chain indent: {cl!r}")
                for l in row_lines:
                    self.assertLessEqual(disp_w(l), 68, msg=f"chain row overflowed 68 cols: {l!r}")

        # 5. Wrapped columns in queue (alias for a focused chain, COLUMNS=66 -> avail_first = 66 - 44 = 22 >= 20)
        r_q = self._run(
            [str(SCRIPT), "queue", "F2", "--all"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "66"},
            check=True,
        )
        q_rows = [l for l in r_q.stdout.splitlines() if l.startswith("  ")]
        q_cont = [l for l in q_rows if l.startswith("    ")]
        self.assertTrue(q_cont, msg=r_q.stdout)
        for cl in q_cont:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 44, msg=f"unexpected queue indent: {cl!r}")
        for l in q_rows:
            self.assertLessEqual(disp_w(l), 66, msg=f"queue row overflowed 66 cols: {l!r}")

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
            env={**os.environ, "COLUMNS": "56"},
            check=True,
        )
        narrow_lines = [
            l for l in r_narrow_list.stdout.splitlines() if l.startswith("  ") and not l.strip().startswith("IDs")
        ]
        self.assertGreaterEqual(len(narrow_lines), 2)
        for cl in narrow_lines[1:]:
            self.assertEqual(len(cl) - len(cl.lstrip(" ")), 4, msg=f"expected 4-space fallback indent: {cl!r}")
        for l in narrow_lines:
            self.assertLessEqual(disp_w(l), 56, msg=f"narrow line overflowed 56 cols: {l!r}")

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
        self.assertEqual(vn_lines[0].strip(), "F1      🔵 [WIP]        TODO.md")
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
        for cmd in ([str(SCRIPT), "overview"], [str(SCRIPT), "show", "F1"], [str(SCRIPT), "last", "NEW"], [str(SCRIPT), "archive"]):
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

    def test_composable_task_styling_in_chain_and_list(self):
        mod = self.todo_md_mod
        # 1. Direct unit tests for _style_task_row() across all 8 combinations + plain text mode
        sample = "  1. F1                    ✅ [DONE]       Done task\n"
        self.assertEqual(
            mod._style_task_row(sample, is_external=True, is_done=True, is_highlighted=True, use_color=False),
            sample,
        )
        self.assertEqual(
            mod._style_task_row(sample, is_external=False, is_done=False, is_highlighted=False, use_color=True),
            sample,
        )
        self.assertTrue(
            mod._style_task_row(sample, is_external=True, is_done=False, is_highlighted=False, use_color=True).startswith("\033[2;3m")
        )
        self.assertTrue(
            mod._style_task_row(sample, is_external=False, is_done=True, is_highlighted=False, use_color=True).startswith("\033[2;90m")
        )
        self.assertTrue(
            mod._style_task_row(sample, is_external=True, is_done=True, is_highlighted=False, use_color=True).startswith("\033[2;3;90m")
        )
        for is_done_flag in (False, True):
            hl_local = mod._style_task_row(
                sample, is_external=False, is_done=is_done_flag, is_highlighted=True, use_color=True
            )
            self.assertTrue(hl_local.startswith("\033[1;93m"), msg=hl_local)
            self.assertIn("✅ [DONE]", hl_local)
            hl_ext = mod._style_task_row(
                sample, is_external=True, is_done=is_done_flag, is_highlighted=True, use_color=True
            )
            self.assertTrue(hl_ext.startswith("\033[1;3;93m"), msg=hl_ext)
            self.assertIn("✅ [DONE]", hl_ext)

        # 2. Multi-project workspace setup to test chain & list multi-ID highlighting, external, and DONE styling
        ws = self.tmp / "ws_style"
        todo_flow = ws / "todo_flow"
        run_block = ws / "run_block"
        for d in (todo_flow, run_block):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)
        (todo_flow / ".todo_projects").write_text("run_block\n", encoding="utf-8")

        # run_block: D1 (DONE), F1 (finale after D1), F2 (in cross-project chain), F3 (standalone),
        # D2 (HOLD) -> F4 (held leaf), F5 (canceled)
        self._run([str(SCRIPT), "add", "D", "RB done design"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "F", "RB finale task", "--next", "--depends", "D1"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "F", "RB chain task", "--next"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "F", "RB standalone task", "--next"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "D", "RB held root", "--status", "HOLD"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "F", "RB held leaf", "--next", "--depends", "D2"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "F", "RB canceled task", "--next"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "cancel", "F5", "-m", "drop"], cwd=str(run_block), check=True)

        # todo_flow orchestrator sequences todo_flow:D1 -> run_block:F2 -> todo_flow:F1,
        # and also has held dependency todo_flow:D2 (HOLD) -> run_block:F4
        self._run([str(SCRIPT), "add", "D", "Flow prereq", "--next"], cwd=str(todo_flow), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Flow goal", "--depends", "D1 -> run_block:F2"],
            cwd=str(todo_flow),
            check=True,
        )
        self._run([str(SCRIPT), "add", "D", "Flow held root", "--status", "HOLD"], cwd=str(todo_flow), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Flow held wrapper", "--depends", "D2 -> run_block:F4"],
            cwd=str(todo_flow),
            check=True,
        )

        base_env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TODO_MD_PROJECTS")}
        color_env = {**base_env, "FORCE_COLOR": "1", "COLUMNS": "80"}

        # 3. `todo_md chain [<ID>...]` with space- and comma-separated refs in child project view:
        # Highlight local finale F1, external prereq todo_flow:D1, local chain task F2, standalone F3,
        # local held D2, and external held todo_flow:D2
        r_chain_hl = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "run_block:F1,todo_flow:D1", "F3", "D2,todo_flow:D2"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        out_hl = r_chain_hl.stdout
        lines_hl = out_hl.splitlines()
        # Enclosing Chain 1 (finale F1) and Chain 2 (containing todo_flow:D1) headers are highlighted
        self.assertTrue(
            any(
                ln.startswith("\033[1;93m[50% | 1/2] Chain 1 -> F1: RB finale task:")
                and ln.endswith("\033[0m")
                for ln in lines_hl
            ),
            msg=out_hl,
        )
        self.assertTrue(
            any(
                ln.startswith("\033[1;93m[0% | 0/3] Chain 2 -> todo_flow:F1: Flow goal:")
                and ln.endswith("\033[0m")
                for ln in lines_hl
            ),
            msg=out_hl,
        )
        # Local finale F1 and standalone F3 are bold bright yellow (\033[1;93m)
        self.assertTrue(any(ln.startswith("\033[1;93m") and "1 F1 " in ln for ln in lines_hl), msg=out_hl)
        self.assertTrue(any(ln.startswith("\033[1;93m") and "5 F3 " in ln for ln in lines_hl), msg=out_hl)
        # External highlighted todo_flow:D1 is bold italic bright yellow (\033[1;3;93m)
        self.assertTrue(any(ln.startswith("\033[1;3;93m") and "2 todo_flow:D1 " in ln for ln in lines_hl), msg=out_hl)
        # Non-highlighted local F2 is unstyled normal text
        self.assertTrue(
            any(ln.startswith("  ") and not ln.startswith("\033[") and "3 F2 " in ln for ln in lines_hl),
            msg=out_hl,
        )
        # Non-highlighted external todo_flow:F1 is dim italic (\033[2;3m)
        self.assertTrue(any(ln.startswith("\033[2;3m") and "4 todo_flow:F1 " in ln for ln in lines_hl), msg=out_hl)
        # Held branches tokens: D2 (local highlighted -> \033[1;93m), todo_flow:D2 (external highlighted -> \033[1;3;93m),
        # F4 (local unhighlighted -> plain), todo_flow:F2 (external unhighlighted -> \033[2;3m)
        self.assertIn("\033[1;93mD2 (HOLD)\033[0m -> F4 (NEXT)", out_hl)
        self.assertIn("\033[1;3;93mtodo_flow:D2 (HOLD)\033[0m -> F4 (NEXT) -> \033[2;3mtodo_flow:F2 (NEW)\033[0m", out_hl)

        # Strip ANSI equals plain output at identical terminal width
        r_chain_plain = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "run_block:F1,todo_flow:D1", "F3", "D2,todo_flow:D2"],
            cwd=str(run_block),
            env={**base_env, "COLUMNS": "80"},
            check=True,
        )
        self.assertNotIn("\033[", r_chain_plain.stdout)
        self.assertEqual(mod._strip_ansi(out_hl), r_chain_plain.stdout)

        # A positional <ID> focuses the view: only the highlighted standalone F3 row and Next actionable remain
        r_chain_only_f3 = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "F3"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        out_f3 = r_chain_only_f3.stdout
        self.assertNotIn("Chain 1 -> todo_flow:F1", out_f3)
        self.assertTrue(any(ln.startswith("\033[1;93m") and "1 F3 " in ln for ln in out_f3.splitlines()), msg=out_f3)
        self.assertIn("Next actionable: F3", mod._strip_ansi(out_f3))

        # --highlight renders the full Quest-Log; Chain header is NOT highlighted when target is only standalone
        r_hl_only_f3 = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--highlight", "F3"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        self.assertTrue(
            any(ln.startswith("[50% | 1/2] Chain 1 -> F1: RB finale task:") for ln in r_hl_only_f3.stdout.splitlines()),
            msg=r_hl_only_f3.stdout,
        )
        self.assertTrue(
            any(ln.startswith("[0% | 0/3] Chain 2 -> todo_flow:F1: Flow goal:") for ln in r_hl_only_f3.stdout.splitlines()),
            msg=r_hl_only_f3.stdout,
        )
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and "5 F3 " in ln for ln in r_hl_only_f3.stdout.splitlines()),
            msg=r_hl_only_f3.stdout,
        )
        self.assertNotIn("Next actionable:", r_hl_only_f3.stdout)

        # Also works with --ready
        r_ready_hl = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready", "F1"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and "1 F1 " in ln for ln in r_ready_hl.stdout.splitlines()),
            msg=r_ready_hl.stdout,
        )

        # 4. `todo_md list [<filter>] [<ID>...]` and `todo_md list -w [<filter>] [<ID>...]`
        # Test default filter with <ID>... directly (`todo_md list F1,F3`)
        r_list_def = self._run(
            [str(SCRIPT), "list", "F1,F3"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        list_def_lines = r_list_def.stdout.splitlines()
        self.assertTrue(any(ln.startswith("\033[1;93m") and "  F1 " in ln for ln in list_def_lines), msg=r_list_def.stdout)
        self.assertTrue(any(ln.startswith("\033[1;93m") and "  F3 " in ln for ln in list_def_lines), msg=r_list_def.stdout)
        self.assertTrue(
            any(ln.startswith("  ") and not ln.startswith("\033[") and "  F2 " in ln for ln in list_def_lines),
            msg=r_list_def.stdout,
        )

        # Test `todo_md list all F2` — D1 (DONE) is dimmed (\033[2;90m), F2 is highlighted (\033[1;93m),
        # F5 (CANCELED) is neither dimmed nor highlighted
        r_list_all = self._run(
            [str(SCRIPT), "list", "all", "F2"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        all_lines = r_list_all.stdout.splitlines()
        self.assertTrue(any(ln.startswith("\033[2;90m") and "  D1 " in ln and "✅ [DONE]" in ln for ln in all_lines), msg=r_list_all.stdout)
        self.assertTrue(any(ln.startswith("\033[1;93m") and "  F2 " in ln for ln in all_lines), msg=r_list_all.stdout)
        self.assertTrue(
            any(ln.startswith("  ") and not ln.startswith("\033[") and "  F5 " in ln and "❌ [CANCELED]" in ln for ln in all_lines),
            msg=r_list_all.stdout,
        )

        # Test `todo_md list archive D1` — highlighting a DONE task uses bold bright yellow (\033[1;93m)
        # while preserving the ✅ [DONE] badge
        r_list_arch_hl = self._run(
            [str(SCRIPT), "list", "archive", "D1"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        arch_lines = r_list_arch_hl.stdout.splitlines()
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and "  D1 " in ln and "✅ [DONE]" in ln for ln in arch_lines),
            msg=r_list_arch_hl.stdout,
        )

        # Test workspace list `todo_md list -w all run_block:D1,todo_flow:D1`
        r_ws_list = self._run(
            [str(SCRIPT), "list", "-w", "all", "run_block:D1,todo_flow:D1"],
            cwd=str(ws),
            env=color_env,
            check=True,
        )
        ws_lines = r_ws_list.stdout.splitlines()
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and "run_block:D1 " in ln and "✅ [DONE]" in ln for ln in ws_lines),
            msg=r_ws_list.stdout,
        )
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and "todo_flow:D1 " in ln for ln in ws_lines),
            msg=r_ws_list.stdout,
        )
        self.assertTrue(
            any(ln.startswith("  ") and not ln.startswith("\033[") and "run_block:F2 " in ln for ln in ws_lines),
            msg=r_ws_list.stdout,
        )

        # Invalid extra non-ID positional arguments in list fail explicitly
        r_bad_list = self._run([str(SCRIPT), "list", "active", "not_an_id"], cwd=str(run_block))
        self.assertNotEqual(r_bad_list.returncode, 0, msg=r_bad_list.stderr)


if __name__ == "__main__":
    unittest.main()
